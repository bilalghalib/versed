import pytest
from versed.repair import repair_words_with_glyph_info


def example(text, positions):
    chars = [{'c': c, 'bbox': (x, 0, x+5, 12), 'origin': (x, 10)} for c,x in zip(text,positions)]
    word = (0, 0, max(positions)+5, 12, text, 0, 0, 3, 'source-extra')
    raw = {'blocks': [{'type': 0, 'number': 0, 'lines': [{'dir': (1,0), 'spans': [{'chars': chars}]}]}]}
    return word,raw


@pytest.mark.parametrize('text,positions,expected', [
    ('Majn¯un', [0,5,10,15,20,20,25], 'Majnūn'),
    ('Ru¯mı¯', [0,5,5,10,15,15], 'Rūmī'),
    ('Ka¯sha¯ni', [0,5,5,10,15,20,20,25,30], 'Kāshāni'),
])
def test_overprinted_macron_in_either_pdf_order_preserves_word_identity(text, positions, expected):
    word,raw=example(text,positions)
    result=repair_words_with_glyph_info([word],raw)
    assert result == [word[:4]+(expected,)+word[5:]]


@pytest.mark.parametrize('text', ['Straße', 'ışık', 'S. adr', 'U.S.A.', 'al-Rah.man', 'بِسْمِ اللَّهِ', 'a¯b'])
def test_plain_letters_punctuation_and_nonoverlapping_macron_are_unchanged(text):
    word,raw=example(text,list(range(0,len(text)*5,5)))
    assert repair_words_with_glyph_info([word],raw) == [word]


def test_ambiguous_geometry_or_raw_text_mismatch_is_not_repaired():
    word,raw=example('a¯u',[0,0,0])
    assert repair_words_with_glyph_info([word],raw) == [word]
    word,raw=example('a¯',[0,0])
    raw['blocks'][0]['lines'][0]['spans'][0]['chars'][0]['c']='o'
    assert repair_words_with_glyph_info([word],raw) == [word]


def test_separate_word_tuples_are_never_merged():
    word,raw=example('a¯',[0,0])
    words=[word[:4]+('a',)+word[5:],word[:4]+('¯',)+word[5:7]+(4,)]
    assert repair_words_with_glyph_info(words,raw) == words
