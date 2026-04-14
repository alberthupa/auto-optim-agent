#!/usr/bin/env bash

# Allow `sh script.sh` by re-executing under Bash before enabling Bash-only
# options and variables.
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
LOCAL_PI_DIR="$ROOT/.pi-agent"
DEFAULT_SESSION_DIR="$LOCAL_PI_DIR/sessions"

# Keep sessions in a project-local directory by default, but preserve the
# user's normal Pi config directory so models/settings from ~/.pi/agent remain
# available. Fall back to a fully local agent dir only when the default one
# is not writable or the user explicitly overrides PI_CODING_AGENT_DIR.
if [ -z "${PI_CODING_AGENT_DIR:-}" ]; then
  DEFAULT_PI_DIR="${HOME:-}/.pi/agent"
  if [ -n "${HOME:-}" ] && mkdir -p "$DEFAULT_PI_DIR" 2>/dev/null; then
    WRITE_TEST="$DEFAULT_PI_DIR/.run_pi_with_skill_write_test.$$"
    if touch "$WRITE_TEST" >/dev/null 2>&1; then
      rm -f "$WRITE_TEST"
    else
      export PI_CODING_AGENT_DIR="$LOCAL_PI_DIR"
    fi
  else
    export PI_CODING_AGENT_DIR="$LOCAL_PI_DIR"
  fi
fi

if [ -n "${PI_CODING_AGENT_DIR:-}" ]; then
  mkdir -p "$PI_CODING_AGENT_DIR"
fi
mkdir -p "$DEFAULT_SESSION_DIR"
cd "$ROOT"

ARGS=(--skill "$ROOT/skills/memory-ingest/SKILL.md")
HAS_TOOLS_FLAG=0
HAS_NO_TOOLS_FLAG=0
HAS_EXTENSION_FLAG=0
HAS_NO_EXTENSIONS_FLAG=0

HAS_SESSION_DIR=0
for arg in "$@"; do
  case "$arg" in
    --session-dir|--session-dir=*)
      HAS_SESSION_DIR=1
      break
      ;;
  esac
done

if [ "$HAS_SESSION_DIR" -eq 0 ]; then
  ARGS+=(--session-dir "$DEFAULT_SESSION_DIR")
fi

for arg in "$@"; do
  case "$arg" in
    --tools|--tools=*)
      HAS_TOOLS_FLAG=1
      ;;
    --no-tools)
      HAS_NO_TOOLS_FLAG=1
      ;;
    --extension|-e)
      HAS_EXTENSION_FLAG=1
      ;;
    --no-extensions|-ne)
      HAS_NO_EXTENSIONS_FLAG=1
      ;;
  esac
done

if [ "$HAS_TOOLS_FLAG" -eq 0 ] && [ "$HAS_NO_TOOLS_FLAG" -eq 0 ]; then
  ARGS+=(--tools read,bash,grep,find,ls)
fi

if [ "$HAS_EXTENSION_FLAG" -eq 0 ] && [ "$HAS_NO_EXTENSIONS_FLAG" -eq 0 ]; then
  ARGS+=(--no-extensions)
fi

exec pi "${ARGS[@]}" "$@"
