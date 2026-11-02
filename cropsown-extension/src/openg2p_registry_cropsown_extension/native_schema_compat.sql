-- Add-only native outgestion compatibility for existing registry databases.
-- Topic IDs, source contracts and WebSub delivery checkpoints are preserved.
DO $native_compat$
DECLARE
  tbl text;
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

  -- Convert legacy VARCHAR land_prep_method to JSONB list for cultivation tables
  FOR tbl IN SELECT unnest(ARRAY['g2p_register_cultivations', 'g2p_register_history_cultivations', 'g2p_intake_form_cultivations'])
  LOOP
    IF to_regclass(quote_ident(current_schema()) || '.' || quote_ident(tbl)) IS NOT NULL THEN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = tbl
          AND column_name = 'land_prep_method'
          AND data_type <> 'jsonb'
      ) THEN
        EXECUTE 'ALTER TABLE ' || quote_ident(current_schema()) || '.' || quote_ident(tbl) ||
                ' ALTER COLUMN land_prep_method TYPE jsonb' ||
                ' USING CASE ' ||
                '   WHEN land_prep_method IS NULL THEN NULL ' ||
                '   WHEN trim(land_prep_method::text) = '''' THEN NULL ' ||
                '   WHEN trim(land_prep_method::text) ~ ''^\s*\['' THEN land_prep_method::text::jsonb ' ||
                '   ELSE to_jsonb(string_to_array(land_prep_method::text, '','')) ' ||
                ' END';
      END IF;
    END IF;
  END LOOP;
END;
$native_compat$;
