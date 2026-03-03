"""versed CLI — local PDF-to-Markdown tooling for Arabic and bilingual PDFs."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import is_dataclass
from enum import Enum
from typing import Any, Optional


def _json_default(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return value.__dict__
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _load_pymupdf():
    try:
        import pymupdf
    except ImportError:
        print(
            "Error: PDF commands require pymupdf. Install with: pip install 'versed-pdf[pdf]'",
            file=sys.stderr,
        )
        return None
    return pymupdf


def cmd_repair_text(args: argparse.Namespace) -> int:
    """Repair a raw text string without opening a PDF."""
    from versed.repair import repair_text

    print(repair_text(args.text))
    return 0


def cmd_repair(args: argparse.Namespace) -> int:
    """Extract text from a PDF and apply repair-only transforms."""
    pymupdf = _load_pymupdf()
    if pymupdf is None:
        return 1

    from versed.repair import extract_repairable_font_spans, repair_words_with_font_info

    document = pymupdf.open(args.input)
    page_texts = []
    json_rows = []

    for page_index in range(len(document)):
        page = document[page_index]
        words_raw = page.get_text("words")
        font_spans = extract_repairable_font_spans(page)
        repaired_words = repair_words_with_font_info(words_raw, font_spans)
        page_text = " ".join(word[4] for word in repaired_words if len(word) > 4)
        page_texts.append(page_text)
        json_rows.append(
            {
                "page": page_index + 1,
                "text": page_text,
                "original": " ".join(word[4] for word in words_raw if len(word) > 4),
                "font_spans_found": len(font_spans),
                "words_total": len(words_raw),
            }
        )

    document.close()

    if args.format == "json":
        payload = json.dumps(json_rows, ensure_ascii=False, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(payload)
        else:
            print(payload)
        return 0

    text_output = "\n\n".join(
        page_texts if len(page_texts) == 1 else [f"--- Page {index + 1} ---\n{text}" for index, text in enumerate(page_texts)]
    )
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text_output)
    else:
        print(text_output)
    return 0


def cmd_detect(args: argparse.Namespace) -> int:
    """Detect mojibake in a PDF."""
    from versed.detect import detect_mojibake_in_pdf

    try:
        report = detect_mojibake_in_pdf(args.input, page_number=args.page)
    except ImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, default=_json_default))
        return 0

    if report.has_mojibake:
        print(
            f"Mojibake detected: {report.mojibake_count} characters "
            f"({report.mojibake_rate:.2%} of {report.total_chars} total)"
        )
        for char, count in report.mojibake_chars.items():
            print(f"  {char!r}: {count} occurrences")
        if report.sample_contexts:
            print("\nSample contexts:")
            for context in report.sample_contexts:
                print(f"  {context}")
        return 0

    print(f"No mojibake detected ({report.total_chars} characters scanned)")
    return 0


def cmd_classify(args: argparse.Namespace) -> int:
    """Classify every page and print the recommended backend."""
    pymupdf = _load_pymupdf()
    if pymupdf is None:
        return 1

    from versed.classify import classify_and_select

    document = pymupdf.open(args.input)
    rows = []
    for page_index in range(len(document)):
        page_type, backend = classify_and_select(args.input, page_index + 1)
        rows.append(
            {
                "page_number": page_index + 1,
                "page_type": page_type.value,
                "backend": backend.ocr_backend,
                "force_ocr": backend.force_ocr,
                "confidence_note": backend.confidence_note,
                "fallback": backend.fallback,
            }
        )
    document.close()

    if args.format == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=_json_default))
        return 0

    for row in rows:
        suffix = " (force OCR)" if row["force_ocr"] else ""
        print(
            f"Page {row['page_number']}: {row['page_type']} -> "
            f"{row['backend']}{suffix}"
        )
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    """Run the full local extract -> classify -> markdown pipeline."""
    from versed.extract import extract_document

    try:
        result = extract_document(
            args.input,
            title=args.title or "",
            allow_ocr=args.allow_ocr,
            output_format=args.format,
        )
    except ImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    unsupported_pages = result.stats.get("unsupported_pages", [])
    exit_code = 2 if unsupported_pages and args.fail_on_unsupported_page else 0

    if args.format == "json":
        payload = json.dumps(result, ensure_ascii=False, indent=2, default=_json_default)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(payload)
        else:
            print(payload)
    else:
        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(result.markdown)
        else:
            print(result.markdown)

    if unsupported_pages:
        print(
            "Unsupported pages require OCR: "
            + ", ".join(str(page_number) for page_number in unsupported_pages),
            file=sys.stderr,
        )

    return exit_code


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="versed",
        description="Semantic PDF-to-Markdown engine for Arabic and bilingual texts",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 1.1.0")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    repair_text_parser = subparsers.add_parser("repair-text", help="Repair a raw text string")
    repair_text_parser.add_argument("text", help="Text to repair")
    repair_text_parser.set_defaults(func=cmd_repair_text)

    repair_parser = subparsers.add_parser("repair", help="Extract and repair text from a PDF")
    repair_parser.add_argument("input", help="Path to the input PDF")
    repair_parser.add_argument("-o", "--output", help="Optional output file path")
    repair_parser.add_argument("--format", choices=["text", "json"], default="text")
    repair_parser.set_defaults(func=cmd_repair)

    detect_parser = subparsers.add_parser("detect", help="Detect mojibake in a PDF")
    detect_parser.add_argument("input", help="Path to the input PDF")
    detect_parser.add_argument("--page", type=int, help="Optional 1-indexed page number")
    detect_parser.add_argument("--format", choices=["text", "json"], default="text")
    detect_parser.set_defaults(func=cmd_detect)

    classify_parser = subparsers.add_parser("classify", help="Classify pages and recommend backends")
    classify_parser.add_argument("input", help="Path to the input PDF")
    classify_parser.add_argument("--format", choices=["text", "json"], default="text")
    classify_parser.set_defaults(func=cmd_classify)

    extract_parser = subparsers.add_parser("extract", help="Run the full local extraction pipeline")
    extract_parser.add_argument("input", help="Path to the input PDF")
    extract_parser.add_argument("-o", "--output", help="Optional output file path")
    extract_parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    extract_parser.add_argument("--title", help="Optional document title")
    extract_parser.add_argument("--allow-ocr", action="store_true", help="Allow local OCR for scanned pages")
    extract_parser.add_argument(
        "--fail-on-unsupported-page",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Return a non-zero exit code when pages need OCR but OCR is unavailable",
    )
    extract_parser.set_defaults(func=cmd_extract)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
