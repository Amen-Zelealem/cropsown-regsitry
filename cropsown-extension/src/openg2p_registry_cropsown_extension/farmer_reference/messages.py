"""What the person submitting an intake is told when its Farmer cannot be used.

Every message says what is wrong and what to do. Codes stay in logs; the
submitter sees the sentence. A message that is already a sentence (field
format errors) is shown as it is.
"""
from __future__ import annotations

from collections.abc import Mapping

_CHECK_IDS = "Check the Farmer ID and Fayda ID against the farmer's Farmer Registry record and submit again"
_REGISTER_FIRST = ("If the farmer is not registered yet, register them in the Farmer Registry first; "
                   "this intake can be submitted once that registration is approved")
_TRY_AGAIN = "Nothing was submitted. Try again in a few minutes; if it keeps failing, tell the administrator"

MESSAGES = {
    "FARMER_REFERENCE_FARMER_ID_REQUIRED":
        "Farmer ID: enter the farmer's Farmer Registry ID (FR- followed by 12 digits)",
    "FARMER_REFERENCE_SOURCE_IDENTITY_REQUIRED":
        "Farmer ID: enter the farmer's Farmer Registry ID (FR- followed by 12 digits)",
    "FARMER_REFERENCE_INVALID_FARMER_ID":
        "Farmer ID: enter FR- followed by exactly 12 digits, preserving leading zeroes",
    "FARMER_REFERENCE_INVALID_UID":
        "Fayda FAN: enter exactly 16 digits, or enter the 12-digit FIN instead",
    "FARMER_REFERENCE_NOT_FOUND":
        "No farmer with {ids} is in the Farmer Registry. " + _CHECK_IDS + ". " + _REGISTER_FIRST,
    "FARMER_REFERENCE_SOURCE_NOT_APPROVED":
        "The farmer with {ids} is in the Farmer Registry but not approved yet. "
        "Submit this intake after the farmer's registration is approved",
    "FARMER_REFERENCE_IDENTITY_MISMATCH":
        "The Farmer ID and Fayda ID belong to different farmers in the Farmer Registry ({ids}). " + _CHECK_IDS,
    "FARMER_REFERENCE_FARMER_ID_MISMATCH":
        "The Farmer ID and Fayda ID belong to different farmers in the Farmer Registry ({ids}). " + _CHECK_IDS,
    "FARMER_REFERENCE_SOURCE_ID_MISMATCH":
        "This registry already links the farmer with {ids} to a different Farmer Registry record. "
        "Ask the administrator to check the farmer's reference before submitting",
    "FARMER_REFERENCE_EXISTING_IDENTITY_AMBIGUOUS":
        "This registry already holds more than one farmer matching {ids}. "
        "Ask the administrator to resolve the duplicate before submitting",
    "FARMER_REFERENCE_SUBMISSION_IDENTITY_CHANGED":
        "The Farmer ID or Fayda ID changed after this intake was linked to a farmer. "
        "Restore the original IDs, or start a new intake for the other farmer",
    "FARMER_REFERENCE_PENDING_IDENTITY_CHANGED":
        "The farmer with {ids} is already awaiting approval with a different Fayda ID. "
        "Use the Fayda ID of that pending registration, or wait for its approval",
    "FARMER_REFERENCE_LOCAL_IDENTITY_UPDATE_REQUIRED":
        "The farmer's Fayda ID changed in the Farmer Registry. Wait for the farmer's update to be approved "
        "in this registry, then submit again",
    "FARMER_REFERENCE_DEPENDENCY_REJECTED":
        "Adding the farmer with {ids} to this registry was rejected. "
        "Check the IDs, or ask the approver why, before submitting again",
    "FARMER_REFERENCE_LOOKUP_UNAVAILABLE":
        "The Farmer Registry could not be reached to check the farmer. " + _TRY_AGAIN,
    "FARMER_REFERENCE_LOOKUP_EXPIRED":
        "The Farmer Registry's answer arrived too late to be used. " + _TRY_AGAIN,
    "FARMER_REFERENCE_LOOKUP_CONFIGURATION_REQUIRED":
        "Farmer lookups are not configured in this registry, so the farmer cannot be checked. "
        "Ask the administrator to set the Farmer Registry connection",
    "FARMER_REFERENCE_ADD_ALREADY_RESOLVED":
        "This farmer was already added to this registry by an earlier request. Refresh the page and check the farmer's record",
    "FARMER_REFERENCE_APPROVED_DEPENDENCY_REQUIRED":
        "The farmer must be approved in this registry before this record can be added. Wait for the approval, then try again",
    "FARMER_REFERENCE_APPROVED_LOCAL_REQUIRED":
        "The farmer's registration in this registry is not approved yet. Wait for the approval, then try again",
    "FARMER_REFERENCE_APPROVED_SCOPE_REQUIRED":
        "The farmer's location is needed to choose approvers. Select the farmer's region, zone and woreda, then submit again",
    "FARMER_REFERENCE_AWE_APPROVAL_REQUIRED":
        "This change needs an approval first. Submit it for approval and wait for the decision",
    "FARMER_REFERENCE_AWE_CALLBACK_REQUIRED":
        "The approval service did not report a decision. Tell the administrator that the approval connection is not set up",
    "FARMER_REFERENCE_AWE_POLICY_CONTEXT_REQUIRED":
        "The approval could not be started because the farmer's location is missing. Select the farmer's location and submit again",
    "FARMER_REFERENCE_AWE_REQUEST_NOT_CREATED":
        "The approval request could not be created. Nothing was submitted. Try again in a few minutes; if it keeps failing, tell the administrator",
    "FARMER_REFERENCE_AWE_REQUIRED":
        "Approval is not set up for farmer registrations in this registry. Ask the administrator to set it up",
    "FARMER_REFERENCE_CHANGE_REQUEST_REQUIRED":
        "Farmer details can only be changed through an approved change request. Submit a change request instead of editing the record",
    "FARMER_REFERENCE_DEPENDENCY_PENDING":
        "The farmer is waiting for approval in this registry. This record will be added once the farmer is approved",
    "FARMER_REFERENCE_DEPENDENCY_REQUIRED":
        "This record needs a linked farmer first. Check the Farmer ID and Fayda ID, then submit again",
    "FARMER_REFERENCE_EXTERNAL_IDENTIFIER_CONFIGURATION_REQUIRED":
        "The Farmer ID type is not set up in this registry. Ask the administrator to set it up",
    "FARMER_REFERENCE_FIELD_OUTSIDE_ALLOWLIST":
        "The Farmer Registry sent a detail that this registry does not accept, so the farmer could not be added. Tell the administrator",
    "FARMER_REFERENCE_IAM_DIRECTORY_INVALID":
        "Approvers could not be looked up because the sign-in service gave an unexpected answer. Tell the administrator",
    "FARMER_REFERENCE_IAM_DIRECTORY_LIMIT":
        "Approvers could not be looked up because too many people matched. Tell the administrator",
    "FARMER_REFERENCE_IAM_DIRECTORY_REQUIRED":
        "Approvers cannot be looked up because the sign-in service connection is not set up for this registry. Ask the administrator to set it up",
    "FARMER_REFERENCE_INTAKE_METADATA_REQUIRES_ROOT_IDENTITY":
        "The intake form must start with the Farmer ID and Fayda ID. Fill in the Farmer lookup section first",
    "FARMER_REFERENCE_INVALID_BIRTH_DATE":
        "The farmer's date of birth in the Farmer Registry is not a valid date. Ask the Farmer Registry team to correct it, then submit again",
    "FARMER_REFERENCE_INVALID_GEOGRAPHY":
        "The farmer's location in the Farmer Registry is not recognised. Ask the Farmer Registry team to correct it, then submit again",
    "FARMER_REFERENCE_INVALID_LOOKUP_LIMITS":
        "The Farmer lookup limits are set incorrectly. Ask the administrator to correct the Farmer Registry connection",
    "FARMER_REFERENCE_INVALID_NOTIFICATION":
        "A farmer update from the Farmer Registry could not be read, so it was ignored. Tell the administrator",
    "FARMER_REFERENCE_INVALID_NOTIFICATION_SECTION":
        "A farmer update from the Farmer Registry named a section this registry does not have, so it was ignored. Tell the administrator",
    "FARMER_REFERENCE_INVALID_PROFILE_VALUE":
        "One of the farmer's details in the Farmer Registry is not valid, so the farmer could not be added. Ask the Farmer Registry team to correct it",
    "FARMER_REFERENCE_INVALID_SOURCE_URL":
        "The Farmer Registry address is not valid. Ask the administrator to correct the Farmer Registry connection",
    "FARMER_REFERENCE_LEGACY_INTAKE_SECTION_BLOCKED":
        "This intake form section is no longer used. Start a new intake",
    "FARMER_REFERENCE_LIFECYCLE_NOT_AVAILABLE":
        "Farmer records cannot be changed here. Make the change in the Farmer Registry",
    "FARMER_REFERENCE_LINK_IDENTITY_MISMATCH":
        "The farmer linked to this intake does not match the Farmer ID and Fayda ID entered. Check the IDs and submit again",
    "FARMER_REFERENCE_LINK_MISMATCH":
        "The farmer linked to this intake does not match the Farmer ID and Fayda ID entered. Check the IDs and submit again",
    "FARMER_REFERENCE_LOCAL_IDENTITY_CONFLICT":
        "Another farmer in this registry already uses these IDs. Ask the administrator to resolve the duplicate",
    "FARMER_REFERENCE_MANAGED_PAYLOAD_CHANGED":
        "The farmer's details changed while the request was waiting for approval. Start a new request",
    "FARMER_REFERENCE_MANAGED_PAYLOAD_REQUIRED":
        "The request has no farmer details. Fill in the Farmer lookup section and submit again",
    "FARMER_REFERENCE_MANAGED_REQUEST_REQUIRED":
        "The approval request for this farmer could not be found. Start a new request",
    "FARMER_REFERENCE_NATIVE_REQUEST_NOT_PENDING":
        "This request has already been decided. Refresh the page to see the result",
    "FARMER_REFERENCE_NO_ELIGIBLE_APPROVER":
        "No approver is assigned for the farmer's location. Ask the administrator to give a staff member the approver role for this location",
    "FARMER_REFERENCE_REQUEST_ALREADY_RESOLVED":
        "This request has already been decided. Refresh the page to see the result",
    "FARMER_REFERENCE_SECTION_BINDING_REQUIRED":
        "This section is not set up for farmer lookups. Ask the administrator to check the intake form",
    "FARMER_REFERENCE_SINGLE_DOMAIN_ROOT_REQUIRED":
        "The farmer lookup needs exactly one Crop Sown record on the form. Check the intake form and submit again",
    "FARMER_REFERENCE_SOURCE_ID_REQUIRED":
        "The Farmer Registry did not give an ID for this farmer. Try again later; if it keeps failing, tell the administrator",
    "FARMER_REFERENCE_SOURCE_PARTNER_REQUIRED":
        "The Farmer Registry is not set up as an approved sender. Ask the administrator to set it up",
    "FARMER_REFERENCE_SOURCE_VERSION_CONFLICT":
        "The Farmer Registry sent two different versions of this farmer's details. Nothing was changed. Tell the administrator",
    "FARMER_REFERENCE_STALE_SOURCE_VERSION":
        "The Farmer Registry sent an older version of this farmer's details. Nothing was changed. Try again later",
    "FARMER_REFERENCE_UNSUPPORTED_ACTION":
        "This kind of farmer request is not supported. Tell the administrator",
    "FARMER_REFERENCE_UNSUPPORTED_DATABASE":
        "This registry's database cannot run the farmer lookup. Tell the administrator",
    "FARMER_REFERENCE_UNSUPPORTED_GEOGRAPHIC_POLICY":
        "The approval rule for the farmer's location is not supported. Ask the administrator to check the approval setup",
    "FARMER_REFERENCE_VERIFIED_LOOKUP_REQUIRED":
        "The farmer must be found in the Farmer Registry first. Check the Farmer ID and Fayda ID, then submit again",
    "FARMER_REFERENCE_VERIFIED_SOURCE_REQUEST_REQUIRED":
        "The farmer must be found in the Farmer Registry first. Check the Farmer ID and Fayda ID, then submit again",
    "FARMER_REFERENCE_WORKFLOW_DELIVERY_FAILED":
        "The approval could not be delivered. Nothing was submitted. Try again in a few minutes; if it keeps failing, tell the administrator",
    "FARMER_REFERENCE_WORKFLOW_IDENTITY_UNAVAILABLE":
        "Your sign-in could not be used to start the approval. Sign in again and try again",
}

# The lookup could not reach or trust the Farmer Registry: nothing is wrong
# with what was entered.
UNAVAILABLE = {
    "FARMER_REFERENCE_LOOKUP_UNAVAILABLE", "FARMER_REFERENCE_LOOKUP_EXPIRED",
    "FARMER_REFERENCE_RESPONSE_REJECTED", "FARMER_REFERENCE_RESPONSE_SIGNATURE_INVALID",
    "FARMER_REFERENCE_RESPONSE_TOO_LARGE", "FARMER_REFERENCE_SOURCE_CONTRACT_INCOMPLETE",
    "FARMER_REFERENCE_INVALID_SOURCE_TIMESTAMP", "FARMER_REFERENCE_INVALID_PROFILE",
    "FARMER_REFERENCE_INVALID_VERIFIED_SNAPSHOT", "FARMER_REFERENCE_UNSAFE_SIGNATURE_ALGORITHM",
}


def _ids(identity: Mapping | None) -> str:
    identity = identity or {}
    parts = []
    if identity.get("farmer_id"):
        parts.append(f"Farmer ID {identity['farmer_id']}")
    if identity.get("fayda_fin"):
        parts.append(f"FIN {identity['fayda_fin']}")
    elif identity.get("fayda_fan_id"):
        parts.append(f"FAN {identity['fayda_fan_id']}")
    return " and ".join(parts) or "these IDs"


def explain(code: str, identity: Mapping | None = None, *, held=False) -> str:
    if not code.startswith("FARMER_REFERENCE_"):
        return code
    if code in MESSAGES:
        text = MESSAGES[code].format(ids=_ids(identity))
    elif code in UNAVAILABLE:
        text = "The Farmer Registry's answer about the farmer could not be verified. " + _TRY_AGAIN
    else:
        text = ("The farmer could not be linked to this intake. Nothing was submitted. "
                f"Tell the administrator the reference {code}")
    if held:
        # Ingestion has already saved the intake; the staff refusal wording
        # must not say otherwise in the durable worker diagnostic.
        text = text.replace("Nothing was submitted.", "This intake is saved and held.")
    return text


# What the intake list shows (register ingest error text) and the intake's
# Farmer reference status while an approved intake waits for the Farmer ADD.
WAITING_FOR_FARMER_APPROVAL = "Approved, waiting for Farmer approval"
FARMER_APPROVAL_REJECTED = (
    "Approved, but the Farmer registration was rejected, so this record was not added. "
    "Check the Farmer ID and Fayda ID, or ask the approver why, and submit a new intake"
)
FARMER_REFERENCE_MISSING = (
    "Approved, but no Farmer registration is linked to this intake, so this record was not added. "
    "Ask the administrator to check the intake"
)
FARMER_REFERENCE_LINKED = "Farmer reference linked"
# Before the intake is approved: the Farmer is itself awaiting approval.
FARMER_REFERENCE_AWAITING = "Farmer reference awaiting approval; the record will be added after that approval"
FARMER_LOOKUP_PENDING = "Waiting for the Farmer lookup; the record will be added once the farmer is found and approved"

# Values written before readable text replaced the codes; still recognised so
# intakes already held keep being released.
LEGACY_WAITING = "FARMER_REFERENCE_DEPENDENCY_PENDING"


def is_waiting_text(value) -> bool:
    return value in (WAITING_FOR_FARMER_APPROVAL, FARMER_LOOKUP_PENDING, LEGACY_WAITING)


def held_text(reference, pending_lookup) -> str:
    """Text for an approved intake whose record cannot be added yet."""
    if reference is None:
        return WAITING_FOR_FARMER_APPROVAL if pending_lookup is not None and pending_lookup.state == "PENDING" \
            else FARMER_REFERENCE_MISSING
    return FARMER_APPROVAL_REJECTED if reference.state == "REJECTED" else WAITING_FOR_FARMER_APPROVAL
