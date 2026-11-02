"""Small registered subclasses around native services, following Farmer 1.2.

No platform method is reassigned. CR construction, approval, history, ingestion,
outgestion and webhook authentication remain native implementations.
"""
import asyncio
from contextvars import ContextVar
from importlib import import_module
import logging
import os

from sqlalchemy import select
from openg2p_fastapi_common.context import get_async_session_maker
from openg2p_registry_core.models import (ChangeRequestSourceEnum, G2PRegisterDefinition, G2PRegisterSection,
                                         G2PRegisterUITabSection, G2PRegisterChangeRequest, G2PIntakeFormSubmission)
from openg2p_registry_core.errors import G2PRegistryErrorCodes, G2PRegistryException
from openg2p_registry_core.schemas import ChangeRequestRequestPayload, ChangePayload
from openg2p_registry_core.services.intake_form_data_service import G2PIntakeFormDataService
from openg2p_registry_core.services.g2p_register_change_request_service import G2PRegisterChangeRequestService
from openg2p_registry_core.services.g2p_change_request_worker_service import G2PChangeRequestWorkerService
from openg2p_registry_core.services.g2p_awe_webhook_service import G2PAweWebhookService

from ..direct_approval import DirectApprovalClosed
from ..fayda_id_view import FaydaIdMixin
from ..required_intake import RequiredFieldsMixin
from . import messages
from .configuration import configured_lookup
from .models import FarmerReference, FarmerReferenceRequest, FarmerSubmissionDependency, FarmerPendingLookup
from .onboarding import OnboardingService
from .profile import FarmerReferenceError, reference_identity, intake_identity, model_identity, matches_declared_identity, PROFILE_FIELDS

# The platform's own name for change requests raised by its ingestion pipeline
# (ChangeRequestSourceEnum.INGESTION_PIPELINE); the native ingest worker passes it.
INGESTION_PIPELINE_SOURCE = ChangeRequestSourceEnum.INGESTION_PIPELINE.value

_logger = logging.getLogger("coss-farmer-reference-validate")
_IDENTITY_MISMATCH = {"FARMER_REFERENCE_IDENTITY_MISMATCH", "FARMER_REFERENCE_FARMER_ID_MISMATCH"}


def _issue_code(reference_code: str) -> str:
    """The Validate issue code for a Farmer reference refusal."""
    if (reference_code in messages.UNAVAILABLE
            or reference_code in {"FARMER_REFERENCE_LOOKUP_UNAVAILABLE", "FARMER_REFERENCE_LOOKUP_CONFIGURATION_REQUIRED"}):
        return "LOOKUP_UNAVAILABLE"
    if reference_code in _IDENTITY_MISMATCH:
        return "FARMER_IDENTITY_MISMATCH"
    return "FARMER_NOT_FOUND"


_approved_callback = ContextVar("coss_farmer_approved_callback", default=None)


def domain_models():
    return import_module("openg2p_registry_extensions.register_domain.models")


async def farmer_definition(session):
    return (await session.execute(select(G2PRegisterDefinition).where(
        G2PRegisterDefinition.register_mnemonic == "Farmer"))).scalar_one()


async def create_native_request(session, local_id, profile, action, *, created_by="system"):
    definition = await farmer_definition(session)
    # Identity section UUIDs remain domain-owned; require one unambiguous native
    # section/tab binding instead of guessing a section or borrowing intake policy.
    bindings = (await session.execute(select(G2PRegisterSection, G2PRegisterUITabSection.tab_id).join(
        G2PRegisterUITabSection, G2PRegisterUITabSection.section_id == G2PRegisterSection.section_id).where(
            G2PRegisterSection.register_id == definition.register_id,
            G2PRegisterSection.section_register_id == definition.register_id,
            G2PRegisterSection.section_id.like("%farmer_identity_section_01")))).all()
    if len(bindings) != 1:
        raise FarmerReferenceError("FARMER_REFERENCE_SECTION_BINDING_REQUIRED")
    section, tab_id = bindings[0]
    if action not in {"ADD", "UPDATE"} or set(profile) - PROFILE_FIELDS:
        raise FarmerReferenceError("FARMER_REFERENCE_MANAGED_PAYLOAD_REQUIRED")
    reference_identity(profile)
    payload = {**profile, "internal_record_id": local_id, "edit_action": action}
    request = ChangeRequestRequestPayload(register_id=definition.register_id, register_mnemonic="Farmer",
        tab_id=tab_id, section_id=section.section_id, section_register_id=definition.register_id,
        internal_record_id=local_id, change_payload=[ChangePayload(**payload)])
    # Generic staff/worker creation intentionally permits only UPDATE for root
    # registers. This extension owns validated source-reference ADD orchestration
    # and uses native construction/persistence without a premature live record.
    # The same native approval/history/outgestion path applies afterwards.
    service = G2PRegisterChangeRequestService.get_component()
    await service._validate_domain_attributes([dict(profile)], "Farmer", section.section_ui_schema)
    cr = await service.construct_change_request(request, section, "Farmer", "Farmer",
        source_partner_id=os.environ.get("COSS_FARMER_SOURCE_PARTNER_ID") or None, created_by=created_by,
        change_request_source_override=INGESTION_PIPELINE_SOURCE, session=session)
    session.add(cr)
    session.add(cr._payload)
    await session.flush()
    return cr


def onboarding_service():
    return OnboardingService(domain_models().G2PRegisterFarmer, create_native_request)


async def record_native_decision(session, cr_id, approved):
    await onboarding_service().record_decision(session, cr_id, approved)
    request = (await session.execute(select(FarmerReferenceRequest).where(
        FarmerReferenceRequest.native_cr_id == cr_id))).scalar_one()
    submissions = (await session.execute(select(G2PIntakeFormSubmission).join(
        FarmerSubmissionDependency, FarmerSubmissionDependency.submission_id == G2PIntakeFormSubmission.submission_id).where(
            FarmerSubmissionDependency.reference_id == request.reference_id).with_for_update(
                of=G2PIntakeFormSubmission, skip_locked=True))).scalars().all()
    for submission in submissions:
        if not approved:
            if request.action == "ADD":
                submission.register_ingest_process_last_error_code = messages.FARMER_APPROVAL_REJECTED
                await set_intake_farmer_status(session, submission, messages.FARMER_APPROVAL_REJECTED)
            continue
        if (submission.approval_status == "APPROVED" and submission.draft_status == "FINAL" and
                submission.register_ingest_process_status == "NOT_APPLICABLE" and
                messages.is_waiting_text(submission.register_ingest_process_last_error_code)):
            # Release the original native ingest queue entry; don't recreate the
            # intake, change its approval, reset attempts, or replay business AWE.
            submission.register_ingest_process_status = "PENDING"
            submission.register_ingest_process_last_error_code = None
            await set_intake_farmer_status(session, submission, messages.FARMER_REFERENCE_LINKED)
    await session.flush()


async def set_intake_farmer_status(session, submission, text):
    """Keep the intake's own Farmer reference status in step with the waiting text."""
    definition = await session.get(G2PRegisterDefinition, submission.register_id)
    root = getattr(domain_models(), "G2PIntakeForm" + definition.register_mnemonic, None) if definition else None
    if root is None:
        return
    row = (await session.execute(select(root).where(root.submission_id == submission.submission_id))).scalars().first()
    if row is not None and hasattr(row, "farmer_reference_status"):
        row.farmer_reference_status = text


async def release_waiting_domains(session):
    """Recover a release skipped because a domain transaction held its row."""
    rows = (await session.execute(select(G2PIntakeFormSubmission, FarmerReference.state).join(
        FarmerSubmissionDependency, FarmerSubmissionDependency.submission_id == G2PIntakeFormSubmission.submission_id).join(
        FarmerReference, FarmerReference.reference_id == FarmerSubmissionDependency.reference_id).where(
            G2PIntakeFormSubmission.approval_status == "APPROVED",
            G2PIntakeFormSubmission.draft_status == "FINAL",
            G2PIntakeFormSubmission.register_ingest_process_status == "NOT_APPLICABLE",
            G2PIntakeFormSubmission.register_ingest_process_last_error_code.in_(
                [messages.WAITING_FOR_FARMER_APPROVAL, messages.FARMER_LOOKUP_PENDING,
                 messages.LEGACY_WAITING]),
            FarmerReference.state.in_(["APPROVED", "REJECTED"])).with_for_update(
                of=G2PIntakeFormSubmission, skip_locked=True))).all()
    for submission, state in rows:
        if state == "APPROVED":
            submission.register_ingest_process_status = "PENDING"
            submission.register_ingest_process_last_error_code = None
            await set_intake_farmer_status(session, submission, messages.FARMER_REFERENCE_LINKED)
        else:
            submission.register_ingest_process_last_error_code = messages.FARMER_APPROVAL_REJECTED
            await set_intake_farmer_status(session, submission, messages.FARMER_APPROVAL_REJECTED)
    await session.flush()
    return len(rows)


async def guard_farmer_approval(change_request, session):
    if _approved_callback.get() != change_request.change_request_id or not change_request.awe_request_id:
        raise FarmerReferenceError("FARMER_REFERENCE_AWE_APPROVAL_REQUIRED")
    return await onboarding_service().approval_guard(session, change_request.change_request_id)


class ReferenceIntakeService(FaydaIdMixin, RequiredFieldsMixin, DirectApprovalClosed, G2PIntakeFormDataService):
    # No approve_submission here: the DirectApprovalClosed guard answers a
    # direct approval first, for every register, before any lookup, so a
    # made-up id and a real one get the same AWE_APPROVAL_REQUIRED.

    async def approve_submission_with_session(self, submission_id, session, approved_by=None):
        dependency = await session.get(FarmerSubmissionDependency, submission_id)
        reference = await session.get(FarmerReference, dependency.reference_id, with_for_update=True) if dependency else None
        submission = await super().approve_submission_with_session(submission_id, session, approved_by)
        definition = await self._get_register_definition(submission.register_id, session)
        if definition.register_mnemonic in {"CropSown", "Livestock"}:
            if not reference or reference.state != "APPROVED":
                submission.register_ingest_process_status = "NOT_APPLICABLE"
                pending_lookup = await session.get(FarmerPendingLookup, submission_id)
                held = messages.held_text(reference, pending_lookup)
                submission.register_ingest_process_last_error_code = held
                await set_intake_farmer_status(session, submission, held)
                await session.flush()
        return submission

    async def finalize_submission_with_session(self, submission_id, session, finalized_by=None,
                                                bearer_token=None, requester_sub=None):
        from .messages import explain
        await self.ensure_form_complete(submission_id, session)
        # The service is a shared component: the declared IDs belong to this call.
        declared_ids = {}
        try:
            return await self._finalize_with_farmer(submission_id, session, finalized_by,
                                                    bearer_token, requester_sub, declared_ids)
        except FarmerReferenceError as error:
            raise G2PRegistryException(code=G2PRegistryErrorCodes.INVALID_REQUEST.value[1],
                                       message=explain(str(error), declared_ids)) from None

    async def validate_submission_for_approval_with_session(self, submission_id, session):
        """Validate also checks what Submit checks before it creates anything:
        the production season, and the Farmer, looked up read only. A wrong
        Farmer ID and Fayda ID pair or an unknown farmer is reported here and
        not first by Submit. The Farmer is checked even when the form is still
        incomplete, so one Validate lists every problem."""
        from openg2p_registry_core.schemas.intake_form import IntakeSubmissionValidationIssue

        result = await super().validate_submission_for_approval_with_session(submission_id, session)
        problems = []
        if not result.issues:
            problems.append(await self._submission_problem(submission_id, session, farmer=False))
        problems.append(await self._submission_problem(submission_id, session, season=False))
        for problem in problems:
            if problem:
                code, sentence = problem
                result.issues.append(IntakeSubmissionValidationIssue(
                    code=code, message=sentence if sentence[-1:] in ".!?" else sentence + "."))
        result.is_valid = not result.issues
        return result

    async def _submission_problem(self, submission_id, session, season=True, farmer=True):
        """The sentence Submit would refuse the draft with after the form is
        complete (season, then the Farmer ID and Fayda ID), or None. Nothing is
        created: the signed lookup is only read. A form already linked to a
        farmer is left to Submit."""
        submission = await self._get_submission_or_error(submission_id, session)
        definition = await self._get_register_definition(submission.register_id, session)
        if definition.register_mnemonic not in {"CropSown", "Livestock"}:
            return None
        models = domain_models()
        root = getattr(models, "G2PIntakeForm" + definition.register_mnemonic)
        rows = (await session.execute(select(root).where(root.submission_id == submission_id))).scalars().all()
        if len(rows) != 1:
            return None
        row = rows[0]
        if season and definition.register_mnemonic == "CropSown":
            sections = await self._get_form_sections(submission.form_id, session)
            if any(section.section_mnemonic in {"cs_intake_season", "cs_common_intake_season"}
                   for section in sections):
                from ..register_domain.services.g2p_register_domain_service_crop_sown import (
                    validate_production_season_fields,
                )
                try:
                    validate_production_season_fields({"crop_year": row.crop_year,
                                                       "production_season": row.production_season})
                except G2PRegistryException as error:
                    return "SUBMISSION_INCOMPLETE", error.message
        if not farmer or await session.get(FarmerSubmissionDependency, submission_id):
            return None
        live = await session.get(getattr(models, "G2PRegister" + definition.register_mnemonic), row.internal_record_id)
        if live and live.last_approved_at and live.farmer_uuid:
            return None
        return await self._farmer_problem(row)

    async def _farmer_problem(self, row):
        from .messages import explain

        declared_ids = {key: value for key, value in model_identity(row).items()
                        if key in {"farmer_id", "fayda_fin", "fayda_fan_id"} and value}
        try:
            declared = intake_identity(model_identity(row))
        except FarmerReferenceError:
            return None  # a missing or malformed ID is reported as a field format issue
        if not declared.get("farmer_id"):
            return None  # the missing ID is reported with the other missing fields
        try:
            client = configured_lookup()
            if declared.get("fayda_fin"):
                call = client.lookup(declared["farmer_id"], declared.get("fayda_fan_id"), fin=declared["fayda_fin"])
            else:
                call = client.lookup(declared["farmer_id"], declared["fayda_fan_id"])
            # httpx times each phase, not the whole call: bound the whole lookup.
            seconds = getattr(getattr(client, "config", None), "timeout_seconds", None) or 8.0
            source = await asyncio.wait_for(call, seconds)
            if not matches_declared_identity(declared, source.profile):
                raise FarmerReferenceError("FARMER_REFERENCE_IDENTITY_MISMATCH")
        except FarmerReferenceError as error:
            return _issue_code(str(error)), explain(str(error), declared_ids)
        except Exception as error:  # noqa: BLE001 - signing, transport or timeout: Validate must answer
            _logger.warning("Farmer lookup during validate failed: %s", type(error).__name__)
            return "LOOKUP_UNAVAILABLE", explain("FARMER_REFERENCE_LOOKUP_UNAVAILABLE", declared_ids)
        return None

    async def _finalize_with_farmer(self, submission_id, session, finalized_by, bearer_token, requester_sub,
                                    declared_ids):
        # A person submitting (bearer present) is told at once; workers hold and retry.
        interactive = bool(bearer_token)
        submission = await self._get_submission_or_error(submission_id, session)
        await session.refresh(submission, with_for_update=True)
        definition = await self._get_register_definition(submission.register_id, session)
        if definition.register_mnemonic == "Farmer":
            if submission.submission_source != INGESTION_PIPELINE_SOURCE:
                raise FarmerReferenceError("FARMER_REFERENCE_CHANGE_REQUEST_REQUIRED")
            return await self._finalize_farmer_notice(submission, session)
        if definition.register_mnemonic in {"CropSown", "Livestock"}:
            models = domain_models()
            root = getattr(models, "G2PIntakeForm" + definition.register_mnemonic)
            rows = (await session.execute(select(root).where(root.submission_id == submission_id))).scalars().all()
            if len(rows) != 1:
                raise FarmerReferenceError("FARMER_REFERENCE_SINGLE_DOMAIN_ROOT_REQUIRED")
            row = rows[0]
            declared_ids.update({key: value for key, value in model_identity(row).items()
                                 if key in {"farmer_id", "fayda_fin", "fayda_fan_id"} and value})
            declared = intake_identity(model_identity(row))
            if not declared.get("farmer_id"):
                raise FarmerReferenceError("FARMER_REFERENCE_FARMER_ID_REQUIRED")
            for field, value in declared.items():
                setattr(row, field, value)
            sections = await self._get_form_sections(submission.form_id, session)
            # Required season fields moved out of Farmer Identity. Check the
            # persisted root at submit too, before any Farmer lookup/CR, so a
            # skipped Production Season section cannot bypass its validation.
            if definition.register_mnemonic == "CropSown" and any(
                section.section_mnemonic in {"cs_intake_season", "cs_common_intake_season"}
                for section in sections
            ):
                from ..register_domain.services.g2p_register_domain_service_crop_sown import (
                    validate_production_season_fields,
                )
                validate_production_season_fields({
                    "crop_year": row.crop_year,
                    "production_season": row.production_season,
                })
            farmer = await farmer_definition(session)
            if any(section.section_register_id == farmer.register_id for section in sections):
                raise FarmerReferenceError("FARMER_REFERENCE_INTAKE_METADATA_REQUIRES_ROOT_IDENTITY")
            dependency = await session.get(FarmerSubmissionDependency, submission_id)
            if dependency:
                reference = await session.get(FarmerReference, dependency.reference_id)
                if reference.state == "REJECTED":
                    raise FarmerReferenceError("FARMER_REFERENCE_DEPENDENCY_REJECTED")
                binding = dependency.identity_binding
                if binding:
                    if (binding.get("source_record_id") != reference.source_record_id or
                            binding.get("source_system") != reference.source_system):
                        raise FarmerReferenceError("FARMER_REFERENCE_SOURCE_ID_MISMATCH")
                    expected = binding["identity"]
                elif reference.state == "APPROVED":
                    local = await onboarding_service().require_approved_dependency(session, submission_id)
                    expected = model_identity(local)
                else:
                    request = await session.get(FarmerReferenceRequest, dependency.farmer_request_id)
                    expected = request.profile if request else {}
                if not matches_declared_identity(declared, expected):
                    raise FarmerReferenceError("FARMER_REFERENCE_SUBMISSION_IDENTITY_CHANGED")
                row.farmer_uuid, row.farmer_id = reference.local_farmer_id, reference.farmer_id
                row.farmer_reference_status = (messages.FARMER_REFERENCE_LINKED if reference.state == "APPROVED" else
                    messages.FARMER_REFERENCE_AWAITING)
            else:
                live = await session.get(getattr(models, "G2PRegister" + definition.register_mnemonic), row.internal_record_id)
                if live and live.last_approved_at and live.farmer_uuid:
                    if not matches_declared_identity(declared, model_identity(live)):
                        raise FarmerReferenceError("FARMER_REFERENCE_SUBMISSION_IDENTITY_CHANGED")
                    reference = await onboarding_service().link_approved_dependency(session, submission_id,
                        live.farmer_uuid, declared.get("farmer_id"), declared.get("fayda_fan_id"), fin=declared.get("fayda_fin"),
                        approved_domain_identity=model_identity(live), approved_domain_record_id=live.internal_record_id)
                    row.farmer_uuid, row.farmer_id = reference.local_farmer_id, reference.farmer_id
                    row.farmer_reference_status = "Farmer reference linked"
                else:
                    from .pending import resolve_or_wait
                    reference = await resolve_or_wait(session, submission, row, interactive=interactive)
                if reference is None:
                    submission.register_ingest_process_last_error_code = messages.FARMER_LOOKUP_PENDING
            await session.flush()
        if not bearer_token:
            # Native ingestion workers have no human bearer. A narrowly scoped
            # service account submits the normal intake policy; never an admin fallback.
            from .workflow import service_bearer
            bearer_token = await service_bearer()
        return await super().finalize_submission_with_session(submission_id, session, finalized_by,
            bearer_token=bearer_token, requester_sub=requester_sub)

    async def _finalize_farmer_notice(self, submission, session):
        """A Farmer Registry change notice for a farmer first seen here reaches the platform as a
        Farmer intake from the ingestion pipeline (the ADD the classifier assigns when no local
        Farmer row exists). Nothing is approved through that intake: its Farmer ID and Fayda ID
        start the Farmer reference ADD, exactly as the same notice does for an unreferenced
        farmer, and the intake is closed as cancelled with a pointer to the change request. It
        stays a draft, so no approval, deduplication or register ingest ever picks it up."""
        expected_partner = os.environ.get("COSS_FARMER_SOURCE_PARTNER_ID", "").strip()
        if not expected_partner or submission.partner_id != expected_partner:
            raise FarmerReferenceError("FARMER_REFERENCE_SOURCE_PARTNER_REQUIRED")
        root = getattr(domain_models(), "G2PIntakeFormFarmer")
        rows = (await session.execute(select(root).where(root.submission_id == submission.submission_id))).scalars().all()
        if len(rows) != 1:
            raise FarmerReferenceError("FARMER_REFERENCE_INVALID_NOTIFICATION")
        request = await first_reference_from_notice(session, reference_identity(model_identity(rows[0])), "system")
        submission.remarks = "Farmer reference requested: change request " + request.change_request_id
        await self.cancel_submission_with_session(submission.submission_id, session, cancelled_by="system")
        return submission

    async def _insert_live_register_row(self, submission, section, register_definition,
                                        schema_class, register_class, intake_row, session):
        root_definition = await self._get_register_definition(submission.register_id, session)
        if root_definition.register_mnemonic in {"CropSown", "Livestock"}:
            if register_definition.register_mnemonic == "Farmer":
                raise FarmerReferenceError("FARMER_REFERENCE_LEGACY_INTAKE_SECTION_BLOCKED")
            approved = await onboarding_service().require_approved_dependency(session, submission.submission_id)
            if register_definition.register_mnemonic == root_definition.register_mnemonic:
                if intake_row.farmer_uuid != approved.internal_record_id:
                    raise FarmerReferenceError("FARMER_REFERENCE_SUBMISSION_IDENTITY_CHANGED")
        return await super()._insert_live_register_row(submission, section, register_definition,
            schema_class, register_class, intake_row, session)


class ReferenceChangeRequestService(DirectApprovalClosed, G2PRegisterChangeRequestService):
    async def create_change_request(self, change_request_request_payload, *args, **kwargs):
        async with get_async_session_maker()() as session:
            section = await session.get(G2PRegisterSection, change_request_request_payload.section_id) if change_request_request_payload.section_id else None
            definition = await session.get(G2PRegisterDefinition, section.section_register_id) if section else None
            if definition and definition.register_mnemonic == "Farmer":
                raise FarmerReferenceError("FARMER_REFERENCE_VERIFIED_SOURCE_REQUEST_REQUIRED")
        return await super().create_change_request(change_request_request_payload, *args, **kwargs)

    async def _ensure_change_request_readable(self, change_request_id, data_policies, session):
        # A source-reference ADD names a Farmer record that exists only once the
        # request is approved. The native check demands that subject record, so a
        # pending (or rejected) ADD could not be opened (REG-ERR-002). Such a
        # request is read on its own when no data policy scopes the caller (a
        # policy is evaluated on the subject record, which does not exist yet);
        # every other request keeps the native check.
        if data_policies:
            return await super()._ensure_change_request_readable(change_request_id, data_policies, session)
        managed = (await session.execute(select(FarmerReferenceRequest).where(
            FarmerReferenceRequest.native_cr_id == change_request_id,
            FarmerReferenceRequest.action == "ADD"))).scalars().first()
        change_request = await session.get(G2PRegisterChangeRequest, change_request_id) if managed else None
        if (change_request is not None and
                await session.get(domain_models().G2PRegisterFarmer, change_request.internal_record_id) is None):
            return change_request
        return await super()._ensure_change_request_readable(change_request_id, data_policies, session)

    async def approve_change_request_from_awe_webhook(self, change_request_id, session, approved_by=None):
        token = _approved_callback.set(change_request_id)
        try:
            return await super().approve_change_request_from_awe_webhook(change_request_id, session, approved_by)
        finally:
            _approved_callback.reset(token)

    async def approve_register(self, change_request, section, session):
        definition = await self.validate_register_definition(section.section_register_id, session)
        if definition.register_mnemonic != "Farmer":
            return await super().approve_register(change_request, section, session)
        reference, request = await guard_farmer_approval(change_request, session)
        payload = await self._get_change_request_payload(change_request.change_request_id, session)
        if len(payload.change_payload or []) != 1:
            raise FarmerReferenceError("FARMER_REFERENCE_MANAGED_PAYLOAD_REQUIRED")
        actual = payload.change_payload[0]
        profile = {field: value for field, value in actual.items() if field in PROFILE_FIELDS}
        if (profile != request.profile or actual.get("edit_action") != request.action or
                set(actual) - (PROFILE_FIELDS | {"internal_record_id", "edit_action", "documents"}) or
                actual.get("documents") not in (None, []) or
                actual.get("internal_record_id") != reference.local_farmer_id or
                change_request.internal_record_id != reference.local_farmer_id):
            raise FarmerReferenceError("FARMER_REFERENCE_MANAGED_PAYLOAD_CHANGED")
        if request.action == "ADD":
            if await session.get(domain_models().G2PRegisterFarmer, reference.local_farmer_id):
                raise FarmerReferenceError("FARMER_REFERENCE_ADD_ALREADY_RESOLVED")
            if definition.functional_id_generation_required:
                raise FarmerReferenceError("FARMER_REFERENCE_EXTERNAL_IDENTIFIER_CONFIGURATION_REQUIRED")
            await self.insert_primary_master_section_into_register(change_request, session)
            await session.flush()
            farmer = await session.get(domain_models().G2PRegisterFarmer, reference.local_farmer_id)
            # Native UPDATE classification resolves functional_record_id. For a
            # newly approved source reference, derive it from the verified pair.
            # Never rewrite an existing record's internal or functional identity.
            if farmer.functional_record_id not in (None, "", request.profile["farmer_id"]):
                raise FarmerReferenceError("FARMER_REFERENCE_LOCAL_IDENTITY_CONFLICT")
            farmer.functional_record_id = request.profile["farmer_id"]
            await session.flush()
        else:
            await super().approve_register(change_request, section, session)
        if any(field in request.profile for field in ("first_name", "middle_name", "last_name")):
            farmer = await session.get(domain_models().G2PRegisterFarmer, reference.local_farmer_id)
            farmer.farmer_name = " ".join(value.strip() for value in
                (farmer.first_name, farmer.middle_name, farmer.last_name) if value and value.strip()) or None
            await session.flush()


class ReferenceWebhookService(G2PAweWebhookService):
    async def _apply_terminal_event_for_change_request(self, event, session):
        await super()._apply_terminal_event_for_change_request(event, session)
        if event.event_type in {"request_rejected", "request_cancelled"}:
            managed = (await session.execute(select(FarmerReferenceRequest).where(
                FarmerReferenceRequest.native_cr_id == event.artifact_id))).scalar_one_or_none()
            if managed:
                await record_native_decision(session, event.artifact_id, False)


class ReferenceIngestionService(G2PChangeRequestWorkerService):
    async def create_change_request(self, change_request_request_payload, session,
                                    source_partner_id=None, created_by=None, change_request_source=None):
        payload = change_request_request_payload
        definition = await session.get(G2PRegisterDefinition, payload.section_register_id)
        if not definition or definition.register_mnemonic != "Farmer":
            return await super().create_change_request(payload, session, source_partner_id, created_by, change_request_source)
        expected_partner = os.environ.get("COSS_FARMER_SOURCE_PARTNER_ID", "").strip()
        if not expected_partner or source_partner_id != expected_partner or change_request_source != INGESTION_PIPELINE_SOURCE:
            raise FarmerReferenceError("FARMER_REFERENCE_SOURCE_PARTNER_REQUIRED")
        reference = (await session.execute(select(FarmerReference).where(
            FarmerReference.local_farmer_id == payload.internal_record_id))).scalar_one_or_none()
        from .notification import notification_change_identity
        notification_pair = notification_change_identity(payload)
        if reference is None or reference.state == "PENDING":
            # The Farmer registry announced a farmer this registry has no approved
            # reference for yet: the notice starts the first reference.
            return await self._first_reference_from_notice(
                session, payload, definition, notification_pair, created_by)
        if reference.state != "APPROVED":
            raise FarmerReferenceError("FARMER_REFERENCE_DEPENDENCY_REJECTED")
        if notification_pair[0] != reference.farmer_id:
            raise FarmerReferenceError("FARMER_REFERENCE_IDENTITY_MISMATCH")
        await self._require_identity_section(session, payload, definition)
        client = configured_lookup()
        if client.config.source_id != reference.source_system:
            raise FarmerReferenceError("FARMER_REFERENCE_SOURCE_ID_MISMATCH")
        # Notification demographic values are deliberately not read.
        lookup_identifier = (notification_pair[1] if len(notification_pair[1]) == 12 and len(reference.uid) == 16
                             else reference.uid)
        current = await client.lookup_current(reference.farmer_id, lookup_identifier, reference.source_record_id)
        # An approved UID correction may be notified using the new UID. Only
        # the signed, consented lookup pinned to this same immutable source
        # person can establish that correction; the event cannot authorize it.
        if notification_pair[1] not in {reference.uid, current.profile.get("fayda_fan_id"), current.profile.get("fayda_fin")}:
            raise FarmerReferenceError("FARMER_REFERENCE_IDENTITY_MISMATCH")
        request = await onboarding_service().queue_current_update(session, current)
        if request is None:
            request = (await session.execute(select(FarmerReferenceRequest).where(
                FarmerReferenceRequest.reference_id == reference.reference_id,
                FarmerReferenceRequest.source_version == current.source_version,
                FarmerReferenceRequest.state == "APPROVED"))).scalar_one_or_none()
            if not request:
                raise FarmerReferenceError("FARMER_REFERENCE_STALE_SOURCE_VERSION")
        return await session.get(G2PRegisterChangeRequest, request.native_cr_id)

    @staticmethod
    async def _require_identity_section(session, payload, definition):
        section = await session.get(G2PRegisterSection, payload.section_id)
        if (payload.register_id != definition.register_id or not section or
                section.register_id != definition.register_id or section.section_register_id != definition.register_id or
                "identity" not in section.section_id):
            raise FarmerReferenceError("FARMER_REFERENCE_INVALID_NOTIFICATION_SECTION")

    async def _first_reference_from_notice(self, session, payload, definition, notification_pair, created_by):
        await self._require_identity_section(session, payload, definition)
        return await first_reference_from_notice(session, notification_pair, created_by)


async def first_reference_from_notice(session, notification_pair, created_by):
    """Queue the Farmer reference ADD for a farmer announced by the Farmer registry.

    Only the Farmer ID and Fayda ID of the notice are used, as the typed IDs
    of an intake are; every value comes from the signed, consented lookup.
    The request needs the normal approval and is never applied here. A repeat
    notice, or an update before the ADD is approved, returns the pending ADD.
    """
    client = configured_lookup()
    onboarding = onboarding_service()
    farmer_id, identifier = notification_pair
    reference = (await session.execute(select(FarmerReference).where(
        FarmerReference.source_system == client.config.source_id,
        FarmerReference.farmer_id == farmer_id))).scalar_one_or_none()
    if reference is not None and reference.state == "PENDING" and reference.pending_add_request_id:
        return await native_request(session, reference.pending_add_request_id)
    declared = ({"farmer_id": farmer_id, "fayda_fin": identifier} if len(identifier) == 12
                else {"farmer_id": farmer_id, "fayda_fan_id": identifier})
    if declared.get("fayda_fin"):
        source = await client.lookup(farmer_id, None, fin=declared["fayda_fin"])
    else:
        source = await client.lookup(farmer_id, declared["fayda_fan_id"])
    if not matches_declared_identity(declared, source.profile):
        raise FarmerReferenceError("FARMER_REFERENCE_IDENTITY_MISMATCH")
    async with session.begin_nested():
        reference = await onboarding.ensure_first_reference(session, source, requester=created_by or "system")
        if reference.state == "APPROVED":
            # An already approved local Farmer with this exact identity was adopted:
            # nothing to add, only the current version to bring in.
            request = await onboarding.queue_current_update(session, source)
            if request is None:
                raise FarmerReferenceError("FARMER_REFERENCE_STALE_SOURCE_VERSION")
            return await session.get(G2PRegisterChangeRequest, request.native_cr_id)
    return await native_request(session, reference.pending_add_request_id)


async def native_request(session, request_id):
    request = await session.get(FarmerReferenceRequest, request_id)
    return await session.get(G2PRegisterChangeRequest, request.native_cr_id)
