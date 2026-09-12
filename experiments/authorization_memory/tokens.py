from __future__ import annotations

import re
from collections.abc import Callable
from functools import lru_cache
from typing import Any


TokenCounter = Callable[[str], int]
_FALLBACK_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


_ENCODER: Any | None = None


def _reference_encoder() -> Any | None:
    """The cl100k encoder, or None when it cannot be loaded.

    tiktoken downloads the encoding on first use, so an offline install with a cold
    cache fails here. Fall back to the regex counter rather than raising; callers
    record `reference_tokenizer_name`, so the two are never confused. A load failure
    is not cached, because a cached failure would silently change token counts for
    the rest of a run that was calibrated with cl100k.
    """

    global _ENCODER
    if _ENCODER is not None:
        return _ENCODER
    if not _tiktoken_available():
        return None
    try:
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None
    return _ENCODER


@lru_cache(maxsize=1)
def _tiktoken_available() -> bool:
    global tiktoken
    try:
        import tiktoken
    except ImportError:
        return False
    return True


def reference_tokenizer_name(counter: TokenCounter | None = None) -> str:
    if counter is not None:
        return "injected"
    return "cl100k_base" if _reference_encoder() is not None else "regex_fallback_v1"


def count_reference_tokens(
    text: str,
    counter: TokenCounter | None = None,
) -> int:
    count = (
        counter(text)
        if counter is not None
        else (
            len(_reference_encoder().encode(text))
            if _reference_encoder() is not None
            else len(_FALLBACK_TOKEN_PATTERN.findall(text))
        )
    )
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("token counter must return a non-negative integer")
    return count
