# shellcheck shell=bash
# Shared helpers for ATLAS shell scripts (installer, updater, model ops).
# Sourced, not executed — do not set -euo here (the calling script owns that).

# Logging (only defined if the caller hasn't already).
command -v log  >/dev/null 2>&1 || log()  { printf '\033[1;34m[atlas]\033[0m %s\n' "$*"; }
command -v warn >/dev/null 2>&1 || warn() { printf '\033[1;33m[atlas][warn]\033[0m %s\n' "$*" >&2; }
command -v err  >/dev/null 2>&1 || err()  { printf '\033[1;31m[atlas][error]\033[0m %s\n' "$*" >&2; }

# set_env_var KEY VALUE ENV_FILE — idempotent, updates or appends KEY=VALUE.
command -v set_env_var >/dev/null 2>&1 || set_env_var() {
  local key="$1" val="$2" file="${3:-${ENV_FILE:-.env}}"
  [ -f "$file" ] || touch "$file"
  if grep -qE "^${key}=" "$file" 2>/dev/null; then
    # Use a temp file + rename so a crash never leaves a half-written .env.
    local tmp
    tmp="$(mktemp "${file}.XXXXXX")"
    sed "s|^${key}=.*|${key}=${val}|" "$file" > "$tmp"
    mv "$tmp" "$file"
  else
    printf '%s=%s\n' "$key" "$val" >> "$file"
  fi
}

# get_env_var KEY ENV_FILE
get_env_var() {
  local key="$1" file="${2:-${ENV_FILE:-.env}}"
  grep -E "^${key}=" "$file" 2>/dev/null | head -1 | cut -d= -f2-
}

# compose_files ROOT — echoes the "-f ..." args, including the GPU override when present.
compose_files() {
  local root="$1"
  printf -- '-f %s/docker-compose.yml' "$root"
  if [ -f "$root/.atlas/docker-compose.gpu.yml" ]; then
    printf -- ' -f %s/.atlas/docker-compose.gpu.yml' "$root"
  fi
}

# ollama_profile ROOT — echoes "--profile ai" when local Ollama is enabled.
ollama_profile() {
  local root="$1"
  [ -f "$root/.atlas/state/ollama.enabled" ] && printf -- '--profile ai'
}

# Build the docker compose command string for the control plane.
# Honors $SUDO (may be empty) set by the caller.
atlas_compose_cmd() {
  local root="$1"
  printf '%s docker compose %s %s' "${SUDO:-}" "$(compose_files "$root")" "$(ollama_profile "$root")"
}
