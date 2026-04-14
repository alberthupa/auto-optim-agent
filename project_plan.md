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
- [x] Milestone 2: Fixed benchmark
- [x] Milestone 3: Optimization loop
- [x] Milestone 4: Better knowledge variety
- [x] Milestone 5: Staging vault realism
- [x] Milestone 6: Personal vault staging path
- [ ] Milestone 7: General benchmark-pack auto-optimization

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

- [x] As a builder, I can run the benchmark repeatedly and get stable results from the same skill version.
- [x] As a reviewer, I can inspect benchmark cases and understand what good behavior looks like.
- [x] As the optimizer, I am judged by a fixed scorer rather than a moving target.

Scope note:

- Milestone 2 scoring is **fully deterministic**. No LLM-judge. A secondary LLM-judge signal may be considered in a later milestone under the rules in README's Benchmark Philosophy.

Tasks:

- [x] Define the benchmark case format: one directory per case under `benchmarks/memory-ingest/cases/<case-name>/`, containing:
  - `case.yaml` — case metadata, input pointers, and expected deterministic checks (expected notes, required links, required facts, duplicate threshold, etc.)
  - `input/` — raw input files for that case (free-form text, transcript, fragments, mixed bundle)
- [x] Create initial hand-written cases for:
  - [x] a plain text knowledge item
  - [x] a dialog or transcript
  - [x] a messy or repetitive input
- [x] Define deterministic scoring dimensions:
  - expected notes exist
  - expected outgoing links exist
  - duplicate count stays below a threshold
  - required facts appear in the expected notes
  - source metadata preserved
  - note count did not explode (and did not under-decompose)
- [x] Implement the benchmark runner as a thin Python script:
  - copies `vaults/sandbox/` to a fresh working directory per run
  - runs ingest for each case's inputs
  - scores the resulting vault against `case.yaml`
  - emits a single aggregate score plus per-dimension breakdown
- [x] Define the **results log format**: `results/experiments.jsonl`, append-only JSONL, one object per experiment with at least:
  - `timestamp`, `experiment_id`, `skill_git_sha`, `baseline_score`, `new_score`, `per_dimension`, `kept` (bool), `notes`
- [x] Ensure benchmark runs use a fresh sandbox copy or fresh state every time.
- [x] Document what the score means in `benchmarks/memory-ingest/README.md`.
- [x] Run the Stage Gate Checklist from `README.md`.

Definition of done:

- [x] The same code and same input produce repeatable scores.
- [x] Benchmark cases are readable by a human.
- [x] The scorer is separate from the editable skill and is not touched during ingest runs.
- [x] The benchmark rewards useful memory structure rather than just pretty formatting.
- [x] Scoring is 100% deterministic in this milestone.

## Milestone 3: Optimization Loop

Aim:

- implement the narrow keep-or-revert loop that lets the agent improve the skill against the fixed benchmark

Stories:

- [x] As a builder, I can run a baseline score, attempt a skill change, and see the result recorded.
- [x] As a reviewer, I can tell which change improved the score and which change was rejected.
- [x] As a future maintainer, I can understand the optimizer without learning a framework.

Two-role model (from README's Optimization Model):

- **Execution agent** — runs the current `memory-ingest` skill to ingest benchmark inputs.
- **Optimization agent** — reads current skill files plus benchmark results, proposes a patch.
- Both roles may share the same underlying model/harness, but they are conceptually and operationally separate.

Tasks:

- [x] Define the editable surface for the optimizer (v1: `SKILL.md` only; v2 may extend to one helper script).
- [x] Implement a thin experiment runner under `optimizer/` that:
  - captures a baseline score on a clean sandbox
  - invokes the optimization agent with current skill + last results
  - applies the proposed patch to the editable surface
  - runs the benchmark on a fresh sandbox
  - keeps or reverts the change based on score delta
- [x] Use `git` as the keep/revert mechanism (commit on keep, `git restore` on revert). Do not hand-roll a diff store.
- [x] Append each experiment outcome to `results/experiments.jsonl`.
- [x] Keep a running baseline score for comparison.
- [x] Ensure each run starts from clean benchmark state.
- [x] Ensure the optimization agent cannot touch `benchmarks/` during a run (enforce in the runner, not just by convention).
- [x] Run the Stage Gate Checklist from `README.md`.

Definition of done:

- [x] The system can run baseline, propose one change, evaluate it, and keep or reject it automatically.
- [x] Result logs (`results/experiments.jsonl`) are readable without special tooling.
- [x] The optimizer does not modify the benchmark during a run.
- [x] Keep/revert is handled via `git`.
- [x] The implementation remains a small file-first workflow.

## Milestone 4: Better Knowledge Variety

Aim:

- expand the ingest scope so the skill handles realistic messy inputs without losing simplicity

Stories:

- [x] As a user, I can ingest not just clean text but also dialogs, transcripts, and fragmented notes.
- [x] As a builder, I can add new input types without redesigning the whole system.
- [x] As a reviewer, I can see that the vault does not explode into duplicates or noise when inputs are messy.

Tasks:

- [x] Expand the knowledge item schema only as much as needed.
- [x] Add benchmark cases for:
- [x] dialogs
- [x] interview transcripts
- [x] copied research snippets
- [x] mixed-source bundles
- [x] Define how raw capture and consolidated notes should relate.
- [x] Add duplicate-control checks to the benchmark.
- [x] Re-run optimization only after the new benchmark cases are fixed.
- [x] Run the Stage Gate Checklist from `README.md`.

Definition of done:

- [x] The skill handles multiple knowledge shapes without special-case chaos.
- [x] Benchmark coverage includes at least one conversational and one messy mixed-source case.
- [x] The vault remains inspectable and reasonably compact.

Optional extension (may be deferred to a later milestone):

- [x] Add an **LLM-judge secondary signal** alongside the deterministic score, following the rules in README's Benchmark Philosophy: deterministic score remains primary and authoritative; LLM-judge uses a fixed prompt and rubric; never editable by the optimizer during a run.

## Milestone 5: Staging Vault Realism

Aim:

- move from a toy sandbox layout toward a more realistic but still disposable vault structure

Stories:

- [x] As a user, I can evaluate the skill against a vault layout that resembles real use.
- [x] As a builder, I can test more realistic note interactions without touching the personal vault.
- [x] As a reviewer, I can verify that the system still respects Obsidian-style readability.

Tasks:

- [x] Design a richer sandbox or staging vault structure.
- [x] Add existing-note scenarios where new ingest must merge or link instead of only create.
- [x] Add benchmark checks for collisions, updates, and cross-note linking.
- [x] Document the difference between disposable sandbox and realistic staging.
- [x] Run the Stage Gate Checklist from `README.md`.

Definition of done:

- [x] The benchmark includes realistic pre-existing vault content.
- [x] The ingest behavior works with existing notes, not just empty-vault cases.
- [x] The system is still reversible and safe to inspect.

## Milestone 6: Personal Vault Staging Path

Aim:

- define a safe path from sandbox experimentation to eventual use with a personal vault

Stories:

- [x] As a user, I can review proposed changes before they touch personal knowledge.
- [x] As a builder, I can reuse the same ingest and evaluation flow in a safer staging setup.
- [x] As a maintainer, I can explain how this system avoids uncontrolled writes to personal data.

Tasks:

- [x] Define a staging-copy workflow for personal vault experiments.
- [x] Define review checkpoints before any personal-vault write.
- [x] Define rollback expectations for note updates.
- [x] Decide which actions must remain manual.
- [x] Document a clear "not yet safe" boundary.
- [x] Run the Stage Gate Checklist from `README.md`.

Definition of done:

- [x] There is a documented path from sandbox to staging to eventual personal usage.
- [x] Personal vault writes are never the first deployment target.
- [x] Human review remains part of the safety boundary.

## Milestone 7: General Benchmark-Pack Auto-Optimization

Aim:

- generalize the optimization loop so it can optimize `memory-ingest` against any fixed vault benchmark pack, not just the current deterministic repo benchmark or one geopolitics-specific dataset

Why this milestone exists:

- the current optimizer is real, but it is wired to `benchmarks/memory-ingest/` only
- the next useful version needs one **general** workflow:
  - ingest a fixed corpus into a fresh vault
  - answer questions in a separate fresh read-only session
  - score those answers
  - keep or revert one skill change
  - record both score history and skill evolution artifacts
- the geopolitics dataset should become the first pack that exercises this workflow, not a one-off special case

Core design rule for this milestone:

- the **process** is general
- the **benchmark pack** is domain-specific
- every optimization run must target one explicit pack with fixed inputs and fixed scoring rules

Stories:

- [ ] As a builder, I can define a benchmark pack for any vault domain without rewriting the optimizer.
- [ ] As an evaluator, I can ingest a corpus into a fresh temp vault and score QA behavior using only that resulting vault as memory.
- [ ] As the optimizer, I can optimize against one chosen pack and keep or revert changes automatically.
- [ ] As a reviewer, I can inspect score deltas, answer traces, and the exact skill diff for each experiment.
- [ ] As a future maintainer, I can understand the whole workflow from one end-user document (`USAGE_v2.md`) instead of reconstructing it from code.

Architecture for this milestone:

- **Benchmark pack** owns:
  - corpus inputs
  - optional seeded vault content
  - question set
  - scoring configuration
  - pack-local documentation
- **Ingest harness** owns:
  - creating a fresh temp vault
  - running the current skill against the pack corpus
- **QA harness** owns:
  - starting a fresh read-only answering session
  - constraining answers to the produced vault only
  - emitting machine-readable answers
- **Scorer** owns:
  - comparing answers to fixed gold points
  - producing aggregate and per-question scores
- **Optimizer** owns:
  - baseline
  - one small skill change
  - candidate run
  - keep/revert
  - experiment history and artifacts

Tasks:

- [x] Define a **general benchmark-pack contract**.
  - decide the pack directory layout under a new stable root (for example `benchmark_packs/<pack_name>/`)
  - define required files:
    - `corpus/`
    - `benchmark/questions.json`
    - `benchmark/README.md`
  - define optional files:
    - `vault_seed/`
    - `benchmark/config.yaml`
    - `benchmark/dev_questions.json`
    - `benchmark/holdout_questions.json`
  - define what makes a pack immutable during an optimization run
  - document how a pack differs from the older `benchmarks/memory-ingest/` case format

- [x] Define the **general question schema**.
  - keep the good parts of the geopolitics format
  - make it domain-neutral rather than geopolitics-specific
  - require fields such as:
    - `id`
    - `question`
    - `type`
    - `difficulty`
    - `gold_points`
    - `gold_points_min`
  - decide which optional fields to support:
    - `answer`
    - `source_docs`
    - `tags`
    - `must_include`
    - `must_include_any`
    - `min_matches`
  - define validation rules and failure behavior for malformed questions

- [x] Define the **pack config schema**.
  - choose settings that belong in pack config rather than hard-coded runner logic
  - likely fields:
    - temp-vault setup rules
    - answer prompt template id or inline template
    - dev vs holdout split
    - score weighting
    - retry policy
    - max question count for fast experiments
    - whether `vault_seed/` is required
  - keep config small; do not create a mini framework

- [x] Build a **generic pack loader and validator**.
  - implement one thin Python entry point that validates pack structure before any run starts
  - validate the question schema
  - validate config
  - reject packs with ambiguous or missing required assets
  - produce one normalized in-memory representation the other runners can use

- [x] Build the **fresh-vault ingest runner** for pack-based evaluation.
  - create a fresh temp vault per run
  - optionally copy in `vault_seed/`
  - ingest every source item from `corpus/`
  - preserve the current safety rule that source trees are read-only
  - record ingest outputs and failures in machine-readable form
  - ensure pack runs never mutate the source corpus or benchmark files

- [x] Build a **fresh read-only QA runner**.
  - use a separate session from ingest every time
  - use a read-only tool surface by default
  - constrain the agent to the produced vault only
  - feed questions from the selected pack
  - capture one structured answer record per question
  - define timeout and failure semantics
  - ensure the runner can operate on:
    - a small dev subset for fast optimization
    - a larger holdout set for final evaluation

- [x] Define the **answer output schema** for QA runs.
  - require stable machine-readable output
  - include fields such as:
    - `question_id`
    - `question`
    - `answer_text`
    - `citations` or note references if available
    - `status`
    - `error` when applicable
  - decide whether to capture auxiliary reasoning metadata; default to minimal

- [x] Build a **generic scorer** for QA answers.
  - score answers against `gold_points` and `gold_points_min`
  - support direct-fact, list, synthesis, and comparison-style questions without per-domain code
  - define normalization rules for text matching
  - define partial-credit behavior
  - emit:
    - aggregate score
    - per-question score
    - per-difficulty breakdown
    - per-question failure reasons
  - keep the primary score deterministic

- [ ] Decide how to use the existing advisory LLM-judge in the new workflow.
  - keep deterministic scoring primary
  - decide whether QA-pack runs may optionally attach an advisory secondary judge
  - ensure that any advisory judge is:
    - fixed
    - versioned
    - never editable by the optimizer during a run

- [ ] Integrate the new QA benchmark path into `optimizer/runner.py`.
  - add a way to choose the evaluation backend:
    - existing deterministic benchmark
    - new pack-based QA benchmark
  - keep the editable surface narrow by default (`SKILL.md` first)
  - keep one-change-per-experiment discipline
  - reuse existing keep/revert logic where possible
  - avoid splitting the optimizer into a framework

- [ ] Define **experiment artifact storage** for score history and skill evolution.
  - keep `results/experiments.jsonl` as the summary log
  - add one artifact directory per experiment under a predictable path
  - store at minimum:
    - baseline score report
    - candidate score report
    - baseline answers
    - candidate answers
    - skill before
    - skill after
    - unified diff
    - pack id and config snapshot
  - ensure rejected runs are still inspectable

- [ ] Extend the **results log schema** carefully.
  - preserve backward readability of `results/experiments.jsonl`
  - add fields for:
    - benchmark pack id
    - eval backend
    - question subset used
    - baseline and candidate artifact paths
    - skill before/after git hashes where applicable
  - document the schema version if needed

- [ ] Define **dev / holdout workflow** for optimization.
  - support small fixed dev subsets for fast iteration
  - support larger holdout runs before accepting a milestone-level result
  - ensure the holdout split is fixed and not changed during optimization
  - define when a holdout run is required
  - define how to prevent accidental tuning on the holdout set

- [ ] Add the first **general benchmark pack implementation** using the geopolitics dataset.
  - adapt `datasets/geopolitics_apr_2026_memory_benchmark/` into the general pack contract without baking geopolitics assumptions into the code
  - decide whether to:
    - move it under the new pack root, or
    - keep it in place and add a compatibility loader
  - define a stable dev subset and holdout subset for that pack
  - document why it is only the first pack, not the only pack

- [ ] Add at least one second small pack or fixture to prove generality.
  - keep it much smaller than geopolitics
  - use a different content shape
  - prove the QA pipeline is not secretly tied to one corpus shape or one question style

- [ ] Define the **safe launcher and session rules** for pack evaluation.
  - document the ingest session launch shape
  - document the read-only QA session launch shape
  - define which tools are allowed in each phase
  - keep direct file writes disabled outside the deterministic helper layer
  - ensure temporary vaults and session dirs are predictable and cleanable

- [ ] Define **failure handling and resumability**.
  - ingest failure on one source file
  - QA timeout on one question
  - partial answer files
  - optimizer proposal parse failure
  - interrupted experiment recovery
  - rerun semantics for a failed experiment id

- [ ] Define **reporting and inspection commands**.
  - choose one or two thin commands for:
    - running a pack manually
    - scoring a finished QA run
    - comparing two experiment artifacts
  - keep them file-first and script-thin

- [ ] Write the final end-user workflow doc as **`USAGE_v2.md`**.
  - position it as the primary guide for the generalized workflow
  - explain the whole lifecycle:
    - define or choose a benchmark pack
    - ingest into a fresh temp vault
    - run read-only QA
    - score results
    - run auto-optimization
    - inspect artifacts
    - interpret keep/revert outcomes
  - include both:
    - a fast-start path
    - a careful inspection path
  - document all important safety boundaries
  - document how to add a new benchmark pack
  - document how to read `results/experiments.jsonl`
  - document how to inspect skill evolution over time
  - explicitly replace or supersede the parts of `USAGE.md` that are now milestone-era or legacy

- [ ] Update supporting docs after `USAGE_v2.md` exists.
  - update `README.md` so it points to `USAGE_v2.md` for the generalized operator workflow
  - update `optimizer/README.md` to distinguish:
    - legacy deterministic benchmark path
    - generalized pack-based QA path
  - update any dataset README files so they describe their pack role cleanly
  - decide what remains in `USAGE.md` as legacy or milestone-specific material

- [ ] Run the Stage Gate Checklist from `README.md`.

Implementation order:

- [x] Phase 1: contract and schemas
  - benchmark-pack layout
  - question schema
  - config schema
  - answer schema
- [x] Phase 2: manual pack execution
  - pack loader
  - temp-vault ingest runner
  - read-only QA runner
  - scorer
- [ ] Phase 3: optimizer integration
  - add pack-backed benchmark mode
  - add experiment artifacts
  - extend results log
- [ ] Phase 4: first real pack rollout
  - geopolitics pack migration
  - dev/holdout split
  - one small second pack for generality proof
- [ ] Phase 5: documentation and operator polish
  - `USAGE_v2.md`
  - supporting docs
  - safety and inspection walkthrough

Definition of done:

- [ ] A benchmark pack can be defined for a new vault domain without changing optimizer code.
- [ ] The system can run ingest, fresh read-only QA, scoring, and keep/revert automatically against one selected pack.
- [ ] The primary score for the new QA workflow is deterministic and reproducible.
- [ ] Experiment history records not just scalar scores but also answer traces and skill evolution artifacts.
- [ ] The geopolitics dataset runs through the general pack path rather than a one-off path.
- [ ] At least one second small pack proves the workflow is domain-general.
- [ ] `USAGE_v2.md` is complete enough that a new operator can run the full workflow without reading implementation files first.
- [ ] The implementation remains thin, file-first, and consistent with the anti-drift rules in `README.md`.

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
