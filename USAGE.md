# Usage (Legacy / Interactive)

> As of Milestone 7, **[`USAGE_v2.md`](USAGE_v2.md) is the primary operator guide**
> for benchmark packs, pack-based optimization, and the generalized workflow.
>
> This file remains the reference for:
> - interactive pi-driven ingest into a personal or sandbox vault
> - the legacy case-based benchmark under `benchmarks/memory-ingest/`
> - the legacy optimizer entry point without `--pack`

This file describes how to use the repository as it is currently implemented.

All commands below assume you run them from the repo root:

```bash
cd /home/albert/Projects/auto-optim-agent
```

## Prerequisites

- `uv` installed
- Python 3.11+
- `git` available if you want to run the optimizer
- `pi` available on `PATH` if you want live ingest via the harness

Install the Python dependencies once:

```bash
uv sync
```

## 1. Ingest In `pi`

The primary way to ingest content is through the `pi` harness with the
`memory-ingest` skill loaded. The harness LLM owns the reasoning; local
helper scripts handle deterministic work.

```text
user -> pi harness -> memory-ingest skill -> helper scripts -> vault
```

In a `pi` session with the skill loaded, you can say things like:

- "ingest this" (with text pasted into chat)
- "ingest the notes in `captures/meeting.txt`"
- "ingest everything in `research/clips/`"
- "turn this conversation into useful vault notes"

The skill will:

1. Gather source material from whatever form you provided
2. Scan the vault for existing notes using `scan_vault.py`
3. Decide what notes to create or update
4. Apply changes via `apply_ingest.py`
5. Report what it changed

No special input format (YAML, frontmatter, etc.) is required from the user.

### Start `pi`

Start `pi` from this repo with the skill loaded:

```bash
./skills/memory-ingest/scripts/run_pi_with_skill.sh
```

Then ask naturally:

- `ingest this`
- `ingest /path/to/file.md`
- `ingest everything in captures/`
- `turn this conversation into useful vault notes`

What this launcher does:

- starts `pi` with `skills/memory-ingest/SKILL.md` loaded
- changes to the repo root first, so helper-script paths resolve correctly
- keeps sessions in a project-local `.pi-agent/sessions/` directory by default
- preserves your normal Pi config in `~/.pi/agent/` when it is writable, so `models.json` and other user settings still apply
- falls back to a fully local `.pi-agent/` directory only if the default Pi directory is not writable
- disables generic `edit` / `write` tools by default; the skill should write only through `apply_ingest.py`
- disables extra `pi` extensions by default so the live skill path stays narrow and repeatable

If you prefer to launch `pi` yourself, the equivalent command is:

```bash
pi --session-dir "$(pwd)/.pi-agent/sessions" --tools read,bash,grep,find,ls --no-extensions --skill skills/memory-ingest/SKILL.md
```

For a fresh read-only QA session after ingest, use:

```bash
pi --session-dir "$(pwd)/.pi-agent/sessions" --tools read,grep,find,ls --no-extensions
```

### What to say in `pi`

Once `pi` is open, ask naturally. Examples:

- `ingest this`
- `ingest /absolute/path/to/file.md`
- `ingest everything in captures/`
- `turn this conversation into useful vault notes`
- `ingest /tmp/meeting.txt into /tmp/my-vault`

The default vault is `vaults/sandbox/`.

If you want a different vault, say so explicitly in the prompt. Examples:

- `ingest this into /tmp/my-vault`
- `ingest notes/research.md into /home/me/obsidian-test-vault`

### What happens

The skill will:

1. Resolve the source material from chat, files, directories, or mixed input.
2. Resolve the target vault path.
3. Scan the vault for existing notes.
4. Decide what notes to create or update.
5. Apply the changes through the deterministic helper layer.
6. Report what it changed.

## 2. Vault Setup

There are two vault paths in the repo:

- `vaults/sandbox/`
  - disposable base vault used by the benchmark runner
  - safe for experiments
- `vaults/staging/`
  - documentation only
  - the personal-vault staging workflow is defined, but not enabled in code

The default vault for the skill is `vaults/sandbox/`. You can point it at
any other directory by saying so in the `pi` prompt. Do not point this at
your real personal Obsidian vault.

## 3. Helper Scripts (Tool Surface)

The skill uses two helper scripts as its tool surface:

### `scan_vault.py` — Read-only vault scanner

```bash
uv run python skills/memory-ingest/scripts/scan_vault.py --vault <path>
uv run python skills/memory-ingest/scripts/scan_vault.py --vault <path> --query "project"
uv run python skills/memory-ingest/scripts/scan_vault.py --vault <path> --limit 20
```

Recursively scans the vault and returns JSON with note titles, paths,
frontmatter, and body previews. Never writes anything.

### `apply_ingest.py` — Proposal applier (single write surface)

```bash
echo '{"operations": [...]}' | uv run python skills/memory-ingest/scripts/apply_ingest.py --vault <path>
uv run python skills/memory-ingest/scripts/apply_ingest.py --vault <path> --proposal-file proposal.json
uv run python skills/memory-ingest/scripts/apply_ingest.py --vault <path> --dry-run < proposal.json
```

Accepts a JSON proposal, validates it, resolves note paths recursively
(including subdirectories), merges frontmatter on updates, and writes
Markdown files. Returns a JSON change summary.

Use `--dry-run` to preview changes without writing.

## 4. Legacy Stub Ingest (Benchmark Adapter)

The `ingest.py` script is retained only as a benchmark adapter. It loads
a single knowledge item file (with optional YAML frontmatter), produces a
deterministic stub proposal, and applies it via the helper layer.

```bash
uv run python skills/memory-ingest/scripts/ingest.py \
  --item skills/memory-ingest/sample_inputs/plain_text.md \
  --vault /tmp/my-memory-vault \
  --stub
```

This is **not** the normal user path. Use `pi` for real ingest. This script
exists so the benchmark runner can drive the stub harness through a single
CLI entry point.

## 5. Run the Benchmark Harness

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
- note scanning is recursive (finds notes in subdirectories too)

## 6. Run Auto-Optimization

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

Current scope:

- this optimizer runs against the fixed `benchmarks/memory-ingest/` benchmark
- it does not yet run the `datasets/geopolitics_apr_2026_memory_benchmark/` question-answer loop
- wiring the geopolitics dataset into auto-optimization requires a separate QA harness that:
  - asks questions from `benchmark/questions.json` in a fresh read-only session
  - constrains answering to the produced vault only
  - scores answers against `gold_points` / `gold_points_min`
  - returns one aggregate score the optimizer can use for keep/revert

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

## 7. Advisory LLM Judge

The benchmark's optional advisory judge is separate:

```bash
uv run python benchmarks/memory-ingest/runner.py --stub --llm-judge
```

`benchmarks/memory-ingest/llm_judge.py` will look for `OPENAI_API_KEY` in
the environment or repo `.env`. That judge is advisory only and is not
used by the optimizer's keep/reject decision.
