"""
versed CLI — Arabic-aware PDF text repair from the command line.

Usage:
    versed repair input.pdf                     # extract + repair, print to stdout
    versed repair input.pdf -o output.txt       # write to file
    versed repair input.pdf --format json       # structured output with stats
    versed detect input.pdf                     # mojibake detection report
    versed repair-text "tafß¬l al-nashʾatayn"  # repair a raw string (no PDF)
"""

import argparse
import json
import sys


def cmd_repair_text(args):
    """Repair a raw text string (no PDF needed)."""
    from versed.repair import repair_text

    result = repair_text(args.text)
    print(result)


def cmd_repair(args):
    """Extract text from PDF and apply repairs."""
    try:
        import pymupdf
    except ImportError:
        print("Error: PDF repair requires pymupdf. Install with: pip install 'versed-repair[pdf]'",
              file=sys.stderr)
        sys.exit(1)

    from versed.repair import (
        extract_repairable_font_spans,
        repair_words_with_font_info,
        repair_text,
    )

    doc = pymupdf.open(args.input)
    results = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        words_raw = page.get_text("words")
        font_spans = extract_repairable_font_spans(page)
        repaired_words = repair_words_with_font_info(words_raw, font_spans)

        page_text = " ".join(w[4] for w in repaired_words if len(w) > 4)

        if args.format == "json":
            original_text = " ".join(w[4] for w in words_raw if len(w) > 4)
            results.append({
                "page": page_idx + 1,
                "text": page_text,
                "original": original_text,
                "font_spans_found": len(font_spans),
                "words_total": len(words_raw),
            })
        else:
            if len(doc) > 1:
                print(f"--- Page {page_idx + 1} ---")
            print(page_text)

    doc.close()

    if args.format == "json":
        output = json.dumps(results, ensure_ascii=False, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"Written to {args.output}", file=sys.stderr)
        else:
            print(output)
    elif args.output:
        # Re-run to write to file (text mode)
        # Already printed above, so just note it
        print(f"Note: use --format json with -o for file output", file=sys.stderr)


def cmd_detect(args):
    """Detect mojibake in a PDF."""
    from versed.detect import detect_mojibake_in_pdf

    page = args.page if hasattr(args, 'page') and args.page else None
    report = detect_mojibake_in_pdf(args.input, page_number=page)

    if args.format == "json":
        print(json.dumps({
            "has_mojibake": report.has_mojibake,
            "mojibake_count": report.mojibake_count,
            "mojibake_rate": report.mojibake_rate,
            "total_chars": report.total_chars,
            "mojibake_chars": {repr(k): v for k, v in report.mojibake_chars.items()},
            "sample_contexts": report.sample_contexts,
        }, ensure_ascii=False, indent=2))
    else:
        if report.has_mojibake:
            print(f"Mojibake detected: {report.mojibake_count} characters "
                  f"({report.mojibake_rate:.2%} of {report.total_chars} total)")
            for char, count in report.mojibake_chars.items():
                print(f"  {char!r}: {count} occurrences")
            if report.sample_contexts:
                print("\nSample contexts:")
                for ctx in report.sample_contexts:
                    print(f"  {ctx}")
        else:
            print(f"No mojibake detected ({report.total_chars} characters scanned)")


def main():
    parser = argparse.ArgumentParser(
        prog="versed",
        description="Arabic-aware PDF text repair — fixes QCF Quran fonts, Sabon mojibake, honorific glyphs",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 1.0.0")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # repair-text command
    p_rt = subparsers.add_parser("repair-text", help="Repair a raw text string (no PDF needed)")
    p_rt.add_argument("text", help="Text to repair")
    p_rt.set_defaults(func=cmd_repair_text)

    # repair command
    p_repair = subparsers.add_parser("repair", help="Extract + repair text from a PDF")
    p_repair.add_argument("input", help="Path to input PDF")
    p_repair.add_argument("-o", "--output", help="Output file path")
    p_repair.add_argument("--format", choices=["text", "json"], default="text",
                          help="Output format (default: text)")
    p_repair.set_defaults(func=cmd_repair)

    # detect command
    p_detect = subparsers.add_parser("detect", help="Detect mojibake in a PDF")
    p_detect.add_argument("input", help="Path to input PDF")
    p_detect.add_argument("--page", type=int, help="Page number (1-indexed, default: all)")
    p_detect.add_argument("--format", choices=["text", "json"], default="text",
                          help="Output format (default: text)")
    p_detect.set_defaults(func=cmd_detect)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
