"""Benchmark runner for the memory-ingest skill.

Responsibilities:
  1. For each case: copy `vaults/sandbox/` to a fresh temp directory.
  2. Run the skill's ingest entry point against each input file in the case.
  3. Load the resulting Markdown notes.
  4. Score them deterministically against `case.yaml`.
  5. Print a per-case / per-dimension / aggregate breakdown.
  6. Optionally append an entry to `results/experiments.jsonl`.

The runner is the benchmark. It is **not** the editable surface of the
optimizer. The optimizer must never touch this file or `cases/` during a run.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from llm_judge import JUDGE_FINGERPRINT, judge_case

ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = Path(__file__).resolve().parent
CASES_DIR = BENCH_DIR / "cases"
SANDBOX_VAULT = ROOT / "vaults" / "sandbox"
INGEST_SCRIPT = ROOT / "skills" / "memory-ingest" / "scripts" / "ingest.py"
RESULTS_LOG = ROOT / "results" / "experiments.jsonl"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)

# Files that exist in the sandbox but do not count as ingested notes.
_VAULT_SCAFFOLD_FILES = {"README.md"}


# ---------------------------------------------------------------------------
# Vault handling.
# ---------------------------------------------------------------------------


def fresh_vault() -> Path:
    """Copy the sandbox vault to a fresh temp directory.

    Returns the path to the vault dir. Caller must clean up the parent.
    """
    tmp_parent = Path(tempfile.mkdtemp(prefix="memingest-bench-"))
    vault = tmp_parent / "vault"
    if SANDBOX_VAULT.exists():
        shutil.copytree(SANDBOX_VAULT, vault)
    else:
        vault.mkdir(parents=True)
    return vault


def load_notes(vault: Path) -> list[dict[str, Any]]:
    """Load every ingested note in the vault (top-level *.md), skipping scaffold."""
    notes: list[dict[str, Any]] = []
    for path in sorted(vault.glob("*.md")):
        if path.name in _VAULT_SCAFFOLD_FILES:
            continue
        raw = path.read_text(encoding="utf-8")
        match = _FRONTMATTER_RE.match(raw)
        if match:
            fm_raw = yaml.safe_load(match.group(1)) or {}
            body = match.group(2)
        else:
            fm_raw = {}
            body = raw
        fm = fm_raw if isinstance(fm_raw, dict) else {}
        notes.append({"title": path.stem, "frontmatter": fm, "body": body, "raw": raw})
    return notes


# ---------------------------------------------------------------------------
# Ingest invocation.
# ---------------------------------------------------------------------------


def run_ingest(item_path: Path, vault: Path, stub: bool) -> None:
    cmd = [
        sys.executable,
        str(INGEST_SCRIPT),
        "--item",
        str(item_path),
        "--vault",
        str(vault),
    ]
    if stub:
        cmd.append("--stub")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"ingest failed for {item_path.name}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# Scoring. Each dimension returns a float in [0.0, 1.0].
# ---------------------------------------------------------------------------


def _combined_bodies(notes: list[dict[str, Any]]) -> str:
    return "\n".join(n["body"] for n in notes).lower()


def _combined_raw(notes: list[dict[str, Any]]) -> str:
    return "\n".join(n["raw"] for n in notes)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _duplicate_title_count(notes: list[dict[str, Any]]) -> int:
    titles = [_normalize_text(n["title"]) for n in notes if n["title"].strip()]
    return len(titles) - len(set(titles))


def _contained_body_duplicate_count(notes: list[dict[str, Any]]) -> int:
    bodies = [_normalize_text(n["body"]) for n in notes]
    duplicates = 0
    for index, left in enumerate(bodies):
        if len(left) < 160:
            continue
        for right in bodies[index + 1 :]:
            shorter, longer = sorted((left, right), key=len)
            if shorter == longer or len(shorter) < 160:
                continue
            if shorter in longer:
                duplicates += 1
    return duplicates


def score_case(spec: dict[str, Any], notes: list[dict[str, Any]]) -> tuple[float, dict[str, float]]:
    dims: dict[str, float] = {}

    expected = spec.get("expected_notes") or []
    if expected:
        hits = 0
        for substr in expected:
            needle = str(substr).lower()
            if any(needle in n["title"].lower() for n in notes):
                hits += 1
        dims["expected_notes"] = hits / len(expected)

    facts = spec.get("required_facts") or []
    if facts:
        haystack = _normalize_text(_combined_bodies(notes))
        hits = sum(1 for f in facts if _normalize_text(str(f)) in haystack)
        dims["required_facts"] = hits / len(facts)

    required_links = spec.get("required_links") or []
    if required_links:
        raw_all = _combined_raw(notes)
        hits = sum(1 for target in required_links if f"[[{target}]]" in raw_all)
        dims["required_links"] = hits / len(required_links)

    max_notes = spec.get("max_notes")
    if max_notes is not None:
        dims["note_count_within_limit"] = 1.0 if len(notes) <= int(max_notes) else 0.0

    min_notes = spec.get("min_notes")
    if min_notes is not None:
        dims["note_count_above_min"] = 1.0 if len(notes) >= int(min_notes) else 0.0

    max_dupes = int(spec.get("max_duplicates", 0))
    if notes:
        bodies = [_normalize_text(n["body"]) for n in notes]
        duplicates = len(bodies) - len(set(bodies))
        dims["duplicates_within_threshold"] = 1.0 if duplicates <= max_dupes else 0.0
    else:
        dims["duplicates_within_threshold"] = 0.0

    max_duplicate_titles = spec.get("max_duplicate_titles")
    if max_duplicate_titles is not None:
        duplicate_titles = _duplicate_title_count(notes)
        dims["duplicate_titles_within_threshold"] = (
            1.0 if duplicate_titles <= int(max_duplicate_titles) else 0.0
        )

    max_contained_bodies = spec.get("max_body_containment_duplicates")
    if max_contained_bodies is not None:
        contained_duplicates = _contained_body_duplicate_count(notes)
        dims["body_containment_within_threshold"] = (
            1.0 if contained_duplicates <= int(max_contained_bodies) else 0.0
        )

    required_note_kinds = spec.get("required_note_kinds") or []
    if required_note_kinds:
        present = {
            str(n["frontmatter"].get("note_kind", "")).strip()
            for n in notes
            if n["frontmatter"].get("note_kind")
        }
        hits = sum(1 for kind in required_note_kinds if str(kind) in present)
        dims["required_note_kinds"] = hits / len(required_note_kinds)

    if spec.get("require_derived_from"):
        consolidated = [
            n for n in notes if n["frontmatter"].get("note_kind") == "consolidated"
        ]
        if consolidated:
            hits = sum(1 for n in consolidated if n["frontmatter"].get("derived_from"))
            dims["derived_from_present"] = hits / len(consolidated)
        else:
            dims["derived_from_present"] = 0.0

    if spec.get("require_source_metadata", True):
        if notes:
            hits = sum(1 for n in notes if "source_type" in n["frontmatter"])
            dims["source_metadata_preserved"] = hits / len(notes)
        else:
            dims["source_metadata_preserved"] = 0.0

    if notes:
        dims["any_notes_produced"] = 1.0
    else:
        dims["any_notes_produced"] = 0.0

    aggregate = sum(dims.values()) / len(dims) if dims else 0.0
    return aggregate, dims


# ---------------------------------------------------------------------------
# Case orchestration.
# ---------------------------------------------------------------------------


def run_case(
    case_dir: Path,
    stub: bool,
    *,
    llm_judge: bool = False,
    llm_judge_stub: bool = False,
) -> dict[str, Any]:
    spec_path = case_dir / "case.yaml"
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}

    inputs_rel = spec.get("inputs") or []
    if not inputs_rel:
        input_dir = case_dir / "input"
        inputs_rel = sorted(
            str(p.relative_to(case_dir)) for p in input_dir.glob("*") if p.is_file()
        )
    if not inputs_rel:
        raise RuntimeError(f"case {case_dir.name} has no inputs")

    vault = fresh_vault()
    try:
        for rel in inputs_rel:
            run_ingest(case_dir / rel, vault, stub)
        notes = load_notes(vault)
        score, dims = score_case(spec, notes)
        judge_block: dict[str, Any] | None = None
        if llm_judge:
            input_texts = [
                (rel, (case_dir / rel).read_text(encoding="utf-8"))
                for rel in inputs_rel
            ]
            judge_block = judge_case(
                case_name=case_dir.name,
                case_description=str(spec.get("description", "")),
                input_texts=input_texts,
                notes=notes,
                stub=llm_judge_stub,
            )
    finally:
        shutil.rmtree(vault.parent, ignore_errors=True)

    result: dict[str, Any] = {
        "case": case_dir.name,
        "score": score,
        "dimensions": dims,
        "note_count": len(notes),
    }
    if judge_block is not None:
        result["llm_judge"] = judge_block
    return result


def discover_cases(filter_name: str | None) -> list[Path]:
    if filter_name:
        path = CASES_DIR / filter_name
        if not (path / "case.yaml").exists():
            raise SystemExit(f"no such case: {filter_name}")
        return [path]
    found = sorted(
        d for d in CASES_DIR.iterdir() if d.is_dir() and (d / "case.yaml").exists()
    )
    if not found:
        raise SystemExit(f"no cases found under {CASES_DIR}")
    return found


# ---------------------------------------------------------------------------
# Results log.
# ---------------------------------------------------------------------------


def append_experiment(
    aggregate: float,
    per_dimension: dict[str, float],
    notes_field: str,
    llm_judge_block: dict[str, Any] | None = None,
) -> str:
    skill_sha = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", "skills/memory-ingest/"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    ).stdout.strip() or "unknown"

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiment_id": str(uuid.uuid4()),
        "skill_git_sha": skill_sha,
        "baseline_score": None,
        "new_score": round(aggregate, 4),
        "per_dimension": {k: round(v, 4) for k, v in per_dimension.items()},
        "kept": None,
        "notes": notes_field,
    }
    if llm_judge_block is not None:
        entry["llm_judge"] = llm_judge_block
    RESULTS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry["experiment_id"]


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="memory-ingest benchmark runner")
    parser.add_argument("--stub", action="store_true", help="use deterministic stub harness")
    parser.add_argument("--case", help="run only the named case")
    parser.add_argument(
        "--record",
        action="store_true",
        help="append the aggregate result to results/experiments.jsonl",
    )
    parser.add_argument(
        "--notes",
        default="manual benchmark run",
        help="free-form notes field stored in the results log",
    )
    parser.add_argument(
        "--llm-judge",
        action="store_true",
        help=(
            "also run the fixed LLM-judge as an advisory secondary signal."
            " Never folded into the deterministic aggregate."
        ),
    )
    parser.add_argument(
        "--llm-judge-stub",
        action="store_true",
        help="use a deterministic offline judge instead of calling OpenAI",
    )
    args = parser.parse_args(argv)

    if args.llm_judge_stub and not args.llm_judge:
        args.llm_judge = True

    case_dirs = discover_cases(args.case)
    case_results = [
        run_case(
            d,
            args.stub,
            llm_judge=args.llm_judge,
            llm_judge_stub=args.llm_judge_stub,
        )
        for d in case_dirs
    ]

    aggregate = sum(r["score"] for r in case_results) / len(case_results)

    dim_accum: dict[str, list[float]] = {}
    for r in case_results:
        for k, v in r["dimensions"].items():
            dim_accum.setdefault(k, []).append(v)
    per_dimension = {k: sum(v) / len(v) for k, v in dim_accum.items()}

    per_case_report: dict[str, Any] = {}
    for r in case_results:
        block: dict[str, Any] = {
            "score": round(r["score"], 4),
            "note_count": r["note_count"],
            "dimensions": {k: round(v, 4) for k, v in r["dimensions"].items()},
        }
        if "llm_judge" in r:
            block["llm_judge"] = r["llm_judge"]
        per_case_report[r["case"]] = block

    report: dict[str, Any] = {
        "aggregate": round(aggregate, 4),
        "per_dimension": {k: round(v, 4) for k, v in per_dimension.items()},
        "per_case": per_case_report,
    }

    judge_summary: dict[str, Any] | None = None
    if args.llm_judge:
        judged = [r for r in case_results if "llm_judge" in r]
        if judged:
            judge_scores = [r["llm_judge"]["score"] for r in judged]
            rubric_accum: dict[str, list[int]] = {}
            for r in judged:
                for k, v in r["llm_judge"]["ratings"].items():
                    rubric_accum.setdefault(k, []).append(int(v))
            judge_summary = {
                "advisory": True,
                "fingerprint": JUDGE_FINGERPRINT,
                "model": judged[0]["llm_judge"].get("model"),
                "aggregate": round(sum(judge_scores) / len(judge_scores), 4),
                "per_rubric": {
                    k: round(sum(v) / len(v), 4) for k, v in rubric_accum.items()
                },
                "case_count": len(judged),
            }
            report["llm_judge"] = judge_summary

    print(json.dumps(report, indent=2))

    if args.record:
        experiment_id = append_experiment(
            aggregate, per_dimension, args.notes, llm_judge_block=judge_summary
        )
        print(f"recorded experiment {experiment_id} -> {RESULTS_LOG}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
