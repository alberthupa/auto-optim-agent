"""Generic deterministic scorer for QA answers against gold_points.

Primary signal: for each question, count how many gold_points appear as
substrings in the answer_text after normalization. A question passes if
matched >= gold_points_min. Per-question score is either binary
(pass/fail) or partial (matched / len(gold_points)) depending on config.

Aggregate score is weighted mean across questions.

Also surfaces must_include / must_include_any legacy checks as
secondary flags, but they do not alter the primary score unless a pack
opts in — we keep the primary surface small.
"""

from __future__ import annotations

import json
import re
import string
from dataclasses import dataclass, field, asdict
from pathlib import Path

from pack_loader import Pack, Question
from qa_runner import AnswerRecord


@dataclass
class QuestionScore:
    question_id: str
    difficulty: str
    type: str
    status: str
    matched_points: int
    total_points: int
    passed: bool
    score: float  # 0..1
    missing_points: list[str] = field(default_factory=list)
    extra_flags: list[str] = field(default_factory=list)


@dataclass
class ScoreReport:
    pack_id: str
    subset: str
    aggregate: float
    pass_rate: float
    per_difficulty: dict[str, float]
    per_question: list[QuestionScore]
    ok_count: int
    total: int

    def to_dict(self) -> dict:
        return {
            "pack_id": self.pack_id,
            "subset": self.subset,
            "aggregate": self.aggregate,
            "pass_rate": self.pass_rate,
            "per_difficulty": self.per_difficulty,
            "ok_count": self.ok_count,
            "total": self.total,
            "per_question": [asdict(q) for q in self.per_question],
        }


def score_answers(pack: Pack, questions: list[Question],
                  answers: list[AnswerRecord], *, subset: str = "full") -> ScoreReport:
    scoring_cfg = (pack.config.get("scoring") or {}) if isinstance(pack.config, dict) else {}
    normalize_mode = scoring_cfg.get("normalize", "casefold_punct")
    partial_credit = bool(scoring_cfg.get("partial_credit", True))
    weights = scoring_cfg.get("weights") or {}

    by_id: dict[str, AnswerRecord] = {a.question_id: a for a in answers}
    per_q: list[QuestionScore] = []
    for q in questions:
        ans = by_id.get(q.id)
        per_q.append(_score_one(q, ans, normalize_mode, partial_credit))

    total_weight = 0.0
    weighted_sum = 0.0
    by_diff_total: dict[str, float] = {}
    by_diff_weight: dict[str, float] = {}
    for qs in per_q:
        w = float(weights.get(qs.difficulty, 1.0))
        weighted_sum += w * qs.score
        total_weight += w
        by_diff_total[qs.difficulty] = by_diff_total.get(qs.difficulty, 0.0) + qs.score
        by_diff_weight[qs.difficulty] = by_diff_weight.get(qs.difficulty, 0.0) + 1.0

    aggregate = (weighted_sum / total_weight) if total_weight else 0.0
    pass_rate = (sum(1 for qs in per_q if qs.passed) / len(per_q)) if per_q else 0.0
    per_difficulty = {
        d: (by_diff_total[d] / by_diff_weight[d]) for d in by_diff_total
    }
    return ScoreReport(
        pack_id=pack.id,
        subset=subset,
        aggregate=aggregate,
        pass_rate=pass_rate,
        per_difficulty=per_difficulty,
        per_question=per_q,
        ok_count=sum(1 for qs in per_q if qs.status == "ok"),
        total=len(per_q),
    )


def _score_one(q: Question, ans: AnswerRecord | None,
               normalize_mode: str, partial_credit: bool) -> QuestionScore:
    total = len(q.gold_points)
    if ans is None or ans.status != "ok" or not ans.answer_text:
        return QuestionScore(
            question_id=q.id, difficulty=q.difficulty, type=q.type,
            status=(ans.status if ans else "missing"),
            matched_points=0, total_points=total, passed=False, score=0.0,
            missing_points=list(q.gold_points),
        )
    answer_norm = _normalize(ans.answer_text, normalize_mode)
    matched: list[str] = []
    missing: list[str] = []
    for gp in q.gold_points:
        if _normalize(gp, normalize_mode) in answer_norm:
            matched.append(gp)
        else:
            missing.append(gp)
    passed = len(matched) >= q.gold_points_min
    if partial_credit:
        score = (len(matched) / total) if total else 0.0
        if not passed:
            score = min(score, 0.999)  # can't reach full credit without passing gate
    else:
        score = 1.0 if passed else 0.0

    flags: list[str] = []
    if q.must_include:
        if not all(_normalize(p, normalize_mode) in answer_norm for p in q.must_include):
            flags.append("must_include_failed")
    if q.must_include_any and q.min_matches:
        hits = sum(1 for p in q.must_include_any if _normalize(p, normalize_mode) in answer_norm)
        if hits < q.min_matches:
            flags.append("must_include_any_failed")

    return QuestionScore(
        question_id=q.id, difficulty=q.difficulty, type=q.type,
        status=ans.status,
        matched_points=len(matched), total_points=total,
        passed=passed, score=score, missing_points=missing,
        extra_flags=flags,
    )


_PUNCT_RE = re.compile(f"[{re.escape(string.punctuation)}]")


def _normalize(text: str, mode: str) -> str:
    t = text.casefold()
    if mode == "casefold_punct":
        t = _PUNCT_RE.sub(" ", t)
    elif mode == "none":
        return text
    return re.sub(r"\s+", " ", t).strip()


if __name__ == "__main__":
    import argparse
    from pack_loader import load_pack
    ap = argparse.ArgumentParser()
    ap.add_argument("pack_root")
    ap.add_argument("--answers", required=True, help="path to answers.json from qa_runner")
    ap.add_argument("--subset", default="full", choices=["dev", "holdout", "full"])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    pack = load_pack(Path(args.pack_root))
    questions = pack.subset(args.subset)
    raw = json.loads(Path(args.answers).read_text(encoding="utf-8"))
    answers = [AnswerRecord(
        question_id=r["question_id"], question=r["question"], status=r["status"],
        answer_text=r.get("answer_text"), citations=r.get("citations", []),
        error=r.get("error"), attempts=r.get("attempts", 1),
        latency_seconds=r.get("latency_seconds", 0.0),
    ) for r in raw]
    report = score_answers(pack, questions, answers, subset=args.subset)
    out = json.dumps(report.to_dict(), indent=2)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
    else:
        print(out)
    print(f"aggregate={report.aggregate:.3f} pass_rate={report.pass_rate:.3f} "
          f"ok={report.ok_count}/{report.total}", flush=True)
