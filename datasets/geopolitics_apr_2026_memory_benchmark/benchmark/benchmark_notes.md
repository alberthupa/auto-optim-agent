# Benchmark design notes

This benchmark tries to expose whether `memory-ingest` creates a useful memory structure rather than only preserving raw text.

## What good ingest should enable

- Entity notes for countries, alliances, chokepoints, and named people when useful
- Concept notes for sanctions, gray-zone tactics, critical minerals, burden sharing, energy security, and reconstruction
- Cross-links between region notes and thematic notes
- Preservation of timeline markers such as `mid-March`, `April 11`, and `2025`
- Retrieval of both direct facts and causal chains

## Failure modes this benchmark should catch

- dumping one note per source with no cross-links
- flattening all conflicts into one vague war note
- missing the difference between trade controls, sanctions, and procurement strategy
- failing to connect Hormuz disruption to Southeast Asian energy policy
- losing named entities like Kirill Dmitriev or Cheng Li-wun
- losing counterparty positions in negotiations

## Difficulty bands

- easy: one-document retrieval
- medium: link two facts within one topic area
- hard: synthesize across regions or policy domains
