#!/usr/bin/env bash
# Put a Jenkins agent on the openg2p-Gen2 WireGuard VPN, so the dev deploy can
# reach the cluster.
#
# The dev cluster's API server — https://10.0.1.58:6443 in the gen2-kubeconfig
# credential, the same address rancher.openg2p.test resolves to — is routable
# only over the openg2p-Gen2 WireGuard VPN. An agent off the VPN builds and
# pushes the images, then fails the dev deploy with
#
#   Error: kubernetes cluster unreachable: Get "https://10.0.1.58:6443/version":
#   dial tcp 10.0.1.58:6443: i/o timeout
#
# Run this ONCE, as root, on the machine that runs the pipeline's builds — the
# Deploy to Dev stage runs on the same agent as the build. If Jenkins itself runs
# in a container, run it on the HOST: the container's traffic leaves through the
# host's routes.
#
# It needs a peer config issued for THIS agent by whoever administers the
# openg2p-Gen2 WireGuard server. Never reuse a person's peer config: two
# machines on one key keep stealing the peer's endpoint from each other, and
# both tunnels drop in turn.
#
# What it does:
#   1. installs wireguard-tools (apt-get, dnf or yum) when wg-quick is missing
#   2. writes /etc/wireguard/<iface>.conf (mode 0600) from the peer config, with
#      - AllowedIPs narrowed to the API server. The deploy talks to the API
#        server and nothing else on the dev network; the cluster pulls the
#        images from ECR itself. A peer config handed out for a person usually
#        routes the whole dev network — or everything, with 0.0.0.0/0, which
#        would send the agent's ECR pushes through the VPN too.
#      - the DNS line dropped. The kubeconfig names the server by IP, and
#        wg-quick hands DNS to resolvconf, which a bare agent often lacks — the
#        tunnel would fail to start over a setting nothing uses.
#      - PersistentKeepalive = 25 added when absent, so a NAT in front of the
#        agent keeps the tunnel's mapping alive between builds.
#   3. enables wg-quick@<iface>, so the tunnel comes back after a reboot
#   4. checks that the API server answers through it
#
# Usage:
#   sudo ./ci/setup-agent-vpn.sh <peer.conf> [options]
#
#   ./ci/setup-agent-vpn.sh jenkins-agent.conf --dry-run   # show what would be
#                                                          # written, keys hidden
# Options:
#   --allowed-ips CIDR[,CIDR]  routed through the tunnel (default 10.0.1.58/32)
#   --iface NAME               interface / config name (default openg2p-gen2)
#   --check HOST:PORT          must accept a connection once up (default 10.0.1.58:6443)
#   --dry-run                  print the config that would be written and stop
set -euo pipefail

ALLOWED_IPS="10.0.1.58/32"
IFACE="openg2p-gen2"
CHECK="10.0.1.58:6443"
DRY_RUN=false
PEER_CONF=""

die()  { echo "ERROR: $*" >&2; exit 1; }
note() { echo "=== $* ==="; }
# The header comment is the help text.
usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --allowed-ips) ALLOWED_IPS="$2"; shift 2 ;;
    --iface)       IFACE="$2";       shift 2 ;;
    --check)       CHECK="$2";       shift 2 ;;
    --dry-run)     DRY_RUN=true;     shift ;;
    -h|--help)     usage 0 ;;
    -*)            echo "unknown option: $1" >&2; usage 2 ;;
    *)             [ -z "$PEER_CONF" ] || die "one peer config only"; PEER_CONF="$1"; shift ;;
  esac
done

[ -n "$PEER_CONF" ] || { echo "usage: $0 <peer.conf> [options]   (--help for more)" >&2; exit 2; }
[ -r "$PEER_CONF" ] || die "cannot read $PEER_CONF"

# A config missing any of these would come up as an interface that routes
# nowhere, and the only symptom would be the same timeout this is here to fix.
for want in '\[Interface\]' PrivateKey Address '\[Peer\]' PublicKey Endpoint; do
  grep -Eq "^[[:space:]]*${want}" "$PEER_CONF" \
    || die "$PEER_CONF has no ${want//\\/} line — is it a WireGuard peer config?"
done
[ "$(grep -Ec '^\[Peer\]' "$PEER_CONF")" -eq 1 ] || die "$PEER_CONF has more than one [Peer]; expected the one VPN server"

# Rewrite rather than copy: see the header for why each line changes. CRLF is
# stripped too, since a config saved on Windows breaks wg-quick's parser.
render() {
  tr -d '\r' < "$PEER_CONF" \
    | sed -E '/^[[:space:]]*DNS[[:space:]]*=/d' \
    | sed -E "s|^[[:space:]]*AllowedIPs[[:space:]]*=.*|AllowedIPs = ${ALLOWED_IPS}|" \
    | awk -v ka="$(grep -Eq '^[[:space:]]*PersistentKeepalive' "$PEER_CONF" && echo yes)" '
        { print }
        /^\[Peer\]/ && ka != "yes" { print "PersistentKeepalive = 25" }'
}
grep -Eq '^[[:space:]]*AllowedIPs' "$PEER_CONF" || die "$PEER_CONF has no AllowedIPs line to narrow"

if [ "$DRY_RUN" = true ]; then
  note "would write /etc/wireguard/${IFACE}.conf (keys hidden)"
  render | sed -E 's/^((PrivateKey|PresharedKey)[[:space:]]*=).*/\1 <hidden>/'
  exit 0
fi

[ "$(id -u)" -eq 0 ] || die "run as root (sudo) — this installs a package and a network interface"

if ! command -v wg-quick >/dev/null; then
  note "installing wireguard-tools"
  if   command -v apt-get >/dev/null; then apt-get update -qq && apt-get install -y -qq wireguard-tools
  elif command -v dnf     >/dev/null; then dnf install -y -q wireguard-tools
  elif command -v yum     >/dev/null; then yum install -y -q wireguard-tools
  else die "no apt-get, dnf or yum; install wireguard-tools, then re-run"
  fi
fi

note "writing /etc/wireguard/${IFACE}.conf"
install -d -m 0700 /etc/wireguard
( umask 077; render > "/etc/wireguard/${IFACE}.conf" )

note "bringing up ${IFACE}"
if command -v systemctl >/dev/null && [ -d /run/systemd/system ]; then
  systemctl enable "wg-quick@${IFACE}" >/dev/null
  systemctl restart "wg-quick@${IFACE}"
else
  echo "note: no systemd — the tunnel is up now but will NOT return after a reboot"
  wg-quick down "$IFACE" 2>/dev/null || true
  wg-quick up "$IFACE"
fi

note "checking ${CHECK} through the tunnel"
host="${CHECK%:*}"; port="${CHECK##*:}"
if timeout 15 bash -c "exec 3<>/dev/tcp/${host}/${port}" 2>/dev/null; then
  echo "ok — ${CHECK} accepts connections"
else
  wg show "$IFACE" || true
  die "${CHECK} did not answer. No 'latest handshake' above means the server never accepted this peer: check the Endpoint is reachable (UDP) and the server has this peer's public key."
fi

note "done — the agent is on the openg2p-Gen2 VPN; re-run the develop build"
