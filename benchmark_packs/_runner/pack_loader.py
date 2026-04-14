"""Validate and load a benchmark pack into a normalized in-memory record.

Single public entry point: `load_pack(pack_root)`. All validation is inline —
no heavy jsonschema dependency. If validation fails, raises `PackValidationError`
with a list of human-readable issues.

The normalized `Pack` record is the only thing downstream runners should see;
they MUST NOT re-read pack files directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_PACK_SCHEMA_VERSION = 1
SUPPORTED_CONFIG_SCHEMA_VERSION = 1
_Q_TYPES = {
    "direct_fact", "list", "synthesis", "comparison",
    "causal", "definition", "numeric", "other",
}
_DIFFICULTIES = {"easy", "medium", "hard"}


class PackValidationError(Exception):
    def __init__(self, issues: list[str]):
        super().__init__("pack validation failed:\n  - " + "\n  - ".join(issues))
        self.issues = issues


@dataclass
class Question:
    id: str
    question: str
    type: str
    difficulty: str
    gold_points: list[str]
    gold_points_min: int
    answer: str | None = None
    source_docs: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    must_include: list[str] = field(default_factory=list)
    must_include_any: list[str] = field(default_factory=list)
    min_matches: int | None = None


@dataclass
class Pack:
    root: Path
    id: str
    description: str
    version: str | None
    corpus_dir: Path
    vault_seed_dir: Path | None
    questions: list[Question]
    dev_ids: list[str] | None
    holdout_ids: list[str] | None
    config: dict[str, Any]

    def subset(self, name: str) -> list[Question]:
        if name == "full":
            return list(self.questions)
        ids = self.dev_ids if name == "dev" else self.holdout_ids
        if ids is None:
            raise PackValidationError([f"pack '{self.id}' has no {name} subset defined"])
        by_id = {q.id: q for q in self.questions}
        missing = [qid for qid in ids if qid not in by_id]
        if missing:
            raise PackValidationError([f"{name} subset references unknown ids: {missing}"])
        return [by_id[qid] for qid in ids]


def load_pack(pack_root: Path) -> Pack:
    pack_root = Path(pack_root).resolve()
    issues: list[str] = []

    if not pack_root.is_dir():
        raise PackValidationError([f"pack root not a directory: {pack_root}"])

    pack_yaml = pack_root / "pack.yaml"
    corpus_dir = pack_root / "corpus"
    bench_dir = pack_root / "benchmark"
    questions_file = bench_dir / "questions.json"
    readme_file = bench_dir / "README.md"
    config_file = bench_dir / "config.yaml"
    vault_seed_dir = pack_root / "vault_seed"

    if not pack_yaml.is_file():
        issues.append("missing pack.yaml")
    if not corpus_dir.is_dir():
        issues.append("missing corpus/ directory")
    elif not any(corpus_dir.rglob("*")):
        issues.append("corpus/ is empty")
    if not bench_dir.is_dir():
        issues.append("missing benchmark/ directory")
    if not questions_file.is_file():
        issues.append("missing benchmark/questions.json")
    if not readme_file.is_file():
        issues.append("missing benchmark/README.md")

    if issues:
        raise PackValidationError(issues)

    pack_meta = _load_yaml(pack_yaml, issues, "pack.yaml") or {}
    _validate_pack_meta(pack_meta, issues)

    config = {}
    if config_file.is_file():
        config = _load_yaml(config_file, issues, "benchmark/config.yaml") or {}
        _validate_config(config, issues)

    questions = _load_questions(questions_file, issues)

    dev_ids = _load_subset(bench_dir / _subset_filename(config, "dev_file", "dev_questions.json"))
    holdout_ids = _load_subset(bench_dir / _subset_filename(config, "holdout_file", "holdout_questions.json"))

    vault_cfg = config.get("vault", {}) if isinstance(config, dict) else {}
    if vault_cfg.get("seed_required") and not vault_seed_dir.is_dir():
        issues.append("config requires vault_seed/ but it is missing")

    if issues:
        raise PackValidationError(issues)

    return Pack(
        root=pack_root,
        id=pack_meta["id"],
        description=pack_meta["description"],
        version=pack_meta.get("version"),
        corpus_dir=corpus_dir,
        vault_seed_dir=vault_seed_dir if vault_seed_dir.is_dir() else None,
        questions=questions,
        dev_ids=dev_ids,
        holdout_ids=holdout_ids,
        config=config or {},
    )


def _load_yaml(path: Path, issues: list[str], label: str) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        issues.append(f"{label}: YAML parse error: {exc}")
        return None


def _validate_pack_meta(meta: Any, issues: list[str]) -> None:
    if not isinstance(meta, dict):
        issues.append("pack.yaml must be a mapping")
        return
    for key in ("id", "schema_version", "description"):
        if key not in meta:
            issues.append(f"pack.yaml missing required key: {key}")
    sv = meta.get("schema_version")
    if sv is not None and sv != SUPPORTED_PACK_SCHEMA_VERSION:
        issues.append(f"pack.yaml schema_version {sv} unsupported (expected {SUPPORTED_PACK_SCHEMA_VERSION})")
    pack_id = meta.get("id")
    if pack_id and not isinstance(pack_id, str):
        issues.append("pack.yaml id must be a string")


def _validate_config(config: Any, issues: list[str]) -> None:
    if not isinstance(config, dict):
        issues.append("benchmark/config.yaml must be a mapping")
        return
    sv = config.get("schema_version", SUPPORTED_CONFIG_SCHEMA_VERSION)
    if sv != SUPPORTED_CONFIG_SCHEMA_VERSION:
        issues.append(f"config.yaml schema_version {sv} unsupported")


def _load_questions(path: Path, issues: list[str]) -> list[Question]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        issues.append(f"questions.json parse error: {exc}")
        return []
    if not isinstance(data, list):
        issues.append("questions.json must be a JSON array")
        return []
    out: list[Question] = []
    seen_ids: set[str] = set()
    for i, raw in enumerate(data):
        if not isinstance(raw, dict):
            issues.append(f"questions[{i}] not an object")
            continue
        qid = raw.get("id")
        if not isinstance(qid, str) or not qid:
            issues.append(f"questions[{i}] missing string id")
            continue
        if qid in seen_ids:
            issues.append(f"duplicate question id: {qid}")
            continue
        seen_ids.add(qid)
        qtype = raw.get("type")
        diff = raw.get("difficulty")
        gp = raw.get("gold_points")
        gpm = raw.get("gold_points_min")
        local: list[str] = []
        if not isinstance(raw.get("question"), str):
            local.append("question must be a string")
        if qtype not in _Q_TYPES:
            local.append(f"type '{qtype}' not in {sorted(_Q_TYPES)}")
        if diff not in _DIFFICULTIES:
            local.append(f"difficulty '{diff}' not in {sorted(_DIFFICULTIES)}")
        if not isinstance(gp, list) or not gp or not all(isinstance(x, str) for x in gp):
            local.append("gold_points must be a non-empty list of strings")
        if not isinstance(gpm, int) or gpm < 1:
            local.append("gold_points_min must be a positive integer")
        elif isinstance(gp, list) and gpm > len(gp):
            local.append("gold_points_min exceeds len(gold_points)")
        mia = raw.get("must_include_any")
        if mia is not None and not isinstance(raw.get("min_matches"), int):
            local.append("must_include_any requires min_matches")
        if local:
            issues.extend(f"questions[{qid}]: {m}" for m in local)
            continue
        out.append(Question(
            id=qid,
            question=raw["question"],
            type=qtype,
            difficulty=diff,
            gold_points=list(gp),
            gold_points_min=gpm,
            answer=raw.get("answer"),
            source_docs=list(raw.get("source_docs") or []),
            tags=list(raw.get("tags") or []),
            must_include=list(raw.get("must_include") or []),
            must_include_any=list(mia or []),
            min_matches=raw.get("min_matches"),
        ))
    return out


def _load_subset(path: Path) -> list[str] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
        raise PackValidationError([f"{path.name} must be a JSON array of question ids"])
    return data


def _subset_filename(config: dict[str, Any], key: str, default: str) -> str:
    return (config.get("subsets") or {}).get(key, default)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("pack_root")
    args = ap.parse_args()
    pack = load_pack(Path(args.pack_root))
    print(f"OK pack='{pack.id}' questions={len(pack.questions)} "
          f"dev={len(pack.dev_ids or [])} holdout={len(pack.holdout_ids or [])} "
          f"vault_seed={'yes' if pack.vault_seed_dir else 'no'}")
