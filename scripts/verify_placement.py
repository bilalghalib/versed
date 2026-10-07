#!/usr/bin/env python
"""Verify alignment-link placement with LaBSE and write verdict sidecars.

For every fine (sentence/paragraph resolution, unflagged, confident) link in a
bundle's ``alignments/recommended.jsonl``, embed the English text and the
Arabic paragraph it targets plus that paragraph's neighbours. The link is
``placed`` when its own paragraph beats every neighbour (within EPSILON) and
clears an absolute floor. This catches the aligner's dominant failure mode:
English attached one or two paragraphs from where it belongs.

LaBSE is used deliberately: it is trained on translation-pair detection, and
it is independent of the MiniLM model the aligner itself scored with, so the
check is not circular.

Calibration (Hamadhani, 12 hand-read links): 11/12 verdicts correct; the
aligner's own MiniLM approved all 5 known-wrong placements.

Usage:
    python scripts/verify_placement.py BUNDLE.zip [BUNDLE2.zip ...]

Writes ``<bundle>.placement.jsonl`` next to each bundle: one row per fine
link, keyed by ``link_index`` (the link's position in recommended.jsonl).
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

MODEL_NAME = "sentence-transformers/LaBSE"
WINDOW = 2       # neighbour paragraphs on each side to compete against
EPSILON = 0.02   # own paragraph may trail the best neighbour by this much
FLOOR = 0.25     # absolute similarity floor (verse translations run low)
CONFIDENCE_MIN = 0.5


def _paragraph_id(arabic_id: str) -> str:
    parts = arabic_id.split(":")
    return ":".join(parts[:3]) if len(parts) >= 4 else arabic_id


def _load_texts(archive: zipfile.ZipFile, names: tuple[str, ...]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for name in names:
        try:
            raw = archive.read(name).decode("utf-8")
        except KeyError:
            continue
        for line in raw.splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("text") and "id" in row:
                texts[str(row["id"])] = str(row["text"])
            for paragraph in row.get("paragraphs") or []:
                if paragraph.get("text"):
                    texts[str(paragraph["id"])] = str(paragraph["text"])
    return texts


def verify_bundle(
    bundle_path: Path,
    model,
    *,
    suffix: str = "placement",
    model_name: str = MODEL_NAME,
) -> dict:
    archive = zipfile.ZipFile(bundle_path)
    structures = [
        json.loads(line)
        for line in archive.read("documents/ar.structures.jsonl").decode().splitlines()
        if line.strip()
    ]
    paragraphs = [p for s in structures for p in s["paragraphs"]]
    position_of = {p["id"]: i for i, p in enumerate(paragraphs)}
    english = _load_texts(
        archive, ("documents/en.sentences.jsonl", "documents/en.structures.jsonl")
    )
    links = [
        json.loads(line)
        for line in archive.read("alignments/recommended.jsonl").decode().splitlines()
        if line.strip()
    ]

    fine: list[tuple[int, dict, str, list[int]]] = []
    needed_positions: set[int] = set()
    for link_index, link in enumerate(links):
        if link.get("resolution") not in ("sentence", "paragraph"):
            continue
        if float(link.get("score_confidence") or 0.0) < CONFIDENCE_MIN:
            continue
        if link.get("flags"):
            continue
        text = " ".join(
            english.get(str(key), "") for key in link.get("english_ids") or []
        ).strip()
        targets = sorted(
            {
                position_of[_paragraph_id(str(a))]
                for a in link.get("arabic_ids") or []
                if _paragraph_id(str(a)) in position_of
            }
        )
        if not text or not targets:
            continue
        fine.append((link_index, link, text, targets))
        for target in targets:
            for offset in range(-WINDOW, WINDOW + 1):
                if 0 <= target + offset < len(paragraphs):
                    needed_positions.add(target + offset)

    result = {"bundle": bundle_path.name, "fine_links": len(fine), "placed": 0}
    rows = []
    if fine:
        ordered = sorted(needed_positions)
        ar_matrix = model.encode(
            [paragraphs[i]["text"] for i in ordered],
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=32,
        )
        ar_vec = {pos: ar_matrix[i] for i, pos in enumerate(ordered)}
        en_matrix = model.encode(
            [text for _, _, text, _ in fine],
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=32,
        )
        for (link_index, link, _text, targets), en in zip(fine, en_matrix):
            own = max(float(ar_vec[t] @ en) for t in targets)
            neighbour_sims = [
                float(ar_vec[j] @ en)
                for t in targets
                for d in range(1, WINDOW + 1)
                for j in (t - d, t + d)
                if j in ar_vec and j not in targets
            ]
            best_neighbour = max(neighbour_sims) if neighbour_sims else -1.0
            placed = own >= FLOOR and own >= best_neighbour - EPSILON
            rows.append(
                {
                    "link_index": link_index,
                    "own_sim": round(own, 4),
                    "best_neighbour_sim": round(best_neighbour, 4),
                    "margin": round(own - best_neighbour, 4),
                    "placed": placed,
                }
            )
            result["placed"] += int(placed)

    sidecar = bundle_path.with_suffix("").with_suffix("")  # strip .alignment.zip
    out_path = bundle_path.parent / f"{sidecar.name}.{suffix}.jsonl"
    with out_path.open("w") as handle:
        handle.write(
            json.dumps(
                {
                    "schema": "versed.alignment.placement-verdicts.v1",
                    "model": model_name,
                    "window": WINDOW,
                    "epsilon": EPSILON,
                    "floor": FLOOR,
                }
            )
            + "\n"
        )
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    result["sidecar"] = str(out_path)
    return result


def main(argv: list[str]) -> int:
    import argparse

    from sentence_transformers import SentenceTransformer

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundles", nargs="+")
    parser.add_argument(
        "--model",
        default=MODEL_NAME,
        help=(
            "embedding model used to judge placement. Use a model the aligner "
            "did NOT score with, so the check stays independent."
        ),
    )
    parser.add_argument(
        "--suffix",
        default="placement",
        help="sidecar suffix, e.g. --suffix placement-qwen",
    )
    args = parser.parse_args(argv)

    model = SentenceTransformer(args.model)
    for bundle in args.bundles:
        result = verify_bundle(
            Path(bundle), model, suffix=args.suffix, model_name=args.model
        )
        result["model"] = args.model
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
