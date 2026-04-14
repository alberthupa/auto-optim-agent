# USAGE v2 — Generalized Benchmark-Pack Workflow

This is the **primary** operator guide as of Milestone 7. It supersedes the
optimization-loop and benchmark sections of `USAGE.md` (which remains a
useful reference for the legacy case-based benchmark and the interactive
pi ingest workflow).

All commands assume the repo root:

```bash
cd /home/albert/Projects/auto-optim-agent
uv sync   # once
```

## 1. The Generalized Workflow At A Glance

```
┌─────────────┐   fresh temp      ┌────────────┐   fresh read-only     ┌─────────┐
│ corpus (ro) │ ─── vault ───▶    │  ingest    │ ─── session ─────▶    │   QA    │
│  +          │ + optional seed   │  (skill)   │   vault-only access   │         │
│ vault_seed  │                   └────────────┘                       └────┬────┘
└─────────────┘                                                              │
                                                                             ▼
                   ┌──────────┐   keep/revert   ┌────────────┐         ┌─────────┐
                   │ skill diff│◀──  git  ──────│ optimizer  │◀────────│ scorer  │
                   └──────────┘                  └────────────┘         └─────────┘
                                                                             │
                                                                 append-only results/
```

A **benchmark pack** is one frozen evaluation target: corpus + questions +
gold points. The pipeline is pack-agnostic; every concrete evaluation names
exactly one pack. A pack is immutable during a run: runners copy `corpus/`
and `vault_seed/` into a temp workspace, and the optimizer's editable
surface (`skills/memory-ingest/SKILL.md`) can't reach pack files.

## 2. Fast Start

Three commands, in order, using the tiny smoke pack:

```bash
# a) validate
uv run python benchmark_packs/_runner/cli.py validate benchmark_packs/smoke

# b) one full pack pipeline run (ingest -> QA -> score)
uv run python benchmark_packs/_runner/cli.py run benchmark_packs/smoke --subset full --mode stub

# c) one optimization experiment against that pack
uv run python optimizer/runner.py \
  --pack benchmark_packs/smoke --subset full --pack-mode stub --stub-optimizer \
  --notes "fast-start smoke"
```

On the real geopolitics pack, swap the path:

```bash
uv run python optimizer/runner.py \
  --pack datasets/geopolitics_apr_2026_memory_benchmark \
  --subset dev --pack-mode stub --stub-optimizer \
  --notes "geopolitics dev smoke"
```

## 3. Lifecycle

### 3.1 Choose or author a pack

Existing packs:

- `benchmark_packs/smoke/` — tiny fantasy fixture, 2 corpus files, 4 questions. Generality proof.
- `datasets/geopolitics_apr_2026_memory_benchmark/` — 50 corpus docs, 96 questions. Real target.

To add a new pack, follow `benchmark_packs/README.md`. Minimum required:

```
<pack_root>/
  pack.yaml                       # id, schema_version, description
  corpus/<one_or_more_files>
  benchmark/questions.json
  benchmark/README.md
```

Optional: `vault_seed/`, `benchmark/config.yaml`, `benchmark/dev_questions.json`, `benchmark/holdout_questions.json`.

Always validate after authoring:

```bash
uv run python benchmark_packs/_runner/cli.py validate <pack_root>
```

### 3.2 Run the pipeline manually (outside the optimizer)

```bash
uv run python benchmark_packs/_runner/cli.py run <pack_root> --subset dev --mode stub
```

Outputs land in a fresh temp workdir (prefix `pack-<id>-`):

- `vault/` — produced vault after ingest
- `ingest_report.json`
- `answers.json`
- `score_report.json`

### 3.3 Run one optimization experiment

```bash
uv run python optimizer/runner.py \
  --pack <pack_root> --subset dev --pack-mode stub \
  --notes "why this run matters"
```

What happens:

1. Baseline evaluation on the subset
2. Optimization agent proposes one `SKILL.md` replacement
3. Candidate evaluation on the same subset
4. Keep if `candidate > baseline`, else `git restore SKILL.md`
5. Append one line to `results/experiments.jsonl`
6. Persist the full trace under `results/artifacts/<experiment_id>/`

Flags:

- `--subset {dev,holdout,full}` — question set. Default `dev`.
- `--pack-mode {stub,harness}` — stub is deterministic; harness is the live path (see §6).
- `--stub-optimizer` — propose a deterministic edit instead of calling a live optimizer model (useful for CI and wiring checks).

### 3.4 Inspect artifacts

Each experiment writes a self-contained directory:

```
results/artifacts/<experiment_id>/
  baseline_answers.json          # what the baseline skill answered
  baseline_score_report.json     # per-question + aggregate
  candidate_answers.json
  candidate_score_report.json
  skill_before.md                # SKILL.md as it was at run start
  skill_after.md                 # SKILL.md after the proposed change (== before on reject)
  skill.diff                     # unified diff
  pack_snapshot.json             # pack id, subset, config, question count
```

Rejected runs keep their full trace — the skill is restored via git, but
the artifacts stay so you can see *why* the proposal didn't help.

### 3.5 Read the results log

`results/experiments.jsonl` is append-only JSONL. One line per experiment.
Key fields:

| field                     | since | notes                                                 |
| ------------------------- | ----- | ----------------------------------------------------- |
| `timestamp`               | M3    | UTC ISO-8601                                          |
| `experiment_id`           | M3    | UUID, matches the artifacts dir                       |
| `skill_git_sha`           | M3    | blob sha of `SKILL.md` at commit time                 |
| `baseline_score`          | M3    | aggregate before the change                           |
| `new_score`               | M3    | aggregate after (or pre-revert value on reject)       |
| `per_dimension`           | M3    | legacy: dimension scores. pack: per_difficulty        |
| `kept`                    | M3    | `true` means a commit; `false` means `git restore`    |
| `notes`                   | M3    | free-form operator notes                              |
| `change_summary`          | M3    | one-line optimizer summary                            |
| `hypothesis`              | M3    | optimizer's stated reason                             |
| `stub_ingest`             | M3    | whether ingest ran in stub mode                       |
| `stub_optimizer`          | M3    | whether optimizer ran in stub mode                    |
| `eval_backend`            | M7    | `"legacy"` or `"pack"`                                |
| `pack_id`                 | M7    | pack identifier (pack runs only)                      |
| `pack_subset`             | M7    | `"dev"` / `"holdout"` / `"full"`                      |
| `artifacts_dir`           | M7    | relative path under repo root                         |
| `skill_git_sha_before`    | M7    | blob sha of `SKILL.md` at run start                   |

Legacy (pre-M7) lines are still valid; new fields are additive.

Quick greps:

```bash
# score history for one pack
grep '"pack_id": "geopolitics-apr-2026"' results/experiments.jsonl | jq '{ts: .timestamp, kept: .kept, base: .baseline_score, new: .new_score}'

# rejected pack runs (useful for root-causing)
grep '"eval_backend": "pack"' results/experiments.jsonl | jq 'select(.kept == false) | {id: .experiment_id, base: .baseline_score, new: .new_score, why: .change_summary}'
```

### 3.6 Compare two experiments

Artifacts are plain files, so a two-experiment comparison is a shell diff:

```bash
# score delta
diff <(jq '.aggregate' results/artifacts/<ID_A>/candidate_score_report.json) \
     <(jq '.aggregate' results/artifacts/<ID_B>/candidate_score_report.json)

# skill evolution
diff results/artifacts/<ID_A>/skill_after.md results/artifacts/<ID_B>/skill_after.md

# per-question deltas
jq -s '.[0].per_question as $a | .[1].per_question |
  map(.question_id as $qid | . + {prev: ($a[] | select(.question_id==$qid).score)})' \
  results/artifacts/<ID_A>/candidate_score_report.json \
  results/artifacts/<ID_B>/candidate_score_report.json
```

## 4. Dev / Holdout Discipline

- **Optimization loops run on `--subset dev`.** Small and stable for fast iteration.
- **Holdout is a checkpoint.** Run against `--subset holdout` only at milestone boundaries, to sanity-check that improvements on dev generalize.
- **Never tune against holdout.** Running many experiments against holdout defeats its purpose and should be treated as a benchmark violation, not just a convention.
- **Subsets are frozen content.** Changing `dev_questions.json` or `holdout_questions.json` mid-milestone is a benchmark modification and must be a separate, reviewed commit — never bundled with an optimization experiment.

## 5. Safety Boundaries

- **Pack immutability.** Runners treat pack roots as read-only. Copy before mutate.
- **Editable surface stays narrow.** The optimizer can only rewrite `skills/memory-ingest/SKILL.md`. It cannot touch packs, runners, scorers, or the results log schema.
- **Fresh temp vault per run.** Ingest never writes to `vaults/sandbox/` or any pre-existing user vault.
- **Fresh read-only QA session.** QA uses only the produced temp vault. No other filesystem access.
- **Legacy runtime guard.** `ensure_clean_runtime_state` refuses to run when `SKILL.md`, `results/experiments.jsonl`, or `benchmarks/memory-ingest/` already have local edits.
- **Personal vault off-limits.** Unchanged from Milestone 6. Personal vaults are never a pack root and never an ingest target for pack runs.
- **Credentials.** Harness credentials live in `.env` (gitignored). Scripts never read them directly; the pi launcher does.

## 6. Pack Mode: Stub vs Harness

- `--pack-mode stub` (default) is deterministic and offline. Ingest uses `skills/memory-ingest/scripts/ingest.py --stub`. QA uses a keyword-retrieval stub inside `qa_runner.py`. Good for wiring checks, CI, and fast optimizer iteration.
- `--pack-mode harness` is reserved for the live pi-driven path. As of this milestone, `qa_runner.py`'s harness backend raises `NotImplementedError` — wiring the live session shape belongs to a follow-up milestone. The session rules below are already fixed so that wiring is straightforward.

### Session rules (binding on the live wiring)

- **Ingest session:** read access to the pack's `corpus/` copy + write access to the temp vault only. Tools whitelisted: `read,bash,grep,find,ls` plus the skill's helper scripts. No network. No access to other packs, the repo, or the user's home dir.
- **QA session:** read access to the temp vault only. Tools whitelisted: `read,grep,find,ls`. No write tools. No bash-exec that can escape the vault. No network. A fresh session per question or per batch is acceptable; carryover between QA runs is not.
- **Session artifacts:** session working dirs land under `<workdir>/sessions/ingest/` and `<workdir>/sessions/qa/`, predictable and cleanable. The temp workdir root is what the CLI reports; everything under it is disposable.

## 7. Failure Handling

- **One failing ingest item.** Recorded in `ingest_report.json` with `status: error` and error text; the run continues on remaining items. The eval runner only aborts if zero items succeed.
- **One QA timeout or error.** Written as an answer record with `status: timeout` or `status: error` and an `error` field. The scorer treats non-`ok` statuses as zero for that question but continues scoring the rest.
- **Partial answer files.** The QA runner always writes `answers.json` after the last question attempt, even if earlier attempts errored. Partial files are valid input to the scorer.
- **Optimizer proposal parse failure.** Exits non-zero *before* any skill mutation. The working tree stays clean.
- **Interrupted experiment.** If the optimizer crashes after applying the skill change, `restore_skill()` runs in the `except` handler. If the process is hard-killed, recover by hand with `git restore -- skills/memory-ingest/SKILL.md`.
- **Rerun semantics.** Experiment ids are UUIDs; a rerun is just another experiment. To re-attempt a failed run, run the CLI again with the same flags — no special resume mode. Compare artifacts by hand if you need the paired trace.

## 8. Reporting And Inspection

Pinned commands (prefer these over inventing new scripts):

```bash
# validate pack
uv run python benchmark_packs/_runner/cli.py validate <pack>

# one end-to-end manual run
uv run python benchmark_packs/_runner/cli.py run <pack> --subset dev --mode stub

# just score an already-produced answers.json
uv run python benchmark_packs/_runner/scorer.py <pack> --answers path/to/answers.json --subset dev

# one optimization experiment
uv run python optimizer/runner.py --pack <pack> --subset dev --stub-optimizer --notes "..."
```

For dashboards and score-over-time views, read `results/experiments.jsonl`
directly with `jq`. Do not add a dashboard layer — the file-first contract
is the point.

## 9. Advisory LLM-Judge

The Milestone 4 LLM-judge (`benchmarks/memory-ingest/llm_judge.py`) is a
secondary signal for the **legacy** case-based benchmark. For pack-based
evaluation it stays **off by default** and is considered advisory:

- Primary score is always the deterministic gold-point scorer.
- A pack may opt in to an advisory judge via `benchmark/config.yaml`:
  `advisory_judge: { enabled: true, prompt_id: <name> }`.
- When enabled, the advisory judge emits a secondary score that never
  alters keep/revert. It is persisted in the artifact tree for inspection.
- The prompt is fixed, versioned, and never editable by the optimizer.

No pack ships with `advisory_judge.enabled = true` as of this milestone.

## 10. How To Add A New Benchmark Pack

1. Pick a short lowercase id and directory under `benchmark_packs/<id>/`.
2. Write `pack.yaml` (id, schema_version: 1, description).
3. Drop source files into `corpus/`. Any format the ingest skill understands.
4. Author `benchmark/questions.json` following `_schemas/question_schema.json`.
5. Write `benchmark/README.md` describing what the pack evaluates.
6. (Optional) Add `dev_questions.json` and `holdout_questions.json` subsets. Keep dev small and stable.
7. (Optional) Add `benchmark/config.yaml` to override scoring normalization, weights, or limits.
8. (Optional) Add `vault_seed/` if the pack should start from pre-existing notes.
9. Validate: `uv run python benchmark_packs/_runner/cli.py validate <pack>`.
10. Smoke-run: `uv run python benchmark_packs/_runner/cli.py run <pack> --subset full --mode stub`.
11. Commit. The pack is now available to the optimizer via `--pack <path>`.

## 11. Relationship To USAGE.md

`USAGE.md` still documents:

- interactive pi-driven ingest of ad-hoc content into a personal or sandbox vault
- the legacy case-based benchmark under `benchmarks/memory-ingest/`
- the legacy optimizer entry point without `--pack`

This file (`USAGE_v2.md`) is the primary guide for:

- anything involving a benchmark pack
- pack-based optimization
- multi-pack generalization

When in doubt, start with `USAGE_v2.md`. Use `USAGE.md` only when you
specifically want the interactive ingest flow or the legacy case runner.
