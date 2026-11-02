-- Add-only native outgestion compatibility for existing registry databases.
-- Topic IDs, source contracts and WebSub delivery checkpoints are preserved.
DO $native_compat$
DECLARE tbl text;
BEGIN
  IF to_regclass('public.outgoing_topics') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='outgoing_topics' AND column_name='topic_type') THEN
      IF EXISTS (SELECT 1 FROM public.outgoing_topics WHERE register_id IS NULL) THEN
        RAISE EXCEPTION 'Legacy outgoing topics require an explicit register/partner migration';
      END IF;
      ALTER TABLE public.outgoing_topics ADD COLUMN IF NOT EXISTS topic_type varchar NOT NULL DEFAULT 'REGISTER';
      ALTER TABLE public.outgoing_topics ALTER COLUMN topic_type DROP DEFAULT;
    END IF;
    ALTER TABLE public.outgoing_topics ADD COLUMN IF NOT EXISTS partner_id varchar;
  END IF;
  -- Land preparation method is a multi-select, so the mapped column is jsonb. Tables
  -- created before that hold it as text (one code or a comma-separated list); convert
  -- it once so every value becomes a list of codes. Skipped when already jsonb.
  FOREACH tbl IN ARRAY ARRAY['g2p_register_cultivations', 'g2p_register_history_cultivations', 'g2p_intake_form_cultivations'] LOOP
    IF EXISTS (SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name=tbl AND column_name='land_prep_method'
          AND data_type IN ('character varying', 'text')) THEN
      EXECUTE format(
        'ALTER TABLE public.%I ALTER COLUMN land_prep_method TYPE jsonb USING CASE '
        'WHEN land_prep_method IS NULL OR btrim(land_prep_method) = '''' THEN NULL '
        'WHEN left(btrim(land_prep_method), 1) = ''['' THEN CAST(land_prep_method AS jsonb) '
        'ELSE to_jsonb(string_to_array(regexp_replace(btrim(land_prep_method), '' *, *'', '','', ''g''), '','')) END', tbl);
    END IF;
  END LOOP;
END;
$native_compat$;
