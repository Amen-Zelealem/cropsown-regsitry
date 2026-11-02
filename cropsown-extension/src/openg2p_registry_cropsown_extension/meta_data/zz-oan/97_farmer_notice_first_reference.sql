-- A Farmer Registry change notice about a farmer this registry has never seen.
--
-- The platform's ingestion classifier gives a notice the action ADD when no local Farmer
-- row carries the notice's Farmer ID, and an ADD needs an intake form and a semantic
-- pattern that matches it; without them the notice fails classification and is never
-- delivered. This file supplies both:
--
--   * a Farmer intake form that is used only by the ingestion pipeline and holds the one
--     Farmer identity section, which is all the notice template fills (the Farmer ID and
--     the Fayda ID the notice names; its other fields are never read);
--   * the notice's semantic patterns match that form for ADD as well as the identity
--     section for UPDATE.
--
-- Nothing is approved through that intake. When the pipeline finalizes it, the extension's
-- intake service starts the Farmer reference ADD (signed, consented lookup, then the
-- normal two-stage approval) and closes the intake as cancelled with a pointer to the
-- change request. Known farmers still classify as UPDATE. Idempotent.

INSERT INTO "public"."g2p_intake_form_definitions" ("form_id","register_id","form_mnemonic","form_description","number_of_verifications","used_only_in_ingestion_pipeline") VALUES
('farmer_registry_notice_to_farmer_reference_form','fa120001-0000-4000-8000-000000000001','Farmer Registry Notice to Farmer Reference','Farmer Registry notice about a farmer not yet referenced here; starts the first Farmer reference',0,TRUE)
ON CONFLICT ("form_id") DO UPDATE SET "register_id" = EXCLUDED."register_id", "form_mnemonic" = EXCLUDED."form_mnemonic", "form_description" = EXCLUDED."form_description", "number_of_verifications" = EXCLUDED."number_of_verifications", "used_only_in_ingestion_pipeline" = EXCLUDED."used_only_in_ingestion_pipeline";

INSERT INTO "public"."g2p_intake_form_ui_tabs" ("tab_id","form_id","tab_label","tab_order") VALUES
('farmer_registry_notice_to_farmer_reference_tab','farmer_registry_notice_to_farmer_reference_form','Farmer Registry notice',10)
ON CONFLICT ("tab_id") DO UPDATE SET "form_id" = EXCLUDED."form_id", "tab_label" = EXCLUDED."tab_label", "tab_order" = EXCLUDED."tab_order";

INSERT INTO "public"."g2p_intake_form_ui_tab_sections" ("tab_section_id","tab_id","section_id","section_order") VALUES
('farmer_registry_notice_to_farmer_reference_tab_section','farmer_registry_notice_to_farmer_reference_tab','cropsown_farmer_identity_section_01',10)
ON CONFLICT ("tab_section_id") DO UPDATE SET "tab_id" = EXCLUDED."tab_id", "section_id" = EXCLUDED."section_id", "section_order" = EXCLUDED."section_order";

UPDATE "public"."incoming_model_semantic_patterns"
SET "intake_form_id" = 'farmer_registry_notice_to_farmer_reference_form',
    "pattern_for_intake_form" = "pattern_for_register"
WHERE "semantic_pattern_id" IN ('a01d73cb-ca18-53b4-9d90-7c1a4841cd37','farmer_changed_v1_pattern');
