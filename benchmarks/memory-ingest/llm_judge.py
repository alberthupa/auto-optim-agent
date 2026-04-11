"""Fixed LLM-judge secondary signal for the memory-ingest benchmark.

Rules (from README's Benchmark Philosophy):

  - Deterministic score remains primary and authoritative.
  - LLM-judge is **secondary and advisory**. The benchmark runner never
    folds the judge score into the deterministic aggregate.
  - Fixed prompt, fixed rubric — both live in this file as constants and
    are hashed into a JUDGE_FINGERPRINT so drift is detectable in the
    experiments log.
  - This file lives under `benchmarks/memory-ingest/`, which the optimizer
    is forbidden from modifying during a run (enforced by the optimizer's
    clean-state guard, not by convention).

The judge sits *outside* the harness boundary. Per the project's auth
topology, that is the legitimate place for OPENAI_API_KEY: the optimized
skill itself still routes through PI, but a benchmark-side judge is a
separate tool that does not run inside the harness.

A `--stub` mode is provided so the runner stays usable offline and so the
optimizer's smoke tests don't depend on a live API key.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"

DEFAULT_MODEL = "gpt-4o-mini"
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 60

# ---------------------------------------------------------------------------
# Fixed rubric. Each dimension is rated 1-5. The judge score is the mean
# of the four ratings, normalized to [0, 1].
# ---------------------------------------------------------------------------

RUBRIC: dict[str, str] = {
    "consolidation_quality": (
        "Does the resulting vault avoid both over-fragmentation and "
        "over-summarization? A good vault has the right number of notes for "
        "the input — neither one giant blob nor a flock of near-duplicates."
    ),
    "link_meaningfulness": (
        "Are the [[wiki links]] pointing to durable, reusable concepts that a "
        "future reader would actually want to follow? Penalize links that "
        "point at trivia or that are missing for obvious shared concepts."
    ),
    "retrieval_usefulness": (
        "If a future user asked a plausible question about this knowledge, "
        "would the notes (titles + bodies) actually surface a useful answer?"
    ),
    "faithfulness": (
        "Are the facts in the notes accurate to the source input? Penalize "
        "hallucinated content, distorted claims, or dropped key context."
    ),
}

PROMPT_TEMPLATE = """\
You are a fixed evaluation judge for a memory-ingest benchmark. Your job is to
rate the quality of a small Obsidian-style vault that an ingest skill produced
from one knowledge item. You are a *secondary, advisory* signal — a separate
deterministic scorer is the primary judge. Be calibrated, not generous.

Rate each rubric dimension on an integer scale 1-5:
  1 = unacceptable
  2 = weak
  3 = acceptable
  4 = good
  5 = excellent

Rubric:
{rubric_block}

# Benchmark case
name: {case_name}
description: {case_description}

# Source input(s) the skill received
{inputs_block}

# Resulting notes in the vault
{notes_block}

Return EXACTLY one JSON object, no markdown fences, no commentary, with this
shape:

{{
  "ratings": {{
{ratings_keys}
  }},
  "rationale": "<= 2 sentences explaining the lowest rating"
}}
"""


def _ratings_keys_block() -> str:
    keys = list(RUBRIC.keys())
    lines = []
    for index, key in enumerate(keys):
        comma = "," if index < len(keys) - 1 else ""
        lines.append(f'    "{key}": <int 1-5>{comma}')
    return "\n".join(lines)


def _rubric_block() -> str:
    return "\n".join(f"- {k}: {v}" for k, v in RUBRIC.items())


def _build_prompt(
    case_name: str,
    case_description: str,
    input_texts: list[tuple[str, str]],
    notes: list[dict[str, Any]],
) -> str:
    inputs_block = "\n\n".join(
        f"## input: {label}\n```\n{text.strip()}\n```" for label, text in input_texts
    ) or "(no inputs)"
    notes_block = "\n\n".join(
        f"## note: {n['title']}\n```\n{n['raw'].strip()}\n```" for n in notes
    ) or "(vault is empty)"
    return PROMPT_TEMPLATE.format(
        rubric_block=_rubric_block(),
        case_name=case_name,
        case_description=case_description.strip() or "(no description)",
        inputs_block=inputs_block,
        notes_block=notes_block,
        ratings_keys=_ratings_keys_block(),
    )


# Stable hash of the rubric + prompt template + default model. Goes into the
# experiments log so a future reader can detect that the judge contract changed.
JUDGE_FINGERPRINT = hashlib.sha256(
    json.dumps(
        {"rubric": RUBRIC, "template": PROMPT_TEMPLATE, "model": DEFAULT_MODEL},
        sort_keys=True,
    ).encode("utf-8")
).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Tiny .env loader. The repo otherwise reads no env files; this stays inline
# rather than introducing python-dotenv as a dependency.
# ---------------------------------------------------------------------------


def _load_openai_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip() == "OPENAI_API_KEY":
                value = value.strip().strip('"').strip("'")
                if value:
                    return value
    raise RuntimeError(
        "OPENAI_API_KEY is not set (checked environment and repo .env). "
        "Either export the key, populate .env, or run with --llm-judge-stub."
    )


# ---------------------------------------------------------------------------
# OpenAI Chat Completions call. Plain urllib — no SDK dependency.
# ---------------------------------------------------------------------------


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json_object(text: str) -> dict[str, Any]:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        match = _JSON_OBJECT_RE.search(text)
        if not match:
            raise ValueError(f"no JSON object in judge output:\n{text}")
        candidate = match.group(0)
    return json.loads(candidate)


def _call_openai(prompt: str, model: str) -> dict[str, Any]:
    api_key = _load_openai_api_key()
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a strict, calibrated evaluation judge. "
                    "Always respond with a single JSON object."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    request = urllib.request.Request(
        OPENAI_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI HTTP {exc.code}: {detail}") from exc
    parsed = json.loads(body)
    content = parsed["choices"][0]["message"]["content"]
    return _extract_json_object(content)


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------


def _normalize_ratings(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        raise ValueError(f"ratings is not a mapping: {raw!r}")
    out: dict[str, int] = {}
    for key in RUBRIC:
        value = raw.get(key)
        if value is None:
            raise ValueError(f"missing rubric key: {key}")
        try:
            ivalue = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"rating for {key} is not an int: {value!r}") from exc
        if not 1 <= ivalue <= 5:
            raise ValueError(f"rating for {key} out of range 1-5: {ivalue}")
        out[key] = ivalue
    return out


def _stub_result() -> dict[str, Any]:
    """Deterministic placeholder used when no live API call is desired."""
    ratings = {key: 3 for key in RUBRIC}
    return {
        "ratings": ratings,
        "rationale": "stub judge: fixed midpoint ratings, no model call",
        "score": _ratings_to_score(ratings),
        "model": "stub",
        "fingerprint": JUDGE_FINGERPRINT,
    }


def _ratings_to_score(ratings: dict[str, int]) -> float:
    return round(sum(ratings.values()) / (5 * len(ratings)), 4)


def judge_case(
    case_name: str,
    case_description: str,
    input_texts: list[tuple[str, str]],
    notes: list[dict[str, Any]],
    *,
    stub: bool = False,
    model: str | None = None,
) -> dict[str, Any]:
    """Score one case with the LLM-judge. Returns an advisory rubric block.

    Output shape:
        {
          "score": float in [0, 1],
          "ratings": {<rubric key>: int 1-5, ...},
          "rationale": str,
          "model": str,
          "fingerprint": str,
        }
    """
    if stub:
        return _stub_result()

    chosen_model = model or os.environ.get("MEMORY_INGEST_JUDGE_MODEL") or DEFAULT_MODEL
    prompt = _build_prompt(case_name, case_description, input_texts, notes)
    raw = _call_openai(prompt, chosen_model)
    ratings = _normalize_ratings(raw.get("ratings"))
    rationale = str(raw.get("rationale", "")).strip()
    return {
        "score": _ratings_to_score(ratings),
        "ratings": ratings,
        "rationale": rationale,
        "model": chosen_model,
        "fingerprint": JUDGE_FINGERPRINT,
    }
