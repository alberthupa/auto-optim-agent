# FR1: Harness-Owned Memory-Ingest Redesign

## What was wrong

The current implementation inverted the ownership boundary.

It currently works like this:

```text
user -> ingest.py -> harness LLM -> JSON proposal -> ingest.py writes vault
```

That is the wrong product shape.

The intended product shape is:

```text
user -> harness LLM -> memory-ingest skill -> local helper scripts -> vault
```

The harness must stay outside. The agent running inside the harness must decide
when to use the skill, gather the source material, reason about note structure,
and invoke local deterministic helpers. No helper script should shell out to
`pi`, Codex, Claude Code, or any other outer harness.

This redesign replaces that execution model.

## Product Requirement

The new `memory-ingest` system must behave like a real harness skill:

1. A user starts a harness session.
2. A user says something like:
   - "ingest this"
   - "ingest the notes in `captures/meeting.txt`"
   - "ingest everything in `research/clips/`"
   - "turn this conversation into useful vault notes"
3. The harness LLM chooses to use the `memory-ingest` skill.
4. The skill reads the source material from whatever form the user provided.
5. The skill uses local helper scripts for deterministic work.
6. The skill writes or updates notes in the vault.
7. The harness LLM reports what it changed.

The skill may contain Python scripts and may rely on other LLM reasoning inside
the harness, but the harness remains the outer runtime.

## Hard Requirements

### 1. No required user-facing input format

The user must not be required to prepare a YAML wrapper, frontmatter block, or
repo-specific input file before ingest.

Valid user inputs must include at least:

- raw text pasted into chat
- one local file path
- multiple file paths
- a directory path
- attached files, if the harness supports attachments
- conversation content already present in the session
- mixed messy material

This does **not** forbid internal structure. Internal schemas are allowed and
desirable between the LLM and helper scripts. The rule is only that the user
must not be forced to author a special ingest format.

### 2. Harness-owned reasoning

The LLM in the harness owns:

- deciding whether the request is an ingest request
- deciding what source material matters
- deciding whether to create or update notes
- deciding how to split raw capture from durable notes
- deciding titles, links, and note boundaries
- deciding when clarification is necessary

### 3. Deterministic local helpers

Local Python scripts own:

- vault scanning
- path safety
- note-path resolution
- schema validation
- file writes
- dry-run and diff generation
- benchmark hooks

### 4. No helper script may invoke a harness

The current `ingest.py -> pi` pattern must be removed.

Forbidden design pattern:

```text
script -> pi
script -> codex
script -> claude
script -> external chat-completions client pretending to be the harness
```

Allowed design pattern:

```text
harness agent -> local script
```

If a secondary LLM call is ever needed, it must still be owned by the harness
layer, not hidden inside a helper script.

## User Experience

The target interaction should feel like this:

```text
User: ingest this into my memory vault

Agent:
- determines what "this" refers to
- asks one short clarifying question only if truly blocked
- reads the relevant source material
- scans the vault for relevant existing notes
- decides the note operations
- invokes the deterministic writer helper
- returns a short summary of created/updated notes
```

Examples that should work without any special input format:

- "Ingest this message."
- "Ingest `/home/me/notes/interview.txt`."
- "Ingest the files in `captures/2026-04-12/`."
- "Use the last three messages as source and store them in the vault."
- "Read `meeting.md`, keep a raw capture, and update the project note."

## Clarifying Questions Policy

The skill should ask a question only when blocked by a real ambiguity.

Allowed reasons to ask:

- no source material was actually provided
- the target vault is unknown and no default is configured
- the user refers to multiple plausible sources and says "ingest this"
- an update would touch an existing note and the risk is materially high

Not valid reasons to ask:

- asking the user to reformat their input
- asking the user to add YAML
- asking for metadata that can be inferred
- asking for a note title before any attempt at reasoning

The default policy should be: infer what can be inferred, ask only when the
request would otherwise be unsafe or impossible.

## Core Architecture

### 1. Skill package

`skills/memory-ingest/` remains the skill package, but its role changes.

It should contain:

- `SKILL.md`
  - instructions for the harness LLM
  - when to trigger the skill
  - how to gather sources
  - how to choose note structure
  - how to use helper tools
- deterministic helper scripts
  - local tools the harness can call
  - never outer entrypoints that call the harness themselves

### 2. Minimal helper toolset

The skill should expose a very small deterministic tool surface.

Recommended first set:

- `scan_vault.py`
  - recursively list existing Markdown notes
  - return titles, paths, and small previews
  - support a relevance-oriented query mode
- `apply_ingest.py`
  - accept a structured proposal
  - validate it
  - write the files
  - return a machine-readable change summary
- `dry_run_ingest.py` or `apply_ingest.py --dry-run`
  - compute the exact creates/updates without writing
  - useful for review, benchmark, and safety

Optional later helper:

- `capture_sources.py`
  - turn arbitrary raw sources into an internal normalized bundle
  - useful for benchmarking and traceability
  - invisible to the user

The important point is that the helper scripts are tools for the harness LLM,
not replacement entrypoints for the user.

### 3. Internal proposal schema

The user should not prepare structured input, but the LLM-to-Python boundary
should stay structured.

The harness LLM should produce an internal proposal with fields such as:

- operation type: create/update
- note title
- target path or placement hint
- frontmatter
- body
- links
- rationale

That proposal is internal contract, not user contract.

## Source Intake Model

The skill must accept arbitrary user-facing source forms and normalize them
internally.

### Supported intake modes

1. **Conversation intake**
   - the source is text already present in the session
   - example: "ingest this message"

2. **File intake**
   - the source is one or more explicit file paths
   - the harness reads them using its normal file tools

3. **Directory intake**
   - the source is a folder
   - the harness enumerates files, selects relevant ones, and ingests them as a bundle

4. **Mixed intake**
   - some content comes from chat, some from files, some from attachments
   - the skill treats them as one request bundle if that is what the user asked for

### Metadata policy

The skill should infer provenance metadata whenever possible instead of asking
the user to provide it.

Examples:

- `source_kind: chat_message`
- `source_kind: local_file`
- `source_kind: directory_bundle`
- `source_label` inferred from file name, folder name, or user wording
- `captured_at` set automatically
- `source_paths` recorded when files were used

If provenance is unknown, it should be stored as unknown or omitted. The user
should not be blocked on metadata.

## Vault Model

The system still writes to an Obsidian-compatible vault, but the vault should
be treated more realistically than the current top-level-only implementation.

### Required behavior

- scan notes recursively, not just in the vault root
- support updates to existing notes wherever they live
- sanitize filenames and paths
- keep Markdown plain and human-readable
- preserve existing frontmatter on updates unless explicitly overridden

### Placement policy

New notes should not be sprayed randomly across the vault.

Chosen default:

- new notes are created directly in the vault root
- updates happen in-place to existing notes automatically by default

This matches the desired Obsidian usage model for the first implementation.

### Vault configuration

The skill needs one configured default target vault, but not a required input
format.

Recommended rule:

- if the user names a vault path explicitly, use it
- else use the configured default vault path for the harness/session
- else ask once and remember

## Recommended Runtime Flow

The real ingest flow should be:

1. User asks the harness to ingest something.
2. Harness LLM decides to use `memory-ingest`.
3. Harness LLM gathers source material from chat, files, directories, or attachments.
4. Harness LLM resolves target vault path.
5. Harness LLM calls `scan_vault.py` to get relevant existing notes.
6. Harness LLM decides note operations.
7. Harness LLM calls `apply_ingest.py` with a structured proposal.
8. Helper script validates and writes.
9. Harness LLM reports what changed.

No step in this flow should ever shell out from Python back into a harness.

## First-Class Harness Target

The first implementation target is `pi`.

That means the redesign should be written for `pi` first, not for a generic
lowest-common-denominator harness abstraction. Other harnesses may come later
through thin adapters, but the design should not be compromised to make all
harnesses look identical from day one.

## Benchmark Redesign

The benchmark must be changed so it tests the same product that users will use.

The current benchmark is also inverted because it drives `ingest.py` directly.

That should be replaced with a harness-driven benchmark:

1. Create a fresh disposable vault copy.
2. Launch the chosen harness adapter with the `memory-ingest` skill enabled.
3. Provide the case input as natural user-facing content, not a forced YAML wrapper.
4. Let the harness LLM use the skill and helper scripts.
5. Score the resulting vault exactly as before or with similar deterministic rules.

The benchmark may still keep internal fixtures on disk. The key rule is that
the benchmark should simulate how the harness skill is actually used.

## Optimizer Redesign

The optimizer can still exist, but it should optimize the real skill surface.

Recommended editable surface for the first redesign:

- `skills/memory-ingest/SKILL.md`
- possibly one small policy file if needed later

The optimizer should not optimize around a fake entrypoint that users do not
actually use.

Recommended optimization loop after redesign:

1. run the harness-driven benchmark against current skill instructions
2. propose a small change to `SKILL.md`
3. rerun the harness-driven benchmark
4. keep or revert based on deterministic score

## What should be removed or demoted

The following should no longer be the primary ingest path:

- `skills/memory-ingest/scripts/ingest.py` as the user entrypoint
- any script that shells out to `pi`
- any assumption that the user prepares YAML-frontmatter knowledge files

If a direct script-based ingest path is kept at all, it should be clearly
labeled as a test harness or benchmark helper, not the product surface.

## What must stay true

Even after redesign, these principles should remain:

- the LLM does the semantic transformation
- deterministic Python does filesystem safety and writes
- the vault stays plain Markdown and Obsidian-compatible
- benchmarking stays fixed and outside the skill
- optimization stays narrow and auditable

## Explicit assumptions in this design

This redesign assumes:

- target harnesses can read local files or attachments and invoke local scripts/tools
- a harness skill can have instructions plus helper commands
- a default vault path can be configured outside the raw user message

If one specific harness cannot satisfy those assumptions, that harness will
need a thin adapter, but the product model should not change.

## Finalized Policy Decisions

The redesign is now locked to these decisions:

- first-class harness target: `pi`
- default placement for newly created notes: vault root
- updates to existing notes: automatic by default
