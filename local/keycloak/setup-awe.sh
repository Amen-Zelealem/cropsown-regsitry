#!/usr/bin/env bash
set -euo pipefail

KCADM="/opt/keycloak/bin/kcadm.sh"
KEYCLOAK_URL="http://localhost:8080"
KEYCLOAK_REALM="staff"

echo "Logging in to master realm..."
"${KCADM}" config credentials --server "${KEYCLOAK_URL}" --realm master --user admin --password admin

client_internal_id() {
  local cid="$1"
  "${KCADM}" get clients -r "${KEYCLOAK_REALM}" -q "clientId=${cid}" --fields id 2>/dev/null \
    | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
    | head -1
}

# 1. awe-admin-portal
PORTAL_UUID="$(client_internal_id "awe-admin-portal" || true)"
if [[ -z "${PORTAL_UUID}" ]]; then
  echo "Creating client awe-admin-portal..."
  "${KCADM}" create clients -r "${KEYCLOAK_REALM}" \
    -s "clientId=awe-admin-portal" \
    -s enabled=true \
    -s publicClient=true \
    -s standardFlowEnabled=true \
    -s directAccessGrantsEnabled=true \
    -s 'redirectUris=["http://localhost:8033/*","http://127.0.0.1:8033/*","http://portal.localtest.me:8033/*"]' \
    -s 'webOrigins=["+"]'
  PORTAL_UUID="$(client_internal_id "awe-admin-portal")"
else
  echo "Updating client awe-admin-portal..."
  "${KCADM}" update "clients/${PORTAL_UUID}" -r "${KEYCLOAK_REALM}" \
    -s 'redirectUris=["http://localhost:8033/*","http://127.0.0.1:8033/*","http://portal.localtest.me:8033/*"]' \
    -s 'webOrigins=["+"]'
fi

# Roles for awe-admin-portal
for role in AWE_ADMIN AWE_VIEWER; do
  if ! "${KCADM}" get "clients/${PORTAL_UUID}/roles/${role}" -r "${KEYCLOAK_REALM}" >/dev/null 2>&1; then
    echo "Creating role ${role} on awe-admin-portal..."
    "${KCADM}" create "clients/${PORTAL_UUID}/roles" -r "${KEYCLOAK_REALM}" -s "name=${role}"
  fi
done

# 2. awe-admin-resolver
RESOLVER_UUID="$(client_internal_id "awe-admin-resolver" || true)"
if [[ -z "${RESOLVER_UUID}" ]]; then
  echo "Creating client awe-admin-resolver..."
  "${KCADM}" create clients -r "${KEYCLOAK_REALM}" \
    -s "clientId=awe-admin-resolver" \
    -s enabled=true \
    -s publicClient=false \
    -s secret="dev-awe-resolver-secret" \
    -s serviceAccountsEnabled=true \
    -s standardFlowEnabled=false \
    -s directAccessGrantsEnabled=false
  RESOLVER_UUID="$(client_internal_id "awe-admin-resolver")"
fi

# Service account roles
for role in view-users view-clients query-groups; do
  "${KCADM}" add-roles -r "${KEYCLOAK_REALM}" \
    --uusername "service-account-awe-admin-resolver" \
    --cclientid realm-management \
    --rolename "${role}" >/dev/null 2>&1 || true
done

# 3. Approver users
ensure_user() {
  local uname="$1"
  local pass="$2"
  local email="$3"
  local fname="$4"
  local lname="$5"

  local uid
  uid="$("${KCADM}" get users -r "${KEYCLOAK_REALM}" -q "username=${uname}" -q "exact=true" --fields id 2>/dev/null \
    | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
    | head -1)"

  if [[ -z "${uid}" ]]; then
    echo "Creating user ${uname}..."
    "${KCADM}" create users -r "${KEYCLOAK_REALM}" \
      -s "username=${uname}" \
      -s enabled=true \
      -s "email=${email}" \
      -s emailVerified=true \
      -s "firstName=${fname}" \
      -s "lastName=${lname}"
  else
    echo "User ${uname} already exists"
  fi

  "${KCADM}" set-password -r "${KEYCLOAK_REALM}" \
    --username "${uname}" \
    --new-password "${pass}" \
    --temporary=false
}

ensure_user "admin" "admin" "admin@localhost" "Staff" "Admin"
ensure_user "alex.carter" "pass" "alex.carter@email.com" "Alex" "Carter"
ensure_user "nina.patel" "pass" "nina.patel@email.com" "Nina" "Patel"

# Assign AWE_ADMIN to admin, alex.carter, nina.patel
for u in admin alex.carter nina.patel; do
  "${KCADM}" add-roles -r "${KEYCLOAK_REALM}" \
    --uusername "${u}" \
    --cclientid "awe-admin-portal" \
    --rolename "AWE_ADMIN" >/dev/null 2>&1 || true
done

echo "Keycloak AWE setup completed successfully!"
