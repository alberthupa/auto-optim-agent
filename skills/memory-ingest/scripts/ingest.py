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
    # Title: first markdown heading, first non-empty line, or item id.
    title = None
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            break
    if not title:
        for line in body.splitlines():
            if line.strip():
                title = line.strip()[:60]
                break
    if not title:
        title = str(meta.get("id", "Untitled"))

    fm: dict[str, Any] = {}
    for key in ("source_type", "timestamp", "origin", "tags", "trust"):
        if key in meta and meta[key] is not None:
            fm_key = "source_timestamp" if key == "timestamp" else (
                "source_origin" if key == "origin" else key
            )
            fm[fm_key] = meta[key]
    fm["item_id"] = meta.get("id")

    return {
        "operations": [
            {
                "op": "create",
                "title": title,
                "frontmatter": fm,
                "body": body or "(empty)",
                "links": [],
                "rationale": "stub harness: single create, raw body preserved",
            }
        ]
    }


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
