"""Farmer Registry enrichment for the Farmer Identity of the Crop Sown intake form.

The Farmer Registry is the system of record for people, so once the operator has
entered a Farmer ID (and Fayda FAN ID) the registry's own copy of that farmer's
identity replaces whatever was typed. Mirrors the livestock-registry's
``farmer_registry_enrichment`` module, with two Crop-Sown-specific differences:

1. The lookup is a DCI ``expression`` search that matches BOTH ``functional_record_id``
   (the Farmer ID) AND ``foundational_id`` (the Fayda FAN / UIN) — so a record is
   returned only when the two belong to the SAME farmer ("both required"). A plain
   ``idtype-value`` search would only full-text match the Fayda and could never
   confirm the Farmer ID, so the stricter expression query is used.
2. The caller is ``G2PRegisterDomainServiceCropSown.validate_domain_attributes``
   (run on intake submit / finalize) rather than a ``pre_finalize`` hook, because
   that is the finalize-time domain-service hook this registry's core exposes.

Every call carries two signatures made with this registry's Partner-Management key:
  * ``signature`` — a detached JWS over the canonical ``{header, message}`` JSON.
  * ``search_criteria.authorize.consent_jws`` — a compact JWS over a fresh consent
    object, forwarded verbatim to the Consent Manager (new ``jti``/``issued_at`` per call).

Fails open: when enrichment is off or misconfigured, the registry is unreachable,
rejects the call, or does not find exactly one farmer, this logs a warning and
returns ``None`` — the operator's own entries stand and intake is never blocked.

Config (env, reused from the existing cropsown ingestion enricher):
  CROPSOWN_FARMER_ENRICHMENT_ENABLED   enable flag (default false)
  CROPSOWN_FARMER_DCI_URL              DCI sync-search URL (farmer-registry-partner-api)
  CROPSOWN_DCI_SENDER_ID               partner sender id (default "cropsown")
  CROPSOWN_CM_SIGNING_KEY_PEM / _PATH  partner private key (PEM text or file path)
  CROPSOWN_CM_SIGNING_KID              key id
  CROPSOWN_CM_ALG                      signing alg (default EdDSA)
  CROPSOWN_CM_PARTNER_AUD              consent audience (e.g. CROPSOWN_DCI)
  CROPSOWN_CM_CONTROLLER_ID            data controller (e.g. ethiopia-moa)
  CROPSOWN_CM_SCOPES                   comma list (default farmer_profile.basic)
  CROPSOWN_CM_PURPOSE                  consent purpose code (default share_farm_profile)
  CROPSOWN_FARMER_DCI_TIMEOUT          http timeout seconds (default 10)
"""

import logging
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import httpx
import jwt
import orjson

from .domain_validation_utils import is_blank, parse_date

_logger = logging.getLogger("g2p-cropsown-farmer-enrichment")

# DCI demographic ``sex`` -> this register's GENDER values. Anything else is left unset.
_SEX_TO_GENDER = {"male": "MALE", "female": "FEMALE", "other": "OTHER"}


def _setting(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _config() -> dict | None:
    """Enrichment settings from CROPSOWN_* env. None (after a warning) when
    enrichment is off or a required setting is missing."""
    if _setting("CROPSOWN_FARMER_ENRICHMENT_ENABLED", "false").lower() not in {"true", "1", "yes"}:
        return None

    signing_key = _setting("CROPSOWN_CM_SIGNING_KEY_PEM")
    key_path = _setting("CROPSOWN_CM_SIGNING_KEY_PATH")
    if not signing_key and key_path:
        try:
            with open(key_path, encoding="utf-8") as key_file:
                signing_key = key_file.read()
        except OSError as exc:
            _logger.warning("CropSown farmer enrichment: cannot read signing key %s: %s", key_path, exc)
            return None

    # Parse the timeout defensively: a bad value like "10s" would otherwise raise
    # ValueError out of _config and escape into submit. Skip enrichment instead.
    raw_timeout = _setting("CROPSOWN_FARMER_DCI_TIMEOUT", "10") or "10"
    try:
        timeout = float(raw_timeout)
    except (TypeError, ValueError):
        timeout = 0.0
    if not (timeout > 0 and timeout != float("inf")):
        _logger.warning("CropSown farmer enrichment: invalid CROPSOWN_FARMER_DCI_TIMEOUT %r — skipping", raw_timeout)
        return None

    cfg = {
        "search_url": _setting("CROPSOWN_FARMER_DCI_URL"),
        "sender_id": _setting("CROPSOWN_DCI_SENDER_ID", "cropsown"),
        "receiver_id": _setting("CROPSOWN_DCI_RECEIVER_ID", "farmer-registry"),
        "signing_key": signing_key,
        "kid": _setting("CROPSOWN_CM_SIGNING_KID"),
        "algorithm": _setting("CROPSOWN_CM_ALG", "EdDSA"),
        "consent_audience": _setting("CROPSOWN_CM_PARTNER_AUD"),
        "consent_data_controller": _setting("CROPSOWN_CM_CONTROLLER_ID", "farmer-registry"),
        # The response field read below is farmer_personal_details, so the consent
        # scope requested must be the same — otherwise scope filtering strips it.
        "consent_scopes": [s.strip() for s in _setting("CROPSOWN_CM_SCOPES", "farmer_personal_details").split(",") if s.strip()],
        "consent_purpose": _setting("CROPSOWN_CM_PURPOSE", "share_farm_profile"),
        "timeout": timeout,
    }
    missing = [
        name
        for name in ("search_url", "sender_id", "signing_key", "kid", "consent_audience")
        if not cfg[name]
    ]
    if missing:
        _logger.warning(
            "CropSown farmer enrichment is enabled but not configured (missing %s) — skipping",
            ", ".join(missing),
        )
        return None
    return cfg


def _sign(payload: bytes, cfg: dict, *, detached: bool) -> str:
    token = jwt.api_jws.PyJWS().encode(
        payload,
        cfg["signing_key"],
        algorithm=cfg["algorithm"],
        headers={"kid": cfg["kid"]},
    )
    if not detached:
        return token
    protected, _, signature = token.split(".")
    return f"{protected}..{signature}"


def _consent_jws(subject_value: str, now: datetime, cfg: dict) -> str:
    issued_at = now.isoformat()
    consent = {
        "@context": "https://openg2p.org/contexts/consent_object.jsonld",
        "@type": "ConsentObject",
        "jti": uuid.uuid4().hex,
        "aud": cfg["consent_audience"],
        "data_controller": cfg["consent_data_controller"],
        "data_scopes": cfg["consent_scopes"],
        "fetch_type": "oneshot",
        "issued_at": issued_at,
        "purpose": {"code": cfg["consent_purpose"], "text": "Crop Sown registry intake: farmer enrichment"},
        "subject_id": {"type": "fayda_fan_id", "value": subject_value},
        "validity": {"valid_from": issued_at, "valid_until": (now + timedelta(hours=1)).isoformat()},
    }
    return _sign(orjson.dumps(consent), cfg, detached=False)


def build_search_request(farmer_id: str | None, fayda: str | None, cfg: dict) -> dict:
    """The signed DCI expression-search envelope matching BOTH farmer_id and fayda.

    Whichever of the two is provided becomes an ``$eq`` clause; SQLAlchemy ANDs
    them, so a record returns only when both belong to the same farmer."""
    now = datetime.now(timezone.utc)
    timestamp = now.isoformat()
    query: dict = {}
    if not is_blank(farmer_id):
        query["functional_record_id"] = {"$eq": str(farmer_id).strip()}
    if not is_blank(fayda):
        query["foundational_id"] = {"$eq": str(fayda).strip()}
    subject = (fayda if not is_blank(fayda) else farmer_id) or ""

    header = {
        "version": "1.0.0",
        "message_id": uuid.uuid4().hex,
        "message_ts": timestamp,
        "action": "search",
        "sender_id": cfg["sender_id"],
        "receiver_id": cfg["receiver_id"],
        "total_count": 1,
        "is_msg_encrypted": False,
    }
    message = {
        "transaction_id": uuid.uuid4().hex[:12],
        "search_request": [
            {
                "reference_id": uuid.uuid4().hex,
                "timestamp": timestamp,
                "locale": "eng",
                "search_criteria": {
                    "version": "1.0.0",
                    "reg_type": "Farmer",
                    "reg_record_type": "Farmer",
                    "query_type": "expression",
                    "query": {"type": "expression", "value": {"expression": {"query": query}}},
                    "authorize": {"consent_jws": _consent_jws(str(subject).strip(), now, cfg)},
                },
            }
        ],
    }
    canonical = orjson.dumps({"header": header, "message": message}, option=orjson.OPT_SORT_KEYS)
    return {"signature": _sign(canonical, cfg, detached=True), "header": header, "message": message}


async def fetch_farmer_record(farmer_id: str | None, fayda: str | None = None) -> dict | None:
    """The Farmer Registry's ``farmer_personal_details`` for this farmer, matched
    on BOTH Farmer ID and Fayda FAN ID (both-required). None when enrichment is
    off/misconfigured, the call fails/rejected, or not exactly one match."""
    if is_blank(farmer_id) and is_blank(fayda):
        return None

    # Config parse, the HTTP call, AND response-shape parsing are all inside the
    # fail-open guard: a bad setting, a non-dict envelope (e.g. an upstream "[]"),
    # or a missing nested field must never escape into submit — they log and skip.
    try:
        cfg = _config()
        if cfg is None:
            return None
        request_body = build_search_request(farmer_id, fayda, cfg)
        async with httpx.AsyncClient(timeout=cfg["timeout"]) as client:
            response = await client.post(cfg["search_url"], json=request_body)
        response.raise_for_status()
        envelope = response.json()

        if not isinstance(envelope, dict):
            _logger.warning("CropSown farmer lookup (id=%s fayda=%s): unexpected response shape %s", farmer_id, fayda, type(envelope).__name__)
            return None
        header = envelope.get("header")
        header = header if isinstance(header, dict) else {}
        message = envelope.get("message")
        message = message if isinstance(message, dict) else {}
        items = message.get("search_response")
        items = items if isinstance(items, list) else []
        item = items[0] if items and isinstance(items[0], dict) else {}
        data = item.get("data")
        data = data if isinstance(data, dict) else {}
        records = data.get("reg_records")
        records = records if isinstance(records, list) else []
        if header.get("status") == "rjct" or item.get("status") != "succ" or len(records) != 1:
            _logger.warning(
                "CropSown farmer lookup (id=%s fayda=%s) returned %s record(s) (status=%s) — not enriching",
                farmer_id, fayda, len(records), item.get("status") or header.get("status"),
            )
            return None

        record0 = records[0] if isinstance(records[0], dict) else {}
        personal = record0.get("farmer_personal_details")
        if not isinstance(personal, dict) or not personal:
            _logger.warning("CropSown farmer lookup (id=%s fayda=%s): no farmer_personal_details — check consent scopes", farmer_id, fayda)
            return None
        return personal
    except Exception as exc:
        _logger.warning("CropSown farmer lookup (id=%s fayda=%s) failed: %r", farmer_id, fayda, exc)
        return None


def _text(value) -> str | None:
    return None if is_blank(value) else str(value).strip()


def to_farmer_fields(personal: dict) -> dict:
    """The plain Farmer fields carried by a DCI ``farmer_personal_details`` record:
    name parts (together), gender, date_of_birth, mobile_number, fayda_fan_id."""
    fields: dict = {}
    if not isinstance(personal, dict):
        return fields
    pd = personal
    demographic = pd.get("demographic_info")
    demographic = demographic if isinstance(demographic, dict) else {}
    name = demographic.get("name")
    name = name if isinstance(name, dict) else {}

    if not is_blank(name.get("given_name")) or not is_blank(name.get("surname")):
        fields["first_name"] = _text(name.get("given_name"))
        fields["middle_name"] = _text(name.get("second_name"))
        fields["last_name"] = _text(name.get("surname"))

    gender = _SEX_TO_GENDER.get(str(demographic.get("sex") or "").strip().lower())
    if gender:
        fields["gender"] = gender

    birth_date = parse_date(demographic.get("birth_date"))
    if birth_date and birth_date <= date.today():
        fields["date_of_birth"] = birth_date

    phones = demographic.get("phone_number") or []
    if isinstance(phones, str):
        phones = [phones]
    phone = next((_text(p) for p in phones if not is_blank(p)), None)
    if phone:
        fields["mobile_number"] = phone

    ident = pd.get("member_identifier")
    ident = ident if isinstance(ident, list) else []
    first_ident = ident[0] if ident and isinstance(ident[0], dict) else {}
    fayda = first_ident.get("identifier_value")
    if not is_blank(fayda):
        fields["fayda_fan_id"] = _text(fayda)

    return fields


def compose_farmer_name(first: str | None, middle: str | None, last: str | None) -> str:
    return " ".join(p for p in (first, middle, last) if not is_blank(p)).strip()
