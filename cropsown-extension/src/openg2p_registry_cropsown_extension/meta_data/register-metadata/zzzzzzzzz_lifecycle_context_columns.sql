-- Land ID, Season and Crop identify one plot's crop cycle, so every lifecycle
-- table of the Crop Sown register shows them first. Before this file only
-- Planning and Cultivation showed all three: Sowing lacked Season, Harvest
-- lacked Season and Crop, Infestation lacked Season, and both cluster tables
-- lacked Crop.
--
--   section                                  table id                          crop column
--   cropsown_planning_details_section_01     cs_planning_details_table         commodity
--   cropsown_cultivation_details_section_01  cs_cultivation_details_table      commodity
--   cropsown_cultivation_cluster_details_..  cs_cultivation_cluster_details_t.  primary_commodity
--   cropsown_sowing_details_section_01       cs_sowing_details_table           commodity
--   cropsown_harvest_details_section_01      cs_harvest_details_table          commodity
--   cropsown_infestation_details_section_01  cs_infestation_details_table       commodity
--   cropsown_cluster_details_section_01      cs_cluster_details_table          primary_commodity
--
-- Harvest and Infestation had no Season column at all: this file adds the
-- Season select (the same CROP_SEASON list the other tables use) right after
-- Land ID, and the models/schemas carry a matching nullable `season` column.
-- The visible columns of each table become Land ID, Season, Crop, then the
-- table's own columns in their existing order.
--
-- Sorts after every earlier file that rewrites the section JSON (the base
-- upsert, field rules, identity overlays) and just before the required-rows
-- overlay, which only sets widget-required flags and so does not care about
-- column order or the Season column added here.
-- Idempotent: it only moves the three keys to the front and adds Season when
-- it is absent, so every install and upgrade can re-run it.
CREATE OR REPLACE FUNCTION pg_temp.coss_lifecycle_context(node jsonb, table_id text, crop_key text)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE
  result jsonb;
  season_column jsonb := '{"widget": "select", "column-key": "season", "widget-type": "input",
    "widget-label": "Season", "widget-readonly": false, "widget-data-path": "season",
    "widget-data-source": {"type": "api", "method": "POST", "params": {"page_size": 200,
    "attribute_id": "CROP_SEASON"}, "service": "attributes", "endpoint": "values",
    "labelKey": "value_display", "valueKey": "value_id"}}'::jsonb;
  context_keys text[] := ARRAY['land_id', 'season', crop_key];
BEGIN
  IF jsonb_typeof(node) = 'array' THEN
    SELECT COALESCE(jsonb_agg(pg_temp.coss_lifecycle_context(value, table_id, crop_key) ORDER BY position), '[]'::jsonb)
      INTO result FROM jsonb_array_elements(node) WITH ORDINALITY AS item(value, position);
  ELSIF jsonb_typeof(node) = 'object' THEN
    SELECT COALESCE(jsonb_object_agg(key, pg_temp.coss_lifecycle_context(value, table_id, crop_key)), '{}'::jsonb)
      INTO result FROM jsonb_each(node);
    IF node->>'widget-id' = table_id AND node->>'widget' IN ('table', 'dialog-table')
       AND jsonb_typeof(node->'widget-data-columns') = 'array' THEN
      -- Season column: add it straight after Land ID when the table has none.
      IF NOT EXISTS (SELECT 1 FROM jsonb_array_elements(node->'widget-data-columns') c
                     WHERE c->>'column-key' = 'season') THEN
        result := jsonb_set(result, '{widget-data-columns}', (
          SELECT COALESCE(jsonb_agg(column_node ORDER BY position), '[]'::jsonb) FROM (
            SELECT column_node, position * 2 AS position
              FROM jsonb_array_elements(node->'widget-data-columns') WITH ORDINALITY AS item(column_node, position)
            UNION ALL
            SELECT season_column,
                   COALESCE((SELECT position * 2 + 1
                               FROM jsonb_array_elements(node->'widget-data-columns') WITH ORDINALITY AS item(column_node, position)
                              WHERE column_node->>'column-key' = 'land_id'), 1)
          ) merged));
      END IF;
      -- Visible columns: Land ID, Season, Crop first, then the rest as they were.
      result := jsonb_set(result, '{widget-data-visible-columns}',
        (SELECT jsonb_agg(to_jsonb(k) ORDER BY ord) FROM (
           SELECT k, ord FROM unnest(context_keys) WITH ORDINALITY AS c(k, ord)
           UNION ALL
           SELECT v.value, 100 + v.position
             FROM jsonb_array_elements_text(COALESCE(node->'widget-data-visible-columns', '[]'::jsonb))
                  WITH ORDINALITY AS v(value, position)
            WHERE v.value <> ALL (context_keys)
         ) ordered(k, ord)));
    END IF;
  ELSE
    result := node;
  END IF;
  RETURN result;
END $$;

UPDATE g2p_register_sections s
SET section_ui_schema = pg_temp.coss_lifecycle_context(s.section_ui_schema::jsonb, v.table_id, v.crop_key)
FROM (VALUES
  ('cropsown_planning_details_section_01',          'cs_planning_details_table',          'commodity'),
  ('cropsown_cultivation_details_section_01',       'cs_cultivation_details_table',       'commodity'),
  ('cropsown_cultivation_cluster_details_section_01', 'cs_cultivation_cluster_details_table', 'primary_commodity'),
  ('cropsown_sowing_details_section_01',            'cs_sowing_details_table',            'commodity'),
  ('cropsown_harvest_details_section_01',           'cs_harvest_details_table',           'commodity'),
  ('cropsown_infestation_details_section_01',       'cs_infestation_details_table',       'commodity'),
  ('cropsown_cluster_details_section_01',           'cs_cluster_details_table',           'primary_commodity')
) AS v(section_id, table_id, crop_key)
WHERE s.section_id = v.section_id AND s.section_ui_schema IS NOT NULL;

-- Check: fail the seed loudly if any table does not lead with the three keys,
-- or one of them has no column to show.
DO $$
DECLARE expected record; table_node jsonb; lead jsonb;
BEGIN
  FOR expected IN SELECT * FROM (VALUES
      ('cropsown_planning_details_section_01',          'cs_planning_details_table',          'commodity'),
      ('cropsown_cultivation_details_section_01',       'cs_cultivation_details_table',       'commodity'),
      ('cropsown_cultivation_cluster_details_section_01', 'cs_cultivation_cluster_details_table', 'primary_commodity'),
      ('cropsown_sowing_details_section_01',            'cs_sowing_details_table',            'commodity'),
      ('cropsown_harvest_details_section_01',           'cs_harvest_details_table',           'commodity'),
      ('cropsown_infestation_details_section_01',       'cs_infestation_details_table',       'commodity'),
      ('cropsown_cluster_details_section_01',           'cs_cluster_details_table',           'primary_commodity')
    ) AS v(section_id, table_id, crop_key)
  LOOP
    SELECT w INTO table_node FROM g2p_register_sections s,
      jsonb_path_query(s.section_ui_schema::jsonb, 'strict $.**') w
      WHERE s.section_id = expected.section_id AND jsonb_typeof(w) = 'object' AND w->>'widget-id' = expected.table_id;
    IF table_node IS NULL THEN
      RAISE EXCEPTION 'table % of % not found', expected.table_id, expected.section_id;
    END IF;
    lead := jsonb_build_array('land_id', 'season', expected.crop_key);
    IF (SELECT jsonb_agg(e) FROM (SELECT e FROM jsonb_array_elements(table_node->'widget-data-visible-columns') WITH ORDINALITY AS t(e, o) ORDER BY o LIMIT 3) x)
       IS DISTINCT FROM lead THEN
      RAISE EXCEPTION 'table % must show land_id, season and % first, got %', expected.table_id, expected.crop_key,
        table_node->'widget-data-visible-columns';
    END IF;
    IF (SELECT count(*) FROM jsonb_array_elements(table_node->'widget-data-columns') c
         WHERE c->>'column-key' IN ('land_id', 'season', expected.crop_key)) <> 3 THEN
      RAISE EXCEPTION 'table % must define land_id, season and % columns', expected.table_id, expected.crop_key;
    END IF;
  END LOOP;
END $$;
