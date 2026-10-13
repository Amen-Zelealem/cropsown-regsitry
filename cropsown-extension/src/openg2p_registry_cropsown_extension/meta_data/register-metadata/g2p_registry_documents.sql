INSERT INTO "public"."g2p_registry_documents" ("document_id","document_store_id","bucket","source_filename","created_by","created_at") VALUES
('1f0953d4-f0fb-4336-a126-4d0519a74ffc','dci_commons_response.json.j2','templates','dci_commons_response.json.j2','seeder','2026-04-01 00:00:00'),
('3b7c1d20-5c0e-4c1b-9f2e-8a1c6d5e4f30','dci_to_openg2p_cropsown.json.j2','templates','dci_to_openg2p_cropsown.json.j2','seeder','2026-04-01 00:00:00'),
('4c8d2e31-6d1f-4d2c-a03f-9b2d7e6f5041','openg2p_cropsown_to_dci.json.j2','templates','openg2p_cropsown_to_dci.json.j2','seeder','2026-04-01 00:00:00'),
('7a8b9c0d-1e2f-4a5b-8c9d-0e1f2a3b4c5d','csr_odk_transform.j2','templates','csr_odk_transform.j2','seeder','2026-04-01 00:00:00')
ON CONFLICT (document_id) DO NOTHING;
