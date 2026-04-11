# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

This is a skeleton repo (Milestone 0 complete). There is no build system, no tests, no runnable code yet — only directory scaffolding and design docs. Do not fabricate commands, lint configs, or test runners that don't exist. When adding tooling, stay consistent with the "thin Python scripts" rule below.

Tooling, when added, is **`uv` with a single repo-root `pyproject.toml`**. No per-subdirectory environments.

## Authoritative Docs

- `README.md` — product brief, architectural rules, and anti-drift guardrails. Read this first.
- `project_plan.md` — milestone-ordered build sheet with stories, tasks, and definitions of done. This is the execution plan; update checkboxes here as work lands.

Before marking any milestone complete, run the Stage Gate Checklist in `README.md`.

## What This Project Is

A deliberately small self-optimizing agent experiment. The entire system optimizes **one** skill (`skills/memory-ingest/`) against **one** fixed benchmark using a keep-or-revert hill-climbing loop. The editable surface is intentionally narrow. The benchmark is intentionally fixed during a run.

The win condition is not sophistication — it's that the loop stays simple, measurable, and demonstrably improves the skill.

## Architecture (Intended)

Five top-level areas, each with a single responsibility:

- `skills/memory-ingest/` — the one skill under optimization. Contains `SKILL.md` (the contract), optional `scripts/`, optional `templates/`. This is the **editable surface** the optimizer may modify.
- `benchmarks/memory-ingest/` — fixed cases and scorer. Treated as a contract; **never modified during an optimization run**.
- `vaults/sandbox/` — disposable Obsidian-style test vault. Benchmark runs must use a fresh copy / clean state — no state leakage between runs.
- `optimizer/` — thin experiment runner implementing: baseline → propose change → run benchmark on fresh sandbox → record → keep-or-revert.
- `results/` — append-only experiment history, human-readable.

The memory artifact is a plain Markdown Obsidian vault (YAML frontmatter, `[[wiki links]]`, no proprietary plugins). If a design choice makes the vault harder for a human to read, it's probably wrong.

## Execution Model (how the skill actually runs)

The LLM lives in the **agent harness**, not inside Python and not inside the vault. The repo stores the skill definition; the harness supplies the model. Credentials live in `.env` (gitignored) and are read by the harness, never by scripts directly.

Responsibility split is strict:

- **LLM owns semantic judgment** — normalization, fact extraction, note create/update decisions, link selection.
- **Python owns determinism** — input loading, schema validation, filesystem safety, writes, benchmark glue.

The LLM **does not write files directly**. One ingest call produces a **structured proposal** (note titles, frontmatter, bodies, links, create-vs-update). Python validates that proposal against a schema and applies it to the vault.

Single-item ingest flow:

1. Python loads one knowledge item + a small slice of vault context.
2. Python calls the harness once with `SKILL.md` and that context.
3. LLM returns one structured proposal.
4. Python validates and applies it to Markdown files.

One LLM call per item. One response schema. One thin writer.

A **stub harness mode** exists so the pipeline can run end-to-end without a live LLM — use it for development and for any work happening before the PI harness is wired up.

## Optimization Loop (two LLM roles)

The loop uses the same harness but two conceptually separate LLM roles:

- **Execution role** — runs the current `memory-ingest` skill to ingest benchmark inputs.
- **Optimization role** — reads current skill files + benchmark results, proposes a patch to the editable surface (initially `SKILL.md` only; later possibly one helper script).

Mantra: **LLM proposes. Python runs. Benchmark judges. Git remembers.** Keep/revert is handled via `git` — commit on keep, `git restore` on revert. Don't hand-roll a diff store.

The optimization role may edit the skill. It may **never** touch `benchmarks/` during a run — enforce this in the runner, not just by convention.

## Scoring

Scoring is **fully deterministic** through Milestone 2. No LLM-judge. Repeatability and low ambiguity matter more than scoring sophistication at this stage.

An LLM-judge secondary signal may be added in a later milestone (optional task in M4). If added: deterministic score stays primary and authoritative, LLM-judge uses a fixed prompt + fixed rubric, and it is never editable by the optimizer during a run. Do not add it before the deterministic foundation is stable.

## Formats (decided)

- **Vault filenames** — human-readable `Title Of Note.md`, Obsidian-native, with a small sanitizer for filesystem-unsafe characters. Not kebab-case.
- **Knowledge item wrapper** — permissive: carries arbitrary text (plain text, transcripts, fragments, mixed bundles) plus minimal metadata (source type, timestamp, origin, tags, optional trust). The skill must handle the mess; the wrapper does not clean it.
- **Benchmark cases** — one directory per case under `benchmarks/memory-ingest/cases/<case-name>/`, containing `case.yaml` (metadata + expected deterministic checks) and `input/` (raw input files).
- **Results log** — `results/experiments.jsonl`, append-only, one JSON object per experiment. Fields: `timestamp`, `experiment_id`, `skill_git_sha`, `baseline_score`, `new_score`, `per_dimension`, `kept`, `notes`.

## Hard Rules (from README.md — enforce these)

1. **One skill under optimization at a time.** Scope-broadening changes default to "no".
2. **Benchmark is fixed during a run.** The thing being optimized cannot modify its own scorer.
3. **Thin Python scripts only.** No deep class hierarchies, framework layers, plugin systems, or hidden state. If a script grows complicated, split the workflow, not the abstraction.
4. **File system first.** No database unless flat files are provably insufficient.
5. **Fresh sandbox per benchmark run.**
6. **One change per experiment** when possible — narrow enough that cause of improvement/regression is clear.
7. **Reversible by default.** Both code and vault mutations.
8. **Personal vault is off-limits** until the sandbox loop is proven.

## Commit Discipline

- Commit at the **end of every milestone**, after the Stage Gate Checklist passes and the milestone's DoD is ticked in `project_plan.md`. The commit bundles the work with the updated checkboxes so the plan and the tree stay in sync.
- Smaller intra-milestone commits are welcome when a task lands cleanly — keep them narrow.
- In Milestone 3+, each optimization experiment is its own commit (keep) or `git restore` (revert). Never bundle experiments.
- Never commit `.env` or harness credentials. `.env.example` is fine.
- Push after each milestone commit so a fresh session can resume from a known-good state.

## Anti-Drift

This project previously drifted into framework-building. Reject changes that make it feel more like a platform than a lab rig. Every new abstraction must justify itself in writing. If a proposed change doesn't clearly serve "optimize one memory-ingest skill against a fixed benchmark," push back before implementing.

## Knowledge Input Scope

The ingest skill must handle messy real-world inputs, not just polished prose: plain text, fragmented notes, dialogs, transcripts, research snippets, mixed bundles. A knowledge item may carry source text, source type, timestamp, origin, tags, and optional trust metadata. The skill's job includes normalizing messy input, extracting stable facts, preserving context, avoiding duplication, and creating useful links — it is not just a formatter.
