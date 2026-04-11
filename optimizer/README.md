# optimizer

This directory contains the Milestone 3 experiment loop in
`optimizer/runner.py`.

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

- `--case <name>` limits the run to one benchmark case
- `--stub-ingest` uses the deterministic ingest stub instead of the live harness
- `--stub-optimizer` proposes a deterministic `SKILL.md` change instead of calling a live optimizer model

## Safety Checks

Before a run, the runner refuses to proceed if any of these paths already have
local edits:

- `skills/memory-ingest/SKILL.md`
- `results/experiments.jsonl`
- `benchmarks/memory-ingest/`

That keeps the benchmark fixed, prevents accidental log stomping, and makes
keep/revert behavior legible.
