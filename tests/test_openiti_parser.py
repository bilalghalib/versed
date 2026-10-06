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


def test_parse_openiti_uses_header_metadata_for_front_matter():
    raw = """######OpenITI#
#META# 010.AuthorNAME :: ابن خلكان
#META# 020.BookTITLE :: وفيات الأعيان
#META#Header#End#

# متن الكتاب
"""

    doc = parse_openiti(raw)

    assert doc.title == "وفيات الأعيان"
    assert doc.author == "ابن خلكان"


def test_parse_openiti_keeps_authorial_qala_as_body_text():
    raw = """######OpenITI#
#META#Header#End#

# قلت: وأين الأقاح قال لنا
"""

    doc = parse_openiti(raw)

    assert [block.type for block in doc.blocks] == [BlockType.PARAGRAPH]
    assert doc.blocks[0].text == "قلت: وأين الأقاح قال لنا"


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


def test_parse_openiti_keeps_guillemet_quotation_as_prose():
    raw = """######OpenITI#
#META#Header#End#

# قال الحكيم: «من عرف نفسه فقد عرف ربه» ثم شرح معنى النفس.
"""

    doc = parse_openiti(raw)

    assert [block.type for block in doc.blocks] == [BlockType.PARAGRAPH]


def test_parse_openiti_recognizes_dedicated_quran_ornaments():
    raw = """######OpenITI#
#META#Header#End#

# قال تعالى: ﴿اقرأ باسم ربك الذي خلق﴾
"""

    doc = parse_openiti(raw)

    assert [block.type for block in doc.blocks] == [BlockType.QURAN_CITATION]


def _verse_words(doc):
    words = []
    for block in doc.blocks:
        for field in ("text", "hemistich_a", "hemistich_b"):
            words.extend((getattr(block, field) or "").split())
    return words


def test_percent_verse_number_is_kept_out_of_the_second_hemistich():
    # Shamela-derived diwans (0466IbnSinanKhafaji.Diwan) number each verse
    # after a doubled separator. The upstream parser read "% % 3" as the
    # second hemistich and moved the real first hemistich into a paragraph.
    raw = """######OpenITI#
#META#Header#End#

# % وصفوا بياض يد الكليم لمعجز % فيه وكم لك من يد بيضاء % % 3
# % زفت إليك ولست من أكفائها % % كالشمس طالعة على حربائها % % ٤
"""

    doc = parse_openiti(raw)

    verses = [block for block in doc.blocks if block.type == BlockType.VERSE_PAIR]
    assert [(v.hemistich_a, v.hemistich_b, v.meta.get("verse_number")) for v in verses] == [
        ("وصفوا بياض يد الكليم لمعجز", "فيه وكم لك من يد بيضاء", "3"),
        ("زفت إليك ولست من أكفائها", "كالشمس طالعة على حربائها", "٤"),
    ]
    assert all(block.type != BlockType.PARAGRAPH for block in doc.blocks)


def test_percent_verse_continuation_lines_keep_every_hemistich_in_order():
    # 1280MullaCimranFarisi.Qasida: a verse line runs on with "~~" and holds
    # a second verse; a lone hemistich carries only a number.
    raw = """######OpenITI#
#META#Header#End#

# % % شكري وقصر عنك جهد ثنائي % % 2
# % لرجاء نفع أو لدفع بلية % الله ينفعني ويدفع ما بي % % والابتداع وكل
~~أمر محدث % في الدين ينكره أولو الألباب %
# % كالشافعي ومالك وأبي حنيفة وابن حنبل التقي الأواب %
"""

    doc = parse_openiti(raw)

    shapes = [
        (block.type, block.text, block.hemistich_a, block.hemistich_b, block.meta.get("verse_number"))
        for block in doc.blocks
        if block.type in (BlockType.VERSE_PAIR, BlockType.VERSE_LINE)
    ]
    assert shapes == [
        (BlockType.VERSE_LINE, "شكري وقصر عنك جهد ثنائي", "", "", "2"),
        (BlockType.VERSE_PAIR, "", "لرجاء نفع أو لدفع بلية", "الله ينفعني ويدفع ما بي", None),
        (BlockType.VERSE_PAIR, "", "والابتداع وكل أمر محدث", "في الدين ينكره أولو الألباب", None),
        (BlockType.VERSE_LINE, "كالشافعي ومالك وأبي حنيفة وابن حنبل التقي الأواب", "", "", None),
    ]
    source_words = "شكري وقصر عنك جهد ثنائي لرجاء نفع أو لدفع بلية الله ينفعني ويدفع ما بي والابتداع وكل أمر محدث في الدين ينكره أولو الألباب كالشافعي ومالك وأبي حنيفة وابن حنبل التقي الأواب".split()
    assert _verse_words(doc) == source_words


def test_percent_verse_keeps_page_markers_and_trailing_labels():
    raw = """######OpenITI#
#META#Header#End#

# % ورأوا وقد طلع السماء محمد % عجبا وقدرك فوق كل سماء % % PageV01P001
~~البحر : كامل تام 1
# % زفت إليك ولست من أكفائها % % كالشمس طالعة على حربائها % % 2
"""

    doc = parse_openiti(raw)

    kinds = [(block.type, block.text or block.hemistich_a) for block in doc.blocks]
    assert (BlockType.VERSE_PAIR, "ورأوا وقد طلع السماء محمد") in kinds
    assert (BlockType.VERSE_LINE, "البحر : كامل تام 1") in kinds
    assert any(block.type == BlockType.PAGE_REF and block.meta == {"vol": 1, "page": 1} for block in doc.blocks)
    for block in doc.blocks:
        if block.type == BlockType.VERSE_PAIR:
            assert not block.hemistich_b.strip().isdigit()
