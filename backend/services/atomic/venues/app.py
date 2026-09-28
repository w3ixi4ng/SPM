import logging
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError
from starlette.exceptions import HTTPException as StarletteHTTPException
from supabase import Client

from authorization import CREATE_PERMISSION, VIEW_PERMISSION, UPDATE_PERMISSION, require_permission
from database import get_db
from schemas import (
    ACCESSIBILITY_FEATURES,
    DAYS,
    FACILITIES,
    ROOM_LAYOUTS,
    VenueCreate,
    VenueOptions,
    VenueRead,
    VenueUpdate,
)
from security import clear_session_cookies

app = FastAPI(title="Venues Service")
logger = logging.getLogger(__name__)

SCHEMA = "venues"
TABLE = "venues"

# Postgres unique_violation. The only unique constraint a client can trip is
# the case-insensitive index on name -- the id is generated.
UNIQUE_VIOLATION = "23505"


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
    logger.exception("Unhandled venues service error", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


def _execute(operation):
    try:
        return operation.execute()
    except APIError as exc:
        if exc.code == UNIQUE_VIOLATION:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A venue with this name already exists",
            ) from exc
        logger.exception("Venue storage operation failed", exc_info=exc)
        raise _storage_unavailable() from exc
    except Exception as exc:
        logger.exception("Venue storage operation failed", exc_info=exc)
        raise _storage_unavailable() from exc


def _storage_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Venue storage unavailable",
    )


@app.get("/health")
@app.get("/venues/health", include_in_schema=False)
def health():
    return {"status": "ok"}


@app.post("/venues", response_model=VenueRead, status_code=status.HTTP_201_CREATED)
def create_venue(
    payload: VenueCreate,
    user=Depends(require_permission(CREATE_PERMISSION)),
    db: Client = Depends(get_db),
):
    values = payload.model_dump(mode="json")
    values["created_by"] = str(user.id)
    result = _execute(db.schema(SCHEMA).table(TABLE).insert(values))
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create venue",
        )
    return result.data[0]


@app.get("/venues", response_model=list[VenueRead])
def list_venues(
    user=Depends(require_permission(VIEW_PERMISSION)),
    db: Client = Depends(get_db),
):
    operation = db.schema(SCHEMA).table(TABLE).select("*").order("name")
    return _execute(operation).data


@app.patch("/venues/{venue_id}", response_model=VenueRead)
def update_venue(
    venue_id: UUID,
    payload: VenueUpdate,
    user=Depends(require_permission(UPDATE_PERMISSION)),
    db: Client = Depends(get_db),
):
    values = payload.model_dump(mode="json", exclude_unset=True)
    operation = db.schema(SCHEMA).table(TABLE).update(values).eq("id", str(venue_id))
    result = _execute(operation)
    if not result.data:
        raise HTTPException(status_code=404, detail="Venue not found")
    return result.data[0]


# Declared before /venues/{venue_id}, which would otherwise try to read
# "options" as a UUID.
@app.get("/venues/options", response_model=VenueOptions)
def venue_options(user=Depends(require_permission(VIEW_PERMISSION))):
    return VenueOptions(
        facilities=list(FACILITIES),
        accessibility=list(ACCESSIBILITY_FEATURES),
        room_layouts=list(ROOM_LAYOUTS),
        days=list(DAYS),
    )


@app.get("/venues/{venue_id}", response_model=VenueRead)
def get_venue(
    venue_id: UUID,
    user=Depends(require_permission(VIEW_PERMISSION)),
    db: Client = Depends(get_db),
):
    operation = db.schema(SCHEMA).table(TABLE).select("*").eq("id", str(venue_id))
    result = _execute(operation)
    if not result.data:
        raise HTTPException(status_code=404, detail="Venue not found")
    return result.data[0]
