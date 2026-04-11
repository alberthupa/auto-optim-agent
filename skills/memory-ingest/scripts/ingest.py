"""Thin ingest entry point for the memory-ingest skill.

Flow:
  1. Load one knowledge item (YAML frontmatter + body).
  2. Load a small vault context slice (list of existing note titles).
  3. Ask the harness (PI, or a deterministic stub) for a structured proposal.
  4. Validate the proposal against a pydantic schema.
  5. Apply writes to the vault as plain Markdown files.

One LLM call per item. One schema. One writer.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# ---------------------------------------------------------------------------
# Schema — the LLM → Python contract.
# ---------------------------------------------------------------------------


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: str = Field(pattern=r"^(create|update)$")
    title: str = Field(min_length=1)
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    body: str = Field(min_length=1)
    links: list[str] = Field(default_factory=list)
    rationale: str | None = None


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operations: list[Operation] = Field(min_length=1)


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
# Vault context.
# ---------------------------------------------------------------------------


def load_vault_titles(vault: Path, cap: int = 200) -> list[str]:
    """Return a flat, sorted list of existing note titles (filename stems)."""
    if not vault.exists():
        return []
    titles = sorted(p.stem for p in vault.glob("*.md"))
    return titles[:cap]


# ---------------------------------------------------------------------------
# Prompt building.
# ---------------------------------------------------------------------------


def build_prompt(item: dict[str, Any], titles: list[str]) -> str:
    meta_yaml = yaml.safe_dump(item["meta"], sort_keys=False).strip()
    if titles:
        context = "\n".join(f"- {t}" for t in titles)
    else:
        context = "(vault is empty)"
    skill_text = SKILL_PATH.read_text(encoding="utf-8")
    return (
        "You are running the memory-ingest skill. The skill contract is"
        " reproduced below in full — follow it strictly.\n\n"
        "================ SKILL.md ================\n"
        f"{skill_text}\n"
        "================ END SKILL.md ================\n\n"
        "## Knowledge item metadata\n"
        f"```yaml\n{meta_yaml}\n```\n\n"
        "## Knowledge item body\n"
        f"```\n{item['body']}\n```\n\n"
        "## Existing vault note titles\n"
        f"{context}\n\n"
        "Return exactly one JSON object matching the schema in SKILL.md."
        " Remember: top-level key is `operations`, per-operation action key"
        " is `op`. No prose, no markdown fences, no commentary."
    )


# ---------------------------------------------------------------------------
# Harness invocation.
# ---------------------------------------------------------------------------

SKILL_PATH = Path(__file__).resolve().parents[1] / "SKILL.md"


def call_pi(prompt: str) -> str:
    """Invoke the PI harness non-interactively with the skill loaded."""
    cmd = [
        "pi",
        "-p",
        "--no-tools",
        "--no-session",
        "--skill",
        str(SKILL_PATH),
        prompt,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"pi exited {result.returncode}\nstderr:\n{result.stderr}"
        )
    return result.stdout


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json_object(text: str) -> dict[str, Any]:
    """Pull the first top-level JSON object out of arbitrary text."""
    # Fenced ```json ... ``` first.
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        m = _JSON_OBJECT_RE.search(text)
        if not m:
            raise ValueError(f"no JSON object found in harness output:\n{text}")
        candidate = m.group(0)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"harness JSON did not parse: {exc}\nraw:\n{candidate}") from exc


# ---------------------------------------------------------------------------
# Stub harness — deterministic, offline, used for dev and verification.
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
# Filename sanitizer.
# ---------------------------------------------------------------------------

_UNSAFE_RE = re.compile(r'[\\/:*?"<>|]')
_WS_RE = re.compile(r"\s+")


def sanitize_filename(title: str) -> str:
    cleaned = _UNSAFE_RE.sub(" ", title)
    cleaned = _WS_RE.sub(" ", cleaned).strip()
    if not cleaned:
        raise ValueError(f"title sanitized to empty: {title!r}")
    return f"{cleaned}.md"


# ---------------------------------------------------------------------------
# Writer.
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


def apply_operation(op: Operation, vault: Path) -> str:
    vault.mkdir(parents=True, exist_ok=True)
    filename = sanitize_filename(op.title)
    target = vault / filename
    if op.op == "create":
        if target.exists():
            raise FileExistsError(f"create conflict: {target} already exists")
        target.write_text(render_note(op.frontmatter, op.body, op.links), encoding="utf-8")
        return f'CREATE  "{filename}"'
    # update: merge frontmatter (existing keys preserved unless overridden)
    merged_fm = dict(op.frontmatter)
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        m = _FRONTMATTER_RE.match(existing)
        if m:
            old_fm = yaml.safe_load(m.group(1)) or {}
            if isinstance(old_fm, dict):
                for k, v in old_fm.items():
                    merged_fm.setdefault(k, v)
    target.write_text(render_note(merged_fm, op.body, op.links), encoding="utf-8")
    return f'UPDATE  "{filename}"'


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="memory-ingest: one item -> vault")
    parser.add_argument("--item", required=True, type=Path, help="path to knowledge item file")
    parser.add_argument("--vault", required=True, type=Path, help="target Obsidian vault dir")
    parser.add_argument("--stub", action="store_true", help="use deterministic stub harness")
    args = parser.parse_args(argv)

    item = load_item(args.item)
    titles = load_vault_titles(args.vault)

    if args.stub:
        raw_proposal = stub_propose(item, titles)
    else:
        prompt = build_prompt(item, titles)
        stdout = call_pi(prompt)
        raw_proposal = extract_json_object(stdout)

    try:
        proposal = Proposal.model_validate(raw_proposal)
    except ValidationError as exc:
        print("PROPOSAL VALIDATION FAILED:", file=sys.stderr)
        print(json.dumps(raw_proposal, indent=2, default=str), file=sys.stderr)
        print(exc, file=sys.stderr)
        return 2

    for op in proposal.operations:
        print(apply_operation(op, args.vault))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
