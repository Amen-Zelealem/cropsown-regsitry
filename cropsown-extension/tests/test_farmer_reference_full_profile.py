"""Every Farmer-tab field and the photo through the signed lookup and onboarding.

Synthetic keys and an in-memory session stand-in; no registry database, HTTP
or document store.
"""

import asyncio
import base64
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import importlib
import os
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

PACKAGE = os.environ.get("REGISTRY_EXTENSION_MODULE", "openg2p_registry_cropsown_extension")
lookup = importlib.import_module(PACKAGE + ".farmer_reference.lookup")
onboarding = importlib.import_module(PACKAGE + ".farmer_reference.onboarding")
profile = importlib.import_module(PACKAGE + ".farmer_reference.profile")
Error = profile.FarmerReferenceError

FAN = "0012345678901234"
FARMER = "FR-000000000001"
NOW = datetime.now(UTC)
JPEG = b"\xff\xd8\xff\xe0" + b"synthetic-photo" * 20


def photo_value(data=JPEG, **changes):
    value = {"content_type": "image/jpeg", "sha256": sha256(data).hexdigest(),
             "data": base64.b64encode(data).decode("ascii")}
    value.update(changes)
    return value


@pytest.fixture(scope="module")
def client():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
    public = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
    cfg = lookup.LookupConfig(
        url="https://synthetic-source.invalid/search", sender_id="synthetic-receiver",
        source_id="synthetic-source", signing_key=private, signing_kid="synthetic-caller",
        source_public_key=public, source_kid="synthetic-source-key", consent_audience="synthetic-consent",
        consent_controller="synthetic-controller", consent_purpose="synthetic-purpose",
        consent_scopes=("farmer_reference",))
    contract = lookup.RecordContract(
        source_id="farmer_reference.source_record_id", farmer_id="farmer_reference.farmer_id",
        uid="farmer_reference.fan", fin="farmer_reference.fin", approved_at="farmer_reference.approved_at",
        status="farmer_reference.record_status", photo="farmer_reference.photo",
        profile_paths={name: "farmer_reference." + name for name in (
            "first_name", "marital_status", "education_level", "disabled", "estimated_age", "is_psnp_user",
            "latitude", "phones", "email", "rid")})
    return lookup.FarmerLookup(cfg, contract)


def signed(client, request, **block):
    reference = {"source_record_id": "synthetic-person", "farmer_id": FARMER, "fan": FAN, "fin": None,
                 "record_status": "ACTIVE", "approved_at": (NOW - timedelta(seconds=10)).isoformat(),
                 "first_name": "Abebe", "marital_status": "MARRIED", "education_level": "BASIC",
                 "disabled": False, "estimated_age": 46, "is_psnp_user": True, "latitude": 9.1,
                 "email": "abebe@example.org", "rid": "1" * 29,
                 "phones": [{"phone_type": "PRIMARY", "phone_number": "911111111", "country_code": "+251",
                             "is_primary": True, "phone_e164": "+251911111111"}],
                 "photo": photo_value()}
    reference.update(block)
    body = {
        "header": {"version": "1.0.0", "message_ts": NOW.isoformat(), "status": "succ",
                   "sender_id": client.config.source_id, "receiver_id": client.config.sender_id,
                   "action": "search", "message_id": request["header"]["message_id"],
                   "meta": {"signature_validation": "enabled", "consent_enforcement": "enabled"}},
        "message": {"transaction_id": request["message"]["transaction_id"], "search_response": [{
            "status": "succ", "reference_id": request["message"]["search_request"][0]["reference_id"],
            "data": {"reg_records": [{"farmer_reference": reference}]}}]},
    }
    body["signature"] = lookup.detached_sign(lookup.canonical(body), client.config.signing_key,
                                             client.config.source_algorithm, client.config.source_kid)
    return body


def verify(client, **block):
    request = client.build_request(FARMER, FAN, now=NOW)
    return client.verify_response(signed(client, request, **block), request, FARMER, FAN, now=NOW)


def test_signed_lookup_carries_the_farmer_tab_and_the_photo(client):
    result = verify(client)
    assert result.profile["marital_status"] == "MARRIED"
    assert result.profile["disabled"] is False and result.profile["is_psnp_user"] is True
    assert result.profile["estimated_age"] == 46 and result.profile["latitude"] == 9.1
    assert result.profile["phones"][0]["phone_e164"] == "+251911111111"
    assert result.profile["photo_sha256"] == sha256(JPEG).hexdigest()
    assert "photo" not in result.profile and "record_image_document_id" not in result.profile
    assert result.photo.data == JPEG and result.photo.content_type == "image/jpeg"


def test_explicit_no_photo_and_unshared_photo_are_distinct(client):
    cleared = verify(client, photo=None)
    assert cleared.profile["photo_sha256"] is None and cleared.photo is None
    unshared = lookup.FarmerLookup(client.config, replace(client.contract, photo=None))
    request = unshared.build_request(FARMER, FAN, now=NOW)
    result = unshared.verify_response(signed(unshared, request), request, FARMER, FAN, now=NOW)
    assert "photo_sha256" not in result.profile and result.photo is None


@pytest.mark.parametrize("bad", [
    photo_value(sha256="0" * 64),
    photo_value(content_type="image/gif"),
    photo_value(content_type="image/png"),
    photo_value(data=b"not an image"),
    {**photo_value(), "data": "not base64!"},
    {**photo_value(), "url": "https://elsewhere.invalid/photo.jpg"},
    "https://elsewhere.invalid/photo.jpg",
])
def test_photo_must_match_its_hash_and_type(client, bad):
    with pytest.raises(Error, match="INVALID_PHOTO"):
        verify(client, photo=bad)


def test_oversized_photo_is_refused():
    big = b"\xff\xd8\xff" + b"0" * lookup.MAX_PHOTO_BYTES
    with pytest.raises(Error, match="INVALID_PHOTO"):
        lookup.verified_photo(photo_value(data=big))


class Session:
    def __init__(self, farmer=None):
        self.farmer = farmer

    async def get(self, model, key, **kwargs):
        return self.farmer


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def service(stored):
    async def store(session, photo):
        stored.append(photo.sha256)
        return "local-document-1"
    return onboarding.OnboardingService(object, None, store)


REFERENCE = SimpleNamespace(local_farmer_id="local-1")


def test_new_photo_is_stored_locally_before_the_request(client):
    source = verify(client)
    stored = []
    result = run(service(stored)._with_photo(Session(None), REFERENCE, source, dict(source.profile)))
    assert stored == [source.photo.sha256]
    assert result["record_image_document_id"] == "local-document-1"


def test_unchanged_photo_is_not_stored_again(client):
    source = verify(client)
    stored = []
    farmer = SimpleNamespace(photo_sha256=source.photo.sha256)
    result = run(service(stored)._with_photo(Session(farmer), REFERENCE, source, dict(source.profile)))
    assert stored == [] and "record_image_document_id" not in result


def test_photo_removed_at_the_source_is_cleared(client):
    source = verify(client, photo=None)
    farmer = SimpleNamespace(photo_sha256="a" * 64)
    result = run(service([])._with_photo(Session(farmer), REFERENCE, source, dict(source.profile)))
    assert result["record_image_document_id"] is None and result["photo_sha256"] is None


def test_photo_hash_without_its_bytes_is_refused(client):
    source = replace(verify(client), photo=None)
    with pytest.raises(Error, match="INVALID_PHOTO"):
        run(service([])._with_photo(Session(None), REFERENCE, source, dict(source.profile)))


def test_redelivered_version_compares_without_the_local_document():
    frozen = {"farmer_id": FARMER, "photo_sha256": "a" * 64, "record_image_document_id": "local-document-1"}
    assert onboarding._source_part(frozen) == {"farmer_id": FARMER, "photo_sha256": "a" * 64}


def test_source_profile_cannot_name_a_local_document(client):
    source = verify(client)
    tampered = replace(source, profile={**source.profile, "record_image_document_id": "someone-elses"})
    with pytest.raises(Error, match="INVALID_VERIFIED_SNAPSHOT"):
        onboarding.OnboardingService(object, None)._validate_snapshot(tampered)
