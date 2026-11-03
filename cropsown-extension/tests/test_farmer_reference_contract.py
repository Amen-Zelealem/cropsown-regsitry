"""Domain rules; no HTTP, registry database, worker or IAM mutation."""
from copy import deepcopy
from datetime import date
import importlib
import os
import unittest

PACKAGE = os.environ.get("REGISTRY_EXTENSION_MODULE", "openg2p_registry_cropsown_extension")
p = importlib.import_module(PACKAGE + ".farmer_reference.profile")
g = importlib.import_module(PACKAGE + ".farmer_reference.geography")
FARMER_ID = "FR-000000000001"
UID = "0000000000000001"


class ProfileContractTests(unittest.TestCase):
    def approved(self):
        return {"farmer_id": FARMER_ID, "fayda_fan_id": UID,
                "first_name": "First", "middle_name": "Middle", "last_name": "Last",
                "mobile_number": "0000000000", "woreda_id": "woreda-A"}

    def test_pair_normalizes_display_whitespace_preserving_zeros(self):
        self.assertEqual(p.identity_pair(" " + FARMER_ID + " ", "0000 0000 0000 0001"), (FARMER_ID, UID))

    def test_invalid_farmer_identifiers(self):
        for value in (None, 1, "fr-000000000001", "FR-0000000001", "FR-000000000001\nextra", "FR-" + "١" * 12):
            with self.subTest(value=value), self.assertRaises(p.FarmerReferenceError):
                p.normalize_farmer_id(value)

    def test_uid_rejects_fin_unicode_and_numeric_coercion(self):
        for value in (None, 1, 1.0, "1" * 12, "1" * 17, "١" * 16, "1" * 15 + "x"):
            with self.subTest(value=value), self.assertRaises(p.FarmerReferenceError):
                p.normalize_uid(value)

    def test_partial_draft_does_not_require_identity_or_onboard(self):
        row = {"first_name": "Draft", "farmer_id": "", "fayda_fan_id": None}
        original = deepcopy(row)
        p.validate_identity_fields(row)
        self.assertEqual(row, original)

    def test_source_allowlist_excludes_household_documents_business_and_grants(self):
        source = {"farmer_id": FARMER_ID, "approved_uid": UID, "first_name": "Trusted",
                  "household_size": 4, "is_psnp_user": True, "education_level": "BASIC",
                  "document_ids": ["secret"], "crop_year": "2026", "head_count": 12,
                  "roles": ["admin"], "status": "APPROVED", "enumerator_user_id": "internal",
                  "last_authentication_status": "SUCCESS", "created_by": "staff", "last_approved_by": "staff",
                  "record_image_document_id": "source-document"}
        before = deepcopy(source)
        # Farmer-tab details are copied; household, documents, business values,
        # grants, the Fayda verification and staff names are not.
        self.assertEqual(p.local_profile(source), {"farmer_id": FARMER_ID, "fayda_fan_id": UID, "first_name": "Trusted",
                                                   "is_psnp_user": True, "education_level": "BASIC"})
        self.assertEqual(source, before)

    def test_farmer_tab_details_keep_their_types(self):
        source = {"farmer_id": FARMER_ID, "approved_uid": UID, "has_national_id": True, "estimated_age": 46,
                  "disabled": False, "latitude": 9, "longitude": 38.7, "altitude": None,
                  "marital_status": "MARRIED", "rid": "1" * 29,
                  "phones": [{"phone_type": "PRIMARY", "phone_number": " 911111111 ", "country_code": "+251",
                              "is_primary": True, "phone_e164": "+251911111111"}]}
        profile = p.local_profile(source)
        self.assertIs(profile["has_national_id"], True)
        self.assertEqual(profile["estimated_age"], 46)
        self.assertEqual(profile["latitude"], 9.0)
        self.assertIsNone(profile["altitude"])
        self.assertEqual(profile["phones"][0]["phone_number"], "911111111")

    def test_farmer_tab_details_reject_wrong_types(self):
        for field, value in (("has_national_id", "yes"), ("disabled", 1), ("estimated_age", True),
                             ("estimated_age", 400), ("latitude", "9.1"), ("latitude", float("nan")),
                             ("marital_status", 3), ("phones", {"phone_number": "1"}),
                             ("phones", [{"phone_number": 911}]), ("phones", [{"pin": "1234"}]),
                             ("phones", [{}] * 11)):
            with self.subTest(field=field, value=value), self.assertRaises(p.FarmerReferenceError):
                p.local_profile({field: value})

    def test_photo_is_never_a_source_profile_value(self):
        self.assertNotIn("record_image_document_id", p.SOURCE_TO_LOCAL_FIELDS.values())
        self.assertNotIn("photo_sha256", p.SOURCE_TO_LOCAL_FIELDS.values())
        self.assertEqual(p.local_profile({"photo": {"data": "x"}, "photo_sha256": "0" * 64}), {})

    def test_explicit_optional_clear_and_omission_are_distinct(self):
        before = self.approved()
        proposed = p.local_profile({"middle_name": None})
        result = p.merge_profile(before, proposed)
        self.assertIsNone(result["middle_name"])
        self.assertEqual(result["mobile_number"], before["mobile_number"])
        self.assertEqual(result["farmer_name"], "First Last")
        self.assertEqual(before, self.approved())

    def test_no_truthiness_coercion_of_profile_values(self):
        for value in (0, False, [], {}):
            with self.subTest(value=value), self.assertRaises(p.FarmerReferenceError):
                p.local_profile({"mobile_number": value})
        self.assertEqual(p.local_profile({"address_line_2": "", "email": None}), {"address_line_2": "", "email": None})

    def test_merge_rejects_domain_fields_and_identity_clear(self):
        for proposed in ({"crop_year": 2027}, {"head_count": 5}, {"roles": ["admin"]}, {"farmer_id": None}, {"fayda_fan_id": None}):
            with self.subTest(proposed=proposed), self.assertRaises(p.FarmerReferenceError):
                p.merge_profile(self.approved(), proposed)

    def test_profile_copy_is_deep(self):
        source = {"geo_code_hierarchy_json": {"hierarchy": [{"level_value_id": "woreda-A"}]}}
        mapped = p.local_profile(source)
        mapped["geo_code_hierarchy_json"]["hierarchy"][0]["level_value_id"] = "woreda-B"
        self.assertEqual(source["geo_code_hierarchy_json"]["hierarchy"][0]["level_value_id"], "woreda-A")

    def test_birth_date_is_valid_and_not_in_future(self):
        self.assertEqual(p.local_profile({"birth_date": "2000-02-29"})["date_of_birth"], date(2000, 2, 29))
        for value in ("2001-02-29", "2999-01-01", 0, False, []):
            with self.subTest(value=value), self.assertRaises(p.FarmerReferenceError):
                p.local_profile({"birth_date": value})

    def update(self, **kwargs):
        defaults = dict(expected_source_id="immutable-source", fetched_source_id="immutable-source",
                        applied_version=4, fetched_version=5)
        defaults.update(kwargs)
        return p.prepare_update(self.approved(), {"farmer_id": FARMER_ID, "approved_uid": UID, "first_name": "Updated"}, **defaults)

    def test_new_source_version_prepares_profile_without_mutation(self):
        result = self.update()
        self.assertEqual(result["first_name"], "Updated")
        self.assertEqual(result["mobile_number"], self.approved()["mobile_number"])

    def test_stale_duplicate_and_invalid_version_rejected(self):
        for version in (3, 4, 0, -1, True, 5.0, "5", None):
            with self.subTest(version=version), self.assertRaises(p.FarmerReferenceError):
                self.update(fetched_version=version)

    def test_source_mismatch_rejected(self):
        with self.assertRaisesRegex(p.FarmerReferenceError, "SOURCE_ID_MISMATCH"):
            self.update(fetched_source_id="another-person")

    def test_approved_uid_rotation_keeps_stable_farmer(self):
        result = p.prepare_update(self.approved(), {"farmer_id": FARMER_ID, "approved_uid": "0000000000000002"},
                                  expected_source_id="immutable", fetched_source_id="immutable", applied_version=4, fetched_version=5)
        self.assertEqual(result["farmer_id"], FARMER_ID)
        self.assertEqual(result["fayda_fan_id"], "0000000000000002")

    def test_missing_identity_or_changed_farmer_id_rejected(self):
        for source in ({"first_name": "Notification"}, {"farmer_id": "FR-000000000002", "approved_uid": UID}):
            with self.subTest(source=source), self.assertRaises(p.FarmerReferenceError):
                p.prepare_update(self.approved(), source, expected_source_id="s", fetched_source_id="s", applied_version=1, fetched_version=2)


class GeographicPolicyTests(unittest.TestCase):
    def candidate(self, user, *, role=True, scope="woreda-A", active=True):
        return g.ApproverEligibility(user, frozenset({g.FARMER_APPROVER_ROLE} if role else {"admin"}), frozenset({scope} if scope else ()), active)

    def test_add_uses_verified_source_scope(self):
        result = g.approver_context("ADD", (self.candidate("eligible"),),
                                    verified_source={"woreda_id": "woreda-A"}, approved_local={"woreda_id": "woreda-B"})
        self.assertEqual(result["farmer_reference_approver_ids"], ["eligible"])

    def test_update_uses_old_approved_scope_and_does_not_mutate(self):
        approved = {"woreda_id": "woreda-A"}
        proposed = {"woreda_id": "woreda-B", "approver_ids": ["attacker"]}
        result = g.approver_context("UPDATE", (self.candidate("old-reviewer"), self.candidate("new-reviewer", scope="woreda-B")),
                                    verified_source=proposed, approved_local=approved)
        self.assertEqual(result["farmer_reference_approver_ids"], ["old-reviewer"])
        self.assertEqual(approved, {"woreda_id": "woreda-A"})
        self.assertEqual(proposed["approver_ids"], ["attacker"])

    def test_missing_scope_never_falls_back_to_proposal_or_name(self):
        for local in (None, {}, {"woreda": "human name"}, {"woreda_id": None}, {"woreda_id": False}):
            with self.subTest(local=local), self.assertRaisesRegex(p.FarmerReferenceError, "SCOPE_REQUIRED"):
                g.approver_context("UPDATE", (self.candidate("eligible"),), approved_local=local, verified_source={"woreda_id": "woreda-A"})

    def test_functional_role_and_policy_scope_are_both_required(self):
        for candidate in (self.candidate("admin", role=False), self.candidate("wrong-location", scope="woreda-B"),
                          self.candidate("unscoped", scope=None), self.candidate("inactive", active=False)):
            with self.subTest(candidate=candidate), self.assertRaisesRegex(p.FarmerReferenceError, "NO_ELIGIBLE_APPROVER"):
                g.approver_context("ADD", (candidate,), verified_source={"woreda_id": "woreda-A"})

    def test_repeated_candidates_deduplicate_and_sort(self):
        result = g.approver_context("ADD", (self.candidate("b"), self.candidate("a"), self.candidate("a")), verified_source={"woreda_id": "woreda-A"})
        self.assertEqual(result["farmer_reference_approver_ids"], ["a", "b"])

    def test_after_address_approval_future_requests_use_new_scope(self):
        result = g.approver_context("UPDATE", (self.candidate("new-reviewer", scope="woreda-B"),),
                                    approved_local={"woreda_id": "woreda-B"})
        self.assertEqual(result["farmer_reference_approver_ids"], ["new-reviewer"])


class PublishedPolicyTests(unittest.TestCase):
    def condition(self, ids):
        return {"type":"CONDITION", "field_id":"woreda_id", "operator":"IN", "values":ids}

    def test_standard_woreda_eq_and_in_have_finite_scopes(self):
        self.assertEqual(g.finite_woredas({"type":"CONDITION", "field_id":"woreda_id", "operator":"eq", "value":"A"}), {"A"})
        self.assertEqual(g.finite_woredas(self.condition(["A", "B"])), {"A", "B"})

    def test_nested_standard_and_or_preserve_scope_intersection(self):
        children = [self.condition(["A", "B"]), self.condition(["B", "C"])]
        self.assertEqual(g.finite_woredas({"type":"GROUP", "operator":"AND", "children":children}), {"B"})
        self.assertEqual(g.finite_woredas({"type":"GROUP", "operator":"OR", "children":children}), {"A", "B", "C"})

    def test_disallow_policy_wins_and_missing_assignment_grants_nothing(self):
        from types import SimpleNamespace
        allow = SimpleNamespace(policy_type="ALLOW", policy_filter_expression=self.condition(["A", "B"]))
        deny = SimpleNamespace(policy_type="DISALLOW", policy_filter_expression=self.condition(["B"]))
        self.assertEqual(g.policy_woredas([allow, deny]), frozenset({"A"}))
        self.assertEqual(g.policy_woredas([]), frozenset())

    def test_broad_unknown_and_non_geographic_policies_never_become_unscoped_approvers(self):
        for expression in ({}, {"type":"GROUP", "operator":"AND", "children":[]},
                           {"type":"GROUP", "operator":"NOT", "children":[self.condition(["A"])]},
                           {"type":"CONDITION", "field_id":"role", "operator":"eq", "value":"admin"},
                           {"type":"CONDITION", "field_id":"woreda_id", "operator":"contains", "value":""}):
            with self.subTest(expression=expression), self.assertRaisesRegex(p.FarmerReferenceError, "UNSUPPORTED_GEOGRAPHIC_POLICY"):
                g.finite_woredas(expression)


if __name__ == "__main__":
    unittest.main()
