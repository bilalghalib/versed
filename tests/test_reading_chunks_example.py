import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('reading_example', Path(__file__).parents[1]/'examples/prepare_reading_chunks.py')
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)


@pytest.mark.parametrize('parts', [
    [('The sentence', 1), ('continues here.', 2)],
    [('هذه جملة', 1), ('تستمر هنا؟', 2)],
])
def test_cross_page_sentence_preserves_source_links_and_character_offsets(parts):
    words = [{'id': str(i), 'page': page, 'text': text, 'bbox': [0,0,1,1]}
             for i,(text,page) in enumerate(parts)]
    chunks = example.chunk_words(words)
    assert len(chunks) == 1
    assert chunks[0]['text'] == ' '.join(w['text'] for w in words)
    for link,word in zip(chunks[0]['word_links'], words):
        assert link['word_id'] == word['id']
        assert chunks[0]['text'][link['start_char']:link['end_char']] == word['text']
    assert chunks[0]['needs_review']


def test_limit_marks_a_forced_split_without_losing_or_duplicating_words():
    words = [{'id': str(i), 'text': 'word'} for i in range(5)]
    chunks = example.chunk_words(words, max_words=2)
    assert [c['boundary'] for c in chunks] == ['word_limit','word_limit','document_end']
    assert [link['word_id'] for c in chunks for link in c['word_links']] == [w['id'] for w in words]


def test_real_pdf_exports_cross_page_source_boxes(tmp_path):
    import pymupdf
    source = tmp_path/'sample.pdf'
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72,72), 'The sentence continues')
        pdf.new_page().insert_text((72,72), 'on the next page.')
        pdf.save(source)
    manifest = example.prepare(source)
    assert len(manifest['chunks']) == 1
    assert {w['page'] for w in manifest['words']} == {1,2}
    assert all(w['bbox'][2] > w['bbox'][0] for w in manifest['words'])
    assert manifest['chunks'][0]['text'] == 'The sentence continues on the next page.'
