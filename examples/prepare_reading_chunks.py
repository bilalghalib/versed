"""Reviewable native-text PDF chunks; no TTS, OCR or timing generation.

Run from this repository after installing versed-pdf[pdf]. See README.md.
"""
import argparse
import hashlib
import json
import re
import unicodedata
from importlib.metadata import version
from pathlib import Path

from versed import PageType, classify_page, extract_repaired_words

END = re.compile(r'[.!?؟][\"\'”’»)]*$')


def chunk_words(words, max_words=120):
    """Simple punctuation boundary example, deliberately not a linguistic parser."""
    if max_words < 1:
        raise ValueError('max_words must be positive')
    chunks, pending = [], []
    def flush(reason):
        text, links = '', []
        for word in pending:
            if text:
                text += ' '
            start = len(text)
            text += word['text']
            links.append({'word_id': word['id'], 'start_char': start, 'end_char': len(text)})
        chunks.append({'id': f'chunk-{len(chunks)+1}', 'text': text,
                       'word_links': links, 'boundary': reason, 'needs_review': True})
        pending.clear()
    for word in words:
        pending.append(word)
        if END.search(word['text']):
            flush('punctuation')
        elif len(pending) >= max_words:
            flush('word_limit')
    if pending:
        flush('document_end')
    return chunks


def prepare(pdf_path, max_words=120):
    import pymupdf
    path = Path(pdf_path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    words = []
    with pymupdf.open(path) as pdf:
        for page_index, page in enumerate(pdf):
            number = page_index + 1
            if classify_page(str(path), number) == PageType.QCF_QURAN:
                raise ValueError(f'Page {number}: this native-word example requires QCF decoding/review first')
            extracted = extract_repaired_words(page)
            if not extracted:
                raise ValueError(f'Page {number}: no native words; review blank/scan pages and perform OCR separately')
            for index, word in enumerate(extracted):
                text = word[4]
                if any(unicodedata.category(char) == 'Co' or char == '\ufffd' for char in text):
                    raise ValueError(f'Page {number}: unresolved font encoding requires review')
                words.append({'id': f'{sha}:p{number}:w{index}', 'page': number,
                              'text': text, 'bbox': list(word[:4]),
                              'source_position': list(word[5:8])})
    return {'schema': 'versed.reading-chunks.example.v1', 'source_sha256': sha,
            'package_version': version('versed-pdf'), 'needs_review': True,
            'words': words, 'chunks': chunk_words(words, max_words)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf')
    parser.add_argument('output')
    parser.add_argument('--max-words', type=int, default=120)
    args = parser.parse_args()
    result = prepare(args.pdf, args.max_words)
    # Avoid overwriting an earlier reviewed manifest or the source PDF.
    with Path(args.output).open('x', encoding='utf-8') as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
