"""Recursive-character chunking (spec section 6)."""
from rag_kro_shared import get_settings


def chunk_text(text: str, source: str = "upload") -> list[dict]:
    settings = get_settings()
    size = settings.chunk_size
    overlap = settings.chunk_overlap
    seen: set[str] = set()
    out: list[dict] = []

    # paragraph-level split first to respect natural boundaries
    paragraphs = [p.strip() for p in text.replace("\r\n", "\n").split("\n\n") if p.strip()]

    buffer = ""
    index = 0
    for para in paragraphs:
        if len(buffer) + len(para) + 2 <= size:
            buffer = f"{buffer}\n\n{para}".strip()
            continue
        # flush current buffer by recursive split if still too long
        for piece in _recursive_split(buffer, size, overlap):
            if piece and piece not in seen:
                out.append({"index": index, "text": piece, "source": source})
                seen.add(piece)
                index += 1
        buffer = para

    if buffer:
        for piece in _recursive_split(buffer, size, overlap):
            if piece and piece not in seen:
                out.append({"index": index, "text": piece, "source": source})
                seen.add(piece)
                index += 1
    return out


def _recursive_split(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text]
    # split at sentence boundary nearest to `size`
    split_at = text.rfind(". ", 0, size)
    if split_at == -1:
        split_at = size
    head, tail = text[: split_at + 1], text[max(0, split_at - overlap):]
    return [head, *_recursive_split(tail, size, overlap)]