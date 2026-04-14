"""Fresh read-only QA runner for a benchmark pack.

Contract:
  - start a fresh session per run (no carry-over between questions)
  - read-only access to the produced temp vault ONLY (no other filesystem access)
  - emit one structured answer record per question (see _schemas/answer_schema.json)

Currently ships a `stub` backend that satisfies the contract deterministically
for development and CI. The `harness` backend is a placeholder — wiring it up
to a real read-only pi session happens in Phase 3 along with optimizer
integration.

Stub semantics:
  - concatenates vault note bodies (shallow scan of *.md)
  - runs a naive keyword retrieval per question (gold_point terms)
  - returns top-matching passages as answer_text
  - never fabricates: if nothing matches, returns status="empty"

This gives the scorer a non-trivial, deterministic signal that measures
whether ingest preserved gold-point phrases in the vault.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

from pack_loader import Pack, Question


@dataclass
class AnswerRecord:
    question_id: str
    question: str
    status: str  # "ok" | "empty" | "timeout" | "error"
    answer_text: str | None = None
    citations: list[str] = field(default_factory=list)
    error: str | None = None
    attempts: int = 1
    latency_seconds: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None and v != []}


def run_qa(pack: Pack, vault_path: Path, questions: list[Question],
           *, mode: str = "stub", output_path: Path | None = None) -> list[AnswerRecord]:
    vault_path = Path(vault_path)
    if not vault_path.is_dir():
        raise FileNotFoundError(f"vault not found: {vault_path}")
    if mode == "stub":
        vault_index = _index_vault(vault_path)
        answers = [_answer_stub(q, vault_index, vault_path) for q in questions]
    elif mode == "harness":
        raise NotImplementedError("harness QA mode not wired yet")
    else:
        raise ValueError(f"unknown QA mode: {mode}")

    if output_path is not None:
        output_path.write_text(
            json.dumps([a.to_dict() for a in answers], indent=2),
            encoding="utf-8",
        )
    return answers


# ---------------------------------------------------------------------------
# Stub backend
# ---------------------------------------------------------------------------

@dataclass
class _IndexedNote:
    path: Path
    rel: str
    text: str
    lower: str


def _index_vault(vault: Path) -> list[_IndexedNote]:
    out: list[_IndexedNote] = []
    for p in sorted(vault.rglob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        out.append(_IndexedNote(
            path=p, rel=str(p.relative_to(vault)), text=text, lower=text.lower()
        ))
    return out


def _answer_stub(q: Question, index: list[_IndexedNote], vault_root: Path) -> AnswerRecord:
    start = time.monotonic()
    terms = [gp.lower() for gp in q.gold_points if gp.strip()]
    hits: list[tuple[_IndexedNote, int]] = []
    for note in index:
        count = sum(1 for t in terms if t in note.lower)
        if count > 0:
            hits.append((note, count))
    hits.sort(key=lambda x: (-x[1], x[0].rel))
    top = hits[:5]
    if not top:
        return AnswerRecord(
            question_id=q.id, question=q.question, status="empty",
            latency_seconds=time.monotonic() - start,
        )
    snippets: list[str] = []
    citations: list[str] = []
    for note, _ in top:
        snippet = _extract_relevant_snippet(note.text, terms)
        snippets.append(f"[{note.rel}]\n{snippet}")
        citations.append(note.rel)
    return AnswerRecord(
        question_id=q.id, question=q.question, status="ok",
        answer_text="\n\n".join(snippets),
        citations=citations,
        latency_seconds=time.monotonic() - start,
    )


def _extract_relevant_snippet(text: str, terms: list[str], *, window: int = 240) -> str:
    lower = text.lower()
    best = 0
    for t in terms:
        idx = lower.find(t)
        if idx != -1:
            best = max(0, idx - 40)
            break
    return text[best:best + window].strip()


if __name__ == "__main__":
    import argparse
    from pack_loader import load_pack
    ap = argparse.ArgumentParser()
    ap.add_argument("pack_root")
    ap.add_argument("--vault", required=True)
    ap.add_argument("--subset", default="full", choices=["dev", "holdout", "full"])
    ap.add_argument("--mode", default="stub", choices=["stub", "harness"])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    pack = load_pack(Path(args.pack_root))
    questions = pack.subset(args.subset)
    out_path = Path(args.out) if args.out else None
    answers = run_qa(pack, Path(args.vault), questions, mode=args.mode, output_path=out_path)
    ok = sum(1 for a in answers if a.status == "ok")
    print(f"qa done: {ok}/{len(answers)} ok")
