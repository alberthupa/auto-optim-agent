# Smoke Pack

A tiny fictional pack used only to exercise the pack pipeline
end-to-end. Two corpus notes, four questions, no vault seed. Not a
measure of real skill quality.

Use it to verify that `pack_loader`, `ingest_runner`, `qa_runner`, and
`scorer` stay wired together after changes.

```
python benchmark_packs/_runner/cli.py run benchmark_packs/smoke
```
