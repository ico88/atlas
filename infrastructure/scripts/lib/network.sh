# shellcheck shell=bash
# ZeroTier / overlay-network helpers for the ATLAS installer (ROADMAP PR 5).
# Sourced, not executed — the calling script owns 'set -euo pipefail'.
#
# ZeroTier gives worker nodes a stable, private overlay address to reach the
# control plane across NAT/LANs without opening ports. Installation touches the
# HOST (systemd service + a /dev/net/tun device), so it is done here rather than
# inside a container. Every function is tolerant: a missing CLI or a failed join
# warns but never aborts the install.

# valid_zerotier_network_id ID — a 16-hex-char network id.
valid_zerotier_network_id() {
  printf '%s' "${1:-}" | grep -qE '^[0-9a-fA-F]{16}$'
}

# zerotier_installed — true if the CLI is present.
zerotier_installed() {
  command -v zerotier-cli >/dev/null 2>&1
}

# install_zerotier — install ZeroTier One via the official script (idempotent).
# Honors $SUDO (may be empty). Returns non-zero on failure (caller decides).
install_zerotier() {
  if zerotier_installed; then
    log "ZeroTier already installed ($(zerotier-cli -v 2>/dev/null || echo present))."
    return 0
  fi
  log "Installing ZeroTier One (official install script)..."
  # The vendor script verifies its own GPG signature before installing.
  if ! curl -fsSL https://install.zerotier.com | $SUDO bash; then
    warn "ZeroTier installation failed; the node will use its LAN address instead."
    return 1
  fi
  $SUDO systemctl enable --now zerotier-one 2>/dev/null \
    || warn "Could not enable zerotier-one via systemctl (no systemd?)."
  return 0
}

# zerotier_join NETWORK_ID — join a network (idempotent). Honors $SUDO.
zerotier_join() {
  local nwid="$1"
  if ! valid_zerotier_network_id "$nwid"; then
    err "Invalid ZeroTier network id '$nwid' (expected 16 hex characters)."
    return 1
  fi
  zerotier_installed || { warn "zerotier-cli not available; cannot join."; return 1; }
  log "Joining ZeroTier network ${nwid}..."
  $SUDO zerotier-cli join "$nwid" || { warn "ZeroTier join failed."; return 1; }
  return 0
}

# zerotier_node_id — this host's ZeroTier address (empty if unavailable). Honors $SUDO.
zerotier_node_id() {
  zerotier_installed || return 0
  $SUDO zerotier-cli info 2>/dev/null | awk '/ info /{print $3; exit}'
}

# zerotier_managed_ip NETWORK_ID — first assigned overlay IP for a network. Honors $SUDO.
zerotier_managed_ip() {
  local nwid="$1"
  zerotier_installed || return 0
  $SUDO zerotier-cli -j listnetworks 2>/dev/null \
    | grep -oE '"'"$nwid"'"[^}]*"assignedAddresses":\[[^]]*\]' \
    | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | head -1
}

# print_zerotier_status NETWORK_ID — human-friendly summary after a join. Honors $SUDO.
print_zerotier_status() {
  local nwid="$1" node_id ip
  node_id="$(zerotier_node_id)"
  log "ZeroTier node id: ${node_id:-unknown}"
  warn "Authorize this node in ZeroTier Central (network ${nwid}) if the network is private."
  # The managed IP appears only after the controller authorizes the member.
  ip="$(zerotier_managed_ip "$nwid")"
  if [ -n "$ip" ]; then
    log "ZeroTier managed IP on ${nwid}: ${ip}"
  else
    warn "No managed IP yet — it appears once the node is authorized in ZeroTier Central."
  fi
}
