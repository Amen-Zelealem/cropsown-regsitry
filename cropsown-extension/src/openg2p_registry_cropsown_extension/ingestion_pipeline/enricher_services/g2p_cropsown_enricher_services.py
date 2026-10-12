import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict

import httpx
from openg2p_registry_core.interfaces import G2PPayloadEnricherInterface
from sqlalchemy.orm import Session

_logger = logging.getLogger('g2p-payload-enricher-service')

# --- Farmer Registry DCI federated-fetch config (env-driven) ---------------
# Full URL of the Farmer Registry partner-api DCI sync-search endpoint
# (e.g. http://<farmer-registry-partner-api-host>:8000/dci/registry/sync/search).
# No baked-in default — the deployment MUST set CROPSOWN_FARMER_DCI_URL; when it
# is unset, enrichment is skipped (fails open, see enrich()).
FARMER_REGISTRY_DCI_URL = os.environ.get("CROPSOWN_FARMER_DCI_URL", "").strip()
# Our onboarded Partner Management identity (sender_id + signing kid).
FARMER_DCI_SENDER_ID = os.environ.get("CROPSOWN_DCI_SENDER_ID", "cropsown")
# Receiver id is env-driven (not hardcoded) and shared with the web lookup.
FARMER_DCI_RECEIVER_ID = os.environ.get("CROPSOWN_DCI_RECEIVER_ID", "farmer-registry")
FARMER_DCI_TIMEOUT = float(os.environ.get("CROPSOWN_DCI_TIMEOUT", "15"))
FARMER_DCI_SUBJECT_ID_TYPE = os.environ.get("CROPSOWN_DCI_SUBJECT_ID_TYPE", "fayda_fan_id")
# Optional: a pre-minted compact consent JWS to embed. If empty, we mint and
# sign one on the fly from the CM signing config below (auto-approved partner
# consent — no human/OTP; CM /validate permits on signature + policy).
FARMER_DCI_CONSENT_JWS = os.environ.get("CROPSOWN_DCI_CONSENT_JWS", "")

# --- Consent Manager partner-signed consent config -------------------------
# The DCI `consent_jws` is a partner-signed compact JWS. We sign it with our
# PM-registered private key (kid); CM /validate verifies the signature against
# the public key PM serves, checks policy, and permits — minting the artefact.
CM_SIGNING_KEY_PEM = os.environ.get("CROPSOWN_CM_SIGNING_KEY_PEM", "")
# Support a mounted key file too (same as the web lookup), so a deployment that
# only sets CROPSOWN_CM_SIGNING_KEY_PATH still signs instead of sending the
# "cropsown-dci" placeholder.
CM_SIGNING_KEY_PATH = os.environ.get("CROPSOWN_CM_SIGNING_KEY_PATH", "").strip()
if not CM_SIGNING_KEY_PEM and CM_SIGNING_KEY_PATH:
    try:
        with open(CM_SIGNING_KEY_PATH, encoding="utf-8") as _key_file:
            CM_SIGNING_KEY_PEM = _key_file.read()
    except OSError as _key_exc:
        _logger.warning("CropSown enricher: cannot read signing key %s: %s", CM_SIGNING_KEY_PATH, _key_exc)
CM_SIGNING_KID = os.environ.get("CROPSOWN_CM_SIGNING_KID", "")
CM_PARTNER_AUD = os.environ.get("CROPSOWN_CM_PARTNER_AUD", "")
CM_CONTROLLER_ID = os.environ.get("CROPSOWN_CM_CONTROLLER_ID", "")
# Must match the response field read downstream (farmer_personal_details) so
# consent scope filtering does not strip it.
CM_DATA_SCOPES = [s for s in os.environ.get("CROPSOWN_CM_SCOPES", "farmer_personal_details").split(",") if s]
CM_SIGNING_ALG = os.environ.get("CROPSOWN_CM_ALG", "EdDSA")
CM_CONSENT_PURPOSE = os.environ.get("CROPSOWN_CM_PURPOSE", "share_farm_profile")
CM_CONSENT_VALIDITY_DAYS = int(os.environ.get("CROPSOWN_CM_VALIDITY_DAYS", "1"))


def _canonical_bytes(obj: Dict) -> bytes:
    """Canonical JSON — MUST match the Consent Manager's canonicalisation
    (stable key order, compact separators) so the signature round-trips."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")


def _mint_consent_jws(farmer_id: str) -> str:
    """Auto-approved consent for the DCI fetch: a partner-signed consent object.

    No human/OTP step — the partner self-asserts consent by signing the object;
    CM /validate permits it on signature + policy. Returns "" when no signing
    key is configured (consent-enforcement-off deployments)."""
    if not (CM_SIGNING_KEY_PEM and CM_SIGNING_KID):
        return ""
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    from jwt.api_jws import PyJWS

    now = datetime.now(timezone.utc)
    claims = {
        "@context": "https://openg2p.org/contexts/consent_object.jsonld",
        "@type": "ConsentObject",
        "jti": uuid.uuid4().hex,
        "subject_id": {"type": FARMER_DCI_SUBJECT_ID_TYPE, "value": farmer_id},
        "data_controller": CM_CONTROLLER_ID,
        "aud": CM_PARTNER_AUD,
        "purpose": {"code": CM_CONSENT_PURPOSE, "text": "crop sown enrichment"},
        "data_scopes": CM_DATA_SCOPES,
        "fetch_type": "oneshot",
        "validity": {
            "valid_from": now.isoformat(),
            "valid_until": (now + timedelta(days=CM_CONSENT_VALIDITY_DAYS)).isoformat(),
        },
        "issued_at": now.isoformat(),
    }
    priv = load_pem_private_key(CM_SIGNING_KEY_PEM.encode("utf-8"), password=None)
    jws = PyJWS().encode(_canonical_bytes(claims), priv, algorithm=CM_SIGNING_ALG,
                         headers={"kid": CM_SIGNING_KID})
    _logger.info("Minted partner-signed consent JWS for farmer=%s (jti=%s, scopes=%s)",
                 farmer_id, claims["jti"], CM_DATA_SCOPES)
    return jws


def _sign_request(header: Dict, message: Dict) -> str:
    """Detached JWS over the canonical ``{header, message}`` — the request-level
    signature the Farmer Registry verifies when partner-signature validation is
    enabled (the consent JWS inside the request is a separate, consent-only
    signature and does not cover the envelope). Signed with the same partner key
    as the consent. Falls back to a non-signature marker only when no signing key
    is configured (signature-validation-off deployments)."""
    if not (CM_SIGNING_KEY_PEM and CM_SIGNING_KID):
        return "cropsown-dci"
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    from jwt.api_jws import PyJWS

    priv = load_pem_private_key(CM_SIGNING_KEY_PEM.encode("utf-8"), password=None)
    token = PyJWS().encode(
        _canonical_bytes({"header": header, "message": message}),
        priv, algorithm=CM_SIGNING_ALG, headers={"kid": CM_SIGNING_KID},
    )
    # Detach by dropping the payload segment (registry verifies over the
    # base64url payload it re-serialises), matching farmer_registry_enrichment.
    protected, _, signature = token.split(".")
    return f"{protected}..{signature}"


def _build_dci_search_envelope(farmer_id: str | None, fayda: str | None = None) -> Dict:
    """Build a DCI sync-search envelope. Uses an expression query with an $eq on
    functional_record_id (Farmer ID) AND/OR foundational_id (Fayda) — the same
    exact-match the web lookup uses, so when both ids are supplied a record is
    returned only when both belong to the same farmer (no ambiguous match)."""
    now = datetime.now(timezone.utc).isoformat()
    query: Dict = {}
    fid = (farmer_id or "").strip()
    fyd = (fayda or "").strip()
    if fid:
        query["functional_record_id"] = {"$eq": fid}
    if fyd:
        query["foundational_id"] = {"$eq": fyd}
    subject = fyd or fid
    search_criteria: Dict = {
        "version": "1.0.0",
        "reg_type": "Farmer",
        "reg_record_type": "Farmer",
        "query_type": "expression",
        "query": {"type": "expression", "value": {"expression": {"query": query}}},
    }
    consent_jws = FARMER_DCI_CONSENT_JWS or _mint_consent_jws(subject)
    if consent_jws:
        # PEP reads the partner-signed consent from here and forwards it to CM.
        search_criteria["authorize"] = {"consent_jws": consent_jws}
    header = {
        "version": "1.0.0",
        "message_id": uuid.uuid4().hex,
        "message_ts": now,
        "action": "search",
        "sender_id": FARMER_DCI_SENDER_ID,
        "receiver_id": FARMER_DCI_RECEIVER_ID,
        "total_count": 1,
        "is_msg_encrypted": False,
    }
    message = {
        "transaction_id": uuid.uuid4().hex,
        "search_request": [
            {
                "reference_id": "cropsown-enrich-1",
                "timestamp": now,
                "locale": "eng",
                "search_criteria": search_criteria,
            }
        ],
    }
    # Signed last — any change to header/message after this invalidates it.
    return {"signature": _sign_request(header, message), "header": header, "message": message}


def _fetch_farmer_from_registry(farmer_id: str | None, fayda: str | None = None) -> Dict:
    """The one Farmer reg_record matching the given id(s), or {} when there is no
    single unambiguous match.

    SYNC on purpose — the enricher runs inside a sync celery task with a sync
    SQLAlchemy session, so an async client cannot be awaited here. Requires the
    header not rejected, the response item 'succ', and EXACTLY one record — an
    ambiguous (0 or >1) result is ignored rather than guessed."""
    envelope = _build_dci_search_envelope(farmer_id, fayda)
    with httpx.Client(timeout=FARMER_DCI_TIMEOUT) as client:
        resp = client.post(FARMER_REGISTRY_DCI_URL, json=envelope)
        resp.raise_for_status()
        body = resp.json()
    if not isinstance(body, dict):
        return {}
    header = body.get("header") if isinstance(body.get("header"), dict) else {}
    if header.get("status") == "rjct":
        raise ValueError(f"Farmer Registry DCI rejected the search: {header.get('status_reason_message')}")
    message = body.get("message") if isinstance(body.get("message"), dict) else {}
    search_response = message.get("search_response")
    search_response = search_response if isinstance(search_response, list) else []
    item = search_response[0] if search_response and isinstance(search_response[0], dict) else {}
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    records = data.get("reg_records")
    records = records if isinstance(records, list) else []
    if item.get("status") != "succ" or len(records) != 1:
        _logger.info(
            "Farmer Registry DCI returned %s record(s) (status=%s) for id=%s fayda=%s — no unambiguous match",
            len(records), item.get("status"), farmer_id, fayda,
        )
        return {}
    return records[0] if isinstance(records[0], dict) else {}


def _map_farmer_to_cropsown(dci_record: Dict) -> Dict:
    """Map a DCI Farmer record (farmer_personal_details scope) onto the crop
    sown record's farmer fields."""
    scope = dci_record.get("farmer_personal_details") or dci_record
    demo = (scope.get("demographic_info") or {})
    name = (demo.get("name") or {})
    ident = ((scope.get("member_identifier") or [{}])[0]) or (demo.get("identifier") or [{}])[0]
    full_name = " ".join(
        p for p in [name.get("given_name"), name.get("second_name"), name.get("surname")] if p
    ).strip()
    out: Dict = {}
    if full_name:
        out["farmer_name"] = full_name
    if scope.get("farmer_id"):
        out["farmer_id"] = scope.get("farmer_id")
    if scope.get("farmer_uuid"):
        out["farmer_uuid"] = scope.get("farmer_uuid")
    if ident.get("identifier_value"):
        out["fayda_fan_id"] = ident.get("identifier_value")
    if demo.get("sex"):
        out["gender"] = demo.get("sex")
    if demo.get("birth_date"):
        out["birth_date"] = demo.get("birth_date")
    return out

# DCI Payload Enrichers
class G2PDciCropSownCreateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        """Federated enrichment: intake carries only a Farmer ID / Fayda ID;
        resolve the full Farmer record from the Farmer Registry (DCI Partner
        API) and merge it into the crop sown payload before transformation.
        """
        _logger.info("Processing G2PDciCropSownCreateEnricherService")
        if not FARMER_REGISTRY_DCI_URL:
            _logger.info("CROPSOWN_FARMER_DCI_URL not set — skipping Farmer Registry enrichment")
            return data

        farmer_id = data.get("farmer_id")
        fayda = data.get("fayda_fan_id")
        if not farmer_id and not fayda:
            _logger.info("No farmer_id/fayda_fan_id in payload — nothing to enrich")
            return data

        _logger.info("Enriching crop sown record via Farmer Registry for farmer_id=%s fayda=%s", farmer_id, fayda)
        try:
            dci_record = _fetch_farmer_from_registry(
                str(farmer_id).strip() if farmer_id else None,
                str(fayda).strip() if fayda else None,
            )
        except Exception as exc:  # fail-closed: don't let a bad fetch corrupt ingest
            _logger.error("Farmer Registry enrichment failed for farmer_id=%s fayda=%s: %s", farmer_id, fayda, exc)
            raise

        farmer_fields = _map_farmer_to_cropsown(dci_record)
        if not farmer_fields:
            raise ValueError(f"Farmer '{farmer_id}' not found in Farmer Registry")

        # Merge resolved farmer data into the crop sown payload (do not clobber
        # any value the intake already provided).
        for key, value in farmer_fields.items():
            if not data.get(key):
                data[key] = value
        _logger.info("Enriched with farmer fields: %s", list(farmer_fields.keys()))
        return data

class G2PDciCropSownUpdateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PDciCropSownUpdateEnricherService")
        return data

class G2PDciCropSownDeleteEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PDciCropSownDeleteEnricherService")
        return data


class G2PPassThroughEnricherService(G2PPayloadEnricherInterface):
    """Identity enricher: returns the raw payload unchanged.

    Used by connectors (e.g. ODK) whose payload already arrives in the
    template's expected ``expanded`` shape, so no per-field enrichment is
    needed before the Jinja transform runs. Farmer identity enrichment for
    those flows is done later, at finalize, by the register domain service /
    two-CR hooks — not here."""

    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PPassThroughEnricherService (identity pass-through)")
        return data


# SPDCI Payload Enrichers
class G2PSpdciCropSownCreateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PSpdciCropSownCreateEnricherService")
        return data

class G2PSpdciCropSownUpdateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PSpdciCropSownUpdateEnricherService")
        return data

class G2PSpdciCropSownDeleteEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PSpdciCropSownDeleteEnricherService")
        return data

# UNDP Payload Enrichers
class G2PUndpCropSownCreateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PUndpCropSownCreateEnricherService")
        return data

class G2PUndpCropSownUpdateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PUndpCropSownUpdateEnricherService")
        return data

class G2PUndpCropSownDeleteEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PUndpCropSownDeleteEnricherService")
        return data
