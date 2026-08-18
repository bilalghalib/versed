from pathlib import Path

from versed.alignment import align_translation, verify_bundle

OPENITI_SAMPLE = """######OpenITI#
#META#Header#End#

### | السن
# بلغ الفتى ٢١ عاما ثم خرج.
"""


def test_local_openiti_and_english_text_build_a_portable_bundle(tmp_path: Path):
    arabic = tmp_path / "0123Author.Book.txt"
    english = tmp_path / "translation.txt"
    output = tmp_path / "aligned.zip"
    arabic.write_text(OPENITI_SAMPLE, encoding="utf-8")
    english.write_text("At the age of 21, the youth left.", encoding="utf-8")

    result = align_translation(arabic, english, output=output)

    assert result.arabic.work_id == "0123Author.Book"
    assert result.recommended_links[0].resolution == "sentence"
    assert verify_bundle(output)["work_id"] == "0123Author.Book"
