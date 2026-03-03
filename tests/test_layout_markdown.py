"""Tests for public layout and markdown builders."""

from versed.layout import document_from_aligned_words
from versed.markdown import build_enhanced_markdown
from versed.types import AlignedWord, BlockType


class TestLayoutAndMarkdown:
    def test_quran_words_become_verse_block(self):
        words = [
            AlignedWord(
                text="بسم",
                spoken_text="بسم",
                language="ar",
                role="quran",
                verse_key="1:1",
                block_no=1,
                line_no=0,
                word_no=0,
            ),
            AlignedWord(
                text="الله",
                spoken_text="الله",
                language="ar",
                role="quran",
                verse_key="1:1",
                block_no=1,
                line_no=0,
                word_no=1,
            ),
        ]

        document = document_from_aligned_words(words, title="Opening")
        assert document.blocks[0].type == BlockType.VERSE

        markdown = build_enhanced_markdown(words, title="Opening")
        assert "## Opening" in markdown.markdown
        assert "> بسم الله **[1:1]**" in markdown.markdown

    def test_heading_role_becomes_heading_block(self):
        words = [
            AlignedWord(
                text="Introduction",
                spoken_text="Introduction",
                language="en",
                role="heading",
                section_type="header",
                block_no=1,
                line_no=0,
                word_no=0,
            )
        ]

        document = document_from_aligned_words(words)
        assert document.blocks[0].type == BlockType.HEADING

