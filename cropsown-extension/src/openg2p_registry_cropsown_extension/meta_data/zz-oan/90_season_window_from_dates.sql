-- The season window is entered once, as Start date and End date on the
-- Ethiopian calendar picker. The tables used to ask for Start/End Day and
-- Month as plain numbers as well, which repeated those dates in the
-- Gregorian calendar and could disagree with them. Those number columns are
-- taken off the form; the server still stores the day and month, worked out
-- from the dates on save (compute_season_parts), so the season check and
-- imports that send day and month keep working.
--
-- The editable dates no longer say "(Gregorian)", because the picker shows
-- and accepts Ethiopian dates. Runs after 85_readable_text, which sets those
-- labels.
CREATE OR REPLACE FUNCTION pg_temp.oan_season_from_dates(node jsonb)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE
  result jsonb;
BEGIN
  IF jsonb_typeof(node) = 'array' THEN
    SELECT COALESCE(jsonb_agg(pg_temp.oan_season_from_dates(value) ORDER BY ord), '[]'::jsonb)
      INTO result
    FROM jsonb_array_elements(node) WITH ORDINALITY AS a(value, ord)
    WHERE NOT (jsonb_typeof(value) = 'object'
               AND value->>'widget' = 'number'
               AND regexp_replace(COALESCE(value->>'widget-data-path', value->>'column-key', ''), '^.*\.', '')
                   IN ('start_month', 'start_day', 'end_month', 'end_day'));
  ELSIF jsonb_typeof(node) = 'object' THEN
    SELECT COALESCE(jsonb_object_agg(key, pg_temp.oan_season_from_dates(value)), '{}'::jsonb)
      INTO result FROM jsonb_each(node);
    IF result->>'widget' = 'date'
       AND COALESCE((result->>'widget-readonly')::boolean, false) = false
       AND result->>'widget-label' ~ '\s*\((Gregorian|GC)\)$' THEN
      result := jsonb_set(result, '{widget-label}',
        to_jsonb(regexp_replace(result->>'widget-label', '\s*\((Gregorian|GC)\)$', '')));
    END IF;
  ELSE
    result := node;
  END IF;
  RETURN result;
END $$;

UPDATE "public"."g2p_register_sections"
SET section_ui_schema = pg_temp.oan_season_from_dates(section_ui_schema)
WHERE section_ui_schema IS NOT NULL;

DO $$
DECLARE
  left_over text;
BEGIN
  SELECT string_agg(DISTINCT s.section_id || '.' || COALESCE(w->>'widget-id', w->>'column-key', w->>'widget-label'), ', ')
    INTO left_over
  FROM "public"."g2p_register_sections" s,
       jsonb_path_query(s.section_ui_schema, 'lax $.** ? (@.widget == "number" || @.widget == "date")') w
  WHERE (w->>'widget' = 'number'
         AND regexp_replace(COALESCE(w->>'widget-data-path', w->>'column-key', ''), '^.*\.', '')
             IN ('start_month', 'start_day', 'end_month', 'end_day'))
     OR (w->>'widget' = 'date'
         AND COALESCE((w->>'widget-readonly')::boolean, false) = false
         AND w->>'widget-label' ~ '\((Gregorian|GC)\)$');
  IF left_over IS NOT NULL THEN
    RAISE EXCEPTION 'Season day/month number boxes or Gregorian date labels still on the form: %', left_over;
  END IF;
END $$;
