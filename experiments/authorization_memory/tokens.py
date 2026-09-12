from __future__ import annotations

import re
from collections.abc import Callable
from functools import lru_cache


TokenCounter = Callable[[str], int]
_FALLBACK_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


@lru_cache(maxsize=1)
def _reference_policy() -> tuple[str, TokenCounter]:
    """Resolve the counting policy once, so the name and the count always agree.

    tiktoken downloads the encoding on first use, so an offline install with a cold
    cache falls back to the regex counter. Resolving per call let one call succeed
    and another fail, which saved a regex count under a cl100k label.
    """

    try:
        import tiktoken
    except ImportError:
        return "regex_fallback_v1", _regex_count
    try:
        encoder = tiktoken.get_encoding("cl100k_base")
    except Exception:
        return "regex_fallback_v1", _regex_count
    return "cl100k_base", lambda text: len(encoder.encode(text))


def _regex_count(text: str) -> int:
    return len(_FALLBACK_TOKEN_PATTERN.findall(text))


def reference_tokenizer_name(counter: TokenCounter | None = None) -> str:
    if counter is not None:
        return "injected"
    return _reference_policy()[0]


def count_reference_tokens(
    text: str,
    counter: TokenCounter | None = None,
) -> int:
    count = counter(text) if counter is not None else _reference_policy()[1](text)
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("token counter must return a non-negative integer")
    return count
