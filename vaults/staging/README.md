# staging vault

This directory is reserved for the **personal-vault staging path**. It is the
bridge between the disposable sandbox in `vaults/sandbox/` and any eventual
write to a real personal Obsidian vault.

The personal vault is still off-limits. Nothing in this project writes to it.
This document defines what would have to be true before that ever changes.

## Why staging exists

The sandbox proves the loop works on toy data. The benchmark proves the loop
improves the skill against fixed cases. Neither proves the skill is safe to
point at notes a human actually cares about. Staging is the gap-closing step:

- it uses **realistic content**, not hand-crafted cases
- it runs against a **copy**, never the original
- it produces a **diff a human reviews before any merge back**
- it never bypasses the existing keep-or-revert discipline

If staging cannot show safety, the personal vault stays off-limits. That is
the whole point of having this stage at all.

## The staging-copy workflow

Staging is a snapshot workflow, not a live mount. The personal vault is read
once, copied into a timestamped snapshot under
`vaults/staging/snapshots/<timestamp>/`, and from that moment on the personal
vault is invisible to the loop.

1. **Snapshot.** Copy the personal vault into
   `vaults/staging/snapshots/<UTC-timestamp>/vault/`. The original path is
   recorded next to it in a small `snapshot.json` (source path, timestamp,
   file count, total size). The snapshot directory is the **only** thing the
   loop is allowed to touch from here on.
2. **Stage inputs.** Place the knowledge items to be ingested under
   `vaults/staging/snapshots/<timestamp>/inputs/`. These are the same shape
   as benchmark inputs, just sourced from real material.
3. **Dry run ingest.** Run `skills/memory-ingest/scripts/ingest.py` against
   the snapshot copy. The ingest produces normal Markdown writes inside the
   snapshot — the personal vault is not involved.
4. **Review diff.** A human inspects the diff between
   `snapshots/<timestamp>/vault/` and the original personal vault path with a
   plain `diff -ruN` (or Obsidian's own diff plugin). No automation merges
   anything.
5. **Manual merge or discard.** If the human approves, they apply the diff
   back to the personal vault by hand. If not, they delete the snapshot
   directory and the run is gone. There is no automated merge step.

Snapshots are append-only by convention. Reviewers should never edit the
snapshot in place — always discard and re-snapshot.

## Review checkpoints

A staging run must pass **all** of these before any byte is written to the
personal vault:

1. **Snapshot integrity** — `snapshot.json` matches the snapshot directory
   contents (same file count, same total size). If the source vault changed
   under the snapshot mid-run, the run is void.
2. **Benchmark green** — the same skill version that produced the staging
   diff has just passed the fixed benchmark on a fresh sandbox. A skill that
   regressed on toy cases does not get to touch real notes.
3. **Diff review by a human** — every created note read end to end, every
   updated note compared line by line against its prior version. No skim,
   no "looks fine".
4. **Reversibility check** — for every `update`, the prior version of the
   file is preserved in the snapshot so the change can be undone later
   without consulting backups.
5. **Sign-off** — the human writes a one-line note in the snapshot's
   `review.md` saying which operations they accept and which they reject.
   Anything not explicitly accepted is rejected by default.

If any checkpoint fails, the snapshot is discarded. There is no partial
acceptance flow.

## Rollback expectations

Rollback is the default, not the exception.

- **Pre-merge rollback.** Until a human runs the manual merge step, rollback
  is just `rm -rf vaults/staging/snapshots/<timestamp>/`. The personal vault
  was never touched.
- **Post-merge rollback for creates.** A `create` operation that turns out
  to be wrong is rolled back by deleting the file from the personal vault.
  The snapshot still holds the original (empty) state, so this is a
  one-step undo.
- **Post-merge rollback for updates.** Every `update` must preserve the
  prior version in the snapshot under
  `snapshots/<timestamp>/before/<original-path>`. Rollback is copying that
  file back over the personal-vault file. If the prior version was not
  preserved, the update is **forbidden** — the workflow refuses to run.
- **No "soft" rollback.** There are no tombstones, no rollback metadata,
  no journal. Files and a snapshot directory are the whole rollback story.

If rollback ever requires more than `cp` and `rm`, the workflow has drifted
and needs to be cut back.

## What must stay manual

These steps are intentionally not automated, and should not be automated by
the optimizer or any future helper script:

- **Choosing a personal vault path.** No discovery, no defaults, no env
  var. The human types the path each run.
- **Confirming the snapshot.** The human eyeballs `snapshot.json` and the
  file count before any ingest runs.
- **Approving the diff.** No "auto-approve if score improved". Benchmark
  improvement is necessary but not sufficient.
- **Merging back into the personal vault.** Done by hand, with the human's
  preferred tool. The project ships no merge command.
- **Deleting snapshots.** The human decides when a snapshot is no longer
  useful for rollback.

The optimizer never sees the staging path. The optimizer's editable surface
is still `skills/memory-ingest/SKILL.md` only, exactly as in Milestone 3.

## "Not yet safe" boundary

As of this milestone, the personal vault staging path is **defined but not
enabled**. The repo deliberately ships:

- this document
- an empty `snapshots/` directory
- no snapshot helper script
- no merge command
- no personal-vault path anywhere in code or config

The next builder who wants to enable a staging run must, in this order:

1. Add a thin `snapshot.py` that only knows how to read a source path and
   write `snapshots/<timestamp>/vault/` + `snapshot.json`. No other writes.
2. Run the existing benchmark and confirm it is green on the current skill.
3. Hand-run ingest against the snapshot.
4. Walk every checkpoint above by hand on a small subset before scaling up.

Until those steps are taken, treat the personal vault as out of scope.
Sandbox and per-case `vault_seed/` (see `vaults/sandbox/README.md`) are the
only places ingest is allowed to write.
