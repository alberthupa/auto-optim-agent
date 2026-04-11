# sandbox vault

This is the disposable Obsidian-style vault used for development and benchmarking.

It should be safe to recreate, reset, or replace during evaluation runs.

Do not treat this directory as a personal knowledge vault.

## Disposable sandbox vs. case-level staging seed

This directory is the **base** vault. Every benchmark case starts from a
fresh copy of it (see `benchmarks/memory-ingest/runner.py`). It is kept
intentionally minimal so cases do not share hidden state through it.

When a case needs to look more like a real, in-use vault — for example to
test that ingest **merges** into an existing note instead of spawning a
near-duplicate, or that it **cross-links** back to durable concept notes
that already exist — those pre-existing notes live in the case's own
`vault_seed/` directory under `benchmarks/memory-ingest/cases/<case>/`.
The runner copies them into the per-case temp vault on top of this base
sandbox before ingest runs, then throws the whole temp vault away.

The split keeps two things straight:

- **Sandbox vault** (this directory) — disposable, shared scaffold; should
  not contain test fixtures.
- **Case staging seed** (per-case `vault_seed/`) — realistic pre-existing
  notes scoped to one case; never leaks into other cases or into the real
  sandbox on disk.

The personal vault is still off-limits. Staging realism happens in temp
copies, not against anything you actually care about. The defined-but-not-
enabled bridge from sandbox to a real personal vault lives in
`vaults/staging/README.md`.
