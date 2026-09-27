import logging

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from supabase import Client

from authorization import (
    CREATE_PERMISSION,
    MANAGE_VIEW_PERMISSION,
    SELECTION_PERMISSION,
    require_permission,
)
from database import get_db
from schemas import EquipmentCreate, EquipmentRead
from security import clear_session_cookies

app = FastAPI(title="Equipment Service")
logger = logging.getLogger(__name__)

SCHEMA = "equipment"
TABLE = "equipment"


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
    logger.exception("Unhandled equipment service error", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


def _execute(operation):
    try:
        return operation.execute()
    except Exception as exc:
        logger.exception("Equipment storage operation failed", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Equipment storage unavailable",
        ) from exc


@app.get("/health")
@app.get("/equipment/health", include_in_schema=False)
def health():
    return {"status": "ok"}


@app.post("/equipment", response_model=EquipmentRead, status_code=status.HTTP_201_CREATED)
def create_equipment(
    payload: EquipmentCreate,
    user=Depends(require_permission(CREATE_PERMISSION)),
    db: Client = Depends(get_db),
):
    values = {
        **payload.model_dump(mode="json"),
        "operational_status": "available",
        "lifecycle_status": "active",
        "created_by": str(user.id),
    }
    result = _execute(db.schema(SCHEMA).table(TABLE).insert(values))
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create equipment item",
        )
    return result.data[0]


@app.get("/equipment", response_model=list[EquipmentRead])
def list_equipment(
    user=Depends(require_permission(MANAGE_VIEW_PERMISSION)),
    db: Client = Depends(get_db),
):
    operation = db.schema(SCHEMA).table(TABLE).select("*").order("type")
    return _execute(operation).data


@app.get("/equipment/selection", response_model=list[EquipmentRead])
def list_equipment_selection(
    user=Depends(require_permission(SELECTION_PERMISSION)),
    db: Client = Depends(get_db),
):
    operation = (
        db.schema(SCHEMA)
        .table(TABLE)
        .select("*")
        .eq("operational_status", "available")
        .eq("lifecycle_status", "active")
        .order("type")
    )
    return _execute(operation).data
