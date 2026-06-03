"""Order ingestion: parse a raw ``order_XX.txt`` into a structured ``RawOrder``.

Each file is a small header (``CHANNEL``/``FROM``, sometimes ``SUBJECT``/
``ATTACHMENT``), a ``---`` separator, then the free-text customer message.

The image case (order 07) is architected as a real vision path, not a string
hack: the parser pulls any ``[IMAGE DESCRIPTION ...]`` block out of the message
and parks it on the attachment as ``vision_text`` — the *simulated output of a
vision step*. The clean ``body`` the downstream LLM sees is only what the
customer actually typed. In a real deployment ``vision_text`` would be ``None``
here and a vision model would be called on the attached file instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# A bracketed block carrying the challenge's stand-in for a vision model's output.
_IMAGE_DESC_RE = re.compile(r"\[IMAGE DESCRIPTION.*?\]", re.DOTALL | re.IGNORECASE)


@dataclass
class Attachment:
    """A file attached to the order (e.g. a photo of the part)."""

    filename: str
    vision_text: str | None = None  # simulated vision output; None -> call a model


@dataclass
class RawOrder:
    """A parsed customer order, before any LLM interpretation."""

    order_id: str
    channel: str | None
    sender: str | None
    subject: str | None
    body: str  # clean customer message (image-description block removed)
    attachments: list[Attachment] = field(default_factory=list)
    raw_text: str = ""  # original file content, kept for audit

    @property
    def has_image(self) -> bool:
        return bool(self.attachments)


def _extract_vision_text(block: str) -> str:
    """Reduce an ``[IMAGE DESCRIPTION ... : <desc>]`` block to just ``<desc>``."""
    inner = block.strip()[1:-1]  # drop the surrounding [ ]
    # Everything after the first colon is the actual description; the prefix is meta.
    _, _, desc = inner.partition(":")
    return (desc or inner).strip()


def parse_order_text(text: str, order_id: str) -> RawOrder:
    """Parse the full text of an order file into a :class:`RawOrder`."""
    header_part, sep, body_part = text.partition("\n---")
    if not sep:  # no separator found: treat the whole thing as body
        header_part, body_part = "", text

    headers: dict[str, str] = {}
    for line in header_part.splitlines():
        key, colon, value = line.partition(":")
        if colon and re.fullmatch(r"[A-Za-z_]+", key.strip()):
            headers[key.strip().upper()] = value.strip()

    body = body_part.lstrip("\n")

    # Pull the simulated vision output out of the body and onto the attachment.
    vision_text: str | None = None
    match = _IMAGE_DESC_RE.search(body)
    if match:
        vision_text = _extract_vision_text(match.group(0))
        body = _IMAGE_DESC_RE.sub("", body)

    body = body.strip()

    attachments: list[Attachment] = []
    if headers.get("ATTACHMENT"):
        attachments.append(Attachment(headers["ATTACHMENT"], vision_text))
    elif vision_text is not None:
        # Image evidence with no explicit attachment header — still route it.
        attachments.append(Attachment("image", vision_text))

    return RawOrder(
        order_id=order_id,
        channel=headers.get("CHANNEL"),
        sender=headers.get("FROM"),
        subject=headers.get("SUBJECT"),
        body=body,
        attachments=attachments,
        raw_text=text,
    )


def parse_order(path: str | Path) -> RawOrder:
    """Read an ``order_XX.txt`` file and parse it."""
    path = Path(path)
    return parse_order_text(path.read_text(encoding="utf-8"), order_id=path.stem)
