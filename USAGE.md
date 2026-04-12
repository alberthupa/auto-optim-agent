# Usage

This file describes how to use the repository as it is currently implemented.

All commands below assume you run them from the repo root:

```bash
cd /home/albert/Projects/auto-optim-agent
```

## Prerequisites

- `uv` installed
- Python 3.11+
- `git` available if you want to run the optimizer
- `pi` available on `PATH` if you want live ingest or live optimization

Install the Python dependencies once:

```bash
uv sync
```

## 1. Prepare a Vault

There are two vault paths in the repo:

- `vaults/sandbox/`
  - disposable base vault used by the benchmark runner
  - safe for experiments
- `vaults/staging/`
  - documentation only
  - the personal-vault staging workflow is defined, but not enabled in code

For actual ingest runs today, use either:

- `vaults/sandbox/` for disposable local testing
- any other directory you choose with `--vault <path>`

Current implementation details that matter:

- The ingest script reads existing context from top-level `*.md` files only.
- The ingest script writes notes into the vault root, not into subfolders.
- If you want update behavior, put the existing note as a top-level Markdown file in that vault first.
- Do not point this at your real personal Obsidian vault. The staging path is not implemented yet.

Example disposable vault:

```bash
mkdir -p /tmp/my-memory-vault
```

## 2. Prepare a Knowledge Item

The ingest entrypoint accepts one Markdown file with:

- optional YAML frontmatter
- free-form body text after the frontmatter

Accepted frontmatter fields used by the current code:

- `id`
- `source_type`
- `timestamp`
- `origin`
- `tags`
- `trust`
- `source_items`

If `id` is missing, it defaults to the input filename stem.

Minimal example:

```md
---
id: 2026-04-12-example
source_type: plain_text
timestamp: 2026-04-12T10:00:00Z
origin: personal-note
tags: [example]
---
# Example note

This is the raw knowledge item to ingest.
```

You can also start from the shipped examples in `skills/memory-ingest/sample_inputs/`.

## 3. Ingest Knowledge Only

Use `skills/memory-ingest/scripts/ingest.py` when you want to ingest one item into one vault without running the benchmark or optimizer.

Stub mode works offline and is the safest first check:

```bash
uv run python skills/memory-ingest/scripts/ingest.py \
  --item skills/memory-ingest/sample_inputs/plain_text.md \
  --vault /tmp/my-memory-vault \
  --stub
```

Live mode uses the `pi` harness:

```bash
uv run python skills/memory-ingest/scripts/ingest.py \
  --item skills/memory-ingest/sample_inputs/plain_text.md \
  --vault /tmp/my-memory-vault
```

What happens on a successful run:

- the script prints one line per operation, like `CREATE "Note Title.md"` or `UPDATE "Note Title.md"`
- filenames are sanitized from note titles
- `update` writes the new body and links, while preserving existing frontmatter keys unless the new proposal overrides them

## 4. Run the Benchmark Harness

If you want to run the full fixed ingest benchmark instead of a single manual ingest:

```bash
uv run python benchmarks/memory-ingest/runner.py --stub
```

Single case:

```bash
uv run python benchmarks/memory-ingest/runner.py --stub --case dialog
```

Record the benchmark result into `results/experiments.jsonl`:

```bash
uv run python benchmarks/memory-ingest/runner.py --stub --record --notes "baseline"
```

Important behavior:

- every case starts from a fresh temp copy of `vaults/sandbox/`
- some cases also layer in case-specific `vault_seed/` notes before ingest
- the sandbox itself is not mutated by benchmark runs

## 5. Run Auto-Optimization

The optimizer only edits one file:

- `skills/memory-ingest/SKILL.md`

Offline smoke test:

```bash
uv run python optimizer/runner.py \
  --stub-ingest \
  --stub-optimizer \
  --notes "offline smoke test"
```

Live optimization:

```bash
uv run python optimizer/runner.py \
  --notes "live optimization attempt"
```

Limit optimization to one benchmark case:

```bash
uv run python optimizer/runner.py \
  --stub-ingest \
  --stub-optimizer \
  --case dialog \
  --notes "single-case experiment"
```

What the optimizer does:

1. Runs the current benchmark as the baseline.
2. Proposes a replacement for `skills/memory-ingest/SKILL.md`.
3. Re-runs the benchmark.
4. Keeps the change only if the new score is strictly higher.
5. Appends a record to `results/experiments.jsonl`.

Keep/reject behavior:

- kept run: commits `skills/memory-ingest/SKILL.md` and `results/experiments.jsonl`
- rejected run: restores `skills/memory-ingest/SKILL.md` from `HEAD` and leaves the new JSONL record in the working tree

Before the optimizer starts, it refuses to run if any of these already have local changes:

- `skills/memory-ingest/SKILL.md`
- `results/experiments.jsonl`
- `benchmarks/memory-ingest/`

## 6. Live-Mode Notes

Live ingest and live optimization shell out to:

```bash
pi -p ...
```

That means:

- the repo does not implement its own model client for ingest or optimization
- `pi` must already be installed and usable in your shell
- any credentials needed by `pi` must already be configured for that harness

The benchmark's optional advisory judge is separate. If you run:

```bash
uv run python benchmarks/memory-ingest/runner.py --stub --llm-judge
```

then `benchmarks/memory-ingest/llm_judge.py` will look for `OPENAI_API_KEY` in the environment or repo `.env`. That judge is advisory only and is not used by the optimizer's keep/reject decision.
