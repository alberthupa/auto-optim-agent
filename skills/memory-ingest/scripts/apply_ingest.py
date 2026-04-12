"""Apply a structured ingest proposal to an Obsidian-compatible vault.

This is the single write surface for memory-ingest. It accepts a JSON
proposal (from stdin or --proposal-file), validates it, resolves note
paths recursively, writes Markdown files, and returns a machine-readable
change summary.

This script never calls any harness. It is a deterministic local tool.

CLI usage:
    echo '{"operations": [...]}' | python apply_ingest.py --vault /path/to/vault
    python apply_ingest.py --vault /path/to/vault --proposal-file proposal.json
    python apply_ingest.py --vault /path/to/vault --dry-run < proposal.json

Input: JSON proposal on stdin or via --proposal-file
Output: JSON change summary on stdout
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# ---------------------------------------------------------------------------
# Proposal schema — the LLM-to-helper contract.
# ---------------------------------------------------------------------------


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: str = Field(pattern=r"^(create|update)$")
    title: str = Field(min_length=1)
    target_path_hint: str | None = None
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    body: str = Field(min_length=1)
    links: list[str] = Field(default_factory=list)
    rationale: str | None = None


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operations: list[Operation] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Filename sanitizer.
# ---------------------------------------------------------------------------

_UNSAFE_RE = re.compile(r'[\\/:*?"<>|]')
_WS_RE = re.compile(r"\s+")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def sanitize_filename(title: str) -> str:
    cleaned = _UNSAFE_RE.sub(" ", title)
    cleaned = _WS_RE.sub(" ", cleaned).strip()
    if not cleaned:
        raise ValueError(f"title sanitized to empty: {title!r}")
    return f"{cleaned}.md"


# ---------------------------------------------------------------------------
# Note renderer.
# ---------------------------------------------------------------------------


def render_note(frontmatter: dict[str, Any], body: str, links: list[str]) -> str:
    parts: list[str] = []
    if frontmatter:
        fm_yaml = yaml.safe_dump(frontmatter, sort_keys=False).strip()
        parts.append(f"---\n{fm_yaml}\n---\n")
    parts.append(body.rstrip() + "\n")
    if links:
        parts.append("\n## Links\n")
        parts.extend(f"- [[{link}]]\n" for link in links)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Recursive note resolution.
# ---------------------------------------------------------------------------


def find_existing_note(vault: Path, title: str) -> Path | None:
    """Find an existing note by title anywhere in the vault.

    Returns the path if exactly one match is found. Returns None if no
    match. Raises ValueError if multiple notes share the same title
    (ambiguous update target).
    """
    target_name = sanitize_filename(title)
    matches: list[Path] = []
    for path in vault.rglob("*.md"):
        if path.name == target_name:
            matches.append(path)
    if len(matches) == 0:
        return None
    if len(matches) == 1:
        return matches[0]
    rel_paths = [str(p.relative_to(vault)) for p in matches]
    raise ValueError(
        f"ambiguous update target: {len(matches)} notes titled "
        f"'{title}': {rel_paths}"
    )


# ---------------------------------------------------------------------------
# Apply operations.
# ---------------------------------------------------------------------------


def apply_operation(
    op: Operation, vault: Path, *, dry_run: bool = False
) -> dict[str, Any]:
    """Apply one operation. Returns a change record."""
    existing = find_existing_note(vault, op.title)

    if op.op == "create":
        if existing is not None:
            raise FileExistsError(
                f"create conflict: '{op.title}' already exists at "
                f"{existing.relative_to(vault)}"
            )
        target = vault / sanitize_filename(op.title)
        content = render_note(op.frontmatter, op.body, op.links)
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return {
            "action": "created",
            "title": op.title,
            "path": str(target.relative_to(vault)),
        }

    # update: merge frontmatter, preserving existing keys not overridden
    if existing is not None:
        target = existing
    else:
        # Update target doesn't exist — create it in vault root
        target = vault / sanitize_filename(op.title)

    merged_fm = dict(op.frontmatter)
    if existing is not None and existing.exists():
        raw = existing.read_text(encoding="utf-8")
        match = _FRONTMATTER_RE.match(raw)
        if match:
            old_fm = yaml.safe_load(match.group(1)) or {}
            if isinstance(old_fm, dict):
                for k, v in old_fm.items():
                    merged_fm.setdefault(k, v)

    content = render_note(merged_fm, op.body, op.links)
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    action = "updated" if existing is not None else "created_as_update"
    return {
        "action": action,
        "title": op.title,
        "path": str(target.relative_to(vault)),
    }


def apply_proposal(
    proposal: Proposal, vault: Path, *, dry_run: bool = False
) -> dict[str, Any]:
    """Apply all operations in a proposal. Returns a summary."""
    vault.mkdir(parents=True, exist_ok=True)
    changes: list[dict[str, Any]] = []
    errors: list[str] = []
    for op in proposal.operations:
        try:
            change = apply_operation(op, vault, dry_run=dry_run)
            changes.append(change)
        except (FileExistsError, ValueError) as exc:
            errors.append(str(exc))
    return {
        "dry_run": dry_run,
        "changes": changes,
        "errors": errors,
        "total_operations": len(proposal.operations),
        "successful": len(changes),
        "failed": len(errors),
    }


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply ingest proposal to vault")
    parser.add_argument("--vault", required=True, type=Path, help="target vault root")
    parser.add_argument("--proposal-file", type=Path, help="path to JSON proposal file")
    parser.add_argument("--dry-run", action="store_true", help="compute changes without writing")
    args = parser.parse_args(argv)

    if args.proposal_file:
        raw_json = args.proposal_file.read_text(encoding="utf-8")
    else:
        raw_json = sys.stdin.read()

    try:
        raw = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"invalid JSON: {exc}"}), file=sys.stderr)
        return 2

    try:
        proposal = Proposal.model_validate(raw)
    except ValidationError as exc:
        print(json.dumps({"error": f"schema validation failed: {exc}"}), file=sys.stderr)
        return 2

    summary = apply_proposal(proposal, args.vault, dry_run=args.dry_run)
    json.dump(summary, sys.stdout, indent=2, default=str)
    print()

    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
