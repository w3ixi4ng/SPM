import httpx

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from supabase import Client

from database import get_auth, get_db
from schemas import CoordinatorRead, CurrentUserRead, LoginRequest, ProfileLookupRequest, SignUpRequest, UserRead
from security import (
    ACCESS_COOKIE,
    clear_session_cookies,
    get_current_user,
    set_session_cookies,
)

try:  # supabase-py re-exports the auth errors
    from supabase import AuthApiError
except ImportError:  # pragma: no cover - older releases keep them here
    try:
        from supabase_auth.errors import AuthApiError
    except ImportError:
        from gotrue.errors import AuthApiError

app = FastAPI(title="Users Service")

SCHEMA = "users"
TABLE = "users"
COORDINATOR_ROLE = "event_coordinator"
TECHNICAL_SUPPORT_ROLE = "technical_support"


@app.exception_handler(StarletteHTTPException)
async def clear_dead_session(request: Request, exc: StarletteHTTPException):
    """Expire the session cookies on the way out of a failed authentication.

    Raising discards the Response a route was handed, so a dependency cannot
    delete a cookie by itself -- it leaves a flag on the request instead, and
    this is where that turns into Set-Cookie headers. Without it a browser
    holding an expired pair would send it on every request for another month.
    """
    response = await http_exception_handler(request, exc)
    if getattr(request.state, "clear_session", False):
        clear_session_cookies(response)
    return response


@app.exception_handler(RequestValidationError)
async def readable_validation_error(request: Request, exc: RequestValidationError):
    """Answer a 422 in the same shape as every other error.

    FastAPI's own is a list of objects under `detail`, so a frontend has to
    branch on whether `detail` is a string or an array -- on the one status a
    sign-up form hits most. This keeps `detail` a sentence and puts the
    per-field messages where a form can read them straight off.
    """
    errors: dict[str, str] = {}
    for error in exc.errors():
        path = [str(part) for part in error["loc"] if part != "body"]
        errors.setdefault(".".join(path) or "body", error["msg"])

    return JSONResponse(
        status_code=422,
        content={"detail": "Please check the details you entered", "errors": errors},
    )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    """Keep a crash JSON, so the frontend can read it like any other error.

    Without this an unhandled exception comes back as text/plain, and the
    caller's `response.json()` throws on exactly the responses worth logging.
    Starlette re-raises afterwards, so the traceback still reaches the logs.
    """
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def _auth_error(exc: AuthApiError) -> HTTPException:
    """Turn a Supabase Auth failure into the right answer for the caller."""
    message = getattr(exc, "message", None) or str(exc)
    upstream = getattr(exc, "status", None) or 502

    if "already registered" in message.lower():
        return HTTPException(status_code=409, detail="Email already registered")
    if upstream == 429:
        return HTTPException(status_code=429, detail="Too many attempts, try again later")
    if upstream in (400, 422):
        # Supabase enforces its own password policy on top of ours, and this
        # is where the caller finds out which rule they broke.
        return HTTPException(status_code=400, detail=message)
    return HTTPException(status_code=502, detail="Authentication service unavailable")


def _discard_auth_user(db: Client, user_id: str) -> None:
    """Best effort undo of a sign-up whose profile could not be written.

    Leaving the account behind would block the address for good: the retry
    would come back from Supabase as already registered, and no profile would
    ever exist for it. The caller is already reporting a failure, so a failure
    here changes nothing it can act on.
    """
    try:
        db.auth.admin.delete_user(user_id)
    except Exception:
        pass


def _list_auth_users_with_role(db: Client, role: str) -> list:
    """Every Auth user with the trusted role, including users without profiles."""
    page_size = 200
    users = []
    page = 1
    while True:
        batch = db.auth.admin.list_users(page=page, per_page=page_size)
        if not batch:
            break
        users.extend(
            user
            for user in batch
            if (getattr(user, "app_metadata", None) or {}).get("role") == role
        )
        if len(batch) < page_size:
            break
        page += 1
    return users


def _list_user_ids_with_role(db: Client, role: str) -> list[str]:
    """IDs for the existing role-specific routes that require profiles."""
    return [user.id for user in _list_auth_users_with_role(db, role)]


def _coordinator_active(user) -> bool | None:
    """Read only the admin-controlled Auth claim; invalid values fail closed."""
    metadata = getattr(user, "app_metadata", None) or {}
    value = metadata.get("coordinator_active", True)
    return value if type(value) is bool else None


def _read_profile(db: Client, user_id: str):
    """Retry a dropped Supabase connection only for this idempotent read."""
    for attempt in range(2):
        try:
            return db.schema(SCHEMA).table(TABLE).select("*").eq("id", user_id).execute()
        except httpx.RemoteProtocolError as exc:
            if attempt:
                raise HTTPException(status_code=502, detail="User profile service unavailable") from exc


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/users/signup", response_model=UserRead, status_code=201)
def signup(
    payload: SignUpRequest,
    response: Response,
    db: Client = Depends(get_db),
    auth: Client = Depends(get_auth),
):
    email = payload.email.lower()

    existing = db.schema(SCHEMA).table(TABLE).select("id").eq("email", email).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail="Email already registered")

    try:
        created = auth.auth.sign_up({"email": email, "password": payload.password})
    except AuthApiError as exc:
        raise _auth_error(exc)

    if created.user is None:
        raise HTTPException(status_code=502, detail="Authentication service unavailable")

    try:
        db.auth.admin.update_user_by_id(
            created.user.id,
            {"app_metadata": {"role": payload.role}},
        )
    except Exception:
        _discard_auth_user(db, created.user.id)
        raise HTTPException(status_code=500, detail="Could not configure user account")

    try:
        inserted = (
            db.schema(SCHEMA)
            .table(TABLE)
            .insert({"id": created.user.id, "name": payload.name, "email": email})
            .execute()
        )
    except Exception:
        _discard_auth_user(db, created.user.id)
        raise HTTPException(status_code=500, detail="Could not create user profile")

    if not inserted.data:
        _discard_auth_user(db, created.user.id)
        raise HTTPException(status_code=500, detail="Could not create user profile")

    # With email confirmation switched on in Supabase, sign-up returns no
    # session: the account exists but is not signed in until the link is
    # clicked. With it off, the session is here and the user is logged in.
    if created.session is not None:
        set_session_cookies(response, created.session)

    return inserted.data[0]


@app.post("/users/login", response_model=UserRead)
def login(
    payload: LoginRequest,
    response: Response,
    db: Client = Depends(get_db),
    auth: Client = Depends(get_auth),
):
    try:
        signed_in = auth.auth.sign_in_with_password(
            {"email": payload.email.lower(), "password": payload.password}
        )
    except AuthApiError as exc:
        if getattr(exc, "status", None) == 429:
            raise _auth_error(exc)
        # Never say which half was wrong. A login form that distinguishes
        # "no such account" from "wrong password" is a way to find out which
        # addresses have accounts.
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if signed_in.session is None or signed_in.user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    res = (
        db.schema(SCHEMA)
        .table(TABLE)
        .select("*")
        .eq("id", signed_in.user.id)
        .execute()
    )
    if not res.data:
        # Credentials are good but the profile row is gone, so there is no
        # user to hand back. No cookies are set: raising here throws away the
        # response this handler was given.
        raise HTTPException(status_code=404, detail="User profile not found")

    set_session_cookies(response, signed_in.session)
    return res.data[0]


@app.post("/users/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def logout(
    request: Request,
    response: Response,
    db: Client = Depends(get_db),
) -> None:
    access_token = request.cookies.get(ACCESS_COOKIE)
    clear_session_cookies(response)

    if access_token:
        # Clearing the cookies logs this browser out; this is what stops the
        # refresh token working anywhere else. Best effort -- the caller is
        # logged out either way, so a failure here is not worth a 500.
        try:
            db.auth.admin.sign_out(access_token)
        except Exception:
            pass

    return None


# Keep this above any "/users/{user_id}" added later: FastAPI matches in
# declaration order, and a dynamic route declared first would swallow "me".
@app.get("/users/me", response_model=CurrentUserRead)
def me(user=Depends(get_current_user), db: Client = Depends(get_db)):
    res = _read_profile(db, user.id)
    if not res.data:
        raise HTTPException(status_code=404, detail="User profile not found")
    app_metadata = getattr(user, "app_metadata", None) or {}
    return {**res.data[0], "role": app_metadata.get("role")}


# --- Internal, composite-only route -----------------------------------------
#
# No Kong route exists for this -- see the events service README's "Internal
# routes" section. Only the event_requests composite calls it, to find who it
# can assign an event request to.
@app.get("/internal/users/coordinators", response_model=list[CoordinatorRead])
def list_coordinators(db: Client = Depends(get_db)):
    coordinators = _list_auth_users_with_role(db, COORDINATOR_ROLE)
    if not coordinators:
        return []

    ids = [user.id for user in coordinators]
    res = db.schema(SCHEMA).table(TABLE).select("id,name,email").in_("id", ids).execute()
    profiles = {row["id"]: row for row in res.data}
    return [
        {
            "id": user.id,
            "name": profiles.get(user.id, {}).get("name")
            or getattr(user, "email", None)
            or getattr(user, "phone", None)
            or user.id,
            "email": profiles.get(user.id, {}).get("email")
            or getattr(user, "email", None),
            "coordinator_active": _coordinator_active(user),
        }
        for user in coordinators
    ]


@app.post("/internal/users/profiles", response_model=list[UserRead])
def lookup_profiles(payload: ProfileLookupRequest, db: Client = Depends(get_db)):
    """Internal batch lookup for composites that must present user names.

    The response deliberately contains profiles only, never trusted roles or
    Auth secrets. Eligibility continues to come from the role-specific pool
    endpoints above.
    """
    if not payload.ids:
        return []
    ids = [str(user_id) for user_id in payload.ids]
    res = db.schema(SCHEMA).table(TABLE).select("id,name,email").in_("id", ids).execute()
    return res.data


@app.get("/users/technical-support", response_model=list[UserRead])
def list_technical_support(db: Client = Depends(get_db)):
    staff_ids = _list_user_ids_with_role(db, TECHNICAL_SUPPORT_ROLE)
    if not staff_ids:
        return []

    res = db.schema(SCHEMA).table(TABLE).select("*").in_("id", staff_ids).execute()
    return res.data
