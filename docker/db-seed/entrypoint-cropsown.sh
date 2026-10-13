#!/bin/sh
# db-seed for the crop sown registry: the platform's seeding, then this
# variant's Ethiopia geo hierarchy.
#
# The base image's /seed/entrypoint.sh loads the registry metadata, and its
# load_geo_data.py loads the generic sample hierarchy that ships in
# /openg2p-data. This registry is Ethiopia-only and needs the real
# region/zone/woreda/kebele hierarchy instead, which lives in this repo as
# geo-seed/ethiopia_geo_seed_fixed.sql (21,057 INSERTs, every one with ON
# CONFLICT, wrapped in one transaction, so re-running it changes nothing).
#
# Until now that file reached only the docker-compose stack, applied by hand
# (docker/local-dev/geo-seed/import_ethiopia_geo.py documents how it was
# generated); nothing copied it into this image, so a deployed cluster kept the
# sample hierarchy. It is now part of the image and applied on every deploy.
#
# It goes into the MASTER DATA database (g2p_geo_levels, g2p_geo_level_values),
# which is where the geo-hierarchy widget reads from, using the MD_PG* variables
# the chart already passes to this Job.
#
# Env:
#   LOAD_ETHIOPIA_GEO  false to skip this step (default true)
#   GEO_SEED_FILE      override the SQL applied
#   MD_PGHOST/MD_PGPORT/MD_PGDATABASE/MD_PGUSER/MD_PGPASSWORD  master data DB
set -eu

GEO_SEED_FILE="${GEO_SEED_FILE:-/seed/geo-seed/ethiopia_geo_seed_fixed.sql}"

# Platform seeding first: its failure is this Job's failure, as before.
/seed/entrypoint.sh "$@"

if [ "${LOAD_ETHIOPIA_GEO:-true}" = "false" ]; then
  echo "[geo-seed] LOAD_ETHIOPIA_GEO=false - skipping the Ethiopia hierarchy"
  exit 0
fi

if [ ! -f "$GEO_SEED_FILE" ]; then
  echo "[geo-seed] ERROR: ${GEO_SEED_FILE} is not in this image" >&2
  exit 1
fi

if [ -z "${MD_PGDATABASE:-}" ] || [ -z "${MD_PGHOST:-}" ]; then
  echo "[geo-seed] ERROR: MD_PGHOST/MD_PGDATABASE are not set; cannot reach the master data DB" >&2
  exit 1
fi

echo "[geo-seed] Applying the Ethiopia hierarchy to ${MD_PGDATABASE}@${MD_PGHOST}:${MD_PGPORT:-5432} ..."
PGPASSWORD="${MD_PGPASSWORD:-}" psql \
  --host "$MD_PGHOST" \
  --port "${MD_PGPORT:-5432}" \
  --username "${MD_PGUSER:-postgres}" \
  --dbname "$MD_PGDATABASE" \
  --set ON_ERROR_STOP=1 \
  --quiet \
  --file "$GEO_SEED_FILE"

if [ -f "/seed/meta_data/lookup-data/g2p_attributes.sql" ]; then
  echo "[db-seed] Applying master data attributes to ${MD_PGDATABASE}@${MD_PGHOST}:${MD_PGPORT:-5432} ..."
  PGPASSWORD="${MD_PGPASSWORD:-}" psql \
    --host "$MD_PGHOST" --port "${MD_PGPORT:-5432}" \
    --username "${MD_PGUSER:-postgres}" --dbname "$MD_PGDATABASE" \
    --file "/seed/meta_data/lookup-data/g2p_attributes.sql" || true
fi

if [ -f "/seed/meta_data/lookup-data/g2p_attribute_values.sql" ]; then
  echo "[db-seed] Applying master data attribute values to ${MD_PGDATABASE}@${MD_PGHOST}:${MD_PGPORT:-5432} ..."
  PGPASSWORD="${MD_PGPASSWORD:-}" psql \
    --host "$MD_PGHOST" --port "${MD_PGPORT:-5432}" \
    --username "${MD_PGUSER:-postgres}" --dbname "$MD_PGDATABASE" \
    --file "/seed/meta_data/lookup-data/g2p_attribute_values.sql" || true
fi

PGPASSWORD="${MD_PGPASSWORD:-}" psql \
  --host "$MD_PGHOST" --port "${MD_PGPORT:-5432}" \
  --username "${MD_PGUSER:-postgres}" --dbname "$MD_PGDATABASE" \
  --tuples-only --no-align \
  --command "SELECT '[geo-seed] ' || (SELECT count(*) FROM g2p_geo_levels) || ' geo levels, ' || (SELECT count(*) FROM g2p_geo_level_values) || ' values, ' || (SELECT count(*) FROM g2p_attributes) || ' attributes, ' || (SELECT count(*) FROM g2p_attribute_values) || ' attribute values'"

rewrite_approver_rules() {
  if [ "${AWE_DB_SEED_ENABLED:-false}" != "true" ]; then
    echo "[db-seed] approver-resolver rules: skipped (AWE_DB_SEED_ENABLED=${AWE_DB_SEED_ENABLED:-false})."
    return
  fi
  if [ -z "${AWE_PGHOST:-}" ] || [ -z "${AWE_PGDATABASE:-}" ]; then
    echo "[db-seed] approver-resolver rules: skipped (AWE_PGHOST/AWE_PGDATABASE not set)."
    return
  fi
  base="${APPROVER_RESOLVER_BASE_URL:-}"
  if [ -z "$base" ]; then
    case "${AWE_CALLBACK_CALLER_SERVICE:-}" in
      http://*|https://*)
        base=$(printf '%s' "$AWE_CALLBACK_CALLER_SERVICE" | sed -E 's#^(https?://[^/]+).*$#\1#') ;;
      *)
        base="http://staff-api:8000" ;;
    esac
  fi
  base=$(printf '%s' "$base" | sed -E 's#/+$##')
  secret="${APPROVER_RESOLVER_SECRET:-cropsown-approver-resolver-secret}"
  export PGHOST="$AWE_PGHOST" PGPORT="${AWE_PGPORT:-5432}" PGDATABASE="$AWE_PGDATABASE" PGUSER="${AWE_PGUSER:-}" PGPASSWORD="${AWE_PGPASSWORD:-}"
  echo "[db-seed] approver-resolver rules: pointing the http rules at ${base}/cropsown/approver-resolver?level=<level>&secret=*** ..."
  n=$(psql -At -v ON_ERROR_STOP=1 -v base="$base" -v secret="$secret" <<'SQL'
WITH changed AS (
  UPDATE approver_rule
     SET rule_value = jsonb_set(rule_value::jsonb, '{url}',
           to_jsonb(:'base' || '/cropsown/approver-resolver?level='
                    || substring(rule_value::jsonb->>'url' from 'level=([a-z]+)')
                    || '&secret=' || :'secret'))::json
   WHERE rule_type = 'http'
     AND rule_value::jsonb->>'url' LIKE '%/cropsown/approver-resolver%'
     AND rule_value::jsonb->>'url' <> (:'base' || '/cropsown/approver-resolver?level='
                    || substring(rule_value::jsonb->>'url' from 'level=([a-z]+)')
                    || '&secret=' || :'secret')
  RETURNING 1)
SELECT count(*) FROM changed;
SQL
  ) || { echo "[db-seed] approver-resolver rules: FAILED (see errors above) — AWE will not find approvers until the rule URLs point at this staff-api."; return; }
  total=$(psql -At -c "SELECT count(*) FROM approver_rule WHERE rule_type='http' AND rule_value::jsonb->>'url' LIKE '%/cropsown/approver-resolver%';" 2>/dev/null || echo "?")
  echo "[db-seed] approver-resolver rules: ${n} rewritten, ${total} in place."
}

rewrite_approver_rules
