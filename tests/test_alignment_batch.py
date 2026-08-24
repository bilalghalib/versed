import json
from pathlib import Path

import pytest

from versed.alignment import align_manifest, verify_bundle


OPENITI_SAMPLE = """######OpenITI#
#META#Header#End#

### | السن
# بلغ الفتى ٢١ عاما ثم خرج.
"""


def test_batch_aligns_multi_file_edition_and_resumes_verified_bundle(tmp_path: Path):
    arabic = tmp_path / "0123Author.Book.txt"
    first = tmp_path / "volume-1.txt"
    second = tmp_path / "volume-2.txt"
    manifest = tmp_path / "batch.json"
    output = tmp_path / "output"
    arabic.write_text(OPENITI_SAMPLE, encoding="utf-8")
    first.write_text("At the age of 21, the youth left.", encoding="utf-8")
    second.write_text("He continued on his journey.", encoding="utf-8")
    manifest.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "id": "demo-edition",
                        "openiti": arabic.name,
                        "translations": [first.name, second.name],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    first_report = align_manifest(manifest, output)
    bundle_path = output / "demo-edition.alignment.zip"
    bundle = verify_bundle(bundle_path)
    second_report = align_manifest(manifest, output)

    assert first_report["summary"] == {
        "total": 1,
        "completed": 1,
        "skipped_verified": 0,
        "errors": 0,
    }
    assert bundle["sources"]["en"]["metadata"]["adapter"] == "plain_text_multi_file"
    assert second_report["summary"]["skipped_verified"] == 1


def test_batch_rejects_item_ids_that_can_escape_output_directory(tmp_path: Path):
    manifest = tmp_path / "batch.jsonl"
    manifest.write_text(
        json.dumps({"id": "../escape", "openiti": "book", "translation": "english.txt"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsafe"):
        align_manifest(manifest, tmp_path / "output")
