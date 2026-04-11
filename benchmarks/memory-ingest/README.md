# memory-ingest benchmark

Fixed benchmark for the `memory-ingest` skill. Treat this directory as a
**contract**. During an optimization run the optimizer must not modify
anything under `benchmarks/`.

## Layout

```
benchmarks/memory-ingest/
├── README.md          (this file)
├── runner.py          (thin benchmark runner + deterministic scorer)
└── cases/
    └── <case-name>/
        ├── case.yaml  (metadata + expected deterministic checks)
        └── input/     (raw input files fed to the ingest skill)
```

Milestone 4 ships with six hand-written cases:

- `plain-text` — one polished note about Obsidian linking
- `dialog` — a short multi-speaker standup transcript
- `rough-notes` — a messy late-night bullet-list dump
- `interview-transcript` — a user interview about trustworthy memory ingest
- `research-snippets` — copied snippets from multiple research sources
- `mixed-source-bundle` — one bundle that mixes several capture types

## Running

```bash
# deterministic, no live LLM required
uv run python benchmarks/memory-ingest/runner.py --stub

# only one case
uv run python benchmarks/memory-ingest/runner.py --stub --case dialog

# record an entry in results/experiments.jsonl
uv run python benchmarks/memory-ingest/runner.py --stub --record --notes "baseline"
```

Each run copies `vaults/sandbox/` into a fresh temp directory, executes the
skill's ingest entry point against every input file in the case, loads the
resulting Markdown notes from that temp vault, and scores them. The temp
vault is deleted at the end of the case — **no state leaks between runs**.

## `case.yaml` fields

| field                     | type         | meaning                                                                                  |
| ------------------------- | ------------ | ---------------------------------------------------------------------------------------- |
| `name`                    | string       | case identifier (matches the directory name)                                             |
| `description`             | string       | what the case is testing and why                                                         |
| `inputs`                  | list\[path]  | input files relative to the case dir; defaults to everything under `input/`              |
| `expected_notes`          | list\[str]   | substrings that must appear in at least one note **title** (case-insensitive)            |
| `required_facts`          | list\[str]   | substrings that must appear in at least one note **body** (case-insensitive)             |
| `required_links`          | list\[str]   | link targets expected as `[[wiki link]]` somewhere in the rendered vault                 |
| `min_notes`               | int          | lower bound on ingested note count (forces decomposition on multi-topic inputs)          |
| `max_notes`               | int          | upper bound on ingested note count                                                       |
| `max_duplicates`          | int          | allowed duplicate-body count (default `0`)                                               |
| `max_duplicate_titles`    | int          | allowed duplicate-title count after case-insensitive normalization                        |
| `max_body_containment_duplicates` | int | allowed count of large note bodies fully contained in another note body                   |
| `required_note_kinds`     | list\[str]   | required `frontmatter.note_kind` values such as `raw_capture` / `consolidated`          |
| `require_derived_from`    | bool         | if true, consolidated notes must carry a non-empty `derived_from` frontmatter field      |
| `require_source_metadata` | bool         | if true, score by fraction of notes carrying `source_type` in frontmatter (default true) |

All check fields are optional. A missing field means that dimension is not
scored for that case.

## Scoring

Scoring is **fully deterministic** in Milestone 2. No LLM-judge. Every
dimension returns a float in `[0.0, 1.0]`:

| dimension                     | how it is computed                                                      |
| ----------------------------- | ----------------------------------------------------------------------- |
| `expected_notes`              | fraction of `expected_notes` substrings found in any note title         |
| `required_facts`              | fraction of `required_facts` substrings found anywhere in any note body |
| `required_links`              | fraction of `required_links` found as `[[wiki links]]` anywhere          |
| `note_count_within_limit`     | `1.0` if `len(notes) <= max_notes` else `0.0`                           |
| `note_count_above_min`        | `1.0` if `len(notes) >= min_notes` else `0.0`                           |
| `duplicates_within_threshold` | `1.0` if duplicate-body count `<= max_duplicates` else `0.0`            |
| `duplicate_titles_within_threshold` | `1.0` if duplicate-title count `<= max_duplicate_titles` else `0.0` |
| `body_containment_within_threshold` | `1.0` if large-body containment count `<= max_body_containment_duplicates` else `0.0` |
| `required_note_kinds`         | fraction of required `frontmatter.note_kind` values present             |
| `derived_from_present`        | fraction of consolidated notes that include non-empty `derived_from`     |
| `source_metadata_preserved`   | fraction of notes with `source_type` in their frontmatter               |
| `any_notes_produced`          | `1.0` if ≥1 note was produced else `0.0`                                |

Per-case score is the mean of the dimensions that the case actually uses.
Aggregate score is the mean of per-case scores. The runner prints a
per-dimension breakdown in addition to the aggregate so regressions are
localizable.

**What the score is trying to reward:** presence of stable facts, reasonable
note counts, preserved provenance, explicit raw-to-consolidated relationships,
and absence of duplication. It deliberately does **not** reward pretty
formatting.

## Results log

`--record` appends one JSON object per run to `results/experiments.jsonl`:

```json
{
  "timestamp": "2026-04-11T12:00:00+00:00",
  "experiment_id": "<uuid4>",
  "skill_git_sha": "<last commit touching skills/memory-ingest/>",
  "baseline_score": null,
  "new_score": 0.8095,
  "per_dimension": {"required_facts": 0.9, "...": 0.8},
  "kept": null,
  "notes": "manual benchmark run"
}
```

`baseline_score` and `kept` stay `null` here; the optimization loop
(Milestone 3) is what populates them.

## Rules of the house

- The benchmark is fixed during an optimization run. Do not edit `cases/` or
  `runner.py` mid-experiment.
- The scorer lives here, not in the skill. The thing being optimized cannot
  modify its own judge.
- Every run uses a fresh vault copy. No state leaks between runs.
- Scoring stays 100% deterministic through Milestone 2. An optional LLM-judge
  secondary signal may be considered later, under the rules in the root
  `README.md` benchmark philosophy section — never as a replacement for the
  deterministic signal, and never editable by the optimizer.
