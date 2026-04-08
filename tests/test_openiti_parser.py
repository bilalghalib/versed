"""Tests for the public OpenITI parser bridge."""

from versed.openiti_parser import BlockType, parse_openiti


OPENITI_SAMPLE = """######OpenITI#
#META#Header#End#

### | كتاب
PageV01P001
هذا نص الصفحة الأولى.

PageV01P002
هذا نص الصفحة الثانية.

PageV01P003
هذا نص الصفحة الثالثة.
"""


OPENITI_TYPED_SAMPLE = """######OpenITI#
#META#Header#End#

### || باب
# $RWY$ حدثنا فلان @MATN@ قال النبي صلى الله عليه وسلم
# شعر %~% موزون
### |EDITOR| تنبيه المحقق
"""


def test_parse_openiti_tracks_page_markers_and_paragraphs():
    doc = parse_openiti(OPENITI_SAMPLE, title="إحياء علوم الدين", author="الغزالي")

    assert [block.type for block in doc.blocks] == [
        BlockType.HEADING_1,
        BlockType.PAGE_REF,
        BlockType.PARAGRAPH,
        BlockType.PAGE_REF,
        BlockType.PARAGRAPH,
        BlockType.PAGE_REF,
        BlockType.PARAGRAPH,
    ]
    assert doc.blocks[2].text == "هذا نص الصفحة الأولى."
    assert doc.blocks[1].meta == {"vol": 1, "page": 1}
    assert doc.blocks[-2].meta == {"vol": 1, "page": 3}


def test_parse_openiti_preserves_hadith_poetry_and_editorial_blocks():
    doc = parse_openiti(OPENITI_TYPED_SAMPLE)

    assert [block.type for block in doc.blocks] == [
        BlockType.HEADING_2,
        BlockType.HADITH_UNIT,
        BlockType.VERSE_PAIR,
        BlockType.EDITORIAL_SECTION,
    ]

    hadith = doc.blocks[1]
    assert hadith.isnad_text == "حدثنا فلان"
    assert hadith.matn_text == "قال النبي صلى الله عليه وسلم"

    verse = doc.blocks[2]
    assert verse.hemistich_a == "شعر"
    assert verse.hemistich_b == "موزون"

    editorial = doc.blocks[3]
    assert editorial.text == "تنبيه المحقق"
