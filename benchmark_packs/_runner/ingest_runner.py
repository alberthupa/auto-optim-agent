"""Fresh-vault ingest runner for a benchmark pack.

Responsibilities:
  1. Create a fresh temp vault directory for this run.
  2. Optionally copy `vault_seed/` into it verbatim.
  3. Iterate every file under `corpus/` and invoke the ingest entry point
     against the temp vault. Corpus files are read-only; the temp vault is
     the only mutable surface.
  4. Record per-item outcomes in a structured ingest report.

The ingest call itself currently shells out to the legacy
`skills/memory-ingest/scripts/ingest.py --stub` adapter. Once the harness-
owned path is wired, swap `_invoke_ingest` for a real harness launcher —
the rest of this module does not care.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from pack_loader import Pack

ROOT = Path(__file__).resolve().parents[2]
INGEST_SCRIPT = ROOT / "skills" / "memory-ingest" / "scripts" / "ingest.py"


@dataclass
class IngestItemResult:
    source: str
    status: str  # "ok" | "error"
    error: str | None = None
    latency_seconds: float = 0.0


@dataclass
class IngestReport:
    vault_path: str
    items: list[IngestItemResult]
    ok_count: int
    error_count: int


def prepare_vault(pack: Pack, workdir: Path) -> Path:
    vault = workdir / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    if pack.vault_seed_dir is not None:
        for src in pack.vault_seed_dir.rglob("*"):
            rel = src.relative_to(pack.vault_seed_dir)
            dst = vault / rel
            if src.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
    return vault


def run_ingest(pack: Pack, workdir: Path | None = None, *, mode: str = "stub") -> IngestReport:
    """Run ingest for every corpus item into a fresh temp vault.

    `mode`:
      - "stub": deterministic stub harness (no live LLM). Default.
      - "harness": live pi harness. Not implemented here; caller plugs it in.
    """
    workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix=f"pack-{pack.id}-"))
    workdir.mkdir(parents=True, exist_ok=True)
    vault = prepare_vault(pack, workdir)

    items: list[IngestItemResult] = []
    for src in sorted(pack.corpus_dir.rglob("*")):
        if not src.is_file():
            continue
        rel = str(src.relative_to(pack.corpus_dir))
        start = time.monotonic()
        try:
            _invoke_ingest(src, vault, mode=mode)
            items.append(IngestItemResult(source=rel, status="ok",
                                          latency_seconds=time.monotonic() - start))
        except Exception as exc:
            items.append(IngestItemResult(source=rel, status="error", error=str(exc),
                                          latency_seconds=time.monotonic() - start))

    report = IngestReport(
        vault_path=str(vault),
        items=items,
        ok_count=sum(1 for i in items if i.status == "ok"),
        error_count=sum(1 for i in items if i.status == "error"),
    )
    (workdir / "ingest_report.json").write_text(
        json.dumps({**asdict(report)}, indent=2, default=str),
        encoding="utf-8",
    )
    return report


def _invoke_ingest(item_path: Path, vault: Path, *, mode: str) -> None:
    if mode != "stub":
        raise NotImplementedError(f"ingest mode '{mode}' not wired yet")
    cmd = [
        sys.executable, str(INGEST_SCRIPT),
        "--item", str(item_path),
        "--vault", str(vault),
        "--stub",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ingest failed: {proc.stderr.strip() or proc.stdout.strip()}")


if __name__ == "__main__":
    import argparse
    from pack_loader import load_pack
    ap = argparse.ArgumentParser()
    ap.add_argument("pack_root")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--mode", default="stub", choices=["stub", "harness"])
    args = ap.parse_args()
    pack = load_pack(Path(args.pack_root))
    report = run_ingest(pack, Path(args.workdir) if args.workdir else None, mode=args.mode)
    print(json.dumps({"vault_path": report.vault_path,
                      "ok": report.ok_count,
                      "errors": report.error_count}, indent=2))
