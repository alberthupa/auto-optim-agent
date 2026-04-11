# Project Plan

This file is the build sheet for the project.

`README.md` defines the purpose, scope, and architectural rules.

This file defines:

- milestone order
- current progress
- concrete stories
- concrete tasks
- definition of done for each stage

Before marking any milestone complete, run the Stage Gate Checklist in `README.md`.

## Current Status

- [x] Milestone 0: Project skeleton
- [x] Milestone 1: Manual ingest baseline
- [ ] Milestone 2: Fixed benchmark
- [ ] Milestone 3: Optimization loop
- [ ] Milestone 4: Better knowledge variety
- [ ] Milestone 5: Staging vault realism
- [ ] Milestone 6: Personal vault staging path

## Milestone 0: Project Skeleton

Aim:

- create the minimum repository structure so another builder can start implementing without rethinking the architecture

Stories:

- [x] As a new contributor, I can identify where skills, benchmarks, vaults, results, and optimizer code live.
- [x] As a contributor, I can read the README for purpose and rules and use this file as the execution plan.
- [x] As a contributor, I am not distracted by stray secret files sitting in the repo root.

Tasks:

- [x] Create `skills/memory-ingest/`.
- [x] Create `benchmarks/memory-ingest/`.
- [x] Create `vaults/sandbox/`.
- [x] Create `results/`.
- [x] Create `optimizer/`.
- [x] Move milestone execution detail out of `README.md` into `project_plan.md`.
- [x] Add ignore rules for `gitkeys` and `gitkeys.pub`.
- [x] Move `gitkeys` and `gitkeys.pub` out of the repository tree.
- [x] Add stub files so the structure is visible and tracked in git.
- [x] Run the stage gate mentally against the current structure and keep it narrow.

Definition of done:

- [x] The repository structure clearly reflects one skill, one benchmark area, one sandbox vault, one optimizer path, and one results area.
- [x] `README.md` acts as the project brief instead of an execution checklist.
- [x] `project_plan.md` is detailed enough that another builder can continue work directly.
- [x] No obvious secret files remain in the repository root.

## Milestone 1: Manual Ingest Baseline

Aim:

- implement the first usable `memory-ingest` skill as a **hybrid** of an LLM-in-harness judgment step and a thin Python glue layer, with clear file-based inputs and outputs

Architecture for this milestone (from README's Execution Model):

- Python loads one knowledge item and a small slice of vault context
- Python calls the harness once with `SKILL.md` and that context
- The LLM returns one **structured proposal** (titles, frontmatter, bodies, links, create/update decisions)
- Python validates the proposal and writes Markdown files
- One LLM call per ingest item, one response schema, one thin writer

Stories:

- [x] As a builder, I can pass one knowledge item and one target vault path into the skill.
- [x] As a user, I can inspect the resulting Markdown notes and understand what the ingest step did.
- [x] As a builder, I can run the baseline ingest from a simple CLI command without extra services.
- [x] As a builder, I can run the full pipeline in a **stub/dry-run mode** even before the live harness (PI) is configured.

Tasks:

- [x] Bootstrap `uv` and a single repo-root `pyproject.toml`; no per-subdirectory environments.
- [x] Add `.env` handling for harness credentials (`.env` is gitignored; `.env.example` is tracked).
- [x] Define the skill contract in `skills/memory-ingest/SKILL.md` — behavioral instructions plus the response schema the LLM must return.
- [x] Define the **knowledge item wrapper**: a simple on-disk format that can carry arbitrary text (plain text, transcripts, fragments, mixed bundles) plus minimal metadata (source type, timestamp, origin, tags, optional trust).
  - raw content stays untouched; messiness is expected
- [x] Define the **structured proposal schema** (initial version):
  - list of note operations (`create` or `update`)
  - per note: target filename, frontmatter, body, outgoing links
  - optional per-note rationale / confidence
- [x] Decide and document the vault filename/slug scheme (proposal: human-readable `Title Of Note.md`, Obsidian-native, with a small sanitizer for filesystem-unsafe characters).
- [x] Implement the Python ingest entry point:
  - reads one knowledge item
  - loads a small vault context slice
  - calls the harness once (real or stub)
  - validates the returned proposal against the schema
  - applies writes to Markdown files
- [x] Implement a **stub harness** mode so the pipeline runs end-to-end without a live LLM (deterministic canned proposal for development).
- [x] Create at least three sample inputs:
  - [x] one plain text item
  - [x] one dialog or chat transcript
  - [x] one rough note bundle
- [x] Ensure the output vault stays human-readable.
- [x] Run the Stage Gate Checklist from `README.md`.

Definition of done:

- [x] A single command can ingest a sample item into the sandbox vault.
- [x] Output notes are readable Markdown with sensible naming and links.
- [x] The LLM/Python split is respected: the LLM returns a structured proposal and Python performs all file writes.
- [x] The pipeline runs end-to-end in stub mode even if the live harness is not yet wired.
- [x] The implementation stays small enough to understand in one sitting.
- [x] No database, service, or framework layer is introduced.

## Milestone 2: Fixed Benchmark

Aim:

- create a stable benchmark that evaluates usefulness of the resulting vault, not just formatting

Stories:

- [ ] As a builder, I can run the benchmark repeatedly and get stable results from the same skill version.
- [ ] As a reviewer, I can inspect benchmark cases and understand what good behavior looks like.
- [ ] As the optimizer, I am judged by a fixed scorer rather than a moving target.

Scope note:

- Milestone 2 scoring is **fully deterministic**. No LLM-judge. A secondary LLM-judge signal may be considered in a later milestone under the rules in README's Benchmark Philosophy.

Tasks:

- [ ] Define the benchmark case format: one directory per case under `benchmarks/memory-ingest/cases/<case-name>/`, containing:
  - `case.yaml` — case metadata, input pointers, and expected deterministic checks (expected notes, required links, required facts, duplicate threshold, etc.)
  - `input/` — raw input files for that case (free-form text, transcript, fragments, mixed bundle)
- [ ] Create initial hand-written cases for:
  - [ ] a plain text knowledge item
  - [ ] a dialog or transcript
  - [ ] a messy or repetitive input
- [ ] Define deterministic scoring dimensions:
  - expected notes exist
  - expected outgoing links exist
  - duplicate count stays below a threshold
  - required facts appear in the expected notes
  - source metadata preserved
  - note count did not explode
- [ ] Implement the benchmark runner as a thin Python script:
  - copies `vaults/sandbox/` to a fresh working directory per run
  - runs ingest for each case's inputs
  - scores the resulting vault against `case.yaml`
  - emits a single aggregate score plus per-dimension breakdown
- [ ] Define the **results log format**: `results/experiments.jsonl`, append-only JSONL, one object per experiment with at least:
  - `timestamp`, `experiment_id`, `skill_git_sha`, `baseline_score`, `new_score`, `per_dimension`, `kept` (bool), `notes`
- [ ] Ensure benchmark runs use a fresh sandbox copy or fresh state every time.
- [ ] Document what the score means in `benchmarks/memory-ingest/README.md`.
- [ ] Run the Stage Gate Checklist from `README.md`.

Definition of done:

- [ ] The same code and same input produce repeatable scores.
- [ ] Benchmark cases are readable by a human.
- [ ] The scorer is separate from the editable skill and is not touched during ingest runs.
- [ ] The benchmark rewards useful memory structure rather than just pretty formatting.
- [ ] Scoring is 100% deterministic in this milestone.

## Milestone 3: Optimization Loop

Aim:

- implement the narrow keep-or-revert loop that lets the agent improve the skill against the fixed benchmark

Stories:

- [ ] As a builder, I can run a baseline score, attempt a skill change, and see the result recorded.
- [ ] As a reviewer, I can tell which change improved the score and which change was rejected.
- [ ] As a future maintainer, I can understand the optimizer without learning a framework.

Two-role model (from README's Optimization Model):

- **Execution agent** — runs the current `memory-ingest` skill to ingest benchmark inputs.
- **Optimization agent** — reads current skill files plus benchmark results, proposes a patch.
- Both roles may share the same underlying model/harness, but they are conceptually and operationally separate.

Tasks:

- [ ] Define the editable surface for the optimizer (v1: `SKILL.md` only; v2 may extend to one helper script).
- [ ] Implement a thin experiment runner under `optimizer/` that:
  - captures a baseline score on a clean sandbox
  - invokes the optimization agent with current skill + last results
  - applies the proposed patch to the editable surface
  - runs the benchmark on a fresh sandbox
  - keeps or reverts the change based on score delta
- [ ] Use `git` as the keep/revert mechanism (commit on keep, `git restore` on revert). Do not hand-roll a diff store.
- [ ] Append each experiment outcome to `results/experiments.jsonl`.
- [ ] Keep a running baseline score for comparison.
- [ ] Ensure each run starts from clean benchmark state.
- [ ] Ensure the optimization agent cannot touch `benchmarks/` during a run (enforce in the runner, not just by convention).
- [ ] Run the Stage Gate Checklist from `README.md`.

Definition of done:

- [ ] The system can run baseline, propose one change, evaluate it, and keep or reject it automatically.
- [ ] Result logs (`results/experiments.jsonl`) are readable without special tooling.
- [ ] The optimizer does not modify the benchmark during a run.
- [ ] Keep/revert is handled via `git`.
- [ ] The implementation remains a small file-first workflow.

## Milestone 4: Better Knowledge Variety

Aim:

- expand the ingest scope so the skill handles realistic messy inputs without losing simplicity

Stories:

- [ ] As a user, I can ingest not just clean text but also dialogs, transcripts, and fragmented notes.
- [ ] As a builder, I can add new input types without redesigning the whole system.
- [ ] As a reviewer, I can see that the vault does not explode into duplicates or noise when inputs are messy.

Tasks:

- [ ] Expand the knowledge item schema only as much as needed.
- [ ] Add benchmark cases for:
- [ ] dialogs
- [ ] interview transcripts
- [ ] copied research snippets
- [ ] mixed-source bundles
- [ ] Define how raw capture and consolidated notes should relate.
- [ ] Add duplicate-control checks to the benchmark.
- [ ] Re-run optimization only after the new benchmark cases are fixed.
- [ ] Run the Stage Gate Checklist from `README.md`.

Definition of done:

- [ ] The skill handles multiple knowledge shapes without special-case chaos.
- [ ] Benchmark coverage includes at least one conversational and one messy mixed-source case.
- [ ] The vault remains inspectable and reasonably compact.

Optional extension (may be deferred to a later milestone):

- [ ] Add an **LLM-judge secondary signal** alongside the deterministic score, following the rules in README's Benchmark Philosophy: deterministic score remains primary and authoritative; LLM-judge uses a fixed prompt and rubric; never editable by the optimizer during a run.

## Milestone 5: Staging Vault Realism

Aim:

- move from a toy sandbox layout toward a more realistic but still disposable vault structure

Stories:

- [ ] As a user, I can evaluate the skill against a vault layout that resembles real use.
- [ ] As a builder, I can test more realistic note interactions without touching the personal vault.
- [ ] As a reviewer, I can verify that the system still respects Obsidian-style readability.

Tasks:

- [ ] Design a richer sandbox or staging vault structure.
- [ ] Add existing-note scenarios where new ingest must merge or link instead of only create.
- [ ] Add benchmark checks for collisions, updates, and cross-note linking.
- [ ] Document the difference between disposable sandbox and realistic staging.
- [ ] Run the Stage Gate Checklist from `README.md`.

Definition of done:

- [ ] The benchmark includes realistic pre-existing vault content.
- [ ] The ingest behavior works with existing notes, not just empty-vault cases.
- [ ] The system is still reversible and safe to inspect.

## Milestone 6: Personal Vault Staging Path

Aim:

- define a safe path from sandbox experimentation to eventual use with a personal vault

Stories:

- [ ] As a user, I can review proposed changes before they touch personal knowledge.
- [ ] As a builder, I can reuse the same ingest and evaluation flow in a safer staging setup.
- [ ] As a maintainer, I can explain how this system avoids uncontrolled writes to personal data.

Tasks:

- [ ] Define a staging-copy workflow for personal vault experiments.
- [ ] Define review checkpoints before any personal-vault write.
- [ ] Define rollback expectations for note updates.
- [ ] Decide which actions must remain manual.
- [ ] Document a clear "not yet safe" boundary.
- [ ] Run the Stage Gate Checklist from `README.md`.

Definition of done:

- [ ] There is a documented path from sandbox to staging to eventual personal usage.
- [ ] Personal vault writes are never the first deployment target.
- [ ] Human review remains part of the safety boundary.

## Notes For The Next Builder

- keep scripts thin and explicit
- prefer one-file tools over abstractions
- treat the benchmark as a fixed contract
- keep the vault human-readable at all times
- reject platform creep early

## Commit Discipline

- Commit at the **end of every milestone**, after the Stage Gate Checklist passes and the milestone's DoD boxes are ticked in this file. The commit should include both the code/doc changes **and** the updated checkboxes so the plan and the tree move together.
- Smaller intra-milestone commits are fine and encouraged when a task lands cleanly — keep them narrow and descriptive so `git log` tells the story of the loop.
- Each optimization experiment in Milestone 3+ is its own commit (keep) or `git restore` (revert). Do not bundle experiments.
- Never commit `.env` or any harness credentials. `.env.example` is fine.
- Push after each milestone commit so a fresh session or a second machine can pick up from a known-good state.
