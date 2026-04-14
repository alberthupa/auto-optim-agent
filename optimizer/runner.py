"""Thin keep-or-revert optimization loop for the memory-ingest skill.

This runner owns one narrow experiment:

1. score the current skill on the fixed benchmark
2. ask an optimization role for one small SKILL.md change
3. benchmark the candidate on a fresh sandbox
4. keep it with a git commit or revert it with git restore
5. append a readable record to results/experiments.jsonl

The editable surface is deliberately tiny: SKILL.md only.
The optimizer never writes to benchmarks/ during a run.

Post-FR1: the optimizer targets the harness-owned SKILL.md which
instructs the pi harness to use scan_vault.py and apply_ingest.py.
The benchmark exercises the same helper layer the real skill uses.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "skills" / "memory-ingest" / "SKILL.md"
BENCHMARK_RUNNER = ROOT / "benchmarks" / "memory-ingest" / "runner.py"
BENCHMARK_SCOPE = ROOT / "benchmarks" / "memory-ingest"
RESULTS_LOG = ROOT / "results" / "experiments.jsonl"

SKILL_REL = str(SKILL_PATH.relative_to(ROOT))
RESULTS_REL = str(RESULTS_LOG.relative_to(ROOT))
BENCHMARK_REL = str(BENCHMARK_SCOPE.relative_to(ROOT))

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
_STUB_MARKER = "## Optimization Loop Hint"


class OptimizationProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    updated_skill_markdown: str = Field(min_length=1)
    hypothesis: str | None = None


def run(cmd: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and fail loudly if it exits non-zero."""
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        joined = " ".join(cmd)
        raise RuntimeError(
            f"command failed: {joined}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def extract_json_object(text: str) -> dict[str, Any]:
    """Pull the first JSON object from arbitrary model output."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        match = _JSON_OBJECT_RE.search(text)
        if not match:
            raise ValueError(f"no JSON object found in output:\n{text}")
        candidate = match.group(0)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON from optimizer: {exc}\nraw:\n{candidate}") from exc


def git_status_for(pathspecs: list[str]) -> str:
    return run(["git", "status", "--porcelain", "--", *pathspecs]).stdout.strip()


def ensure_clean_runtime_state() -> None:
    """Refuse to run if protected runtime paths already have local edits."""
    dirty = git_status_for([SKILL_REL, RESULTS_REL, BENCHMARK_REL])
    if dirty:
        raise RuntimeError(
            "refusing to run optimizer with local changes in the runtime surface.\n"
            "Please clean these paths first:\n"
            f"{dirty}"
        )


def run_benchmark(*, stub_ingest: bool, case: str | None) -> dict[str, Any]:
    cmd = [sys.executable, str(BENCHMARK_RUNNER)]
    if stub_ingest:
        cmd.append("--stub")
    if case:
        cmd.extend(["--case", case])
    result = run(cmd)
    payload = extract_json_object(result.stdout)
    if "aggregate" not in payload or "per_dimension" not in payload:
        raise RuntimeError(f"unexpected benchmark report:\n{result.stdout}")
    return payload


def run_pack_benchmark(pack, *, subset: str, mode: str, workdir: Path) -> dict[str, Any]:
    """Run one pack evaluation and reshape it to match run_benchmark's contract."""
    from pack_backend import evaluate_pack
    result = evaluate_pack(pack, subset=subset, mode=mode, workdir=workdir)
    return {
        "aggregate": result.aggregate,
        "per_dimension": result.per_dimension,
        "pass_rate": result.pass_rate,
        "ok": result.ok_count,
        "total": result.total,
        "_eval_result": result,
    }


def load_recent_results(limit: int = 5) -> list[dict[str, Any]]:
    if not RESULTS_LOG.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in RESULTS_LOG.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows[-limit:]


def current_skill_blob_sha() -> str:
    return run(["git", "hash-object", SKILL_REL]).stdout.strip() or "unknown"


def build_optimizer_prompt(
    *,
    skill_text: str,
    baseline_report: dict[str, Any],
    recent_results: list[dict[str, Any]],
) -> str:
    return (
        "You are the optimization role for a very small memory-ingest project.\n\n"
        "Rules:\n"
        "- Editable surface is exactly one file: skills/memory-ingest/SKILL.md\n"
        "- Do not propose changes to benchmarks, the runner, results format, or git workflow\n"
        "- Make one small, concrete change only\n"
        "- Return exactly one JSON object with keys: summary, updated_skill_markdown, hypothesis\n"
        "- updated_skill_markdown must be the full replacement contents of SKILL.md\n"
        "- No markdown fences, no prose outside the JSON\n\n"
        "Current benchmark report:\n"
        f"```json\n{json.dumps(baseline_report, indent=2)}\n```\n\n"
        "Most recent experiment log entries:\n"
        f"```json\n{json.dumps(recent_results, indent=2)}\n```\n\n"
        "Current SKILL.md:\n"
        f"```markdown\n{skill_text}\n```\n\n"
        "Improve the skill for the fixed deterministic benchmark while keeping the file readable."
    )


def call_optimizer_model(
    *,
    skill_text: str,
    baseline_report: dict[str, Any],
    recent_results: list[dict[str, Any]],
) -> OptimizationProposal:
    prompt = build_optimizer_prompt(
        skill_text=skill_text,
        baseline_report=baseline_report,
        recent_results=recent_results,
    )
    result = run(["pi", "-p", "--no-tools", "--no-session", prompt])
    payload = extract_json_object(result.stdout)
    try:
        return OptimizationProposal.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError(f"optimizer response failed validation:\n{exc}") from exc


def stub_optimizer(skill_text: str, baseline_report: dict[str, Any]) -> OptimizationProposal:
    """Deterministic fallback for local verification without a live optimizer."""
    aggregate = baseline_report.get("aggregate", "unknown")
    if _STUB_MARKER in skill_text:
        updated = skill_text.replace(
            "- For multi-topic inputs, prefer a compact summary note plus a small number of durable entity or concept notes when that avoids under-decomposition.\n",
            "- For multi-topic inputs, prefer a compact summary note plus 1-3 durable entity or concept notes when that avoids under-decomposition.\n",
            1,
        )
        summary = "tighten decomposition guidance in optimization hint block"
    else:
        block = (
            "\n\n"
            f"{_STUB_MARKER}\n\n"
            "- For multi-topic inputs, prefer a compact summary note plus a small number of durable entity or concept notes when that avoids under-decomposition.\n"
            "- When stable people, systems, or concepts appear repeatedly, include them in `links` and mirror the most useful `[[wiki links]]` inline in the body when natural.\n"
            f"- The last baseline aggregate seen by the optimizer was {aggregate}.\n"
        )
        updated = skill_text.rstrip() + block + "\n"
        summary = "add optimization hint block for decomposition and linking"
    return OptimizationProposal(
        summary=summary,
        updated_skill_markdown=updated,
        hypothesis="clearer guidance may improve note-count and link dimensions",
    )


def apply_skill_update(new_text: str, current_text: str) -> None:
    if new_text == current_text:
        raise RuntimeError("optimizer proposed no change to SKILL.md")
    SKILL_PATH.write_text(new_text.rstrip() + "\n", encoding="utf-8")


def restore_skill() -> None:
    run(["git", "restore", "--source=HEAD", "--", SKILL_REL])


def append_result(
    *,
    experiment_id: str,
    baseline_score: float,
    new_score: float,
    per_dimension: dict[str, float],
    kept: bool,
    notes: str,
    summary: str,
    hypothesis: str | None,
    stub_ingest: bool,
    stub_optimizer_mode: bool,
    eval_backend: str = "legacy",
    pack_id: str | None = None,
    pack_subset: str | None = None,
    artifacts_dir: str | None = None,
    skill_sha_before: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiment_id": experiment_id,
        "skill_git_sha": current_skill_blob_sha(),
        "baseline_score": round(baseline_score, 4),
        "new_score": round(new_score, 4),
        "per_dimension": {k: round(v, 4) for k, v in per_dimension.items()},
        "kept": kept,
        "notes": notes,
        "change_summary": summary,
        "hypothesis": hypothesis,
        "stub_ingest": stub_ingest,
        "stub_optimizer": stub_optimizer_mode,
        "eval_backend": eval_backend,
    }
    if pack_id is not None:
        entry["pack_id"] = pack_id
    if pack_subset is not None:
        entry["pack_subset"] = pack_subset
    if artifacts_dir is not None:
        entry["artifacts_dir"] = artifacts_dir
    if skill_sha_before is not None:
        entry["skill_git_sha_before"] = skill_sha_before
    RESULTS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    return entry


def commit_kept_change(summary: str) -> str:
    run(["git", "add", "--", SKILL_REL, RESULTS_REL])
    message = f"experiment: keep {summary}"
    run(["git", "commit", "-m", message])
    return run(["git", "rev-parse", "HEAD"]).stdout.strip()


def commit_pack_experiment(*, kept: bool, summary: str, artifacts_dir: Path | None) -> str:
    """Commit a pack experiment regardless of outcome.

    Pack runs produce durable artifacts and an appended log line on every
    experiment. Leaving those as working-tree changes blocks the next run
    via ensure_clean_runtime_state. We commit both kept and rejected
    outcomes so state stays clean and every experiment is a named commit.
    """
    paths = [RESULTS_REL]
    if kept:
        paths.append(SKILL_REL)
    if artifacts_dir is not None:
        paths.append(str(artifacts_dir.relative_to(ROOT)))
    run(["git", "add", "--", *paths])
    prefix = "keep" if kept else "reject"
    run(["git", "commit", "-m", f"experiment[pack]: {prefix} {summary}"])
    return run(["git", "rev-parse", "HEAD"]).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="thin optimizer loop for memory-ingest")
    parser.add_argument("--stub-ingest", action="store_true", help="benchmark with the deterministic ingest stub")
    parser.add_argument(
        "--stub-optimizer",
        action="store_true",
        help="propose a deterministic SKILL.md change instead of calling a live optimizer model",
    )
    parser.add_argument("--case", help="run only one benchmark case (legacy backend)")
    parser.add_argument(
        "--pack",
        help="path to a benchmark pack directory; enables pack-backed QA evaluation",
    )
    parser.add_argument(
        "--subset",
        default="dev",
        choices=["dev", "holdout", "full"],
        help="which question subset to run when using --pack (default: dev)",
    )
    parser.add_argument(
        "--pack-mode",
        default="stub",
        choices=["stub", "harness"],
        help="backend mode for pack ingest and QA (default: stub)",
    )
    parser.add_argument(
        "--notes",
        default="optimization run",
        help="free-form notes stored in results/experiments.jsonl",
    )
    args = parser.parse_args(argv)

    if args.pack and args.case:
        parser.error("--pack and --case are mutually exclusive")

    if args.pack:
        return _main_pack(args)
    return _main_legacy(args)


def _main_legacy(args: argparse.Namespace) -> int:
    ensure_clean_runtime_state()

    current_skill = SKILL_PATH.read_text(encoding="utf-8")
    recent_results = load_recent_results()
    baseline_report = run_benchmark(stub_ingest=args.stub_ingest, case=args.case)
    baseline_score = float(baseline_report["aggregate"])

    if args.stub_optimizer:
        proposal = stub_optimizer(current_skill, baseline_report)
    else:
        proposal = call_optimizer_model(
            skill_text=current_skill,
            baseline_report=baseline_report,
            recent_results=recent_results,
        )

    apply_skill_update(proposal.updated_skill_markdown, current_skill)

    kept = False
    commit_sha = None
    try:
        candidate_report = run_benchmark(stub_ingest=args.stub_ingest, case=args.case)
        new_score = float(candidate_report["aggregate"])
        kept = new_score > baseline_score

        if not kept:
            restore_skill()

        entry = append_result(
            experiment_id=str(uuid.uuid4()),
            baseline_score=baseline_score,
            new_score=new_score,
            per_dimension=candidate_report["per_dimension"],
            kept=kept,
            notes=args.notes,
            summary=proposal.summary,
            hypothesis=proposal.hypothesis,
            stub_ingest=args.stub_ingest,
            stub_optimizer_mode=args.stub_optimizer,
        )

        if kept:
            commit_sha = commit_kept_change(proposal.summary)
    except Exception:
        restore_skill()
        raise

    report = {
        "baseline_score": round(baseline_score, 4),
        "new_score": round(new_score, 4),
        "kept": kept,
        "change_summary": proposal.summary,
        "hypothesis": proposal.hypothesis,
        "commit_sha": commit_sha,
        "results_log": str(RESULTS_LOG),
        "experiment_id": entry["experiment_id"],
    }
    print(json.dumps(report, indent=2))
    return 0


def _main_pack(args: argparse.Namespace) -> int:
    """Pack-backed QA evaluation loop. See optimizer/README.md for the contract."""
    import pack_backend as pb

    ensure_clean_runtime_state()

    pack = pb.load_pack(Path(args.pack))
    experiment_id = str(uuid.uuid4())
    exp_tmp = Path(tempfile.mkdtemp(prefix=f"optim-{pack.id}-{experiment_id[:8]}-"))

    skill_before = SKILL_PATH.read_text(encoding="utf-8")
    skill_sha_before = current_skill_blob_sha()
    recent_results = load_recent_results()

    baseline = run_pack_benchmark(pack, subset=args.subset, mode=args.pack_mode,
                                  workdir=exp_tmp / "baseline")
    baseline_score = float(baseline["aggregate"])

    if args.stub_optimizer:
        proposal = stub_optimizer(skill_before, baseline)
    else:
        proposal = call_optimizer_model(
            skill_text=skill_before,
            baseline_report={
                "aggregate": baseline["aggregate"],
                "per_dimension": baseline["per_dimension"],
                "pass_rate": baseline["pass_rate"],
                "pack_id": pack.id,
                "subset": args.subset,
            },
            recent_results=recent_results,
        )

    apply_skill_update(proposal.updated_skill_markdown, skill_before)

    new_score = baseline_score
    commit_sha = None
    kept = False
    artifacts_dir: Path | None = None
    try:
        candidate = run_pack_benchmark(pack, subset=args.subset, mode=args.pack_mode,
                                       workdir=exp_tmp / "candidate")
        new_score = float(candidate["aggregate"])
        kept = new_score > baseline_score

        skill_after = SKILL_PATH.read_text(encoding="utf-8") if kept else skill_before
        skill_diff = "".join(difflib.unified_diff(
            skill_before.splitlines(keepends=True),
            SKILL_PATH.read_text(encoding="utf-8").splitlines(keepends=True),
            fromfile="skill_before.md", tofile="skill_after.md",
        ))

        if not kept:
            restore_skill()

        artifacts_dir = pb.collect_artifacts(
            experiment_id=experiment_id,
            pack=pack,
            subset=args.subset,
            baseline=baseline["_eval_result"],
            candidate=candidate["_eval_result"],
            skill_before=skill_before,
            skill_after=skill_after,
            skill_diff=skill_diff,
        )

        entry = append_result(
            experiment_id=experiment_id,
            baseline_score=baseline_score,
            new_score=new_score,
            per_dimension=candidate["per_dimension"],
            kept=kept,
            notes=args.notes,
            summary=proposal.summary,
            hypothesis=proposal.hypothesis,
            stub_ingest=(args.pack_mode == "stub"),
            stub_optimizer_mode=args.stub_optimizer,
            eval_backend="pack",
            pack_id=pack.id,
            pack_subset=args.subset,
            artifacts_dir=str(artifacts_dir.relative_to(ROOT)),
            skill_sha_before=skill_sha_before,
        )

        commit_sha = commit_pack_experiment(
            kept=kept, summary=proposal.summary, artifacts_dir=artifacts_dir,
        )
    except Exception:
        restore_skill()
        raise

    report = {
        "eval_backend": "pack",
        "pack_id": pack.id,
        "subset": args.subset,
        "baseline_score": round(baseline_score, 4),
        "new_score": round(new_score, 4),
        "kept": kept,
        "change_summary": proposal.summary,
        "hypothesis": proposal.hypothesis,
        "commit_sha": commit_sha,
        "artifacts_dir": str(artifacts_dir) if artifacts_dir else None,
        "results_log": str(RESULTS_LOG),
        "experiment_id": experiment_id,
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
