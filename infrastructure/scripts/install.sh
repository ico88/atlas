#!/usr/bin/env bash
# ===========================================================================
# ATLAS installer (role-aware).
#
# Target host: Ubuntu Server 24.04 LTS (spec §4).
# Installs Docker Engine + Compose plugin, git, make, curl, then configures the
# host for one of two ROLES:
#
#   control-plane  the manager: runs the full stack (frontend, backend, worker,
#                  PostgreSQL, Redis, Caddy). Run this on the primary server.
#   node           a worker: runs only the node agent, which registers with the
#                  control plane and sends heartbeats (spec §8, M4).
#
# Usage:
#   sudo ./infrastructure/scripts/install.sh                 # interactive
#   sudo ./infrastructure/scripts/install.sh --role node \
#        --manager-url http://10.0.0.1:80 --token <TOKEN> \
#        --capabilities llm,build --label gpu-1 [--yes]
#
# By default the installer also builds and starts the stack (delivering a
# ready-to-use system). Pass --no-start to only install prerequisites + config.
#
# The script is idempotent: re-running it is safe.
# ===========================================================================
set -euo pipefail

log()  { printf '\033[1;34m[atlas]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[atlas][warn]\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m[atlas][error]\033[0m %s\n' "$*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

# --- defaults / CLI args --------------------------------------------------
ROLE=""
ASSUME_YES=0
NO_START=0
MANAGER_URL=""
NODE_TOKEN=""
NODE_ID=""
NODE_LABEL=""
NODE_CAPS=""

usage() {
  sed -n '2,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --role) ROLE="${2:-}"; shift 2 ;;
    --manager-url) MANAGER_URL="${2:-}"; shift 2 ;;
    --token) NODE_TOKEN="${2:-}"; shift 2 ;;
    --node-id) NODE_ID="${2:-}"; shift 2 ;;
    --label) NODE_LABEL="${2:-}"; shift 2 ;;
    --capabilities) NODE_CAPS="${2:-}"; shift 2 ;;
    -y|--yes) ASSUME_YES=1; shift ;;
    --no-start) NO_START=1; shift ;;
    -h|--help) usage 0 ;;
    *) err "Unknown argument: $1"; usage 1 ;;
  esac
done

# --- privilege handling ---------------------------------------------------
if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
  TARGET_USER="${SUDO_USER:-root}"
else
  if ! command -v sudo >/dev/null 2>&1; then
    err "This script needs root privileges and 'sudo' is not available."
    exit 1
  fi
  SUDO="sudo"
  TARGET_USER="$(id -un)"
fi

prompt() {
  # prompt <var_name> <question> <default>
  local __var="$1" __q="$2" __def="${3:-}" __ans=""
  if [ "$ASSUME_YES" -eq 1 ] || [ ! -t 0 ]; then
    printf -v "$__var" '%s' "$__def"
    return
  fi
  if [ -n "$__def" ]; then
    read -rp "$__q [$__def]: " __ans || true
  else
    read -rp "$__q: " __ans || true
  fi
  printf -v "$__var" '%s' "${__ans:-$__def}"
}

# --- OS detection ---------------------------------------------------------
check_os() {
  if [ ! -r /etc/os-release ]; then
    warn "/etc/os-release not found; cannot verify the OS. Proceeding anyway."
    return
  fi
  # shellcheck disable=SC1091
  . /etc/os-release
  if [ "${ID:-}" != "ubuntu" ]; then
    warn "Detected '${PRETTY_NAME:-unknown}'. ATLAS targets Ubuntu Server 24.04 LTS (spec §4)."
  elif [ "${VERSION_ID:-}" != "24.04" ]; then
    warn "Detected Ubuntu ${VERSION_ID:-?}. The recommended version is 24.04 LTS."
  else
    log "Ubuntu 24.04 LTS detected."
  fi
}

install_base_packages() {
  log "Updating apt package index..."
  $SUDO apt-get update -y
  log "Installing base packages (ca-certificates, curl, git, make, gnupg, openssl)..."
  $SUDO apt-get install -y ca-certificates curl git make gnupg openssl
}

install_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    log "Docker Engine and Compose plugin already installed ($(docker --version))."
    return
  fi
  log "Setting up Docker's official apt repository..."
  $SUDO install -m 0755 -d /etc/apt/keyrings
  if [ ! -f /etc/apt/keyrings/docker.asc ]; then
    $SUDO curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    $SUDO chmod a+r /etc/apt/keyrings/docker.asc
  fi
  # shellcheck disable=SC1091
  . /etc/os-release
  local codename="${VERSION_CODENAME:-noble}"
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu ${codename} stable" \
    | $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null
  log "Installing Docker Engine, CLI, containerd, buildx and the Compose plugin..."
  $SUDO apt-get update -y
  $SUDO apt-get install -y \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  log "Enabling and starting the Docker service..."
  $SUDO systemctl enable --now docker || warn "Could not enable docker via systemctl (no systemd?)."
}

configure_docker_group() {
  [ "$TARGET_USER" = "root" ] && return
  if id -nG "$TARGET_USER" | tr ' ' '\n' | grep -qx docker; then
    log "User '$TARGET_USER' is already in the 'docker' group."
  else
    log "Adding user '$TARGET_USER' to the 'docker' group..."
    $SUDO usermod -aG docker "$TARGET_USER"
    warn "Log out and back in (or run 'newgrp docker') for this to take effect."
  fi
}

ensure_env_file() {
  if [ ! -f "$ENV_FILE" ]; then
    log "Creating .env from .env.example..."
    cp "${REPO_ROOT}/.env.example" "$ENV_FILE"
  fi
}

set_env_var() {
  # set_env_var KEY VALUE  (updates or appends KEY=VALUE in .env)
  local key="$1" val="$2"
  if grep -qE "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$val" >> "$ENV_FILE"
  fi
}

# --- role selection -------------------------------------------------------
select_role() {
  [ -n "$ROLE" ] && return
  if [ "$ASSUME_YES" -eq 1 ] || [ ! -t 0 ]; then
    ROLE="control-plane"
    return
  fi
  echo
  echo "Select installation role:"
  echo "  1) control-plane  (manager — runs the full stack)   [default]"
  echo "  2) node           (worker  — runs only the node agent)"
  local choice=""
  read -rp "Role [1]: " choice || true
  case "${choice:-1}" in
    2|node) ROLE="node" ;;
    *) ROLE="control-plane" ;;
  esac
}

configure_control_plane() {
  ensure_env_file
  log "Configuring host as CONTROL PLANE (manager)."
  local existing
  existing="$(grep -E '^ATLAS_NODE_JOIN_TOKEN=' "$ENV_FILE" | cut -d= -f2-)"
  if [ -z "$existing" ]; then
    local gen="yes"
    prompt gen "Generate a node join token now? (recommended)" "yes"
    if [ "$gen" = "yes" ] || [ "$gen" = "y" ]; then
      local token
      token="$(openssl rand -hex 32)"
      set_env_var "ATLAS_NODE_JOIN_TOKEN" "$token"
      log "Generated ATLAS_NODE_JOIN_TOKEN and wrote it to .env."
      warn "Share this token with each node (as ATLAS_NODE_TOKEN):"
      echo "    $token"
    fi
  else
    log "ATLAS_NODE_JOIN_TOKEN already set in .env — leaving it unchanged."
  fi
  warn "Set a strong POSTGRES_PASSWORD in .env before production use."
}

configure_node() {
  ensure_env_file
  log "Configuring host as NODE (worker)."
  prompt MANAGER_URL "Control plane URL" "${MANAGER_URL:-http://host.docker.internal:80}"
  prompt NODE_TOKEN  "Node join token (must match the manager)" "${NODE_TOKEN:-}"
  prompt NODE_ID     "Node id" "${NODE_ID:-$(hostname)}"
  prompt NODE_LABEL  "Node label" "${NODE_LABEL:-worker}"
  prompt NODE_CAPS   "Capabilities (comma separated)" "${NODE_CAPS:-build,test}"

  set_env_var "ATLAS_CONTROL_PLANE_URL" "$MANAGER_URL"
  set_env_var "ATLAS_NODE_TOKEN" "$NODE_TOKEN"
  set_env_var "ATLAS_NODE_ID" "$NODE_ID"
  set_env_var "ATLAS_NODE_LABEL" "$NODE_LABEL"
  set_env_var "ATLAS_NODE_CAPABILITIES" "$NODE_CAPS"
  log "Wrote node configuration to .env."
  [ -z "$NODE_TOKEN" ] && warn "No token set — the node will only be accepted if the control plane runs open (dev)."
}

verify() {
  log "Verifying installation..."
  docker --version || true
  docker compose version || true
}

# Bring the stack up so the installer delivers a ready-to-use system.
start_stack() {
  if [ "$NO_START" -eq 1 ]; then
    log "Skipping startup (--no-start). Start it yourself with the commands below."
    return 0
  fi
  local compose_args
  if [ "$ROLE" = "node" ]; then
    compose_args="-f docker-compose.node.yml"
    log "Building and starting the node agent (this can take a while)..."
  else
    compose_args=""
    log "Building and starting the full stack (this can take a while)..."
  fi
  # shellcheck disable=SC2086
  if (cd "$REPO_ROOT" && $SUDO docker compose $compose_args up -d --build); then
    STACK_STARTED=1
    log "Stack is up."
  else
    STACK_STARTED=0
    warn "Automatic startup failed. Bring it up manually with the command below."
  fi
}

print_next_steps() {
  log "Done (role: ${ROLE})."
  local started="${STACK_STARTED:-0}"
  if [ "$ROLE" = "node" ]; then
    if [ "$started" = "1" ]; then
      cat <<EOF

  The node agent is running and registering with ${MANAGER_URL}.
  Check it on the manager: GET /api/v1/nodes  or the UI "Nodes" page.
  Logs:  cd ${REPO_ROOT} && docker compose -f docker-compose.node.yml logs -f
EOF
    else
      cat <<EOF

  cd ${REPO_ROOT}
  docker compose -f docker-compose.node.yml up --build -d
EOF
    fi
  else
    if [ "$started" = "1" ]; then
      cat <<EOF

  ATLAS is running. Open:
    http://localhost/system   (System Status)
    http://localhost/health   (backend health)
  Logs:  cd ${REPO_ROOT} && docker compose logs -f
  Stop:  cd ${REPO_ROOT} && docker compose down

  To add a worker node later, run this installer on that machine with:
    sudo ./infrastructure/scripts/install.sh --role node \\
         --manager-url http://<this-host>:80 --token <ATLAS_NODE_JOIN_TOKEN>
EOF
    else
      cat <<EOF

  cd ${REPO_ROOT}
  docker compose up --build          # or: make up
  Open:  http://localhost/system   http://localhost/health
EOF
    fi
  fi
  if [ "$TARGET_USER" != "root" ] && ! id -nG "$TARGET_USER" | tr ' ' '\n' | grep -qx docker; then
    echo "  (For docker without sudo later: run 'newgrp docker' or re-login.)"
  fi
}

main() {
  log "Starting ATLAS installation."
  select_role
  check_os
  install_base_packages
  install_docker
  configure_docker_group
  case "$ROLE" in
    control-plane) configure_control_plane ;;
    node) configure_node ;;
    *) err "Invalid role: '$ROLE' (expected 'control-plane' or 'node')"; exit 1 ;;
  esac
  verify
  start_stack
  print_next_steps
}

main "$@"
