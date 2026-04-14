# Geopolitics April 2026 Pack — Benchmark Notes

This directory is the pack's benchmark surface. It is consumed by the
generic pack runner under `benchmark_packs/_runner/`.

## Files

- `questions.json` — 96 questions with `gold_points` anchors
- `benchmark_notes.md` — human-facing question design notes
- `dev_questions.json` — fixed 30-question dev subset for fast optimization
- `holdout_questions.json` — fixed 30-question holdout subset for final evaluation

The dev and holdout subsets are non-overlapping and were chosen to
preserve difficulty and type balance from the full set. They are frozen:
changing them mid-milestone is a benchmark modification and must be a
separate, reviewed commit.

## Running

```bash
# validate the pack
uv run python benchmark_packs/_runner/cli.py validate \
  datasets/geopolitics_apr_2026_memory_benchmark

# one full pipeline run (ingest -> QA -> score) on the dev subset, stub mode
uv run python benchmark_packs/_runner/cli.py run \
  datasets/geopolitics_apr_2026_memory_benchmark --subset dev --mode stub

# one optimization experiment against the pack
uv run python optimizer/runner.py \
  --pack datasets/geopolitics_apr_2026_memory_benchmark \
  --subset dev --pack-mode stub --stub-optimizer \
  --notes "geopolitics dev smoke"
```

## Scoring

The generic scorer under `benchmark_packs/_runner/scorer.py` matches
each answer against its `gold_points` after `casefold_punct` normalization.
A question passes if `matched >= gold_points_min`. Partial credit is
enabled by default.

## Question Types

This pack uses a richer `type` taxonomy than the recommended baseline
(e.g. `cross_doc_synthesis`, `cross_doc_causal_chain`, `regional_perception`).
The pack schema accepts any non-empty string for `type`; it is used for
reporting, not scoring.

## Dev / Holdout Discipline

- Optimization runs should use `--subset dev` by default.
- Holdout runs happen at milestone checkpoints, not during active tuning.
- Never run multiple optimization experiments against `--subset holdout`
  — that defeats its purpose.
