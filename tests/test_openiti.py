"""Tests for public OpenITI normalization helpers."""

from versed.markdown import build_markdown_from_document
from versed.openiti import assign_openiti_pages, build_openiti_markdown, document_from_openiti_blocks
from versed.types import BlockType, Document, TextBlock


OPENITI_PARSED = {
    "metadata": {"title": "رسالة في التوبة"},
    "content": [
        {"type": "title", "content": "رسالة في التوبة"},
        {"type": "pageNumber", "content": {"volume": "01", "page": "218"}},
        {"type": "paragraph", "content": "فصل"},
        {"type": "paragraph", "content": "قال الإمام العلامة"},
        {"type": "verse", "content": ["قفا نبك", "من ذكرى حبيب"]},
        {"type": "pageNumber", "content": {"volume": "01", "page": "219"}},
        {"type": "blockquote", "content": "هذا نص مقتبس"},
        {"type": "year_of_death", "content": "505"},
    ],
}


def test_assign_openiti_pages_tracks_latest_page_marker():
    numbered = assign_openiti_pages(OPENITI_PARSED)

    assert [item.page for item in numbered] == [1, 218, 218, 218, 219, 219]
    assert numbered[1].volume == 1
    assert numbered[-1].page == 219


def test_document_from_openiti_blocks_normalizes_public_document():
    document = document_from_openiti_blocks(OPENITI_PARSED)

    assert document.title == "رسالة في التوبة"
    assert document.blocks[0].type == BlockType.HEADING
    assert document.blocks[1].type == BlockType.PARAGRAPH
    assert document.blocks[3].type == BlockType.VERSE
    assert document.blocks[-1].text == "Year of death: 505"
    assert document.blocks[1].meta["page"] == 218
    assert document.meta["source"] == "openiti"
    assert document.meta["page_numbers"] == [1, 218, 219]


def test_build_openiti_markdown_renders_quotes_and_labels():
    result = build_openiti_markdown(OPENITI_PARSED)

    assert "## رسالة في التوبة" in result.markdown
    assert "> قفا نبك // من ذكرى حبيب" in result.markdown
    assert "Year of death: 505" in result.markdown
    assert result.plain_text.startswith("رسالة في التوبة")


def test_build_markdown_from_document_supports_generic_public_documents():
    document = Document(
        title="Demo",
        blocks=[
            TextBlock(type=BlockType.HEADING, text="Intro"),
            TextBlock(type=BlockType.PARAGRAPH, text="Body text"),
            TextBlock(type=BlockType.VERSE, text="بسم الله", meta={"verse_key": "1:1"}),
        ],
    )

    result = build_markdown_from_document(document)

    assert "## Demo" in result.markdown
    assert "## Intro" in result.markdown
    assert "> بسم الله **[1:1]**" in result.markdown
    assert result.plain_text.endswith("بسم الله [1:1]")
