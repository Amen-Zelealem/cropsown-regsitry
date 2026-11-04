-- Every date that staff enter uses OpenG2P's native date widget in the
-- Ethiopian calendar ("widget-data-format": {"calendar": "ethiopic"}, from
-- registry-widgets 1.1.9-dev.17 on the platform 1.2 branch), the same as the
-- Farmer registry. The picker shows and accepts Ethiopian dates; the stored
-- value stays the Gregorian ISO date, so the server, ODK, imports and reports
-- are unchanged. The widget's own date rules (past-only, min and max dates)
-- still apply. Read-only dates (the *_ec twins, audit timestamps) keep the
-- Gregorian display.
--
-- Runs last in zz-oan so it also covers sections that earlier files rewrite.
-- Livestock's Next Due Date (oan-next-due-date) renders the same native
-- widget, so it takes the same calendar.
CREATE OR REPLACE FUNCTION pg_temp.oan_ethiopian_dates(node jsonb)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE
  result jsonb;
BEGIN
  IF jsonb_typeof(node) = 'array' THEN
    SELECT COALESCE(jsonb_agg(pg_temp.oan_ethiopian_dates(value) ORDER BY ord), '[]'::jsonb)
      INTO result FROM jsonb_array_elements(node) WITH ORDINALITY AS a(value, ord);
  ELSIF jsonb_typeof(node) = 'object' THEN
    SELECT COALESCE(jsonb_object_agg(key, pg_temp.oan_ethiopian_dates(value)), '{}'::jsonb)
      INTO result FROM jsonb_each(node);
    -- Metadata seeded before the native calendar used an OAN widget variant
    -- and table-cell alias; both go back to the native date widget.
    IF result->>'widget' = 'oan-ethiopian-date-input' THEN
      result := result || '{"widget": "date"}'::jsonb;
    END IF;
    IF result->>'widget-variant' = 'ethiopian' THEN
      result := result - 'widget-variant';
    END IF;
    IF result->>'widget' IN ('date', 'oan-next-due-date')
       AND COALESCE((result->>'widget-readonly')::boolean, false) = false THEN
      result := jsonb_set(result, '{widget-data-format}',
        CASE WHEN jsonb_typeof(result->'widget-data-format') = 'object'
             THEN result->'widget-data-format' ELSE '{}'::jsonb END
        || '{"calendar": "ethiopic"}'::jsonb);
    END IF;
  ELSE
    result := node;
  END IF;
  RETURN result;
END $$;

UPDATE "public"."g2p_register_sections"
SET section_ui_schema = pg_temp.oan_ethiopian_dates(section_ui_schema)
WHERE section_ui_schema IS NOT NULL;

DO $$
DECLARE
  missing text;
BEGIN
  SELECT string_agg(DISTINCT s.section_id || '.' || COALESCE(w->>'widget-id', w->>'column-key'), ', ')
    INTO missing
  FROM "public"."g2p_register_sections" s,
       jsonb_path_query(s.section_ui_schema,
         'lax $.** ? (@.widget == "date" || @.widget == "oan-next-due-date" || @.widget == "oan-ethiopian-date-input")') w
  WHERE COALESCE((w->>'widget-readonly')::boolean, false) = false
    AND (w #>> '{widget-data-format,calendar}' IS DISTINCT FROM 'ethiopic'
         OR w->>'widget' = 'oan-ethiopian-date-input'
         OR w->>'widget-variant' = 'ethiopian');
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'Staff-entered dates not on the native Ethiopian calendar: %', missing;
  END IF;
END $$;
