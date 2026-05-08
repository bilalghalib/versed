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
        BlockType.PAGE_REF,
        BlockType.HEADING_1,
        BlockType.PAGE_REF,
        BlockType.PARAGRAPH,
        BlockType.PAGE_REF,
        BlockType.PARAGRAPH,
        BlockType.PARAGRAPH,
    ]
    assert doc.blocks[3].text == "هذا نص الصفحة الأولى."
    assert doc.blocks[0].meta == {"vol": 1, "page": 1}
    assert doc.blocks[4].meta == {"vol": 1, "page": 3}


def test_parse_openiti_preserves_hadith_poetry_and_editorial_blocks():
    doc = parse_openiti(OPENITI_TYPED_SAMPLE)

    assert [block.type for block in doc.blocks] == [
        BlockType.HEADING_2,
        BlockType.PARAGRAPH,
        BlockType.VERSE_PAIR,
        BlockType.HEADING_1,
        BlockType.APPARATUS_NOTE,
    ]

    assert doc.blocks[1].text == "حدثنا فلان قال النبي صلى الله عليه وسلم"

    verse = doc.blocks[2]
    assert verse.hemistich_a == "شعر"
    assert verse.hemistich_b == "موزون"

    editorial = doc.blocks[4]
    assert editorial.text == "تنبيه المحقق"


def test_parse_openiti_splits_inline_layout_markers_from_body_text():
    raw = """######OpenITI#
#META#Header#End#

PageV01P001
# متن المؤلف قبل الحاشية + حديث تخريج الحديث + وتتمة الصفحة ms0001
"""

    doc = parse_openiti(raw)

    assert [block.type for block in doc.blocks] == [
        BlockType.PAGE_REF,
        BlockType.PARAGRAPH,
        BlockType.APPARATUS_NOTE,
        BlockType.PARAGRAPH,
    ]
    assert doc.blocks[1].text == "متن المؤلف قبل الحاشية"
    assert doc.blocks[2].text == "حديث تخريج الحديث"
    assert doc.blocks[3].text == "وتتمة الصفحة"


def test_parse_openiti_splits_inline_title_markers():
    raw = """######OpenITI#
#META#Header#End#

# الباب السابع في العقل $ الباب الأول في فضل العلم
# شواهدها من القرآن
"""

    doc = parse_openiti(raw)

    assert [block.type for block in doc.blocks] == [
        BlockType.PARAGRAPH,
        BlockType.TITLE,
        BlockType.PARAGRAPH,
    ]
    assert doc.blocks[0].text == "الباب السابع في العقل"
    assert doc.blocks[1].text == "الباب الأول في فضل العلم"
