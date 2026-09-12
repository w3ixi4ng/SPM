from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from supabase import Client

from database import get_auth, get_db
from schemas import LoginRequest, SignUpRequest, UserRead
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
@app.get("/users/me", response_model=UserRead)
def me(user=Depends(get_current_user), db: Client = Depends(get_db)):
    res = db.schema(SCHEMA).table(TABLE).select("*").eq("id", user.id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="User profile not found")
    return res.data[0]
