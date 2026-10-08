import logging

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from supabase import Client

from database import get_db
from schemas import NotificationBatchCreate, NotificationRead
from security import clear_session_cookies, get_current_user

app = FastAPI(title="Notifications Service")
logger = logging.getLogger(__name__)

SCHEMA = "notifications"
TABLE = "notifications"


@app.exception_handler(StarletteHTTPException)
async def clear_dead_session(request: Request, exc: StarletteHTTPException):
    response = await http_exception_handler(request, exc)
    if getattr(request.state, "clear_session", False):
        clear_session_cookies(response)
    return response


@app.exception_handler(RequestValidationError)
async def readable_validation_error(request: Request, exc: RequestValidationError):
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
    logger.exception("Unhandled notifications service error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def _execute(operation):
    try:
        return operation.execute()
    except Exception as exc:
        logger.exception("Notification storage operation failed", exc_info=exc)
        raise HTTPException(status_code=500, detail="Notification storage unavailable") from exc


@app.get("/health")
@app.get("/notifications/health", include_in_schema=False)
def health():
    return {"status": "ok"}


@app.get("/notifications", response_model=list[NotificationRead])
def list_notifications(
    user=Depends(get_current_user),
    db: Client = Depends(get_db),
):
    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .select("*")
        .eq("recipient_id", str(user.id))
        .order("created_at", desc=True)
    )
    return _execute(operation).data


# Internal-only: Kong exposes /notifications but this route sits outside that
# prefix. The event_requests composite is the sole caller.
@app.post(
    "/internal/notifications",
    response_model=list[NotificationRead],
    status_code=status.HTTP_201_CREATED,
)
def create_notifications(
    payload: NotificationBatchCreate,
    db: Client = Depends(get_db),
):
    rows = [item.model_dump(mode="json") for item in payload.notifications]
    result = _execute(
        db.schema(SCHEMA)
        .table(TABLE)
        .upsert(rows, on_conflict="deduplication_key")
    )
    if len(result.data or []) != len(rows):
        raise HTTPException(status_code=500, detail="Could not persist notifications")
    return result.data
