import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from supabase import Client

from authorization import (
    CREATE_PERMISSION,
    MANAGE_VIEW_PERMISSION,
    RETIRE_PERMISSION,
    SELECTION_PERMISSION,
    UPDATE_PERMISSION,
    require_permission,
)
from database import get_db
from schemas import (
    EquipmentCreate,
    EquipmentRead,
    EquipmentRequirementDetail,
    EquipmentRequirementRead,
    EquipmentRequirementWrite,
    EquipmentRequirementRemove,
    EquipmentUpdate,
)
from security import clear_session_cookies

app = FastAPI(title="Equipment Service")
logger = logging.getLogger(__name__)

SCHEMA = "equipment"
TABLE = "equipment"
REQUIREMENTS_TABLE = "requirements"

REQUIREMENT_SELECT = (
    "id,event_id,equipment_item_id,required_quantity,"
    "recorded_by_coordinator_id,created_at,updated_at,"
    "equipment("
    "id,type,description,total_quantity,operational_status,lifecycle_status)"
)


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


@app.get("/equipment/{equipment_item_id}", response_model=EquipmentRead)
def get_equipment(
    equipment_item_id: UUID,
    user=Depends(require_permission(MANAGE_VIEW_PERMISSION)),
    db: Client = Depends(get_db),
):
    result = _execute(
        db.schema(SCHEMA)
        .table(TABLE)
        .select("*")
        .eq("id", str(equipment_item_id))
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Equipment item not found")
    return result.data[0]


@app.put("/equipment/{equipment_item_id}", response_model=EquipmentRead)
def update_equipment(
    equipment_item_id: UUID,
    payload: EquipmentUpdate,
    user=Depends(require_permission(UPDATE_PERMISSION)),
    db: Client = Depends(get_db),
):
    values = {
        **payload.model_dump(mode="json"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    result = _execute(
        db.schema(SCHEMA)
        .table(TABLE)
        .update(values)
        .eq("id", str(equipment_item_id))
        .select("*")
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Equipment item not found")
    return result.data[0]


@app.post("/equipment/{equipment_item_id}/retire", response_model=EquipmentRead)
def retire_equipment(
    equipment_item_id: UUID,
    user=Depends(require_permission(RETIRE_PERMISSION)),
    db: Client = Depends(get_db),
):
    current = _execute(
        db.schema(SCHEMA)
        .table(TABLE)
        .select("*")
        .eq("id", str(equipment_item_id))
    )
    if not current.data:
        raise HTTPException(status_code=404, detail="Equipment item not found")

    item = current.data[0]
    if item["lifecycle_status"] == "retired":
        return item

    result = _execute(
        db.schema(SCHEMA)
        .table(TABLE)
        .update(
            {
                "lifecycle_status": "retired",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("id", str(equipment_item_id))
        .select("*")
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Equipment item not found")
    return result.data[0]


# Internal-only routes. They deliberately sit outside /equipment, so Kong's
# browser-facing equipment route cannot reach them. The composite service
# verifies the current role, assignment, and event status before calling here.
@app.put(
    "/internal/equipment-requirements/{event_id}/{equipment_item_id}",
    response_model=EquipmentRequirementRead,
)
def upsert_equipment_requirement(
    event_id: UUID,
    equipment_item_id: UUID,
    payload: EquipmentRequirementWrite,
    db: Client = Depends(get_db),
):
    usable = _execute(
        db.schema(SCHEMA)
        .table(TABLE)
        .select("id")
        .eq("id", str(equipment_item_id))
        .eq("operational_status", "available")
        .eq("lifecycle_status", "active")
    )
    if not usable.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Equipment item is not available for new requirements",
        )

    values = {
        "event_id": str(event_id),
        "equipment_item_id": str(equipment_item_id),
        **payload.model_dump(mode="json"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    result = _execute(
        db.schema(SCHEMA)
        .table(REQUIREMENTS_TABLE)
        .upsert(values, on_conflict="event_id,equipment_item_id")
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save equipment requirement",
        )
    return result.data[0]


@app.put(
    "/internal/equipment-requirements/{event_id}/{equipment_item_id}/audited",
    response_model=EquipmentRequirementRead,
)
def upsert_equipment_requirement_audited(
    event_id: UUID,
    equipment_item_id: UUID,
    payload: EquipmentRequirementWrite,
    db: Client = Depends(get_db),
):
    """S-18 atomic requirement change plus its immutable audit entry."""
    usable = _execute(
        db.schema(SCHEMA).table(TABLE).select("id")
        .eq("id", str(equipment_item_id))
        .eq("operational_status", "available")
        .eq("lifecycle_status", "active")
    )
    if not usable.data:
        raise HTTPException(status_code=409, detail="Equipment item is not available for new requirements")
    result = _execute(
        db.schema(SCHEMA).rpc("save_requirement_with_history", {
            "p_event_id": str(event_id),
            "p_equipment_item_id": str(equipment_item_id),
            "p_required_quantity": payload.required_quantity,
            "p_changed_by": str(payload.recorded_by_coordinator_id),
        })
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Could not save equipment requirement")
    return result.data[0]


@app.post(
    "/internal/equipment-requirements/{event_id}/{equipment_item_id}/remove-audited",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_equipment_requirement_audited(
    event_id: UUID,
    equipment_item_id: UUID,
    payload: EquipmentRequirementRemove,
    db: Client = Depends(get_db),
):
    result = _execute(
        db.schema(SCHEMA).rpc("delete_requirement_with_history", {
            "p_event_id": str(event_id),
            "p_equipment_item_id": str(equipment_item_id),
            "p_changed_by": str(payload.recorded_by_coordinator_id),
        })
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Equipment requirement not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/internal/equipment-requirements",
    response_model=list[EquipmentRequirementDetail],
)
def list_equipment_requirements(
    event_id: UUID | None = Query(default=None),
    # S-44: the requirements of several events at once -- the events
    # overlapping an availability check's window.
    event_ids: list[UUID] | None = Query(default=None),
    db: Client = Depends(get_db),
):
    operation = (
        db.schema(SCHEMA)
        .table(REQUIREMENTS_TABLE)
        .select(REQUIREMENT_SELECT)
    )
    if event_id is not None:
        operation = operation.eq("event_id", str(event_id))
    if event_ids is not None:
        operation = operation.in_("event_id", [str(value) for value in event_ids])
    return _execute(operation.order("created_at")).data


@app.delete(
    "/internal/equipment-requirements/{event_id}/{equipment_item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_equipment_requirement(
    event_id: UUID,
    equipment_item_id: UUID,
    db: Client = Depends(get_db),
):
    result = _execute(
        db.schema(SCHEMA)
        .table(REQUIREMENTS_TABLE)
        .delete()
        .eq("event_id", str(event_id))
        .eq("equipment_item_id", str(equipment_item_id))
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Equipment requirement not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
