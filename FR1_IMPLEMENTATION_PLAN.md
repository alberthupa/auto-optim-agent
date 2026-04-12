# FR1 Implementation Plan

This file turns [FR1.md](/home/albert/Projects/auto-optim-agent/FR1.md) into a concrete implementation plan.

It is a replacement plan for the current inverted ingest architecture.

The target end state is:

```text
user -> pi harness -> memory-ingest skill -> local helper scripts -> vault
```

The target is **not**:

```text
user -> ingest.py -> pi -> proposal -> ingest.py writes vault
```

## Outcome

When this plan is complete, a user should be able to:

1. start `pi`
2. ask it to ingest chat text, one file, several files, or a directory
3. have `pi` choose and use the `memory-ingest` skill
4. have the skill call local deterministic helpers
5. get plain Markdown notes written into the vault root
6. run benchmarks and optimization against that same real skill path

## Constraints

- first-class harness target is `pi`
- new notes are written into the vault root
- updates to existing notes happen automatically by default
- no user-facing YAML or repo-specific input wrapper is required
- no helper script may call `pi` or any other harness
- deterministic scoring remains the primary optimization signal

## Implementation Strategy

Do this as a migration, not a big-bang rewrite.

The main rule is:

- first build the helper layer the harness should call
- then rewrite the skill around that helper layer
- then change the benchmark so it drives the real skill path
- only after that update the optimizer

Do **not** optimize or benchmark the old inverted path once the new path exists.

## Workstreams

There are four code workstreams:

1. `skills/memory-ingest/` redesign
2. helper-script redesign under `skills/memory-ingest/scripts/`
3. benchmark redesign under `benchmarks/memory-ingest/`
4. optimizer redesign under `optimizer/`

Docs should be updated only after the runtime path is real.

## Phase 0: Freeze The Wrong Surface

Aim:

- stop treating the current `ingest.py` flow as the intended product

Tasks:

- mark the current [skills/memory-ingest/scripts/ingest.py](/home/albert/Projects/auto-optim-agent/skills/memory-ingest/scripts/ingest.py) as legacy or transitional in comments and docs
- remove or rewrite any documentation that tells users to run `ingest.py` as the primary ingest experience
- update [USAGE.md](/home/albert/Projects/auto-optim-agent/USAGE.md) later so direct script execution is clearly a helper/test path, not the main product
- keep the old path temporarily only if it helps the migration or benchmarking bootstrap

Definition of done:

- no core doc describes `ingest.py -> pi` as the intended architecture
- the repo has one clear direction: harness-owned skill execution

## Phase 1: Build The Deterministic Helper Layer

Aim:

- create the small tool surface the `pi` skill will call

New scripts to build:

- [skills/memory-ingest/scripts/scan_vault.py](/home/albert/Projects/auto-optim-agent/skills/memory-ingest/scripts/scan_vault.py)
- [skills/memory-ingest/scripts/apply_ingest.py](/home/albert/Projects/auto-optim-agent/skills/memory-ingest/scripts/apply_ingest.py)

Optional in the same phase if needed:

- `skills/memory-ingest/scripts/normalize_sources.py`

### 1A. `scan_vault.py`

Responsibilities:

- scan the vault recursively
- load Markdown notes from all subdirectories
- extract note title, relative path, frontmatter, and small body preview
- support title/path lookup
- support a simple relevance filter for the harness to reduce context size

CLI shape:

- `--vault <path>` required
- `--query <text>` optional
- `--limit <n>` optional
- `--json` output only

Important rules:

- no writes
- no harness calls
- must work even on large-ish vaults without exploding context

### 1B. `apply_ingest.py`

Responsibilities:

- accept a structured proposal from stdin or `--proposal-file`
- validate the proposal schema
- resolve creates and updates against the vault recursively
- write Markdown notes
- preserve existing frontmatter keys unless overridden
- return a machine-readable change summary

CLI shape:

- `--vault <path>` required
- `--proposal-file <path>` optional
- `--dry-run` optional
- JSON in, JSON out

Important rules:

- this becomes the single write surface for ingest
- it must reject invalid proposals loudly
- update resolution must work even if the target note is outside the vault root

### 1C. Internal proposal schema

Move the structured proposal contract out of the current legacy flow and make
it the formal helper boundary.

Recommended fields:

- `operations`
- per operation:
  - `op`
  - `title`
  - `target_path_hint` optional
  - `frontmatter`
  - `body`
  - `links`
  - `rationale`

Decision:

- the user never sees or prepares this schema
- only the harness LLM and `apply_ingest.py` care about it

Definition of done:

- the helper layer is usable without any harness-calling code
- a fake JSON proposal can be applied to a vault through `apply_ingest.py`
- recursive scan and recursive update resolution both work

## Phase 2: Rewrite The Skill For `pi`

Aim:

- make the skill usable from inside `pi` as the real product surface

Primary file to rewrite:

- [skills/memory-ingest/SKILL.md](/home/albert/Projects/auto-optim-agent/skills/memory-ingest/SKILL.md)

Tasks:

- rewrite `SKILL.md` so it instructs the harness LLM to:
  - detect ingest intent
  - determine what source material the user means
  - gather raw source from chat, file paths, directories, or mixed inputs
  - resolve the target vault path
  - call `scan_vault.py`
  - reason about note operations
  - call `apply_ingest.py`
  - summarize the result to the user
- remove instructions that assume Python is the outer entrypoint
- remove instructions that require user-authored YAML or fixed knowledge-item files
- explicitly document the clarifying-question policy from [FR1.md](/home/albert/Projects/auto-optim-agent/FR1.md)
- explicitly document automatic update behavior

Needed skill behavior:

- if the user pastes text directly, the skill should use that text as source
- if the user references one file, the skill should read it
- if the user references a directory, the skill should enumerate and ingest an internal bundle
- if the user references ambiguous content, the skill should ask one short clarifying question

`pi`-specific implementation note:

- the design should be written for `pi` first, not for a synthetic cross-harness abstraction
- if `pi` needs a thin wrapper or invocation convention for local helper tools, implement that directly inside the skill instructions and helper usage examples

Definition of done:

- a person using `pi` can naturally ask to ingest content without preparing special files
- the skill uses helper scripts rather than being wrapped by them
- no skill path depends on a helper script calling `pi`

## Phase 3: Replace The Legacy Ingest Entry Point

Aim:

- remove the architectural confusion caused by [ingest.py](/home/albert/Projects/auto-optim-agent/skills/memory-ingest/scripts/ingest.py)

Tasks:

- decide whether to delete `ingest.py` or keep it only as a thin migration helper
- if kept, strip out any `pi` invocation and make it call the deterministic helper layer only
- remove prompt-building and harness-calling responsibilities from `ingest.py`
- move any reusable validation/writer logic from `ingest.py` into shared functions used by `apply_ingest.py`
- ensure there is exactly one write path to the vault

Recommended decision:

- do not keep `ingest.py` as the main path
- either delete it or rename its role to something obviously non-product, such as a legacy benchmark adapter

Definition of done:

- there is no primary code path in which a Python script calls `pi`
- vault writes are centralized behind the new helper layer

## Phase 4: Redesign The Benchmark Around The Real Skill Path

Aim:

- make benchmark runs exercise the same skill path users will actually use

Primary files to replace or heavily rewrite:

- [benchmarks/memory-ingest/runner.py](/home/albert/Projects/auto-optim-agent/benchmarks/memory-ingest/runner.py)
- [benchmarks/memory-ingest/README.md](/home/albert/Projects/auto-optim-agent/benchmarks/memory-ingest/README.md)

Current problem:

- the benchmark drives `ingest.py` directly
- that tests the wrong product

New benchmark shape:

1. create a fresh temp copy of `vaults/sandbox/`
2. seed case-specific notes if needed
3. present the case to the `pi` execution path in user-facing form
4. let the harness LLM use `memory-ingest`
5. score the resulting vault deterministically

Case format changes:

- keep `case.yaml`
- keep fixture files under `input/` and optional `vault_seed/`
- add a field describing how the user-facing request should be presented to the harness

Recommended new case fields:

- `user_request`
  - the natural-language instruction sent to the harness
- `source_mode`
  - `chat_text`, `file`, `directory`, or `mixed`
- `source_refs`
  - paths or fixture references used to stage the benchmark request

Important rule:

- the benchmark may still use files internally to stage source material
- but it must present them to the harness in a way that mirrors real usage

Stub mode redesign:

- keep an offline stub mode if it helps development
- but the stub should mimic the harness-owned flow, not the legacy script-owned flow

Definition of done:

- the benchmark exercises the same ingest path a `pi` user uses
- deterministic scoring still works
- legacy script-entry benchmarking is gone or clearly marked transitional only

## Phase 5: Redesign The Optimizer Around The Real Skill Path

Aim:

- make optimization runs improve the actual harness-owned skill

Primary files:

- [optimizer/runner.py](/home/albert/Projects/auto-optim-agent/optimizer/runner.py)
- [optimizer/README.md](/home/albert/Projects/auto-optim-agent/optimizer/README.md)

Tasks:

- keep the editable surface narrow:
  - `skills/memory-ingest/SKILL.md` first
  - helper scripts only later if absolutely necessary
- change optimizer benchmark calls so they run the new harness-driven benchmark
- update safety checks for the new runtime surface if needed
- keep `git` as the keep/revert mechanism
- keep deterministic score as the keep/reject authority

Important rule:

- do not optimize a fake path the user will never invoke

Definition of done:

- optimizer runs the real benchmark path
- a kept change corresponds to an improvement in the actual `pi` skill behavior

## Phase 6: Vault Semantics Hardening

Aim:

- make vault behavior safe and realistic enough for real use

Tasks:

- implement recursive note discovery
- implement title collision handling across subdirectories
- define the exact note resolution rule for updates when several notes share a title
- define path-safety rules for create operations
- define how `[[wiki links]]` are rendered when links point at notes that already live in subdirectories
- preserve human readability of written Markdown

Required policy decisions already made:

- create new notes in vault root
- update existing notes automatically by default

One technical rule must be explicit:

- if multiple existing notes have the same title, automatic update must not silently choose the wrong one

Recommended implementation:

- treat duplicate-title matches as an ambiguity
- ask the harness to resolve it, or fail the helper call with a clear error

Definition of done:

- automatic updates are safe in normal cases
- ambiguous update targets fail explicitly

## Phase 7: Docs And Operator Workflow

Aim:

- make the repo understandable again after the architectural flip

Files to update:

- [README.md](/home/albert/Projects/auto-optim-agent/README.md)
- [USAGE.md](/home/albert/Projects/auto-optim-agent/USAGE.md)
- [optimizer/README.md](/home/albert/Projects/auto-optim-agent/optimizer/README.md)
- [benchmarks/memory-ingest/README.md](/home/albert/Projects/auto-optim-agent/benchmarks/memory-ingest/README.md)
- possibly [project_plan.md](/home/albert/Projects/auto-optim-agent/project_plan.md), if you want the old milestone plan formally superseded

Docs changes required:

- explain that the harness is the outer runtime
- explain that the skill can ingest chat text, files, directories, and mixed inputs
- explain that no special user-facing input format is required
- explain that helper scripts are tool backends for the harness
- remove docs that present direct script ingest as the intended product
- document the new benchmark and optimizer entrypoints

Definition of done:

- a new contributor would not reconstruct the same inverted architecture by reading the docs

## Migration Order

Use this sequence:

1. build `scan_vault.py`
2. build `apply_ingest.py`
3. move validation/write logic out of legacy `ingest.py`
4. rewrite `SKILL.md` for `pi`
5. prove manual `pi`-driven ingest works
6. rewrite benchmark runner around the `pi` skill path
7. rewrite optimizer to use the new benchmark
8. clean up or remove legacy entrypoints
9. rewrite docs

This order matters.

If the benchmark is rewritten before the real skill path exists, it will drift.
If the skill is rewritten before helper tools exist, it will turn into vague promptware.

## Deliverables

Minimum deliverables for the FR1 migration:

- new recursive vault scanner helper
- new deterministic apply-ingest helper
- rewritten `SKILL.md` for `pi`
- benchmark runner that drives the real skill path
- optimizer runner that uses the new benchmark
- updated documentation
- old `ingest.py -> pi` path removed or clearly demoted

## Acceptance Criteria

The redesign is complete only if all of these are true:

1. A `pi` user can ask to ingest content without preparing a special input file.
2. The `memory-ingest` skill, not a wrapper script, is what the user is actually using.
3. No helper script invokes `pi`.
4. Vault scans are recursive.
5. New notes are created in the vault root.
6. Existing notes are updated automatically by default when the target is unambiguous.
7. Benchmark runs exercise the same harness-owned skill path.
8. Optimizer runs improve that same real path.
9. The docs describe the real architecture clearly.

## Explicit Non-Goals

Do not do these during FR1:

- do not build a generic multi-harness abstraction layer
- do not build a service, daemon, or web UI
- do not add a database
- do not require users to prepare YAML knowledge wrappers
- do not let helper scripts make hidden secondary LLM calls

## Suggested First Commit Breakdown

If this work is implemented incrementally, the first sensible commits are:

1. `memory-ingest: add recursive vault scan helper`
2. `memory-ingest: add apply-ingest helper and shared schema`
3. `memory-ingest: rewrite pi skill around helper tools`
4. `benchmark: drive harness-owned memory-ingest path`
5. `optimizer: evaluate rewritten harness-owned skill`
6. `docs: remove legacy ingest entrypoint guidance`

That sequence keeps the migration legible and reversible.
