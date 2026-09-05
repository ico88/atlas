# shellcheck shell=bash
# Ollama model operations (ROADMAP PR 2/PR 3). Sourced by installer + model scripts.
# Requires ATLAS_COMPOSE (docker compose command incl. -f/profile) set by the caller.

# validate_model_name NAME[:TAG] — accept only safe names/tags, no shell metachars.
validate_model_name() {
  local name="$1"
  # Reject any shell metacharacter (each '...' is a literal, incl. a backslash).
  # shellcheck disable=SC1003
  case "$name" in
    *' '*|*';'*|*'|'*|*'&'*|*'$'*|'`'*|*'`'*|*'('*|*')'*|*'<'*|*'>'*|*'\'*|*'"'*|*"'"*)
      return 1 ;;
  esac
  [[ "$name" =~ ^[a-zA-Z0-9][a-zA-Z0-9._/-]*(:[a-zA-Z0-9._-]+)?$ ]] || return 1
  return 0
}

# _ollama ARGS... — run ollama inside the container (no TTY).
_ollama() {
  # shellcheck disable=SC2086
  $ATLAS_COMPOSE exec -T ollama ollama "$@"
}

# wait_for_ollama [TIMEOUT_SECONDS] — block until the Ollama server answers.
wait_for_ollama() {
  local timeout="${1:-120}" waited=0
  while ! _ollama list >/dev/null 2>&1; do
    sleep 3
    waited=$((waited + 3))
    if [ "$waited" -ge "$timeout" ]; then
      return 1
    fi
  done
  return 0
}

# model_exists NAME — idempotency check.
model_exists() {
  local name="$1"
  _ollama list 2>/dev/null | awk 'NR>1{print $1}' | grep -qx "$name"
}

# pull_model NAME — validate then pull (propagates errors). Always pulls (a tag may move).
pull_model() {
  local name="$1"
  if ! validate_model_name "$name"; then
    err "Invalid model name: '$name'"
    return 2
  fi
  case "$name" in
    *:latest|*[!:]) : ;;
  esac
  if [ "${name##*:}" = "latest" ] || [ "$name" = "${name%:*}" ]; then
    warn "Model '$name' uses a moving tag; pin a version (e.g. name:1b) for reproducibility."
  fi
  log "Pulling model '$name' (this can take a while)..."
  _ollama pull "$name"
}

# smoke_test_model NAME — minimal generation to confirm the model actually runs.
smoke_test_model() {
  local name="$1"
  log "Smoke-testing '$name'..."
  _ollama run "$name" "Reply with exactly: OK" >/dev/null 2>&1
}

# list_installed_models — one model name per line (no header).
list_installed_models() {
  _ollama list 2>/dev/null | awk 'NR>1 && $1!="" {print $1}'
}

# models_to_prune PROTECTED... — read candidate names on stdin, print those NOT
# in the protected set. Pure (no ollama needed) so it is unit-testable.
models_to_prune() {
  local keep=" $* " m
  while IFS= read -r m; do
    [ -n "$m" ] || continue
    case "$keep" in
      *" $m "*) continue ;;   # protected
    esac
    printf '%s\n' "$m"
  done
}

# ollama_uses_gpu — 0 (true) if a currently-loaded model is running on the GPU.
# Real verification: `ollama ps` reports the PROCESSOR (e.g. "100% GPU"/"100% CPU").
ollama_uses_gpu() {
  _ollama ps 2>/dev/null | awk 'NR>1' | grep -qi 'gpu'
}

# refresh_atlas_models — update the model registry via the backend API.
refresh_atlas_models() {
  # shellcheck disable=SC2086
  $ATLAS_COMPOSE exec -T backend python -c \
    "import urllib.request as u; u.urlopen(u.Request('http://localhost:8000/api/v1/models/refresh', method='POST'), timeout=30)" \
    >/dev/null 2>&1
}
