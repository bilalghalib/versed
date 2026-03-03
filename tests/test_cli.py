"""Tests for the public CLI entrypoint."""

from argparse import Namespace

from versed.cli import cmd_extract, main
from versed.extract import ExtractResult
from versed.types import Document


class TestCLI:
    def test_main_without_command_returns_error(self, capsys):
        assert main([]) == 1
        captured = capsys.readouterr()
        assert "usage:" in captured.out.lower()

    def test_cmd_extract_returns_nonzero_for_unsupported_pages(self, monkeypatch, capsys):
        fake_result = ExtractResult(
            markdown="",
            plain_text="",
            document=Document(),
            pages=[{"page_number": 1, "warnings": ["OCR required for this page."]}],
            stats={"unsupported_pages": [1]},
        )
        monkeypatch.setattr("versed.extract.extract_document", lambda *args, **kwargs: fake_result)

        exit_code = cmd_extract(
            Namespace(
                input="dummy.pdf",
                title=None,
                allow_ocr=False,
                format="markdown",
                output=None,
                fail_on_unsupported_page=True,
            )
        )

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "Unsupported pages require OCR" in captured.err

