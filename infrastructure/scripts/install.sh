#!/usr/bin/env bash
# ===========================================================================
# ATLAS prerequisites installer.
#
# Target host: Ubuntu Server 24.04 LTS (spec §4).
# Installs: Docker Engine + Compose plugin, git, make, curl, ca-certificates.
# Prepares: a .env file from .env.example (if missing).
#
# Usage (from the repository root):
#     sudo ./infrastructure/scripts/install.sh
#     # or: make install
#
# The script is idempotent: re-running it is safe.
# ===========================================================================
set -euo pipefail

# --- pretty logging -------------------------------------------------------
log()  { printf '\033[1;34m[atlas]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[atlas][warn]\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m[atlas][error]\033[0m %s\n' "$*" >&2; }

# Resolve the repository root (two levels up from this script).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# --- privilege handling ---------------------------------------------------
# We need root for apt/systemctl. Use sudo transparently when not root.
if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
  # The user who invoked sudo (so we add the right account to the docker group).
  TARGET_USER="${SUDO_USER:-root}"
else
  if ! command -v sudo >/dev/null 2>&1; then
    err "This script needs root privileges (apt/systemctl) and 'sudo' is not available."
    err "Re-run as root: su -c '${BASH_SOURCE[0]}'"
    exit 1
  fi
  SUDO="sudo"
  TARGET_USER="$(id -un)"
fi

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
    warn "The installer may still work on other Debian-based systems, but is untested."
  elif [ "${VERSION_ID:-}" != "24.04" ]; then
    warn "Detected Ubuntu ${VERSION_ID:-?}. The recommended version is 24.04 LTS."
  else
    log "Ubuntu 24.04 LTS detected."
  fi
}

# --- base packages --------------------------------------------------------
install_base_packages() {
  log "Updating apt package index..."
  $SUDO apt-get update -y
  log "Installing base packages (ca-certificates, curl, git, make, gnupg)..."
  $SUDO apt-get install -y ca-certificates curl git make gnupg
}

# --- Docker Engine + Compose plugin (official repository) -----------------
install_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    log "Docker Engine and Compose plugin already installed ($(docker --version))."
    return
  fi

  log "Setting up Docker's official apt repository..."
  $SUDO install -m 0755 -d /etc/apt/keyrings
  if [ ! -f /etc/apt/keyrings/docker.asc ]; then
    $SUDO curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      -o /etc/apt/keyrings/docker.asc
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

# --- allow the invoking user to run docker without sudo -------------------
configure_docker_group() {
  if [ "$TARGET_USER" = "root" ]; then
    return
  fi
  if id -nG "$TARGET_USER" | tr ' ' '\n' | grep -qx docker; then
    log "User '$TARGET_USER' is already in the 'docker' group."
  else
    log "Adding user '$TARGET_USER' to the 'docker' group..."
    $SUDO usermod -aG docker "$TARGET_USER"
    warn "Log out and back in (or run 'newgrp docker') for group membership to take effect."
  fi
}

# --- environment file -----------------------------------------------------
prepare_env() {
  if [ -f "${REPO_ROOT}/.env" ]; then
    log ".env already exists — leaving it unchanged."
  else
    log "Creating .env from .env.example..."
    cp "${REPO_ROOT}/.env.example" "${REPO_ROOT}/.env"
    warn "Edit ${REPO_ROOT}/.env and set a strong POSTGRES_PASSWORD before production use."
  fi
}

# --- verification ---------------------------------------------------------
verify() {
  log "Verifying installation..."
  docker --version || true
  docker compose version || true
}

main() {
  log "Starting ATLAS prerequisites installation."
  check_os
  install_base_packages
  install_docker
  configure_docker_group
  prepare_env
  verify
  log "Done. Next steps:"
  cat <<EOF

  cd ${REPO_ROOT}
  docker compose up --build        # or: make up

  Then open:
    - App / System Status : http://localhost/system
    - Backend health      : http://localhost/health

  If you were just added to the 'docker' group, run 'newgrp docker'
  (or re-login) first so 'docker' works without sudo.
EOF
}

main "$@"
