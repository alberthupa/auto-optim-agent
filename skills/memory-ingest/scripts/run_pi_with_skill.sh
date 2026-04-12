#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

# Keep pi state in a writable project-local directory by default so the
# launcher works in constrained environments too. Users can override this.
export PI_CODING_AGENT_DIR="${PI_CODING_AGENT_DIR:-$ROOT/.pi-agent}"

mkdir -p "$PI_CODING_AGENT_DIR"
cd "$ROOT"

exec pi --skill "$ROOT/skills/memory-ingest/SKILL.md" "$@"
