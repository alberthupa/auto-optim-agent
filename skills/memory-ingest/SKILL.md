# memory-ingest

## Purpose

This skill ingests knowledge into an Obsidian-compatible vault.

The output should remain:

- readable by a human
- compatible with normal Obsidian usage
- structured enough for later retrieval and linking

## Scope

The first implementation should handle:

- plain text
- rough notes
- dialogs or transcripts

## Expected Inputs

The first implementation should expect:

- a path to one knowledge item
- a path to the target vault

The exact schema is still to be finalized in Milestone 1.

## Expected Outputs

The first implementation should:

- create or update Markdown notes
- preserve useful source context
- add links only when they are meaningful
- avoid obvious duplication

## Constraints

- keep the implementation simple
- prefer one thin Python script
- do not introduce a database
- do not depend on Obsidian plugins
