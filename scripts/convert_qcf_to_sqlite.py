#!/usr/bin/env python3
"""Convert qcf_mapping.min.json to qcf_mapping.db (SQLite).

Run from the versed repo root:
    python scripts/convert_qcf_to_sqlite.py
"""

import json
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "src" / "versed" / "_data"
JSON_PATH = DATA_DIR / "qcf_mapping.min.json"
DB_PATH = DATA_DIR / "qcf_mapping.db"


def convert():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    # Schema
    c.execute("""
        CREATE TABLE metadata (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE glyphs (
            page             INTEGER NOT NULL,
            glyph            TEXT    NOT NULL,
            arabic           TEXT    NOT NULL,
            verse_key        TEXT,
            word_position    INTEGER,
            transliteration  TEXT,
            PRIMARY KEY (page, glyph)
        )
    """)
    c.execute("""
        CREATE TABLE verses (
            verse_key   TEXT PRIMARY KEY,
            arabic_text TEXT NOT NULL
        )
    """)

    # Metadata
    for key in ("version", "source", "created_at"):
        val = data.get(key)
        if val is not None:
            c.execute("INSERT INTO metadata VALUES (?, ?)", (key, str(val)))

    # Glyphs
    glyph_count = 0
    for page_str, glyphs in data.get("pages", {}).items():
        page_num = int(page_str)
        for glyph_char, info in glyphs.items():
            if isinstance(info, str):
                arabic = info
                verse_key = None
                word_pos = None
                translit = None
            else:
                arabic = info.get("arabic", "")
                verse_key = info.get("verse_key")
                word_pos = info.get("word_position")
                translit = info.get("transliteration")
            c.execute(
                "INSERT INTO glyphs VALUES (?, ?, ?, ?, ?, ?)",
                (page_num, glyph_char, arabic, verse_key, word_pos, translit),
            )
            glyph_count += 1

    # Verses
    verse_count = 0
    for verse_key, arabic_text in data.get("verses", {}).items():
        c.execute("INSERT INTO verses VALUES (?, ?)", (verse_key, arabic_text))
        verse_count += 1

    # Indexes for fast lookup
    c.execute("CREATE INDEX idx_glyphs_page ON glyphs(page)")
    c.execute("CREATE INDEX idx_verses_key ON verses(verse_key)")

    conn.commit()
    conn.close()

    json_size = JSON_PATH.stat().st_size / (1024 * 1024)
    db_size = DB_PATH.stat().st_size / (1024 * 1024)
    print(f"Converted: {glyph_count} glyphs, {verse_count} verses across 604 pages")
    print(f"JSON: {json_size:.1f} MB -> SQLite: {db_size:.1f} MB ({db_size/json_size:.0%})")


if __name__ == "__main__":
    convert()
