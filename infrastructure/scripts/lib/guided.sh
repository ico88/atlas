# shellcheck shell=bash
# Guided node install: verification + manager autodiscovery (ROADMAP PR 5+).
# Sourced by install.sh. Pure helpers are unit-tested; network helpers curl with
# a timeout and degrade gracefully (a failure warns, never aborts the install).

# cp_health_url URL — normalized control-plane health endpoint. Pure.
cp_health_url() {
  local u="${1%/}"
  printf '%s/api/v1/system/status' "$u"
}

# cp_reachable URL [timeout] — 0 if the control plane answers its health check.
cp_reachable() {
  local url timeout
  url="$(cp_health_url "$1")"
  timeout="${2:-3}"
  curl -fsS --max-time "$timeout" "$url" 2>/dev/null | grep -q '"status"'
}

# local_ipv4 — primary LAN IPv4 of this host (best-effort, may be empty).
local_ipv4() {
  if command -v ip >/dev/null 2>&1; then
    ip -4 route get 1.1.1.1 2>/dev/null \
      | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}'
  else
    hostname -I 2>/dev/null | awk '{print $1}'
  fi
}

# subnet_prefix IP — the first three octets (e.g. 192.168.1). Pure.
subnet_prefix() {
  printf '%s' "${1:-}" | grep -oE '^[0-9]+\.[0-9]+\.[0-9]+'
}

# discover_candidates LOCAL_IP [ENV_URL] — candidate manager base URLs, one per
# line, most-likely first. Pure (no network), so it is unit-tested.
discover_candidates() {
  local ip="${1:-}" env_url="${2:-}" pfx
  [ -n "$env_url" ] && printf '%s\n' "${env_url%/}"
  printf '%s\n' "http://host.docker.internal"
  pfx="$(subnet_prefix "$ip")"
  if [ -n "$pfx" ]; then
    printf '%s\n' "http://${pfx}.1" "http://${pfx}.254"
  fi
}

# discover_manager [ENV_URL] — echo the first reachable manager base URL on the
# LAN, or return non-zero. Used as a ZeroTier-KO fallback so the user still
# reaches the control plane without hand-entering an IP.
discover_manager() {
  local env_url="${1:-}" ip cand
  ip="$(local_ipv4)"
  while IFS= read -r cand; do
    [ -n "$cand" ] || continue
    if cp_reachable "$cand" 2; then
      printf '%s' "$cand"
      return 0
    fi
  done < <(discover_candidates "$ip" "$env_url")
  return 1
}

# zerotier_wait_authorized NETWORK [timeout] — poll until the controller assigns
# a managed IP (i.e. the node is authorized). Echoes the IP on success.
zerotier_wait_authorized() {
  local nwid="$1" timeout="${2:-60}" waited=0 ip
  while [ "$waited" -lt "$timeout" ]; do
    ip="$(zerotier_managed_ip "$nwid")"
    if [ -n "$ip" ]; then
      printf '%s' "$ip"
      return 0
    fi
    sleep 3
    waited=$((waited + 3))
  done
  return 1
}

# wait_node_registered CP_URL NODE_ID [timeout] — poll the control plane until
# this node appears in its node list (the real "match" after startup).
wait_node_registered() {
  local cp="${1%/}" node_id="$2" timeout="${3:-90}" waited=0
  while [ "$waited" -lt "$timeout" ]; do
    if curl -fsS --max-time 3 "${cp}/api/v1/nodes" 2>/dev/null | grep -q "\"${node_id}\""; then
      return 0
    fi
    sleep 3
    waited=$((waited + 3))
  done
  return 1
}
