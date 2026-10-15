import datetime
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import Request
from openg2p_fastapi_common.controller import BaseController
from starlette.responses import JSONResponse

_logger = logging.getLogger("g2p-cropsown-awe-emulator")

# In-memory store for local standalone AWE workflow emulation
_MOCK_REQUESTS: Dict[str, Dict[str, Any]] = {}
_MOCK_TASKS: Dict[str, Dict[str, Any]] = {}


async def _enrich_task(task: Dict[str, Any]) -> None:
    if not task.get("assignee"):
        task["assignee"] = "admin"
    if not task.get("assignee_name"):
        task["assignee_name"] = "Admin User"
    if not task.get("kind"):
        task["kind"] = "user"
    if "decision_action" not in task:
        task["decision_action"] = task.get("decision") if task.get("status") == "completed" else None

    ctx = dict(task.get("context") or {})
    if not ctx.get("register_mnemonic") or not ctx.get("record_name"):
        clean_id = task.get("artifact_id") or task.get("id", "").replace("task_", "").replace("req_", "")
        try:
            from openg2p_fastapi_common.context import dbengine
            from sqlalchemy import text
            engine = dbengine.get()
            async with engine.connect() as conn:
                res = await conn.execute(
                    text("""
                        SELECT s.submission_id, s.application_reference, s.register_id, s.form_id,
                               d.form_mnemonic, r.register_mnemonic
                        FROM g2p_intake_form_submissions s
                        LEFT JOIN g2p_intake_form_definitions d ON s.form_id = d.form_id
                        LEFT JOIN g2p_register_definitions r ON s.register_id = r.register_id
                        WHERE s.submission_id::text = :sid
                    """),
                    {"sid": clean_id}
                )
                row = res.mappings().first()
                if row:
                    reg_mnem = row.get("register_mnemonic") or "cropsown"
                    form_mnem = row.get("form_mnemonic") or task.get("policy_key", "").split(".")[-1] or "planning_cropsown"
                    ref = row.get("application_reference") or clean_id
                    ctx["register_mnemonic"] = reg_mnem
                    ctx["section_mnemonic"] = form_mnem
                    ctx["intake_form_mnemonic"] = form_mnem
                    ctx["record_name"] = ref
                    ctx["submission_id"] = str(row.get("submission_id"))
                    ctx["register_id"] = str(row.get("register_id"))
                    task["artifact_type"] = "registry.intake_form"
                    task["artifact_id"] = str(row.get("submission_id"))
                else:
                    res_cr = await conn.execute(
                        text("""
                            SELECT c.change_request_id, c.application_reference, c.register_id, r.register_mnemonic
                            FROM g2p_register_change_requests c
                            LEFT JOIN g2p_register_definitions r ON c.register_id = r.register_id
                            WHERE c.change_request_id::text = :cid
                        """),
                        {"cid": clean_id}
                    )
                    row_cr = res_cr.mappings().first()
                    if row_cr:
                        reg_mnem = row_cr.get("register_mnemonic") or "cropsown"
                        ref = row_cr.get("application_reference") or clean_id
                        ctx["register_mnemonic"] = reg_mnem
                        ctx["record_name"] = ref
                        ctx["change_request_id"] = str(row_cr.get("change_request_id"))
                        ctx["register_id"] = str(row_cr.get("register_id"))
                        task["artifact_type"] = "registry.change_request"
                        task["artifact_id"] = str(row_cr.get("change_request_id"))
                    else:
                        ctx["register_mnemonic"] = "cropsown"
                        ctx["section_mnemonic"] = "1. Crop Sown Planning Intake"
                        ctx["record_name"] = clean_id
                        ctx["submission_id"] = clean_id
                        task["artifact_type"] = "registry.intake_form"
                        task["artifact_id"] = clean_id
        except Exception as exc:
            _logger.warning("Error enriching task: %s", exc)
            ctx["register_mnemonic"] = "cropsown"
            ctx["section_mnemonic"] = "1. Crop Sown Planning Intake"
            ctx["record_name"] = clean_id
            ctx["submission_id"] = clean_id
            task["artifact_type"] = "registry.intake_form"
            task["artifact_id"] = clean_id
    task["context"] = ctx


class G2PAweTasksStatsController(BaseController):
    """Full-featured local AWE emulator controller for standalone development.

    Emulates AWE request creation, task assignment to admin/current user,
    task listing, and decision submission (approve/reject).
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.router.tags += ["/v1/awe"]

        # Register AWE routes under both /v1/awe and /awe
        for prefix in ["/v1/awe", "/awe"]:
            self.router.add_api_route(f"{prefix}/tasks/stats", self.get_stats, methods=["GET"])
            self.router.add_api_route(f"{prefix}/requests", self.create_request, methods=["POST"])
            self.router.add_api_route(f"{prefix}/requests", self.search_requests, methods=["GET"])
            self.router.add_api_route(f"{prefix}/requests/{{request_id}}", self.get_request_by_id, methods=["GET"])
            self.router.add_api_route(f"{prefix}/requests/{{request_id}}/events", self.get_request_events, methods=["GET"])
            self.router.add_api_route(f"{prefix}/tasks", self.list_tasks, methods=["GET"])
            self.router.add_api_route(f"{prefix}/tasks/{{task_id}}/claim", self.claim_task, methods=["POST"])
            self.router.add_api_route(f"{prefix}/tasks/{{task_id}}/decision", self.submit_decision, methods=["POST"])

    async def get_stats(self, request: Request) -> JSONResponse:
        open_count = sum(1 for t in _MOCK_TASKS.values() if t.get("status") in {"open", "claimed"})
        completed_count = sum(1 for t in _MOCK_TASKS.values() if t.get("status") == "completed")
        return JSONResponse({"pending": open_count, "approved": completed_count, "draft": 0, "completed": completed_count})

    async def create_request(self, request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}

        artifact_id = str(body.get("artifact_id") or uuid.uuid4())
        policy_key = str(body.get("policy_key") or "registry.intake_form.planning_cropsown")
        artifact_type = str(body.get("artifact_type") or "registry.intake_form")
        callback_url = body.get("callback_url")
        context = body.get("context") or {}

        request_id = f"req_{artifact_id}"
        task_id = f"task_{artifact_id}"
        now_str = datetime.datetime.utcnow().isoformat()

        request_data = {
            "request_id": request_id,
            "id": request_id,
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "policy_key": policy_key,
            "status": "active",
            "current_stage_order": 1,
            "created_at": now_str,
            "callback_url": callback_url,
            "context": context,
        }
        _MOCK_REQUESTS[request_id] = request_data

        task_data = {
            "id": task_id,
            "task_id": task_id,
            "request_id": request_id,
            "stage_order": 1,
            "stage_name": "Admin Approval",
            "status": "open",
            "assignee": "admin",
            "assignee_name": "Admin User",
            "kind": "user",
            "decision_action": None,
            "assigned_to": ["admin", "Admin User"],
            "actions": ["approve", "reject"],
            "artifact_type": artifact_type,
            "artifact_id": artifact_id,
            "policy_key": policy_key,
            "context": context,
            "created_at": now_str,
            "callback_url": callback_url,
        }
        _MOCK_TASKS[task_id] = task_data

        _logger.info("Local AWE Emulator: Created request %s and task %s for artifact %s", request_id, task_id, artifact_id)
        return JSONResponse({
            "request_id": request_id,
            "id": request_id,
            "status": "active",
            "current_stage_order": 1,
        })

    async def get_request_by_id(self, request_id: str) -> JSONResponse:
        req_data = _MOCK_REQUESTS.get(request_id)
        if not req_data:
            # Fallback mock for direct lookups
            req_data = {
                "id": request_id,
                "request_id": request_id,
                "status": "active",
                "current_stage_order": 1,
            }
        return JSONResponse(req_data)

    async def get_request_events(self, request_id: str) -> JSONResponse:
        return JSONResponse([])

    async def search_requests(self, request: Request) -> JSONResponse:
        items = list(_MOCK_REQUESTS.values())
        return JSONResponse({"items": items, "total": len(items), "page": 1, "page_size": 25, "pages": 1})

    async def list_tasks(self, request: Request) -> JSONResponse:
        params = request.query_params
        request_id_filter = params.get("request_id")
        artifact_id_filter = params.get("artifact_id")
        status_filter = params.get("status")

        # Auto-load pending submissions with awe_request_id into _MOCK_TASKS
        try:
            from openg2p_fastapi_common.context import dbengine
            from sqlalchemy import text
            engine = dbengine.get()
            async with engine.connect() as conn:
                res_all = await conn.execute(
                    text("""
                        SELECT s.submission_id, s.application_reference, s.register_id, s.form_id,
                               s.awe_request_id, s.approval_status, s.first_created_at,
                               d.form_mnemonic, r.register_mnemonic
                        FROM g2p_intake_form_submissions s
                        LEFT JOIN g2p_intake_form_definitions d ON s.form_id = d.form_id
                        LEFT JOIN g2p_register_definitions r ON s.register_id = r.register_id
                        WHERE s.approval_status = 'PENDING' AND s.awe_request_id IS NOT NULL
                        ORDER BY s.first_created_at DESC
                    """)
                )
                for row in res_all.mappings():
                    clean_id = str(row["submission_id"])
                    t_id = f"task_{clean_id}"
                    req_id = row["awe_request_id"] or f"req_{clean_id}"
                    if t_id not in _MOCK_TASKS:
                        reg_mnem = row.get("register_mnemonic") or "cropsown"
                        form_mnem = row.get("form_mnemonic") or "1. Crop Sown Planning Intake"
                        ref = row.get("application_reference") or clean_id
                        now_str = row["first_created_at"].isoformat() if row.get("first_created_at") else datetime.datetime.utcnow().isoformat()
                        _MOCK_TASKS[t_id] = {
                            "id": t_id,
                            "task_id": t_id,
                            "request_id": req_id,
                            "stage_order": 1,
                            "stage_name": "Admin Approval",
                            "status": "open",
                            "assignee": "admin",
                            "assignee_name": "Admin User",
                            "kind": "user",
                            "decision_action": None,
                            "assigned_to": ["admin", "Admin User"],
                            "actions": ["approve", "reject"],
                            "artifact_type": "registry.intake_form",
                            "artifact_id": clean_id,
                            "policy_key": "registry.intake_form.planning_cropsown",
                            "context": {
                                "register_mnemonic": reg_mnem,
                                "section_mnemonic": form_mnem,
                                "intake_form_mnemonic": form_mnem,
                                "record_name": ref,
                                "submission_id": clean_id,
                                "register_id": str(row.get("register_id")),
                            },
                            "created_at": now_str,
                        }
        except Exception as exc:
            _logger.warning("Error auto-loading pending tasks: %s", exc)

        # Auto-create task dynamically if requested for an existing submission/change_request
        target_id = request_id_filter or artifact_id_filter
        if target_id and not any(
            t for t in _MOCK_TASKS.values()
            if t.get("request_id") == target_id or t.get("artifact_id") == target_id or t.get("id") == target_id
        ):
            # Clean target ID
            clean_id = target_id.replace("req_", "").replace("task_", "")
            req_id = f"req_{clean_id}"
            t_id = f"task_{clean_id}"
            now_str = datetime.datetime.utcnow().isoformat()

            _MOCK_REQUESTS[req_id] = {
                "request_id": req_id,
                "id": req_id,
                "artifact_id": clean_id,
                "artifact_type": "registry.intake_form",
                "status": "active",
                "current_stage_order": 1,
            }
            _MOCK_TASKS[t_id] = {
                "id": t_id,
                "task_id": t_id,
                "request_id": req_id,
                "stage_order": 1,
                "stage_name": "Admin Approval",
                "status": "open",
                "assignee": "admin",
                "assignee_name": "Admin User",
                "kind": "user",
                "decision_action": None,
                "assigned_to": ["admin", "Admin User"],
                "actions": ["approve", "reject"],
                "artifact_type": "registry.intake_form",
                "artifact_id": clean_id,
                "created_at": now_str,
            }

        matching = []
        for task in _MOCK_TASKS.values():
            if status_filter and status_filter != "all" and task.get("status") != status_filter:
                continue
            if request_id_filter and task.get("request_id") != request_id_filter and task.get("id") != request_id_filter:
                continue
            if artifact_id_filter and task.get("artifact_id") != artifact_id_filter:
                continue
            matching.append(task)

        for task in matching:
            await _enrich_task(task)

        return JSONResponse({"items": matching, "total": len(matching), "page": 1, "page_size": 25, "pages": 1})

    async def claim_task(self, task_id: str, request: Request) -> JSONResponse:
        task = _MOCK_TASKS.get(task_id)
        if task:
            task["status"] = "claimed"
        return JSONResponse(task or {"id": task_id, "status": "claimed"})

    async def submit_decision(self, task_id: str, request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}

        action = (body.get("action") or "approve").lower()
        comment = body.get("comment") or body.get("remarks") or ""

        task = _MOCK_TASKS.get(task_id)
        artifact_id = task.get("artifact_id") if task else task_id.replace("task_", "").replace("req_", "")
        request_id = task.get("request_id") if task else f"req_{artifact_id}"

        if task:
            task["status"] = "completed"
            task["decision"] = action
            task["decision_action"] = action

        _logger.info("Local AWE Emulator: Submitted decision '%s' for task %s (artifact %s)", action, task_id, artifact_id)

        try:
            from openg2p_fastapi_common.context import dbengine
            from sqlalchemy import text
            engine = dbengine.get()

            try:
                from openg2p_registry_core.services.intake_form_data_service import G2PIntakeFormDataService
                from openg2p_registry_core.services.g2p_register_change_request_service import G2PRegisterChangeRequestService
            except ImportError:
                from core_pkg.services.intake_form_data_service import G2PIntakeFormDataService
                from core_pkg.services.g2p_register_change_request_service import G2PRegisterChangeRequestService

            if action == "approve":
                # Ensure number_of_verifications_required = 0 so approval passes validation
                try:
                    async with engine.connect() as conn:
                        await conn.execute(
                            text("UPDATE g2p_intake_form_submissions SET number_of_verifications_required = 0 WHERE submission_id = :sid"),
                            {"sid": artifact_id}
                        )
                        await conn.commit()
                except Exception as ve:
                    _logger.warning("Could not reset number_of_verifications_required: %s", ve)

                try:
                    await G2PIntakeFormDataService.get_component().approve_submission(artifact_id, "Admin User")
                    _logger.info("Local AWE Emulator: Approved intake submission %s", artifact_id)
                except Exception as e:
                    _logger.warning("Intake form approval exception: %s", e)
                    try:
                        async with engine.connect() as conn:
                            await conn.execute(
                                text("""
                                    UPDATE g2p_intake_form_submissions 
                                    SET approval_status = 'APPROVED',
                                        approved_by = 'Admin User',
                                        approved_at = NOW(),
                                        last_updated_at = NOW(),
                                        number_of_verifications_required = 0,
                                        register_ingest_process_status = 'PENDING'
                                    WHERE submission_id = :sid
                                """),
                                {"sid": artifact_id}
                            )
                            await conn.commit()
                        await G2PIntakeFormDataService.get_component().process_submission_register_ingest(artifact_id)
                        _logger.info("Local AWE Emulator: Direct DB approval and register ingestion succeeded for %s", artifact_id)
                    except Exception as fe:
                        _logger.warning("Fallback direct approval exception (checking change request): %s", fe)
                        try:
                            await G2PRegisterChangeRequestService.get_component().approve_change_request(artifact_id, "Admin User")
                            _logger.info("Local AWE Emulator: Approved change request %s", artifact_id)
                        except Exception as ex:
                            _logger.warning("Change request approval exception: %s", ex)
            elif action == "reject":
                try:
                    await G2PIntakeFormDataService.get_component().reject_submission(artifact_id, "Admin User")
                    _logger.info("Local AWE Emulator: Rejected intake submission %s", artifact_id)
                except Exception as e:
                    _logger.warning("Intake form rejection exception: %s", e)
        except Exception as exc:
            _logger.error("Error applying local AWE decision: %s", exc)

        now_str = datetime.datetime.utcnow().isoformat()
        return JSONResponse({
            "id": f"dec_{task_id}",
            "request_id": request_id,
            "task_id": task_id,
            "actor": "Admin User",
            "action": action,
            "comment": comment,
            "created_at": now_str,
        })
