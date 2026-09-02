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
# Control-plane AI options (ROADMAP PR 2):
#   --with-ollama                 enable local AI (Ollama) + 'ai' compose profile
#   --without-ollama              install without local inference (echo fallback)
#   --ollama-model <name:tag>     chat model to install (default llama3.2)
#   --with-ollama-embeddings      use Ollama embeddings for RAG
#   --embedding-model <name:tag>  embedding model (default nomic-embed-text)
#   --gpu auto|nvidia|rocm|vulkan|cpu   acceleration backend (default auto)
#   --allow-experimental-gpu      allow auto-selecting the Vulkan backend
#   --allow-cpu-fallback          allow CPU when a requested GPU is unavailable
#
# Node networking options (ROADMAP PR 5):
#   --network-provider none|zerotier|existing   overlay network for the node
#   --zerotier-network-id <16-hex>              ZeroTier network to join
#   --await-enrollment                          wait for control-plane enrollment
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

# Shared libraries (log/set_env_var already defined above are kept; libs add
# GPU + Ollama helpers).
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/atlas-lib.sh"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/gpu.sh"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/ollama.sh"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/network.sh"

# --- defaults / CLI args --------------------------------------------------
ROLE=""
ASSUME_YES=0
NO_START=0
MANAGER_URL=""
NODE_TOKEN=""
NODE_ID=""
NODE_LABEL=""
NODE_CAPS=""
# Ollama / GPU (control-plane)
WITH_OLLAMA=""            # "", "1" or "0" (unset => ask/interactive default yes)
OLLAMA_MODEL="llama3.2"
WITH_OLLAMA_EMB=0
EMBEDDING_MODEL="nomic-embed-text"
GPU_MODE="auto"           # auto|nvidia|rocm|vulkan|cpu
ALLOW_EXPERIMENTAL_GPU=0
ALLOW_CPU_FALLBACK=0
# Node networking (ROADMAP PR 5)
NETWORK_PROVIDER=""       # none|zerotier|existing (unset => ask for nodes)
ZEROTIER_NETWORK_ID=""
AWAIT_ENROLLMENT=0

usage() {
  sed -n '2,/^# ===/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
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
    --with-ollama) WITH_OLLAMA=1; shift ;;
    --without-ollama) WITH_OLLAMA=0; shift ;;
    --ollama-model) OLLAMA_MODEL="${2:-}"; WITH_OLLAMA=1; shift 2 ;;
    --with-ollama-embeddings) WITH_OLLAMA_EMB=1; WITH_OLLAMA=1; shift ;;
    --embedding-model) EMBEDDING_MODEL="${2:-}"; shift 2 ;;
    --gpu) GPU_MODE="${2:-auto}"; shift 2 ;;
    --allow-experimental-gpu) ALLOW_EXPERIMENTAL_GPU=1; shift ;;
    --allow-cpu-fallback) ALLOW_CPU_FALLBACK=1; shift ;;
    --network-provider) NETWORK_PROVIDER="${2:-none}"; shift 2 ;;
    --zerotier-network-id) ZEROTIER_NETWORK_ID="${2:-}"; NETWORK_PROVIDER="zerotier"; shift 2 ;;
    --await-enrollment) AWAIT_ENROLLMENT=1; shift ;;
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
  ensure_http_port
  configure_ollama
  warn "Set a strong POSTGRES_PASSWORD in .env before production use."
}

# Configure local AI (Ollama) + GPU acceleration for the control plane.
configure_ollama() {
  # Decide whether to enable Ollama (interactive default: yes).
  if [ -z "$WITH_OLLAMA" ]; then
    local ans="yes"
    prompt ans "Enable local AI with Ollama? (downloads a model)" "yes"
    case "$ans" in y|yes|Y|YES) WITH_OLLAMA=1 ;; *) WITH_OLLAMA=0 ;; esac
  fi

  mkdir -p "${REPO_ROOT}/.atlas/state"

  if [ "$WITH_OLLAMA" != "1" ]; then
    log "Local AI disabled — using the built-in echo provider."
    set_env_var "ATLAS_OLLAMA_URL" "" "$ENV_FILE"
    set_env_var "ATLAS_DEFAULT_MODEL" "" "$ENV_FILE"
    set_env_var "ATLAS_USE_OLLAMA_EMBEDDINGS" "false" "$ENV_FILE"
    rm -f "${REPO_ROOT}/.atlas/state/ollama.enabled"
    generate_gpu_override "$REPO_ROOT" cpu
    return
  fi

  prompt OLLAMA_MODEL "Chat model to install" "${OLLAMA_MODEL}"
  if ! validate_model_name "$OLLAMA_MODEL"; then
    err "Invalid model name '$OLLAMA_MODEL'"; exit 1
  fi
  set_env_var "ATLAS_OLLAMA_URL" "http://ollama:11434" "$ENV_FILE"
  set_env_var "ATLAS_DEFAULT_MODEL" "$OLLAMA_MODEL" "$ENV_FILE"

  if [ "$WITH_OLLAMA_EMB" = "1" ]; then
    prompt EMBEDDING_MODEL "Embedding model" "${EMBEDDING_MODEL}"
    set_env_var "ATLAS_USE_OLLAMA_EMBEDDINGS" "true" "$ENV_FILE"
    set_env_var "ATLAS_EMBEDDING_MODEL" "$EMBEDDING_MODEL" "$ENV_FILE"
  else
    set_env_var "ATLAS_USE_OLLAMA_EMBEDDINGS" "false" "$ENV_FILE"
  fi

  touch "${REPO_ROOT}/.atlas/state/ollama.enabled"
  resolve_and_write_gpu
}

# Resolve the GPU backend (respecting --gpu) and generate the Compose override.
resolve_and_write_gpu() {
  local backend="$GPU_MODE"
  if [ "$GPU_MODE" = "auto" ]; then
    backend="$(detect_gpu_backend)"
    if [ "$backend" = "vulkan" ] && [ "$ALLOW_EXPERIMENTAL_GPU" != "1" ]; then
      warn "Detected an AMD/Vulkan GPU (experimental Ollama backend)."
      local ans="yes"
      prompt ans "Enable experimental Vulkan acceleration? (else CPU)" "yes"
      case "$ans" in y|yes|Y|YES) : ;; *) backend="cpu" ;; esac
    fi
    log "GPU auto-detection selected backend: ${backend}"
  else
    # Explicit backend requested: in non-interactive mode a mismatch is an error.
    local detected
    detected="$(detect_gpu_backend)"
    if [ "$backend" != "cpu" ] && [ "$detected" = "cpu" ] && [ "$ALLOW_CPU_FALLBACK" != "1" ]; then
      if [ "$ASSUME_YES" = "1" ]; then
        err "Requested --gpu $backend but no GPU detected (use --allow-cpu-fallback)."
        exit 1
      fi
      warn "Requested --gpu $backend but no GPU detected; continuing (may fall back to CPU)."
    fi
  fi
  generate_gpu_override "$REPO_ROOT" "$backend"
  check_render_permissions "$TARGET_USER" || true
}

# After the stack is up, pull the model and verify (control plane + Ollama).
post_start_ollama() {
  [ "${WITH_OLLAMA:-0}" = "1" ] || return 0
  [ "${STACK_STARTED:-0}" = "1" ] || return 0
  export SUDO
  ATLAS_COMPOSE="$(atlas_compose_cmd "$REPO_ROOT")"
  export ATLAS_COMPOSE
  log "Waiting for Ollama to become ready..."
  if ! wait_for_ollama 180; then
    warn "Ollama did not become ready in time; pull the model later with: make model-pull MODEL=$OLLAMA_MODEL"
    return 0
  fi
  if pull_model "$OLLAMA_MODEL"; then
    if [ "$WITH_OLLAMA_EMB" = "1" ]; then
      pull_model "$EMBEDDING_MODEL" || warn "Embedding model pull failed."
    fi
    smoke_test_model "$OLLAMA_MODEL" && log "Model '$OLLAMA_MODEL' responded." \
      || warn "Smoke test did not confirm a response (model may still be loading)."
    refresh_atlas_models || warn "Could not refresh the model registry (backend starting?)."
  else
    warn "Model pull failed; the app runs with the echo provider until a model is available."
  fi
}

port_in_use() {
  local p="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "( sport = :$p )" 2>/dev/null | grep -q LISTEN
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1
  else
    (exec 3<>"/dev/tcp/127.0.0.1/$p") 2>/dev/null && { exec 3>&- 3<&-; return 0; } || return 1
  fi
}

effective_http_port() {
  grep -E '^ATLAS_HTTP_PORT=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- | head -1
}

# Best-effort primary LAN IP so the user can open ATLAS from another machine.
server_ip() {
  local ip
  ip="$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
  [ -z "$ip" ] && ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  echo "${ip:-<server-ip>}"
}

# Pick a host port for the reverse proxy. If 80 (or the configured port) is taken
# — e.g. a system nginx/apache — fall back to a free port instead of clobbering
# another service's config. The user can reclaim 80 by freeing it and setting
# ATLAS_HTTP_PORT=80 in .env.
ensure_http_port() {
  local current desired
  current="$(effective_http_port)"
  desired="${current:-80}"
  if ! port_in_use "$desired"; then
    set_env_var ATLAS_HTTP_PORT "$desired"
    return
  fi
  warn "Host port $desired is already in use (likely a system web server such as nginx)."
  local candidate
  for candidate in 8080 8081 8090 8888 9080; do
    if ! port_in_use "$candidate"; then
      set_env_var ATLAS_HTTP_PORT "$candidate"
      warn "Falling back to host port $candidate (not overwriting the other server)."
      warn "To use port 80 instead: stop the other server (e.g. 'sudo systemctl stop nginx')"
      warn "then set ATLAS_HTTP_PORT=80 in .env and re-run 'docker compose up -d'."
      return
    fi
  done
  warn "No free fallback port found; leaving ATLAS_HTTP_PORT=$desired (startup may fail)."
  set_env_var ATLAS_HTTP_PORT "$desired"
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

  configure_node_network
  # A fresh bootstrap token for the local Setup UI so its guarded actions
  # (re-enroll) require a code shown at agent startup.
  if [ -z "$(get_env_var ATLAS_NODE_BOOTSTRAP_TOKEN "$ENV_FILE")" ]; then
    set_env_var "ATLAS_NODE_BOOTSTRAP_TOKEN" "$(openssl rand -hex 4)"
  fi
  [ "$AWAIT_ENROLLMENT" = "1" ] && set_env_var "ATLAS_NODE_AWAIT_ENROLLMENT" "true"
}

# Configure the node's overlay network (ROADMAP PR 5).
configure_node_network() {
  if [ -z "$NETWORK_PROVIDER" ]; then
    local ans="none"
    prompt ans "Overlay network for this node? (none/zerotier)" "none"
    NETWORK_PROVIDER="$ans"
  fi
  case "$NETWORK_PROVIDER" in
    zerotier)
      set_env_var "ATLAS_NETWORK_PROVIDER" "zerotier"
      if [ -z "$ZEROTIER_NETWORK_ID" ]; then
        prompt ZEROTIER_NETWORK_ID "ZeroTier network id (16 hex chars)" ""
      fi
      if ! valid_zerotier_network_id "$ZEROTIER_NETWORK_ID"; then
        warn "No valid ZeroTier network id given — skipping ZeroTier setup."
        set_env_var "ATLAS_NETWORK_PROVIDER" "none"
        return
      fi
      set_env_var "ATLAS_ZEROTIER_NETWORK_ID" "$ZEROTIER_NETWORK_ID"
      if install_zerotier && zerotier_join "$ZEROTIER_NETWORK_ID"; then
        print_zerotier_status "$ZEROTIER_NETWORK_ID"
      fi
      ;;
    existing)
      set_env_var "ATLAS_NETWORK_PROVIDER" "existing"
      log "Using the existing network — reach the control plane at ${MANAGER_URL}."
      ;;
    *)
      set_env_var "ATLAS_NETWORK_PROVIDER" "none"
      ;;
  esac
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
    # Base + optional GPU override + optional 'ai' profile (Ollama).
    compose_args="$(compose_files "$REPO_ROOT") $(ollama_profile "$REPO_ROOT")"
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
  local port base ipbase suffix ip
  port="$(effective_http_port)"
  suffix=""
  if [ -n "$port" ] && [ "$port" != "80" ]; then
    suffix=":${port}"
  fi
  base="http://localhost${suffix}"
  ip="$(server_ip)"
  ipbase="http://${ip}${suffix}"
  if [ "$ROLE" = "node" ]; then
    local setup_port
    setup_port="$(get_env_var ATLAS_NODE_SETUP_UI_PORT "$ENV_FILE")"
    setup_port="${setup_port:-8971}"
    if [ "$started" = "1" ]; then
      cat <<EOF

  The node agent is running and registering with ${MANAGER_URL}.
  Check it on the manager: GET /api/v1/nodes  or the UI "Nodes" page.

  Node Setup UI (local status & diagnostics, no secrets):
      http://127.0.0.1:${setup_port}/
      (remote? tunnel it: ssh -L ${setup_port}:127.0.0.1:${setup_port} ${TARGET_USER}@$(server_ip))
  The one-time bootstrap code for guarded actions is printed in the agent log:
      cd ${REPO_ROOT} && docker compose -f docker-compose.node.yml logs -f
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

  ATLAS is running. Open in a browser:

      ${ipbase}/            <-- from another machine (the server address)
      ${base}/             <-- from this machine

  (System Status: ${ipbase}/system   health: ${ipbase}/health)
  Logs:  cd ${REPO_ROOT} && docker compose logs -f
  Stop:  cd ${REPO_ROOT} && docker compose down
  Firewall: ensure port ${port:-80}/tcp is open (e.g. 'sudo ufw allow ${port:-80}/tcp').

  To add a worker node later, run this installer on that machine with:
    sudo ./infrastructure/scripts/install.sh --role node \\
         --manager-url http://<this-host>:80 --token <ATLAS_NODE_JOIN_TOKEN>
EOF
    else
      cat <<EOF

  cd ${REPO_ROOT}
  docker compose up --build          # or: make up
  Open:  ${base}/system   ${base}/health
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
  [ "$ROLE" = "control-plane" ] && post_start_ollama
  print_next_steps
}

main "$@"
