"""Thin end-to-end CLI: validate pack, ingest, QA, score.

Usage:
  python benchmark_packs/_runner/cli.py run <pack_root> [--subset dev|holdout|full]
                                                        [--mode stub|harness]
                                                        [--workdir DIR]

Writes (under workdir, default: a fresh temp dir):
  vault/                   # produced vault after ingest
  ingest_report.json
  answers.json
  score_report.json

Prints a one-line summary on stdout. Returns exit code 0 unless ingest or
scoring is outright broken (score value itself is never gate-worthy here).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pack_loader import load_pack, PackValidationError  # noqa: E402
from ingest_runner import run_ingest  # noqa: E402
from qa_runner import run_qa  # noqa: E402
from scorer import score_answers  # noqa: E402


def cmd_validate(args) -> int:
    try:
        pack = load_pack(Path(args.pack_root))
    except PackValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"OK {pack.id}: {len(pack.questions)} questions")
    return 0


def cmd_run(args) -> int:
    pack = load_pack(Path(args.pack_root))
    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix=f"pack-{pack.id}-"))
    workdir.mkdir(parents=True, exist_ok=True)

    print(f"pack={pack.id} workdir={workdir} subset={args.subset} mode={args.mode}")
    ingest = run_ingest(pack, workdir, mode=args.mode)
    print(f"ingest: ok={ingest.ok_count} err={ingest.error_count} vault={ingest.vault_path}")

    questions = pack.subset(args.subset)
    answers_path = workdir / "answers.json"
    answers = run_qa(pack, Path(ingest.vault_path), questions,
                     mode=args.mode, output_path=answers_path)
    ok = sum(1 for a in answers if a.status == "ok")
    print(f"qa: ok={ok}/{len(answers)} -> {answers_path}")

    report = score_answers(pack, questions, answers, subset=args.subset)
    (workdir / "score_report.json").write_text(
        json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(f"score: aggregate={report.aggregate:.3f} pass_rate={report.pass_rate:.3f} "
          f"({report.ok_count}/{report.total})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="validate pack structure and schemas")
    v.add_argument("pack_root")
    v.set_defaults(func=cmd_validate)

    r = sub.add_parser("run", help="validate -> ingest -> QA -> score")
    r.add_argument("pack_root")
    r.add_argument("--subset", default="full", choices=["dev", "holdout", "full"])
    r.add_argument("--mode", default="stub", choices=["stub", "harness"])
    r.add_argument("--workdir", default=None)
    r.set_defaults(func=cmd_run)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
