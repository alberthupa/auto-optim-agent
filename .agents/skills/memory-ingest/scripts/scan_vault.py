"""Recursive vault scanner for the memory-ingest skill.

Scans an Obsidian-compatible vault and returns structured note metadata
as JSON. This is a read-only helper — it never writes to the vault and
never calls any harness.

CLI usage:
    python scan_vault.py --vault /path/to/vault [--query "search text"] [--limit 20]

Output is always JSON (list of note objects) to stdout.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_PREVIEW_LEN = 200


def scan_note(path: Path, vault_root: Path) -> dict[str, Any]:
    """Parse one Markdown note into a structured dict."""
    raw = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(raw)
    if match:
        fm_raw = yaml.safe_load(match.group(1)) or {}
        body = match.group(2)
    else:
        fm_raw = {}
        body = raw
    fm = fm_raw if isinstance(fm_raw, dict) else {}
    rel_path = str(path.relative_to(vault_root))
    preview = body.strip()[:_PREVIEW_LEN]
    return {
        "title": path.stem,
        "path": rel_path,
        "frontmatter": fm,
        "preview": preview,
    }


def scan_vault(
    vault: Path,
    *,
    query: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Recursively scan the vault for Markdown notes.

    If *query* is given, filter to notes whose title, path, or preview
    contain the query string (case-insensitive).
    """
    if not vault.exists():
        return []
    notes: list[dict[str, Any]] = []
    for path in sorted(vault.rglob("*.md")):
        if path.name == "README.md":
            continue
        try:
            note = scan_note(path, vault)
        except Exception:
            continue
        notes.append(note)

    if query:
        q = query.lower()
        notes = [
            n
            for n in notes
            if q in n["title"].lower()
            or q in n["path"].lower()
            or q in n["preview"].lower()
        ]

    if limit is not None and limit > 0:
        notes = notes[:limit]

    return notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recursive vault scanner")
    parser.add_argument("--vault", required=True, type=Path, help="path to vault root")
    parser.add_argument("--query", default=None, help="filter notes by relevance query")
    parser.add_argument("--limit", type=int, default=None, help="max notes to return")
    args = parser.parse_args(argv)

    notes = scan_vault(args.vault, query=args.query, limit=args.limit)
    json.dump(notes, sys.stdout, indent=2, default=str)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
