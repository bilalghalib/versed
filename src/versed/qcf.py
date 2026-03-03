"""
QCF (Quran Complex Font) Decoder.

Decodes Private Use Area (PUA) glyphs from King Fahd Complex fonts
back to standard Arabic Unicode text.

QCF fonts use page-specific encodings (QCF_P001 through QCF_P604)
where each glyph represents a word or word-group from that mushaf page.

Usage:
    from versed.qcf import QCFDecoder, detect_qcf_regions

    # Initialize decoder (auto-loads mapping from data directory)
    decoder = QCFDecoder()

    # Decode QCF glyphs from PDF
    regions = detect_qcf_regions(pdf_path, page_number=1)
    for region in regions:
        arabic, words = decoder.decode_text(region['text'], region['font'])
        for word in words:
            print(f"{word.glyph} -> {word.arabic} (verse: {word.verse_key})")
"""

import json
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass


@dataclass
class QCFWord:
    """A decoded QCF word."""
    glyph: str           # Original PUA glyph
    arabic: str          # Decoded Arabic text
    page: int            # Mushaf page number (1-604)
    position: int        # Position in text span
    verse_key: Optional[str] = None     # e.g., "45:23"
    word_position: Optional[int] = None # Position within verse
    transliteration: Optional[str] = None


@dataclass
class QCFVerse:
    """A decoded QCF verse."""
    glyphs: List[str]
    arabic_text: str
    verse_key: Optional[str]  # e.g., "45:23"
    font_name: str
    page: int


# PUA ranges used by QCF fonts (includes Arabic Presentation Forms)
QCF_PUA_RANGES = [
    (0xFB50, 0xFDFF),  # Arabic Presentation Forms-A
    (0xFE70, 0xFEFF),  # Arabic Presentation Forms-B
    (0xE000, 0xF8FF),  # Private Use Area
]

# Default data directory (relative to this file)
_DATA_DIR = Path(__file__).parent / "_data"
_DB_PATH = _DATA_DIR / "qcf_mapping.db"
_JSON_PATH = _DATA_DIR / "qcf_mapping.min.json"  # Legacy fallback


def is_qcf_glyph(char: str) -> bool:
    """Check if a character is a QCF PUA glyph."""
    if not char:
        return False
    if len(char) != 1:
        return all(is_qcf_glyph(single_char) for single_char in char)
    code = ord(char)
    for start, end in QCF_PUA_RANGES:
        if start <= code <= end:
            return True
    return False


def is_qcf_text(text: str) -> bool:
    """Check if text contains QCF glyphs."""
    return any(is_qcf_glyph(c) for c in text)


def extract_qcf_page_number(font_name: str) -> Optional[int]:
    """Extract mushaf page number from QCF font name.

    QCF fonts are named like: QCF_P363, QCF_P001, KFGQPC_P363, etc.
    """
    match = re.search(r'[_P](\d{1,3})(?:\D|$)', font_name)
    if match:
        return int(match.group(1))
    return None


class QCFDecoder:
    """
    Decoder for QCF (Quran Complex Font) glyphs.

    Uses mapping data to convert PUA glyphs back to standard Arabic.
    The mapping is organized by mushaf page for efficient lookup.

    Supports two backends:
    - SQLite (preferred): lazy per-page loading, low memory (~0 at init)
    - JSON (legacy fallback): loads all 604 pages into memory (~40 MB)
    """

    _instance: Optional['QCFDecoder'] = None

    def __init__(self, mapping_path: Optional[str] = None, auto_load: bool = True):
        """
        Initialize decoder.

        Args:
            mapping_path: Path to mapping file (.db or .json).
                         If None and auto_load=True, auto-detects from data dir.
            auto_load: If True and no mapping_path given, auto-load from data dir.
        """
        # page -> {glyph: {arabic, verse_key, word_position, transliteration}}
        self._mapping: Dict[int, Dict[str, Dict[str, Any]]] = {}
        self._verses: Dict[str, str] = {}  # verse_key -> full arabic text
        self._loaded = False
        self._db_conn: Optional[sqlite3.Connection] = None
        self._db_path: Optional[str] = None
        self._pages_cached: set = set()  # Track which pages are loaded

        if mapping_path:
            self._load_from_path(mapping_path)
        elif auto_load:
            self._auto_load_mapping()

    @classmethod
    def get_instance(cls) -> 'QCFDecoder':
        """Get singleton instance with auto-loaded mapping."""
        if cls._instance is None:
            cls._instance = cls(auto_load=True)
        return cls._instance

    def _auto_load_mapping(self):
        """Auto-load mapping, preferring SQLite over JSON."""
        if _DB_PATH.exists():
            self._load_sqlite(str(_DB_PATH))
        elif _JSON_PATH.exists():
            self._load_json(str(_JSON_PATH))

    def _load_from_path(self, path: str):
        """Load from either SQLite or JSON based on file extension."""
        if path.endswith('.db'):
            self._load_sqlite(path)
        else:
            self._load_json(path)

    def _load_sqlite(self, path: str):
        """Open SQLite connection (lazy — pages loaded on demand)."""
        try:
            self._db_conn = sqlite3.connect(path, check_same_thread=False)
            self._db_conn.row_factory = sqlite3.Row
            self._db_path = path
            self._loaded = True
        except Exception as e:
            print(f"Warning: Could not open QCF database {path}: {e}")

    def _load_json(self, path: str):
        """Load QCF mapping from JSON file (legacy)."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            raw_pages = data.get('pages', {})
            for page_str, glyphs in raw_pages.items():
                page_num = int(page_str)
                self._mapping[page_num] = {}
                for glyph, info in glyphs.items():
                    if isinstance(info, str):
                        self._mapping[page_num][glyph] = {"arabic": info}
                    else:
                        self._mapping[page_num][glyph] = info
                self._pages_cached.add(page_num)

            self._verses = data.get('verses', {})
            self._loaded = True

        except Exception as e:
            print(f"Warning: Could not load QCF mapping from {path}: {e}")

    def _ensure_page(self, page: int):
        """Lazy-load a page from SQLite if not cached."""
        if page in self._pages_cached:
            return
        if self._db_conn is None:
            return

        cursor = self._db_conn.execute(
            "SELECT glyph, arabic, verse_key, word_position, transliteration "
            "FROM glyphs WHERE page = ?",
            (page,),
        )
        page_map: Dict[str, Dict[str, Any]] = {}
        for row in cursor:
            info: Dict[str, Any] = {"arabic": row[1]}
            if row[2] is not None:
                info["verse_key"] = row[2]
            if row[3] is not None:
                info["word_position"] = row[3]
            if row[4] is not None:
                info["transliteration"] = row[4]
            page_map[row[0]] = info

        self._mapping[page] = page_map
        self._pages_cached.add(page)

    def _get_verse_from_db(self, verse_key: str) -> Optional[str]:
        """Fetch a single verse from SQLite."""
        if self._db_conn is None:
            return None
        cursor = self._db_conn.execute(
            "SELECT arabic_text FROM verses WHERE verse_key = ?",
            (verse_key,),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    @property
    def is_loaded(self) -> bool:
        """Check if mapping data is available."""
        return self._loaded

    def decode_glyph(self, glyph: str, page: int) -> Optional[Dict[str, Any]]:
        """
        Decode a single QCF glyph to word info.

        Returns dict with: arabic, verse_key, word_position, transliteration
        """
        self._ensure_page(page)
        page_map = self._mapping.get(page)
        if page_map:
            return page_map.get(glyph)
        return None

    def decode_text(self, text: str, font_name: str) -> Tuple[str, List[QCFWord]]:
        """
        Decode QCF text to Arabic.

        Args:
            text: Text containing QCF glyphs
            font_name: QCF font name (e.g., "QCF_P363")

        Returns:
            Tuple of (decoded_arabic_text, list of QCFWord details)
        """
        page = extract_qcf_page_number(font_name) or 0

        decoded_parts = []
        words = []

        for i, char in enumerate(text):
            if is_qcf_glyph(char):
                info = self.decode_glyph(char, page)
                if info:
                    arabic = info.get("arabic", char)
                    decoded_parts.append(arabic)
                    words.append(QCFWord(
                        glyph=char,
                        arabic=arabic,
                        page=page,
                        position=i,
                        verse_key=info.get("verse_key"),
                        word_position=info.get("word_position"),
                        transliteration=info.get("transliteration")
                    ))
                else:
                    # Unknown glyph - keep original
                    decoded_parts.append(char)
                    words.append(QCFWord(
                        glyph=char,
                        arabic=char,
                        page=page,
                        position=i
                    ))
            elif char.strip():
                decoded_parts.append(char)

        return ' '.join(decoded_parts), words

    def get_verse_text(self, verse_key: str) -> Optional[str]:
        """Get full Arabic text for a verse key."""
        result = self._verses.get(verse_key)
        if result is None:
            result = self._get_verse_from_db(verse_key)
            if result is not None:
                self._verses[verse_key] = result  # Cache
        return result

    def find_verse_key(self, arabic_text: str) -> Optional[str]:
        """
        Find verse key for decoded Arabic text.

        Looks up the text in the verse index to find its reference.
        """
        normalized = self._normalize_arabic(arabic_text)

        # Try in-memory cache first
        for verse_key, verse_text in self._verses.items():
            verse_normalized = self._normalize_arabic(verse_text)
            if normalized == verse_normalized:
                return verse_key
            if normalized in verse_normalized or verse_normalized in normalized:
                return verse_key

        # Fall back to SQLite scan if available
        if self._db_conn is not None:
            cursor = self._db_conn.execute("SELECT verse_key, arabic_text FROM verses")
            for row in cursor:
                vk, vt = row[0], row[1]
                if vk in self._verses:
                    continue  # Already checked
                verse_normalized = self._normalize_arabic(vt)
                if normalized == verse_normalized:
                    self._verses[vk] = vt
                    return vk
                if normalized in verse_normalized or verse_normalized in normalized:
                    self._verses[vk] = vt
                    return vk

        return None

    def _normalize_arabic(self, text: str) -> str:
        """Normalize Arabic text for matching."""
        import unicodedata
        # Remove combining marks (tashkeel/diacritics)
        normalized = ''.join(
            c for c in unicodedata.normalize('NFD', text)
            if unicodedata.category(c) != 'Mn'
        )
        # Normalize alef variants
        normalized = normalized.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا').replace('ٱ', 'ا')
        # Normalize other letters
        normalized = normalized.replace('ة', 'ه').replace('ى', 'ي')
        # Remove spaces and tatweel
        normalized = normalized.replace(' ', '').replace('\u0640', '')
        return normalized

    def get_stats(self) -> Dict[str, Any]:
        """Get mapping statistics."""
        if self._db_conn is not None:
            # Query totals from DB without loading everything
            page_count = self._db_conn.execute(
                "SELECT COUNT(DISTINCT page) FROM glyphs"
            ).fetchone()[0]
            glyph_count = self._db_conn.execute(
                "SELECT COUNT(*) FROM glyphs"
            ).fetchone()[0]
            verse_count = self._db_conn.execute(
                "SELECT COUNT(*) FROM verses"
            ).fetchone()[0]
            return {
                "loaded": self._loaded,
                "backend": "sqlite",
                "pages": page_count,
                "verses": verse_count,
                "glyphs": glyph_count,
                "pages_cached": len(self._pages_cached),
            }
        return {
            "loaded": self._loaded,
            "backend": "json",
            "pages": len(self._mapping),
            "verses": len(self._verses),
            "glyphs": sum(len(g) for g in self._mapping.values()),
        }


def detect_qcf_regions(pdf_path: str, page_number: int) -> List[Dict]:
    """
    Detect QCF font regions in a PDF page.

    Requires pymupdf: pip install pymupdf

    Returns list of regions with:
    - text: The QCF glyph text
    - font: Font name
    - bbox: Bounding box
    - page: Mushaf page number (from font name)
    """
    try:
        import pymupdf
    except ImportError:
        raise ImportError(
            "detect_qcf_regions requires pymupdf: pip install 'versed-pdf[pdf]'"
        )

    regions = []
    doc = pymupdf.open(pdf_path)
    page = doc[page_number - 1]

    text_dict = page.get_text("dict")

    for block in text_dict.get('blocks', []):
        if block.get('type') != 0:  # Skip non-text blocks
            continue

        for line in block.get('lines', []):
            for span in line.get('spans', []):
                text = span.get('text', '')
                font = span.get('font', '')

                # Check if this is QCF text
                if is_qcf_text(text) and ('QCF' in font.upper() or 'KFGQPC' in font.upper()):
                    mushaf_page = extract_qcf_page_number(font)
                    regions.append({
                        'text': text,
                        'font': font,
                        'bbox': span.get('bbox'),
                        'mushaf_page': mushaf_page,
                        'size': span.get('size'),
                    })

    doc.close()
    return regions


def build_qcf_mapping_from_quran_data(quran_csv_path: str, output_path: str):
    """
    Build QCF mapping file from Quran CSV data.

    The CSV should have columns:
    Surah Number, Surah Name, Ayah Number, Ayah Text (decoded), Ayah Text (encoded), Page
    """
    import csv

    pages: Dict[int, Dict[str, str]] = {}
    verses: Dict[str, str] = {}

    with open(quran_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            page = int(row.get('Page', 0))
            encoded = row.get('Ayah Text (encoded)', '')
            decoded = row.get('Ayah Text (decoded)', '')
            surah = row.get('Surah Number', '')
            ayah = row.get('Ayah Number', '')

            if page and encoded and decoded:
                if page not in pages:
                    pages[page] = {}

                for glyph in encoded:
                    if is_qcf_glyph(glyph):
                        pages[page][glyph] = decoded

                verse_key = f"{surah}:{ayah}"
                verses[decoded] = verse_key

    mapping = {
        'pages': pages,
        'verses': verses,
        'version': '1.0',
        'source': 'King Fahd Complex'
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    print(f"Built QCF mapping: {len(pages)} pages, {len(verses)} verses")
    return output_path
