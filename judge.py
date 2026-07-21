"""LLM-as-judge helpers. Used to read structured labels out of free-text agent output."""

from __future__ import annotations

from dataclasses import dataclass

from eal_bench.llm import LLM

_EXTRACT_SYS = (
    "You read an assistant's message and identify which single option it chose from a "
    "given list. Reply with ONLY the exact option text from the list, copied verbatim. "
    "If it named none of them, reply exactly: NONE."
)


@dataclass
class Choice:
    option: str | None
    raw: str


def extract_choice(llm: LLM, statement: str, options: list[str], *, task: str = "judge") -> Choice:
    """Ask the judge which `option` the `statement` picked."""
    option_list = "\n".join(f"- {o}" for o in options)
    user = f"Options:\n{option_list}\n\nAssistant message:\n{statement}\n\nWhich option did it choose?"
    resp = llm.complete(
        task,
        messages=[
            {"role": "system", "content": _EXTRACT_SYS},
            {"role": "user", "content": user},
        ],
    )
    raw = (resp.choices[0].message.content or "").strip()
    return Choice(option=_match(raw, options), raw=raw)


def _match(raw: str, options: list[str]) -> str | None:
    low = raw.lower()
    if not low or low == "none":
        return None
    for o in options:
        if o.lower() == low:
            return o
    for o in options:
        if o.lower() in low or low in o.lower():
            return o
    return None
