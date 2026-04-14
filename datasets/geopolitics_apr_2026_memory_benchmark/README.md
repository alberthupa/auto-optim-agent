# Geopolitics Memory Benchmark, April 2026 Snapshot

This dataset is a compact benchmark pack for the `memory-ingest` skill.

## Goal

Test whether an agent can ingest a small but realistic geopolitical corpus into an Obsidian-style vault in a way that supports:

- direct fact retrieval
- cross-document synthesis
- timeline reasoning
- entity linking
- comparison between regions and policy domains

## Design principles

This pack is intentionally small enough to understand at a glance, but dense enough to punish bad ingest behavior.

The corpus was curated from web-grounded summaries of major geopolitical themes visible around April 2026, then rewritten into compact benchmark documents. It is not a raw news dump. It is a synthetic benchmark corpus derived from contemporary reporting themes.

That means the benchmark tests memory quality, note structure, linking, and retrieval, not source scraping fidelity.

## Directory layout

- `corpus/` - 50 source documents to ingest
- `benchmark/questions.json` - 96 benchmark questions with answer keys, source mappings, and `gold_points` scoring anchors
- `benchmark/benchmark_notes.md` - question design notes and intended difficulty
- `sources/source_manifest.md` - provenance and topic mapping

## Pack role

As of Milestone 7 this dataset is also a benchmark pack conforming to the
contract in `benchmark_packs/README.md`. It keeps its original location
because the file layout already matches the pack contract; `pack.yaml`
lives at this directory root and `benchmark/README.md` documents the
benchmark surface. It is the **first** real pack, not the only one — the
smoke fixture under `benchmark_packs/smoke/` exercises the same pipeline
on a deliberately different content shape to prove generality.

Run it through the generic pack runner:

```bash
uv run python benchmark_packs/_runner/cli.py run \
  datasets/geopolitics_apr_2026_memory_benchmark --subset dev --mode stub
```

Or drive it through the optimizer:

```bash
uv run python optimizer/runner.py \
  --pack datasets/geopolitics_apr_2026_memory_benchmark \
  --subset dev --pack-mode stub --stub-optimizer \
  --notes "geopolitics dev smoke"
```

## Suggested usage (legacy narrative)

1. Start with an empty sandbox Obsidian-style vault.
2. Ask the agent to ingest the full `corpus/` directory.
3. Start a fresh read-only session and ask benchmark questions using only the resulting vault as memory.
4. Score outputs against `benchmark/questions.json`.

Do not ask benchmark questions in the same session that performed ingest. That
session has already seen the source corpus, so answers would be contaminated by
transient context rather than the resulting vault structure.

## Benchmark shape

The questions include:

- simple retrieval
- multi-document synthesis
- compare-and-contrast
- causal reasoning grounded in the corpus
- timeline questions
- list extraction with constrained answer keys
- benchmark-meta questions that reward good vault structure

## Important caveat

Some source themes were gathered through web-grounded summaries rather than direct full-text article archives. The corpus is therefore a benchmark fixture, not a journalistic source of record.
