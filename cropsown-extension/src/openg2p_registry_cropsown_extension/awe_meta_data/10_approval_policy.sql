INSERT INTO "public"."approval_policy" (
    "id",
    "policy_key",
    "version",
    "name",
    "description",
    "status",
    "artifact_type",
    "created_by",
    "forbid_self_approval",
    "forbid_repeat_approvers",
    "created_at",
    "updated_at"
) VALUES
    ('a1c3e5f7-1b2d-4e6f-8a90-1c2d3e4f5a61', 'registry.change_request.cropsown', 1, 'Policy for Crop Sown Change Request', NULL, 'active', 'registry.change_request', 'seed', 'FALSE', 'FALSE', NOW(), NOW()),
    ('28466668-7498-48a4-b445-282b31fe13ad', 'registry.intake_form.planning_cropsown', 1, 'Policy for Crop Sown Planning Intake', NULL, 'active', 'registry.intake_form', 'seed', 'FALSE', 'FALSE', NOW(), NOW()),
    ('dc30c216-f20f-478b-bc71-c7a37c79edea', 'registry.intake_form.cultivation_cropsown', 1, 'Policy for Crop Sown Cultivation Intake', NULL, 'active', 'registry.intake_form', 'seed', 'FALSE', 'FALSE', NOW(), NOW()),
    ('74482d2a-cb1d-4297-a4d2-0feb4d09fcc8', 'registry.intake_form.sowing_cropsown', 1, 'Policy for Crop Sown Sowing Intake', NULL, 'active', 'registry.intake_form', 'seed', 'FALSE', 'FALSE', NOW(), NOW()),
    ('696d5f2e-baca-48a2-8128-875bf1043f25', 'registry.intake_form.harvesting_cropsown', 1, 'Policy for Crop Sown Harvesting Intake', NULL, 'active', 'registry.intake_form', 'seed', 'FALSE', 'FALSE', NOW(), NOW())
ON CONFLICT ("id") DO NOTHING;

