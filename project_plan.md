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
- [ ] Milestone 1: Manual ingest baseline
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

- implement the first usable `memory-ingest` skill with minimal logic and clear file-based inputs and outputs

Stories:

- [ ] As a builder, I can pass one knowledge item and one target vault path into the skill.
- [ ] As a user, I can inspect the resulting Markdown notes and understand what the ingest step did.
- [ ] As a builder, I can run the baseline ingest from a simple CLI command without extra services.

Tasks:

- [ ] Define the skill contract in `skills/memory-ingest/SKILL.md`.
- [ ] Define the input format for one knowledge item.
- [ ] Decide the minimum required metadata fields.
- [ ] Implement one thin Python entry point for ingest.
- [ ] Write notes into Obsidian-compatible Markdown files only.
- [ ] Create at least three sample inputs:
- [ ] one plain text item
- [ ] one dialog or chat transcript
- [ ] one rough note bundle
- [ ] Ensure the output vault stays human-readable.
- [ ] Run the Stage Gate Checklist from `README.md`.

Definition of done:

- [ ] A single command can ingest a sample item into the sandbox vault.
- [ ] Output notes are readable Markdown with sensible naming and links.
- [ ] The implementation stays small enough to understand in one sitting.
- [ ] No database, service, or framework layer is introduced.

## Milestone 2: Fixed Benchmark

Aim:

- create a stable benchmark that evaluates usefulness of the resulting vault, not just formatting

Stories:

- [ ] As a builder, I can run the benchmark repeatedly and get stable results from the same skill version.
- [ ] As a reviewer, I can inspect benchmark cases and understand what good behavior looks like.
- [ ] As the optimizer, I am judged by a fixed scorer rather than a moving target.

Tasks:

- [ ] Define the benchmark case format.
- [ ] Add an isolated benchmark fixture area under `benchmarks/memory-ingest/cases/`.
- [ ] Create initial hand-written cases for:
- [ ] a plain text knowledge item
- [ ] a dialog or transcript
- [ ] a messy or repetitive input
- [ ] Define scoring dimensions for note existence, links, duplication, and question answering.
- [ ] Implement the benchmark runner as a thin Python script.
- [ ] Ensure benchmark runs use a fresh sandbox copy or fresh state.
- [ ] Document what the score means.
- [ ] Run the Stage Gate Checklist from `README.md`.

Definition of done:

- [ ] The same code and same input produce repeatable scores.
- [ ] Benchmark cases are readable by a human.
- [ ] The scorer is separate from the editable skill.
- [ ] The benchmark rewards useful memory structure rather than just pretty formatting.

## Milestone 3: Optimization Loop

Aim:

- implement the narrow keep-or-revert loop that lets the agent improve the skill against the fixed benchmark

Stories:

- [ ] As a builder, I can run a baseline score, attempt a skill change, and see the result recorded.
- [ ] As a reviewer, I can tell which change improved the score and which change was rejected.
- [ ] As a future maintainer, I can understand the optimizer without learning a framework.

Tasks:

- [ ] Define the editable surface for the optimizer.
- [ ] Decide whether v1 may edit only `SKILL.md` or `SKILL.md` plus one script.
- [ ] Implement a thin experiment runner under `optimizer/`.
- [ ] Record each run in a simple append-only log.
- [ ] Keep a baseline score for comparison.
- [ ] Implement keep-or-revert logic.
- [ ] Ensure each run starts from clean benchmark state.
- [ ] Run the Stage Gate Checklist from `README.md`.

Definition of done:

- [ ] The system can run baseline, propose one change, evaluate it, and keep or reject it automatically.
- [ ] Result logs are readable without special tooling.
- [ ] The optimizer does not modify the benchmark during a run.
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
