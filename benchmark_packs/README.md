# Benchmark Packs

A **benchmark pack** is a self-contained, immutable definition of one QA evaluation target for the `memory-ingest` skill. Packs are the general evaluation contract introduced in Milestone 7 (see `project_plan.md`).

Each pack bundles:

- a fixed **corpus** (input knowledge items for ingest)
- a fixed **question set** (with gold points for scoring)
- optional **vault seed** content (existing notes the agent must merge into)
- a **config** declaring how runners should treat the pack

The optimizer targets exactly one pack per run. During a run, the pack is treated as a read-only contract: no runner, scorer, or optimization agent may modify any file under the pack root.

## Pack Directory Layout

```
benchmark_packs/<pack_name>/
  pack.yaml                       # top-level pack metadata (id, version, description)
  corpus/                         # REQUIRED. raw knowledge items for ingest
    <free-form files>             # plain text, transcripts, md, etc.
  benchmark/
    questions.json                # REQUIRED. full question set (see question_schema.json)
    README.md                     # REQUIRED. human-readable pack doc
    config.yaml                   # OPTIONAL. pack-level runner config (see config_schema.json)
    dev_questions.json            # OPTIONAL. fixed dev subset (id references)
    holdout_questions.json        # OPTIONAL. fixed holdout subset (id references)
  vault_seed/                     # OPTIONAL. preexisting vault notes copied in before ingest
```

### Required vs optional

| Path                                  | Required | Purpose                                                    |
| ------------------------------------- | -------- | ---------------------------------------------------------- |
| `pack.yaml`                           | yes      | pack identity + schema version                             |
| `corpus/`                             | yes      | raw inputs the ingest skill must process                   |
| `benchmark/questions.json`            | yes      | gold questions + scoring points                            |
| `benchmark/README.md`                 | yes      | explains what this pack evaluates                          |
| `benchmark/config.yaml`               | no       | overrides default runner behavior                          |
| `benchmark/dev_questions.json`        | no       | small fixed subset for fast optimization iteration         |
| `benchmark/holdout_questions.json`    | no       | larger fixed subset for final evaluation                   |
| `vault_seed/`                         | no       | if present, copied verbatim into the temp vault before ingest |

### Immutability rules

A pack is **frozen during an optimization run**. Concretely:

- runners MUST open pack files read-only
- runners MUST copy `corpus/` and `vault_seed/` into a temp workspace before any mutation
- the optimization agent MUST NOT be able to propose changes to any file under the pack root
- pack edits happen out-of-band, between runs, as ordinary repo commits

## Difference From The Legacy `benchmarks/memory-ingest/` Layout

The legacy layout (`benchmarks/memory-ingest/cases/<case>/`) is **case-oriented and deterministic-scorer-oriented**: each case directory carries `case.yaml` with expected notes, required links, duplicate thresholds — rules the scorer checks against the produced vault structure directly.

A pack is **QA-oriented**: the scorer never inspects the vault's shape. It runs a fresh read-only QA session against the produced vault and scores those answers against gold points. The corpus and the question set are separate concerns; one corpus supports many questions.

Both paths coexist: legacy cases keep working under the existing deterministic benchmark runner; packs run through the new pack-based QA runner (Phase 2+).

## Pack Lifecycle

1. Author the pack: drop corpus files, author `questions.json`, write `benchmark/README.md`.
2. Validate the pack: run the pack loader (Phase 2) which enforces the schemas in `_schemas/`.
3. Select a pack for optimization: the runner copies `corpus/` and `vault_seed/` into a fresh temp vault and invokes the skill to ingest.
4. Answer: a separate fresh read-only QA session answers `dev_questions.json` (or full `questions.json`) using only the produced vault.
5. Score: the deterministic scorer compares answers to gold points and produces an aggregate score.
6. Optimize: the optimizer proposes one skill change, re-runs the full pipeline, and keeps or reverts based on score delta.
7. Final evaluation: on milestone-level checkpoints, re-run against `holdout_questions.json` to guard against overfitting on `dev_questions.json`.

## Schemas

All schemas live under `_schemas/` and are versioned via the `schema_version` field on each pack.

- `_schemas/pack_schema.json` — structure of `pack.yaml`
- `_schemas/question_schema.json` — one element of `questions.json`
- `_schemas/config_schema.json` — structure of `benchmark/config.yaml`
- `_schemas/answer_schema.json` — structure of one answer record emitted by the QA runner

The schemas are JSON Schema draft 2020-12. They describe the contract; runner code validates against them in Phase 2.
