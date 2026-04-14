# optimizer

This directory contains the experiment loop in `optimizer/runner.py`.

Post-FR1, the optimizer targets the harness-owned SKILL.md which
instructs the `pi` harness to use `scan_vault.py` and `apply_ingest.py`
as local tools. The benchmark exercises the same helper layer.

The loop stays narrow on purpose:

1. score the current `skills/memory-ingest/SKILL.md`
2. ask an optimization role for one small replacement of that file
3. benchmark the candidate against the fixed runner in `benchmarks/`
4. keep it with a git commit or reject it with `git restore`
5. append the outcome to `results/experiments.jsonl`

## Editable Surface

Milestone 3 edits exactly one file:

- `skills/memory-ingest/SKILL.md`

The optimizer runner never writes to `benchmarks/` during a run. The benchmark
remains the contract.

Keep/reject behavior:

- kept experiments stage and commit `SKILL.md` plus `results/experiments.jsonl`
- rejected experiments restore `SKILL.md` with `git restore` and leave only the
  new JSONL record as a working-tree change

## Running

Offline verification:

```bash
uv run python optimizer/runner.py --stub-ingest --stub-optimizer --notes "offline smoke test"
```

Live optimization loop:

```bash
uv run python optimizer/runner.py --notes "live optimization attempt"
```

Useful flags:

- `--case <name>` limits the run to one benchmark case (legacy backend)
- `--stub-ingest` uses the deterministic ingest stub instead of the live harness
- `--stub-optimizer` proposes a deterministic `SKILL.md` change instead of calling a live optimizer model

## Evaluation Backends

The optimizer supports two backends for scoring a skill:

1. **Legacy deterministic benchmark** — `benchmarks/memory-ingest/runner.py`, case-based, checks vault shape (expected notes, required links, duplicates, etc.). Default when neither `--pack` nor `--case` is given.
2. **Pack-backed QA benchmark** (Milestone 7) — ingests a pack's corpus into a fresh temp vault, runs a fresh read-only QA session against it, scores answers against `gold_points`. Enabled by `--pack <path>`.

Pack-mode flags:

- `--pack <path>` — path to a `benchmark_packs/<pack>/` directory. Mutually exclusive with `--case`.
- `--subset {dev,holdout,full}` — which question subset to run. Default `dev`.
- `--pack-mode {stub,harness}` — backend mode for pack ingest and QA. Default `stub` (deterministic, no live LLM). `harness` is not wired yet.

Example:

```bash
uv run python optimizer/runner.py --pack benchmark_packs/smoke --subset full --stub-optimizer \
  --notes "smoke pack wiring verification"
```

## Experiment Artifacts (pack backend only)

Each pack-backed experiment produces an artifact directory at
`results/artifacts/<experiment_id>/` containing:

- `baseline_score_report.json` / `candidate_score_report.json`
- `baseline_answers.json` / `candidate_answers.json`
- `skill_before.md` / `skill_after.md` / `skill.diff`
- `pack_snapshot.json` — pack id, subset, config snapshot

Rejected runs are fully inspectable — their artifacts persist even though
`SKILL.md` has been restored.

## Extended Results Log

`results/experiments.jsonl` still carries the original fields. Pack-backed
runs additionally include:

- `eval_backend`: `"legacy"` or `"pack"`
- `pack_id`, `pack_subset` (pack runs only)
- `artifacts_dir` (relative path under repo root)
- `skill_git_sha_before`

These fields are additive; legacy log entries remain valid.

## Safety Checks

Before a run, the runner refuses to proceed if any of these paths already have
local edits:

- `skills/memory-ingest/SKILL.md`
- `results/experiments.jsonl`
- `benchmarks/memory-ingest/`

That keeps the benchmark fixed, prevents accidental log stomping, and makes
keep/revert behavior legible.
