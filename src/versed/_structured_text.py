"""Helpers for extracting structured text without regex parsers."""

from __future__ import annotations

import html as html_lib
from html.parser import HTMLParser


class _HTMLTextExtractor(HTMLParser):
    _SPACING_TAGS = {
        "br",
        "div",
        "li",
        "p",
        "section",
        "table",
        "td",
        "th",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[no-untyped-def]
        if tag.lower() in self._SPACING_TAGS:
            self._parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._SPACING_TAGS:
            self._parts.append(" ")

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def text(self) -> str:
        return collapse_whitespace("".join(self._parts))


def collapse_whitespace(text: str) -> str:
    return " ".join((text or "").split())


def tighten_punctuation_spacing(text: str) -> str:
    cleaned = collapse_whitespace(text)
    for mark in (".", ",", ";", ":", "!", "?"):
        cleaned = cleaned.replace(f" {mark}", mark)
    return cleaned


def html_to_text(text: str) -> str:
    if not text:
        return ""
    parser = _HTMLTextExtractor()
    parser.feed(text)
    parser.close()
    return collapse_whitespace(html_lib.unescape(parser.text()))


def strip_markdown_inline(text: str) -> str:
    if not text:
        return ""
    text = _remove_fenced_blocks(text)
    output: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "`":
            end = text.find("`", i + 1)
            if end == -1:
                i += 1
                continue
            output.append(text[i + 1 : end])
            i = end + 1
            continue
        if ch == "!" and i + 1 < len(text) and text[i + 1] == "[":
            next_i = _consume_markdown_link(text, i, keep_label=False)
            if isinstance(next_i, int):
                output.append(" ")
                i = next_i
                continue
        if ch == "[":
            consumed = _consume_markdown_link(text, i, keep_label=True)
            if isinstance(consumed, tuple):
                label, next_i = consumed
                output.append(label)
                i = next_i
                continue
        if ch not in "*_~":
            output.append(ch)
        i += 1
    return collapse_whitespace("".join(output))


def _remove_fenced_blocks(text: str) -> str:
    output: list[str] = []
    pos = 0
    while True:
        start = text.find("```", pos)
        if start == -1:
            output.append(text[pos:])
            return "".join(output)
        output.append(text[pos:start])
        end = text.find("```", start + 3)
        if end == -1:
            return "".join(output)
        output.append(" ")
        pos = end + 3


def _consume_markdown_link(text: str, start: int, *, keep_label: bool):
    label_start = start + (2 if text.startswith("![", start) else 1)
    label_end = text.find("]", label_start)
    if label_end == -1 or label_end + 1 >= len(text) or text[label_end + 1] != "(":
        return None
    url_end = _find_closing_paren(text, label_end + 2)
    if url_end == -1:
        return None
    if keep_label:
        return text[label_start:label_end], url_end + 1
    return url_end + 1


def _find_closing_paren(text: str, start: int) -> int:
    depth = 0
    for index in range(start, len(text)):
        ch = text[index]
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                return index
            depth -= 1
    return -1
