from pathlib import Path

import pytest

from versed.alignment.sources import (
    LoadedText,
    _plain_text_document,
    _validated_openiti_url,
    load_english_translation,
    openiti_alignment_document,
)

OPENITI_SAMPLE = """######OpenITI#
#META# 000.BookURI :: 0581IbnTufayl.HayyIbnYaqzan
#META#Header#End#

### | المقدمة
# كلام في طبيعة الأرض.

### | حي بن يقظان
# بلغ حي ٢١ عاما ثم رأى النار.
"""


def test_openiti_adapter_keeps_structures_paragraphs_and_stable_ids():
    source = LoadedText(OPENITI_SAMPLE, "hayy.txt", "0581IbnTufayl.HayyIbnYaqzan", {})

    document = openiti_alignment_document(source)

    assert [unit.heading for unit in document.structures] == ["المقدمة", "حي بن يقظان"]
    assert document.structures[1].paragraphs[0].id == "ar:u0001:p0000"


def test_plain_english_adapter_detects_numbered_sections_without_losing_text():
    text = "CHAPTER 1\n\nThe first passage.\n\nCHAPTER 2\n\nThe second passage."

    document = _plain_text_document(text, source_name="translation.txt", work_id="demo")

    assert [unit.heading for unit in document.structures] == ["CHAPTER 1", "CHAPTER 2"]
    assert [unit.paragraphs[0].text for unit in document.structures] == [
        "The first passage.",
        "The second passage.",
    ]


def test_plain_english_adapter_does_not_treat_uppercase_ocr_as_structure():
    text = """THE TRANSLATOR

An introductory paragraph.

I. THE MAQAMA OF BALKH
The first body.

THE MAQAMAT OF BADI 12

II. THE MAQAMA OF BASRA
The second body.
"""

    document = _plain_text_document(text, source_name="translation.txt", work_id="demo")
    alignable = [
        unit
        for unit in document.structures
        if any("exclude_from_alignment" not in paragraph.flags for paragraph in unit.paragraphs)
    ]

    assert [unit.heading for unit in alignable] == [
        "I. THE MAQAMA OF BALKH",
        "II. THE MAQAMA OF BASRA",
    ]
    assert document.metadata["dominant_heading_family"] == "maqama"
    assert all(
        "exclude_from_alignment" in paragraph.flags
        for paragraph in document.structures[0].paragraphs
    )


def test_explicit_heading_line_does_not_consume_following_body_without_blank_line():
    text = """CHAPTER 1
The opening body continues on the next line.

CHAPTER 2
The closing body.
"""

    document = _plain_text_document(text, source_name="translation.txt", work_id="demo")

    assert document.structures[0].heading == "CHAPTER 1"
    assert document.structures[0].paragraphs[0].text == (
        "The opening body continues on the next line."
    )


def test_plain_text_quarantines_probable_scholarly_notes_but_retains_them():
    text = """CHAPTER 1

The translated narrative remains alignable.

1 Literally: the proper name refers to an older manuscript.

CHAPTER 2

The next narrative remains alignable.
"""

    document = _plain_text_document(text, source_name="translation.txt", work_id="demo")
    note = document.structures[0].paragraphs[1]

    assert note.text.startswith("1 Literally")
    assert note.flags == ("exclude_from_alignment", "possible_footnote")


def test_plain_english_file_loads_without_pdf_dependencies(tmp_path: Path):
    translation = tmp_path / "translation.txt"
    translation.write_text("A complete English paragraph.", encoding="utf-8")

    document = load_english_translation(translation, work_id="demo")

    assert document.metadata["adapter"] == "plain_text"
    assert document.structures[0].paragraphs[0].text == "A complete English paragraph."


def test_plain_text_quarantines_gutenberg_boilerplate_and_footnotes():
    text = """License preface.

*** START OF THE PROJECT GUTENBERG EBOOK DEMO ***

CHAPTER 1

The translated body.

[Footnote 1: An editorial note.]

*** END OF THE PROJECT GUTENBERG EBOOK DEMO ***

License footer.
"""

    document = _plain_text_document(text, source_name="translation.txt", work_id="demo")
    paragraphs = [paragraph for unit in document.structures for paragraph in unit.paragraphs]
    excluded = [value for value in paragraphs if "exclude_from_alignment" in value.flags]

    assert document.metadata["gutenberg_markers_detected"] is True
    assert any(value.text == "The translated body." and not value.flags for value in paragraphs)
    assert {value.metadata.get("paratext") for value in excluded} == {
        "footnote",
        "gutenberg_boilerplate",
    }


def test_openiti_url_is_allowlisted_and_converted_to_raw():
    url = _validated_openiti_url(
        "https://github.com/OpenITI/0575AH/blob/master/data/book/version-ara1"
    )

    assert url == "https://raw.githubusercontent.com/OpenITI/0575AH/master/data/book/version-ara1"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/OpenITI/0575AH/blob/master/file",
        "https://example.com/OpenITI/file",
        "https://raw.githubusercontent.com/someone-else/repo/master/file",
    ],
)
def test_openiti_url_rejects_unsafe_or_unrelated_hosts(url):
    with pytest.raises(ValueError):
        _validated_openiti_url(url)
