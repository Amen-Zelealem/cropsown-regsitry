"""Expose the current intake submission_id to section-save validation.

The platform calls ``validate_domain_attributes`` (and therefore the cross-section
checks) WITHOUT a DB session during a section save ("Next"), and the child-section
payload carries no submission/record id. So checks like season-consistency cannot
resolve the parent / Production Season on the Next button.

This subclass stashes the ``submission_id`` (a parameter of the save method) in a
ContextVar for the duration of the save; ``resolve_production_season`` reads it and
opens its own session. We SUBCLASS the farmer-reference ``ReferenceIntakeService``
(we do not edit it) so all of its finalize/approve behaviour is preserved, then
register our subclass ahead of it in the component registry.
"""
from contextvars import ContextVar

from openg2p_fastapi_common.context import component_registry

from ...farmer_reference.native import G2PIntakeFormDataService, ReferenceIntakeService

# Set for the duration of a single section save; read by resolve_production_season.
submission_ctx: ContextVar[str | None] = ContextVar("coss_crop_submission_id", default=None)


class CropIntakeService(ReferenceIntakeService):
    async def save_intake_form_submission_with_session(self, submission_id, *args, **kwargs):
        token = submission_ctx.set(submission_id)
        try:
            return await super().save_intake_form_submission_with_session(
                submission_id, *args, **kwargs
            )
        finally:
            submission_ctx.reset(token)


def install():
    """Swap CropIntakeService ahead of ReferenceIntakeService / the base intake
    service in the shared component registry. Idempotent; run from app.py AFTER
    ``farmer_reference.runtime.install()``."""
    if any(isinstance(item, CropIntakeService) for item in component_registry):
        return
    # Remove the farmer-reference instance so lookups resolve to ours (a subclass).
    for item in [i for i in component_registry if isinstance(i, ReferenceIntakeService)]:
        component_registry.remove(item)
    instance = CropIntakeService()
    first = next(
        (index for index, item in enumerate(component_registry)
         if isinstance(item, G2PIntakeFormDataService)),
        len(component_registry),
    )
    component_registry.insert(first, instance)
