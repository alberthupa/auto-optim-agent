# auto-optim-agent

## Purpose

This project is a deliberately small experiment in self-optimizing agent skills.

The end goal is not a general autonomous research system. The end goal is much narrower:

- run a self-hosted agent in a harness
- give it a memory skill
- store the memory in an Obsidian-style vault
- evaluate how well that skill works
- let the system improve that skill through repeated test-and-keep iterations

The first target is one specific capability:

- `memory-ingest`: ingest knowledge into a dedicated Obsidian vault so that the resulting notes are useful for later retrieval, linking, and question answering

The project should stay small enough that one person can understand the whole system at a glance.

## Big Idea

The core idea is simple:

1. An agent has a skill.
2. The skill writes knowledge into an Obsidian-style memory vault.
3. A fixed benchmark asks whether the resulting memory is actually good.
4. The agent is allowed to improve the skill.
5. Improvements are kept only if benchmark results improve.

This is inspired by optimization loops such as Karpathy's `autoresearch`, but the scope here is much smaller and more controlled.

The project is not trying to optimize an entire agent stack. It is trying to optimize one skill, against one fixed evaluation harness, with a very small amount of code.

## Project Shape

The intended shape of the system is:

- one agent harness at a time
- one main skill under optimization at a time
- one sandbox vault for development and testing
- one fixed benchmark suite
- one keep-or-revert optimization loop

That means the first real system should look more like a tiny lab rig than a platform.

## What Is an Agent Here

An "agent" here means:

- an LLM running inside a practical harness such as Codex, Claude Code, OpenCode, PI, or a similar tool
- plus a small set of skills
- plus access to a local memory vault

The harness itself is not the product. The skill and the evaluation loop are the product.

To keep the design simple, the system should expose one thin adapter per harness instead of building a universal abstraction layer too early.

## What Is a Skill Here

A skill means an actual skill folder, not just a prompt string.

Each skill should contain:

- instructions in `SKILL.md` — behavioral guidance for the LLM running in the harness
- small Python scripts — deterministic glue: input loading, schema validation, file writes, benchmark hooks
- optional templates or helper assets

The first skill should be:

- `skills/memory-ingest/`

This skill receives some knowledge input and a target vault path and is responsible for producing or updating Obsidian-compatible notes.

## Execution Model

The skill is executed by an LLM running inside an agent harness (`pi` is the first-class target). The repository stores the skill definition; the harness supplies the model. Credentials live outside the repo in `.env` and are read by the harness, not by scripts directly.

The intended product flow is:

```text
user -> pi harness -> memory-ingest skill -> local helper scripts -> vault
```

The harness is the outer runtime. Helper scripts are tools the harness calls, not entrypoints that call the harness.

Responsibilities are split cleanly:

- **LLM (in the harness)** owns semantic judgment: how to normalize messy input, what facts to extract, what notes to create or update, and what links are meaningful. The LLM also owns source gathering — it reads files, enumerates directories, and handles whatever form the user provides.
- **Python (in `skills/memory-ingest/scripts/`)** owns determinism: vault scanning (`scan_vault.py`), schema validation, filesystem safety, and writes (`apply_ingest.py`).

The LLM does not write files directly. It produces a **structured proposal** — note titles, frontmatter, bodies, links, and create/update decisions. The `apply_ingest.py` helper validates that proposal against a schema and applies it to the vault. This keeps LLM work focused on judgment and the filesystem side deterministic and reviewable.

The runtime flow:

1. User asks the harness to ingest something (chat text, file path, directory, or mixed).
2. Harness LLM gathers the source material.
3. Harness LLM calls `scan_vault.py` to get existing vault context.
4. Harness LLM decides note operations and builds a structured proposal.
5. Harness LLM calls `apply_ingest.py` with the proposal.
6. Helper validates and writes Markdown files.
7. Harness LLM reports what changed.

No helper script may call `pi` or any other harness. No special user-facing input format is required.

For the first-class `pi` path, start the harness with the skill loaded from
the repo root:

```bash
./skills/memory-ingest/scripts/run_pi_with_skill.sh
```

## What Is Memory Here

Memory is a directory tree that is compatible with normal Obsidian usage.

The initial assumptions are:

- plain Markdown files
- standard folders and subfolders
- YAML frontmatter when useful
- wiki links such as `[[Concept Name]]`
- no dependency on proprietary plugins in v0

The vault is both:

- the memory store used by the agent
- the artifact evaluated by the benchmark

## What Counts as Ingested Knowledge

This must be broader than "documents".

Ingested knowledge can include:

- raw texts
- cleaned notes
- conversations
- chat transcripts
- interview transcripts
- meeting notes
- research snippets
- copied web content
- personal observations
- structured metadata
- short atomic facts
- long-form documents

In practical terms, the system should be built so that a knowledge item may contain:

- source text
- source type
- source timestamp
- source identity or origin
- tags
- optional trust or confidence metadata

The system should not assume that all inputs are polished prose. Some inputs will be messy, partial, repetitive, contradictory, or conversational.

That matters because the ingest skill is not just a formatter. It must decide how to:

- normalize messy inputs
- extract stable facts
- preserve important context
- avoid duplication
- create useful links
- separate raw capture from consolidated knowledge when needed

## Initial Product Goal

The first useful version of this project should answer one question:

> Can a very small self-hosted optimization loop measurably improve a memory-ingest skill for an Obsidian vault?

If the answer is yes, the project is working.

Everything else is secondary.

## Non-Goals

The early versions of this project should not try to:

- become a general agent platform
- support every harness equally well
- optimize many skills at once
- modify the evaluation harness during optimization
- write directly into a personal vault
- build a complex graph database
- add orchestration layers, queues, services, or dashboards unless they become unavoidable

## Core Architecture

The intended minimal architecture is:

- `skills/`
  - skill instructions and tiny helper scripts
- `vaults/sandbox/`
  - disposable Obsidian-style test vault
- `benchmarks/`
  - benchmark cases and scoring logic
- `results/`
  - experiment history
- `optimizer/`
  - the thin loop that runs experiments and applies keep-or-revert logic
- `pyproject.toml`
  - single `uv`-managed project for the whole repo; no per-subdirectory environments
- `.env` (gitignored)
  - harness credentials such as `OPENAI_API_KEY`, consumed by the agent harness, never by scripts directly

The optimizer should be able to:

1. run a baseline
2. ask the agent to propose a small change to the skill
3. run the benchmark on a fresh sandbox vault
4. record results
5. keep or revert the change

## Optimization Model

The loop has two LLM roles, even if they share the same underlying model and harness:

- **Execution role** — runs the current `memory-ingest` skill to ingest knowledge into a fresh sandbox vault.
- **Optimization role** — reads the current skill files, benchmark results, and failure cases, then proposes a patch to the editable surface (initially `SKILL.md`, later possibly one helper script).

The optimization role may edit the skill. It may never edit the benchmark or scorer during a run.

Mental model:

- **LLM proposes.**
- **Python runs.**
- **Benchmark judges.**
- **Git remembers** — keep or revert.

The optimization model should stay close to the simple keep/discard logic:

1. establish a baseline
2. make one small change
3. run the benchmark
4. keep the change only if the benchmark improves
5. otherwise revert
6. repeat

This project should strongly prefer this simple hill-climbing loop over more elaborate search strategies in the beginning.

The benchmark is fixed.

The editable surface is narrow.

That is intentional.

## Skill Evolution And Auditability

The system should preserve a visible history of skill evolution.

The simplest intended approach is:

- accepted skill changes live in git history
- optimization attempts are recorded in a small experiment log under `results/`
- rejected attempts remain visible in the experiment log even if they do not become the live skill

This should make it easy to inspect:

- how the skill changed
- which changes improved the benchmark
- which ideas were tried and rejected

If skill evolution is not easy to inspect later, the system is too opaque.

## Why This Must Stay Simple

This project previously drifted architecturally during development. That means this time the system needs hard rules, not just good intentions.

The main failure mode to avoid is this:

- the project starts as a small skill optimizer
- then slowly becomes a general framework
- then gains abstractions, optional layers, and helper systems
- then the actual optimization problem gets buried

To prevent that, simplicity is a first-order requirement, not a style preference.

## Core Rules

These rules must be checked at every development stage.

### Rule 1: Optimize one skill, not the world

At any stage, there should be exactly one primary skill under active optimization.

If a change broadens scope beyond that skill, the default answer is no.

### Rule 2: Keep the benchmark fixed

The benchmark and scorer are not part of the thing being optimized during a run.

If the system can freely modify its own tests, the whole setup becomes untrustworthy.

### Rule 3: Prefer thin Python scripts

Python should be used for short, direct scripts with obvious input/output behavior.

The project should avoid:

- deep class hierarchies
- framework-heavy abstractions
- large utility layers
- premature plugin systems
- hidden state

If a script grows complicated, split the workflow, not the abstraction.

### Rule 4: File system first

The system should operate on normal files and directories.

No database should be introduced unless a concrete bottleneck proves that flat files are no longer sufficient.

### Rule 5: Obsidian compatibility first

The memory artifact should remain useful as a normal Obsidian vault.

If a design choice makes the vault harder for a human to read, browse, or edit, it is probably wrong.

### Rule 6: Fresh sandbox runs only

Benchmark evaluation should run against a fresh copy of the sandbox vault or a clean test state.

State leakage between runs will make results noisy and untrustworthy.

### Rule 7: One change per experiment when possible

Each optimization step should be narrow enough that the cause of an improvement or regression is understandable.

Large bundled changes reduce learning value.

### Rule 8: Human readability is required

All key artifacts should remain inspectable by a human:

- benchmark cases
- resulting notes
- experiment logs
- score outputs

If a result cannot be inspected easily, the loop is too opaque.

### Rule 9: Default to reversible changes

The system should favor changes that are easy to keep or revert.

This applies both to code and to vault mutations.

### Rule 10: Personal vault stays out until the sandbox is proven

Development and optimization happen against a disposable test vault first.

The personal vault is a later-stage target, never the first proving ground.

## Stage Gate Checklist

Every milestone should be checked against these questions:

1. Did this stage keep the system understandable in one sitting?
2. Did this stage preserve a narrow editable surface?
3. Did this stage avoid adding a framework or abstraction layer without a proven need?
4. Did this stage preserve plain-file Obsidian compatibility?
5. Did this stage keep scripts small and direct?
6. Did this stage keep the benchmark separate from the optimized skill?
7. Did this stage make rollback and debugging easy?

If the answer to any of these is no, the stage should be reconsidered before moving on.

## Delivery Plan

Execution milestones, tasks, and definitions of done live in [project_plan.md](project_plan.md).

That file is the build sheet for the next contributor. This README remains the product brief, architecture guardrail, and anti-drift reference.

## Benchmark Philosophy

Scoring starts **fully deterministic**. Repeatability, low ambiguity, and resistance to benchmark drift matter more than scoring sophistication in the early milestones.

An LLM-judge supplement may be added in a later milestone as a secondary signal for things deterministic checks cannot see (consolidation quality, link meaningfulness, whether the vault would actually help answer a question). If added, it must follow these rules:

- deterministic score remains primary and authoritative
- LLM score is secondary and advisory
- fixed prompt, fixed rubric, no edits during a run
- multiple runs or pairwise comparison if variance becomes a problem
- never editable by the optimizer during an optimization run

Adding an LLM-judge before the deterministic foundation is stable will make the whole loop noisy. Don't.

The benchmark should test usefulness, not just formatting.

Useful benchmark dimensions may include:

- note existence
- note structure
- link quality
- duplicate control
- preservation of source context
- ability to answer test questions from the resulting vault
- resistance to messy or redundant inputs

The benchmark should reward memory that is:

- accurate
- linked
- compact
- understandable
- retrievable

The benchmark should penalize memory that is:

- duplicated
- fragmented
- over-summarized
- under-linked
- noisy
- impossible to inspect

## Development Style

Implementation should follow these preferences:

- plain files over services
- short scripts over frameworks
- explicit inputs and outputs over magic
- deterministic evaluation where possible
- simple CLI entry points
- small commits
- aggressive avoidance of premature abstraction
- `uv` with a single repo-root `pyproject.toml`; no per-subdirectory environments

If a future design introduces a complex layer, it should justify itself in writing.

## Two Important Considerations

### 1. Preventing architectural drift

The project needs explicit anti-drift discipline.

That means:

- every stage must be checked against the core rules
- every new abstraction must justify its existence
- every script should stay small enough to read quickly
- every milestone should preserve the central idea: optimize one memory skill with a fixed benchmark

If a proposed change makes the project feel more like a platform than a lab rig, it should be rejected unless there is a strong concrete reason.

### 2. Broad definition of ingested knowledge

The ingest problem is not limited to polished articles or documents.

The system should be designed from the beginning to handle:

- plain text
- fragmented notes
- dialogs
- transcripts
- copied research snippets
- mixed raw materials

This is important because memory quality depends not only on storing content, but on handling messy real-world inputs without losing meaning or exploding the vault into junk.

## End-State Vision

If this experiment succeeds, the result should be a small self-hosted system that can be left running on a sandbox or staging vault and gradually become better at one thing:

- turning incoming knowledge into a useful, navigable Obsidian memory

The win condition is not sophistication.

The win condition is that the system stays simple, measurable, and actually gets better.
