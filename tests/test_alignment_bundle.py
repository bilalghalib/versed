import zipfile
from pathlib import Path

import pytest

from versed.alignment.bundle import verify_bundle, write_bundle
from versed.alignment.engine import align_documents
from versed.alignment.models import (
    AlignmentDocument,
    AlignmentParagraph,
    AlignmentStructure,
    sha256_text,
)


def _result():
    def document(language, text):
        paragraph = AlignmentParagraph.create(
            paragraph_id=f"{language}:u0000:p0000", sequence=0, text=text
        )
        structure = AlignmentStructure(f"{language}:u0000", 0, "", (paragraph,))
        return AlignmentDocument("demo", language, f"{language}.txt", sha256_text(text), (structure,))

    return align_documents(document("ar", "بلغ ٢١ عاما."), document("en", "He reached 21 years."))


def test_bundle_is_deterministic_and_verifiable(tmp_path: Path):
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    first_manifest = write_bundle(_result(), first)
    second_manifest = write_bundle(_result(), second)

    assert first.read_bytes() == second.read_bytes()
    assert first_manifest["bundle_id"] == second_manifest["bundle_id"]
    assert verify_bundle(first)["counts"]["recommended_links"] == 1


def test_bundle_verifier_rejects_undeclared_members(tmp_path: Path):
    bundle = tmp_path / "alignment.zip"
    write_bundle(_result(), bundle)
    with zipfile.ZipFile(bundle, "a") as archive:
        archive.writestr("extra.txt", "not declared")

    with pytest.raises(ValueError, match="members do not match"):
        verify_bundle(bundle)
