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
        BlockType.EDITORIAL_SECTION,
    ]

    assert doc.blocks[1].text == "حدثنا فلان قال النبي صلى الله عليه وسلم"

    verse = doc.blocks[2]
    assert verse.hemistich_a == "شعر"
    assert verse.hemistich_b == "موزون"

    # mARkdown scheme "Editorial section": ### |EDITOR| (was a heading that
    # printed "EDITOR|" plus a duplicate apparatus note).
    editorial = doc.blocks[3]
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


# ---------------------------------------------------------------------------
# Conformance with the OpenITI mARkdown scheme
# (https://github.com/OpenITI/mARkdown_scheme, EditPad Pro 8 syntax file;
# prose docs at https://maximromanov.github.io/mARkdown/). Each case names
# the scheme category its pattern comes from.
# ---------------------------------------------------------------------------

def _printed_words(doc):
    return [
        word
        for block in doc.blocks
        for field in ("text", "hemistich_a", "hemistich_b", "isnad_text", "matn_text", "hukm_text")
        for word in (getattr(block, field) or "").split()
    ]


def _parse_body(body):
    return parse_openiti("######OpenITI#\n#META#Header#End#\n\n" + body)


def test_scheme_inline_tags_are_stripped_and_their_words_kept():
    doc = _parse_body(
        # "Major Units: Men Bio" category: @QURS\d+A\d+_(BEG|END)
        "# قال @QURS002A255_BEG الله لا إله إلا هو @QURS002A255_END ثم مضى\n"
        # "Auto Tagged Named Entities": @(TOP|SOC|PER|BOK|SOURCE)\d\d
        "# ودخل @TOP02 مدينة السلام ولقي @PER03 أبا بكر محمد وقرأ @BOK11 كتابا عن @SOURCE01 سفيان @SOC11 القرشي\n"
        # Manually disambiguated entities: @T, @S, @B, @P, @SRC
        "# رأى @T12 مكة ولقي @P21 ابن عباس @S11 القرشي وقرأ @B12 كتاب سيبويه عن @SRC11 مالك\n"
        # "Dividing tags": @Y[ABD]\d+
        "# ولد سنة @YB45 خمس ومات سنة @YD123 ثلاث وعشرين ومائة @YA78 عن ثمانين\n"
        # Text reuse, passage ids and REF magic values
        "# نص @SHAMV01P012A_BEG مكرر @SHAMV01P012A_END REF0123456789 JKS_SHAMV01P012A هنا SHAMV01P013B\n"
        # Open tagging pattern: @[A-Z]{3}@[A-Z]{3,}@[A-Za-z_0-9,]+@(-@true@|true)
        "# في @TOP@TOP@baghdad_1@-@true@ بغداد\n"
    )
    words = _printed_words(doc)
    assert not [word for word in words if "@" in word or word.startswith("REF")]
    assert words == (
        "قال الله لا إله إلا هو ثم مضى "
        "ودخل مدينة السلام ولقي أبا بكر محمد وقرأ كتابا عن سفيان القرشي "
        "رأى مكة ولقي ابن عباس القرشي وقرأ كتاب سيبويه عن مالك "
        "ولد سنة خمس ومات سنة ثلاث وعشرين ومائة عن ثمانين "
        "نص مكرر هنا "
        "في بغداد"
    ).split()


def test_scheme_ignore_elements_and_annotations_are_not_printed():
    doc = _parse_body(
        # "Ignore Elements": ~!~[^~]+~!!~, NoteV..P\d\d\dN\d\d, Page(Wrong|Start)V..P\d\d\d
        "# كلام ~!~ حاشية يجب تجاهلها ~!!~ متصل NoteV01P012N03 بعده PageWrongV01P013 تم PageStartV01P001\n"
        # "Paragraphs" / "Dividing tags": StartingPage, PageBeg, PageEnd anchors
        "# أول StartingPageV01P001 ثان PageBegV01P002 ثالث PageEndV01P002 رابع\n"
        # "Annotations": ^#COMMENT# .*, ^#ENTITIES# .*; "Morphological": ^#@COMMENT
        "#COMMENT# هذا تعليق لا يطبع\n"
        "#ENTITIES# كيانات\n"
        "#@COMMENT تعليق آخر\n"
    )
    assert _printed_words(doc) == "كلام متصل بعده تم أول ثان ثالث رابع".split()


def test_scheme_editorial_section_is_one_editorial_block():
    # "Editorial section": ^### \|(EDITOR|SKIP)\|
    doc = _parse_body("### |EDITOR| تنبيه المحقق\n# نص التنبيه\n### |SKIP| فهرس\n")

    assert [(block.type, block.text) for block in doc.blocks] == [
        (BlockType.EDITORIAL_SECTION, "تنبيه المحقق"),
        (BlockType.PARAGRAPH, "نص التنبيه"),
        (BlockType.EDITORIAL_SECTION, "فهرس"),
    ]


def test_scheme_morphological_category_line():
    # "Morphological elements": ^#~:[\w/]+:
    doc = _parse_body("# قبل\n#~:fiqh:\n# بعد\n")

    assert [block.type for block in doc.blocks] == [
        BlockType.PARAGRAPH, BlockType.MORPHO_TAG, BlockType.PARAGRAPH,
    ]
    assert doc.blocks[1].meta == {"category": "fiqh"}


def test_scheme_hemistich_divider_and_continuation_line():
    # "In-text Elements": %~% and ^~~
    doc = _parse_body("# أول البيت %~% ثاني البيت\n# سطر طويل\n~~يكمل هنا\n")

    assert (doc.blocks[0].type, doc.blocks[0].hemistich_a, doc.blocks[0].hemistich_b) == (
        BlockType.VERSE_PAIR, "أول البيت", "ثاني البيت",
    )
    assert (doc.blocks[1].type, doc.blocks[1].text) == (BlockType.PARAGRAPH, "سطر طويل يكمل هنا")


def test_scheme_repeated_biography_tag_is_not_printed():
    # "Major Units: Biography repeated": ^### $BIO_REP$
    doc = _parse_body("### $BIO_REP$ أحمد بن حنبل\n")

    assert [(block.type, block.text) for block in doc.blocks] == [
        (BlockType.BIO_MAN, "أحمد بن حنبل"),
    ]


def test_hemistich_divider_without_words_on_both_sides_is_not_a_couplet():
    # 0671AbuCabdAllahQurtubi.Asna: OCR margin noise carries %~% ("قدهة 1 %~% 11").
    # A couplet needs words on both sides; otherwise keep the line as one
    # verse line, every character preserved.
    doc = _parse_body(
        "# قدهة 1 %~% 11\n"
        "# 4 %~% \n"
        "# وذلك في ذات الإله وإن يشا %~% يبارك على أوصال شلو ممزع\n"
    )

    shapes = [(block.type, block.text, block.hemistich_a, block.hemistich_b) for block in doc.blocks]
    assert shapes == [
        (BlockType.VERSE_LINE, "قدهة 1 11", "", ""),
        (BlockType.VERSE_LINE, "4", "", ""),
        (BlockType.VERSE_PAIR, "", "وذلك في ذات الإله وإن يشا", "يبارك على أوصال شلو ممزع"),
    ]


def test_text_after_a_line_initial_page_marker_is_kept():
    # 0711IbnIbrahimCimadDinWasiti.Tadhkira: "PageV01P023 وتسديدهم ..." at the
    # start of a continuation line lost every word after the marker.
    doc = _parse_body(
        "# وأدام توفيق السادة المبدئ بذكرهم\n"
        "PageV01P023 وتسديدهم، وأجزل لهم حظهم، ومزيدهم\n"
        "# السلام عليكم\n"
    )

    assert _printed_words(doc) == (
        "وأدام توفيق السادة المبدئ بذكرهم وتسديدهم، وأجزل لهم حظهم، ومزيدهم السلام عليكم"
    ).split()
    assert any(block.type == BlockType.PAGE_REF and block.meta == {"vol": 1, "page": 23} for block in doc.blocks)
