import logging
import os
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
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
    EquipmentChangeBatch,
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
    "id,type,description,storage_location,total_quantity,"
    "operational_status,lifecycle_status)"
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
        if getattr(exc, "code", None) == "23514" and "Requirement change is in progress" in str(exc):
            raise HTTPException(status_code=409, detail="Requirement change is in progress") from exc
        logger.exception("Equipment storage operation failed", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Equipment storage unavailable",
        ) from exc


def require_change_service(x_assignment_service_token: str | None = Header(default=None)):
    expected = os.environ.get("ASSIGNMENT_SERVICE_SECRET")
    if not expected:
        raise HTTPException(status_code=503, detail="Change service is not configured")
    if not x_assignment_service_token or not secrets.compare_digest(x_assignment_service_token, expected):
        raise HTTPException(status_code=403, detail="Trusted change service required")


def _batch_rpc(db: Client, name: str, params: dict):
    try:
        result = db.schema(SCHEMA).rpc(name, params).execute()
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code == "P0002":
            raise HTTPException(status_code=404, detail="Change operation not found") from exc
        if code in {"23514", "23505"}:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        logger.exception("Equipment change operation failed", exc_info=exc)
        raise HTTPException(status_code=500, detail="Equipment storage unavailable") from exc
    if not result.data:
        raise HTTPException(status_code=500, detail="Equipment storage unavailable")
    return result.data[0]


@app.post("/internal/equipment-requirements/change-batches")
def apply_change_batch(
    payload: EquipmentChangeBatch,
    _service=Depends(require_change_service),
    db: Client = Depends(get_db),
):
    for values in (payload.baseline, payload.proposed):
        if len({item.equipment_item_id for item in values}) != len(values):
            raise HTTPException(status_code=422, detail="Equipment item IDs must be unique")
    canonical = lambda items: [item.model_dump(mode="json") for item in sorted(items, key=lambda value: str(value.equipment_item_id))]
    return _batch_rpc(db, "apply_change_batch", {
        "p_operation_id": str(payload.operation_id), "p_event_id": str(payload.event_id),
        "p_actor_id": str(payload.actor_id), "p_baseline": canonical(payload.baseline),
        "p_proposed": canonical(payload.proposed),
    })


@app.get("/internal/equipment-requirements/change-batches/{operation_id}")
def get_change_batch(
    operation_id: UUID,
    _service=Depends(require_change_service),
    db: Client = Depends(get_db),
):
    rows = _execute(
        db.schema(SCHEMA).table("change_operations").select("*").eq("id", str(operation_id)).limit(1)
    ).data
    if not rows:
        raise HTTPException(status_code=404, detail="Change operation not found")
    return rows[0]


@app.post("/internal/equipment-requirements/change-batches/{operation_id}/finish")
def finish_change_batch(
    operation_id: UUID,
    _service=Depends(require_change_service),
    db: Client = Depends(get_db),
):
    return _batch_rpc(db, "finish_change_batch", {"p_operation_id": str(operation_id)})


@app.post("/internal/equipment-requirements/change-batches/{operation_id}/abort")
def abort_change_batch(
    operation_id: UUID,
    _service=Depends(require_change_service),
    db: Client = Depends(get_db),
):
    return _batch_rpc(db, "abort_change_batch", {"p_operation_id": str(operation_id)})


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
