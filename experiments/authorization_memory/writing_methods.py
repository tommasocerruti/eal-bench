"""How the LangMem writer is fed at each block.

incremental          (previous memory, new block), the paper's method
rebuild_every=k      every k blocks, and at the last block, an empty profile plus the history
                     so far, so memory is rebuilt from source
writer_retrieval_k=k the new block plus the k earlier messages most similar to it (BM25)
"""

from __future__ import annotations

from typing import Any

from domains.base import AuthorizationMemoryDomain, PresentationProfile

from .extensions_common import BM25Index, turn_text
from .langmem_writer import WriterUpdateSpec


def parse_method(value: str) -> tuple[int | None, int | None]:
    """'incremental' | 'rebuild:3' | 'retrieve:6' | 'rebuild:3+retrieve:6' -> (rebuild_every, retrieval_k)."""

    rebuild = retrieve = None
    for part in value.split("+"):
        name, _, number = part.strip().partition(":")
        if name == "rebuild":
            rebuild = int(number)
        elif name == "retrieve":
            retrieve = int(number)
        elif name != "incremental":
            raise ValueError(f"unknown writing method {part!r}")
    if (rebuild is not None and rebuild < 1) or (retrieve is not None and retrieve < 1):
        raise ValueError(f"writing method {value!r} needs k >= 1")
    return rebuild, retrieve


def method_suffix(rebuild_every: int | None, writer_retrieval_k: int | None) -> str:
    parts = [f"rebuild{rebuild_every}" if rebuild_every else "", f"retrieve{writer_retrieval_k}" if writer_retrieval_k else ""]
    joined = "+".join(p for p in parts if p)
    return f"__{joined}" if joined else ""


def _wrap(tag: str, content: str) -> dict[str, str]:
    return {"role": "user", "content": f"<{tag}>\n{content}\n</{tag}>"}


def incremental_updates(
    domain: AuthorizationMemoryDomain,
    case: Any,
    presentation: PresentationProfile,
    *,
    rebuild_every: int | None = None,
    writer_retrieval_k: int | None = None,
) -> tuple[WriterUpdateSpec, ...]:
    blocks = list(domain.corpus.blocks(case))
    updates = []
    for position, block in enumerate(blocks):
        visible = frozenset(domain.corpus.source_turn_ids(case, through_block_index=block.block_index))
        if rebuild_every and ((position + 1) % rebuild_every == 0 or block is blocks[-1]):
            history = "\n\n".join(domain.corpus.render_block(b, presentation) for b in blocks[: position + 1])
            updates.append(WriterUpdateSpec(block.block_index, (_wrap("SOURCE_HISTORY", history),), visible, "full_history", rebuild_from_history=True))
            continue
        content = _wrap("NEW_CONVERSATION_BLOCK", domain.corpus.render_block(block, presentation))["content"]
        earlier = [turn for b in blocks[:position] for turn in b.turns]
        if writer_retrieval_k and earlier:
            picked = sorted(BM25Index([turn_text(t) for t in earlier]).top(" ".join(t.content for t in block.turns), writer_retrieval_k))
            retrieved = "\n".join(turn_text(earlier[i]) for i in picked)
            content += f"\n\n<RETRIEVED_EARLIER_MESSAGES>\n{retrieved}\n</RETRIEVED_EARLIER_MESSAGES>"
        updates.append(WriterUpdateSpec(block.block_index, ({"role": "user", "content": content},), visible, "new_conversation_block"))
    return tuple(updates)
