"""Pack-backed evaluation backend for the optimizer.

Runs one full pack evaluation (ingest -> QA -> score) against a fresh temp
vault and returns a report shaped for the optimizer loop: aggregate score,
per-dimension breakdown (currently per_difficulty), rich per-question detail,
and paths to persisted artifact files.

This module owns NO loop logic. It just runs one evaluation.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
_RUNNER_DIR = ROOT / "benchmark_packs" / "_runner"
sys.path.insert(0, str(_RUNNER_DIR))

from pack_loader import Pack, load_pack  # noqa: E402
from ingest_runner import run_ingest  # noqa: E402
from qa_runner import run_qa  # noqa: E402
from scorer import score_answers  # noqa: E402


@dataclass
class PackEvalResult:
    aggregate: float
    per_dimension: dict[str, float]
    pass_rate: float
    ok_count: int
    total: int
    workdir: Path
    vault_path: Path
    answers_path: Path
    score_report_path: Path
    score_report: dict[str, Any]

    def to_summary(self) -> dict[str, Any]:
        return {
            "aggregate": self.aggregate,
            "per_dimension": self.per_dimension,
            "pass_rate": self.pass_rate,
            "ok": self.ok_count,
            "total": self.total,
            "workdir": str(self.workdir),
        }


def evaluate_pack(pack: Pack, *, subset: str, mode: str,
                  workdir: Path | None = None) -> PackEvalResult:
    """Run ingest + QA + score on a fresh temp vault. Persist artifacts in workdir."""
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix=f"packeval-{pack.id}-"))
    workdir.mkdir(parents=True, exist_ok=True)

    ingest = run_ingest(pack, workdir, mode=mode)
    if ingest.error_count > 0 and ingest.ok_count == 0:
        raise RuntimeError(
            f"pack ingest produced no successful items; errors: "
            f"{[i.error for i in ingest.items if i.status == 'error'][:3]}"
        )

    questions = pack.subset(subset)
    answers_path = workdir / "answers.json"
    answers = run_qa(pack, Path(ingest.vault_path), questions,
                     mode=mode, output_path=answers_path)

    report = score_answers(pack, questions, answers, subset=subset)
    score_report_path = workdir / "score_report.json"
    score_dict = report.to_dict()
    score_report_path.write_text(json.dumps(score_dict, indent=2), encoding="utf-8")

    return PackEvalResult(
        aggregate=report.aggregate,
        per_dimension=dict(report.per_difficulty),
        pass_rate=report.pass_rate,
        ok_count=report.ok_count,
        total=report.total,
        workdir=workdir,
        vault_path=Path(ingest.vault_path),
        answers_path=answers_path,
        score_report_path=score_report_path,
        score_report=score_dict,
    )


def collect_artifacts(
    *,
    experiment_id: str,
    pack: Pack,
    subset: str,
    baseline: PackEvalResult,
    candidate: PackEvalResult,
    skill_before: str,
    skill_after: str,
    skill_diff: str,
) -> Path:
    """Persist a per-experiment artifact tree under results/artifacts/<id>/."""
    artifacts_root = ROOT / "results" / "artifacts" / experiment_id
    artifacts_root.mkdir(parents=True, exist_ok=True)

    shutil.copy2(baseline.answers_path, artifacts_root / "baseline_answers.json")
    shutil.copy2(baseline.score_report_path, artifacts_root / "baseline_score_report.json")
    shutil.copy2(candidate.answers_path, artifacts_root / "candidate_answers.json")
    shutil.copy2(candidate.score_report_path, artifacts_root / "candidate_score_report.json")

    (artifacts_root / "skill_before.md").write_text(skill_before, encoding="utf-8")
    (artifacts_root / "skill_after.md").write_text(skill_after, encoding="utf-8")
    (artifacts_root / "skill.diff").write_text(skill_diff, encoding="utf-8")

    snapshot = {
        "pack_id": pack.id,
        "pack_root": str(pack.root),
        "subset": subset,
        "description": pack.description,
        "version": pack.version,
        "config": pack.config,
        "question_count": len(pack.subset(subset)),
    }
    (artifacts_root / "pack_snapshot.json").write_text(
        json.dumps(snapshot, indent=2, default=str), encoding="utf-8"
    )

    return artifacts_root


__all__ = ["evaluate_pack", "collect_artifacts", "PackEvalResult", "load_pack"]
