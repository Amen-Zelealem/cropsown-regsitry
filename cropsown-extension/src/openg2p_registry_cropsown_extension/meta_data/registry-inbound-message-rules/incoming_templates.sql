INSERT INTO "public"."incoming_templates" ("template_id","register_id","data_model_id","template_document_id","jsonld_expansion_required","created_at","updated_at") VALUES
('IN-TMPL-1','6b06a95a-9a6c-5a33-a33d-c1625716c59c','c331ba96-ac35-4014-9d13-4ef327f6b79b','3b7c1d20-5c0e-4c1b-9f2e-8a1c6d5e4f30','FALSE','2026-05-07 04:31:27.828397',NULL),
('IN-TMPL-CSR','6b06a95a-9a6c-5a33-a33d-c1625716c59c','e442ca96-ac35-4014-9d13-4ef327f6b79c','7a8b9c0d-1e2f-4a5b-8c9d-0e1f2a3b4c5d','FALSE','2026-10-12 00:00:00',NULL)
ON CONFLICT (template_id) DO NOTHING;

-- DCI: dci_to_openg2p_cropsown.json.j2
