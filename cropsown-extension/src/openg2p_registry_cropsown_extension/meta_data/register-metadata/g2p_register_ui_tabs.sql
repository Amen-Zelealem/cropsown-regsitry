-- Intake-form columns added after the initial release. Idempotent: a no-op on a
-- fresh database (create_all already made them with a server_default), and on an
-- existing database it adds them with defaults so current rows and the inserts
-- below both get a value.
ALTER TABLE IF EXISTS "public"."g2p_register_ui_tabs"
    ADD COLUMN IF NOT EXISTS "used_for_new_intake_form" boolean NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS "no_of_verifications_required" integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS "intake_form_name" varchar,
    ADD COLUMN IF NOT EXISTS "intake_form_description" varchar,
    ADD COLUMN IF NOT EXISTS "intake_form_auto_approve" boolean NOT NULL DEFAULT false;

-- Ensure the defaults are set even when the columns were added by an earlier
-- run without one (ADD COLUMN IF NOT EXISTS is a no-op if they already exist).
ALTER TABLE public.g2p_register_ui_tabs
  ALTER COLUMN used_for_new_intake_form SET DEFAULT true,
  ALTER COLUMN no_of_verifications_required SET DEFAULT 0,
  ALTER COLUMN intake_form_auto_approve SET DEFAULT false;

INSERT INTO "public"."g2p_register_ui_tabs" ("tab_id","register_id","tab_label","tab_order","is_active") VALUES
('cropsown_cropsown_tab','6b06a95a-9a6c-5a33-a33d-c1625716c59c','cropsown_record_tab',0,'TRUE'),
('cropsown_planning_tab','6b06a95a-9a6c-5a33-a33d-c1625716c59c','cropsown_planning_tab',10,'TRUE'),
('cropsown_cultivation_tab','6b06a95a-9a6c-5a33-a33d-c1625716c59c','cropsown_cultivation_tab',20,'TRUE'),
('cropsown_sowing_tab','6b06a95a-9a6c-5a33-a33d-c1625716c59c','cropsown_sowing_tab',30,'TRUE'),
('cropsown_harvest_tab','6b06a95a-9a6c-5a33-a33d-c1625716c59c','cropsown_harvest_tab',40,'TRUE'),
('cropsown_production_tab','6b06a95a-9a6c-5a33-a33d-c1625716c59c','cropsown_production_tab',50,'TRUE');
