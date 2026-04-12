"""Legacy ingest entry point — retained as a benchmark adapter only.

WARNING: This script is NOT the intended product surface. The real ingest
path is: user -> pi harness -> memory-ingest skill -> helper scripts -> vault.
This file exists only so the benchmark runner can drive the stub harness
through a single CLI entry point. It will be removed once the benchmark
is fully migrated to the harness-owned path.

Flow (stub mode only — the intended remaining use):
  1. Load one knowledge item (YAML frontmatter + body).
  2. Load vault context via scan_vault.py.
  3. Produce a structured proposal via the deterministic stub.
  4. Apply the proposal via apply_ingest.py's logic.

The live `pi` harness path has been removed. Use the pi skill directly.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from apply_ingest import Operation, Proposal, apply_proposal
from scan_vault import scan_vault

# ---------------------------------------------------------------------------
# Item loader.
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def load_item(path: Path) -> dict[str, Any]:
    """Load a knowledge item file. Permissive: only `id` is required.

    Accepts a Markdown-style file with optional YAML frontmatter followed by
    free-form body. If no frontmatter, the file id is derived from the filename.
    """
    raw = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(raw)
    if match:
        meta = yaml.safe_load(match.group(1)) or {}
        body = match.group(2)
    else:
        meta = {}
        body = raw
    if not isinstance(meta, dict):
        raise ValueError(f"{path}: frontmatter is not a mapping")
    source_items = meta.get("source_items")
    if source_items is not None:
        if not isinstance(source_items, list):
            raise ValueError(f"{path}: source_items must be a list")
        normalized_source_items: list[dict[str, Any]] = []
        for index, entry in enumerate(source_items, start=1):
            if isinstance(entry, str):
                normalized_source_items.append({"kind": entry})
            elif isinstance(entry, dict):
                normalized_source_items.append(entry)
            else:
                raise ValueError(
                    f"{path}: source_items[{index}] must be a mapping or string"
                )
        meta["source_items"] = normalized_source_items
        meta.setdefault("source_item_count", len(normalized_source_items))
    meta.setdefault("id", path.stem)
    return {"meta": meta, "body": body}


# ---------------------------------------------------------------------------
# Stub harness — deterministic, offline, used for dev and benchmarking.
# ---------------------------------------------------------------------------


def stub_propose(item: dict[str, Any], titles: list[str]) -> dict[str, Any]:
    """Return a deterministic canned proposal derived from the item."""
    meta = item["meta"]
    body = item["body"].strip()
    # Title: first markdown heading, a humanized id, or first non-empty line.
    title = None
    prefer_id_title = bool(meta.get("source_items")) or str(
        meta.get("source_type", "")
    ).lower() == "mixed_bundle"
    if not prefer_id_title:
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("#"):
                title = line.lstrip("#").strip()
                break
    if not title:
        raw_id = str(meta.get("id", "")).strip()
        if raw_id:
            title = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", raw_id)
            title = title.replace("_", " ").replace("-", " ").strip().title()
    if not title:
        for line in body.splitlines():
            if line.strip():
                title = line.strip()[:60]
                break
    if not title:
        title = str(meta.get("id", "Untitled"))

    fm: dict[str, Any] = {}
    for key in (
        "source_type",
        "timestamp",
        "origin",
        "tags",
        "trust",
        "source_items",
        "source_item_count",
    ):
        if key in meta and meta[key] is not None:
            fm_key = "source_timestamp" if key == "timestamp" else (
                "source_origin" if key == "origin" else key
            )
            fm[fm_key] = meta[key]
    fm["item_id"] = meta.get("id")

    body_lower = body.lower()
    source_type = str(meta.get("source_type", "")).lower()
    needs_raw_capture = bool(
        meta.get("source_items")
        or source_type in {
            "dialog",
            "transcript",
            "interview_transcript",
            "research_snippets",
            "mixed_bundle",
            "rough_notes",
        }
        or re.search(r"^\[[0-9:]+\]\s+[A-Z][a-z]+:", body, re.MULTILINE)
        or body.count("\n- ") >= 3
    )

    def choose_op(note_title: str) -> str:
        return "update" if note_title in titles else "create"

    def unique_preserving_order(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            cleaned = value.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            ordered.append(cleaned)
        return ordered

    def extract_links(text: str) -> list[str]:
        links: list[str] = []
        hint_map = {
            "obsidian": "Obsidian",
            "wiki links": "Wiki Links",
            "karpathy": "Karpathy",
            "memory-ingest": "Memory Ingest",
            "raw capture": "Raw Capture",
            "consolidated note": "Consolidated Note",
            "consolidated notes": "Consolidated Notes",
            "source provenance": "Source Provenance",
            "retrieval evaluation": "Retrieval Evaluation",
            "embedding drift": "Embedding Drift",
            "project atlas": "Project Atlas",
            "review queue": "Review Queue",
            "eva": "Eva",
            "alice": "Alice",
            "bob": "Bob",
            "carol": "Carol",
            "grafana": "Grafana",
            "iam": "IAM",
            "s3:putobject": "s3:PutObject",
        }
        lowered = text.lower()

        def phrase_present(needle: str) -> bool:
            pattern = re.compile(
                rf"(?<![a-z0-9]){re.escape(needle).replace('\\ ', r'\s+')}(?![a-z0-9])"
            )
            return bool(pattern.search(lowered))

        for needle, label in hint_map.items():
            if phrase_present(needle):
                links.append(label)
        for match in re.finditer(r"^\[[0-9:]+\]\s+([A-Z][a-z]+):", text, re.MULTILINE):
            links.append(match.group(1))
        return unique_preserving_order(links)[:8]

    def build_consolidated_body(raw_title: str, links: list[str]) -> str:
        bundle_items = meta.get("source_items") or []
        summary_lines = [
            "## Consolidated Notes",
            f"- Input shape: {source_type or 'note'}",
        ]
        if bundle_items:
            bundle_kinds = ", ".join(
                str(entry.get("kind", "capture")) for entry in bundle_items[:4]
            )
            summary_lines.append(f"- Bundle members: {bundle_kinds}")
        if links:
            summary_lines.append(f"- Durable links: {', '.join(links[:4])}")
        summary_lines.append(f"- See [[{raw_title}]] for the preserved source capture.")
        return "\n".join(summary_lines)

    links = extract_links(body)
    operations: list[dict[str, Any]] = []

    if needs_raw_capture:
        raw_title = f"{title} Raw Capture"
        raw_frontmatter = dict(fm)
        raw_frontmatter["note_kind"] = "raw_capture"
        operations.append(
            {
                "op": choose_op(raw_title),
                "title": raw_title,
                "frontmatter": raw_frontmatter,
                "body": body or "(empty)",
                "links": links,
                "rationale": "stub harness: preserve the raw source before consolidation",
            }
        )

        consolidated_title = f"{title} Notes"
        consolidated_frontmatter = dict(fm)
        consolidated_frontmatter["note_kind"] = "consolidated"
        consolidated_frontmatter["derived_from"] = [raw_title]
        operations.append(
            {
                "op": choose_op(consolidated_title),
                "title": consolidated_title,
                "frontmatter": consolidated_frontmatter,
                "body": build_consolidated_body(raw_title, links),
                "links": unique_preserving_order(links + [raw_title]),
                "rationale": "stub harness: add one durable summary note tied to the raw capture",
            }
        )
    else:
        operations.append(
            {
                "op": choose_op(title),
                "title": title,
                "frontmatter": fm,
                "body": body or "(empty)",
                "links": links,
                "rationale": "stub harness: single create for a clean source item",
            }
        )

    return {"operations": operations}


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="memory-ingest: legacy benchmark adapter (not the product surface)"
    )
    parser.add_argument("--item", required=True, type=Path, help="path to knowledge item file")
    parser.add_argument("--vault", required=True, type=Path, help="target Obsidian vault dir")
    parser.add_argument(
        "--stub",
        action="store_true",
        default=True,
        help="use deterministic stub harness (now always on)",
    )
    args = parser.parse_args(argv)

    item = load_item(args.item)

    # Use recursive vault scan for titles
    vault_notes = scan_vault(args.vault)
    titles = [n["title"] for n in vault_notes]

    raw_proposal = stub_propose(item, titles)

    try:
        proposal = Proposal.model_validate(raw_proposal)
    except Exception as exc:
        print("PROPOSAL VALIDATION FAILED:", file=sys.stderr)
        print(json.dumps(raw_proposal, indent=2, default=str), file=sys.stderr)
        print(exc, file=sys.stderr)
        return 2

    # Use the centralized apply logic from apply_ingest.py
    summary = apply_proposal(proposal, args.vault)

    for change in summary["changes"]:
        action = change["action"].upper()
        print(f'{action}  "{change["path"]}"')

    if summary["errors"]:
        for err in summary["errors"]:
            print(f"ERROR  {err}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
