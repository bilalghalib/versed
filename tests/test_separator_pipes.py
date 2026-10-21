"""A pipe in its own span is a separator, not a broken-CMap ff (PNAS keyword line)."""
from versed.ligatures import repair_words_keeping_separator_pipes


def _word(x0, x1, text):
    return (x0, 100.0, x1, 110.0, text, 0, 0, 0)


def test_separator_pipe_kept_when_it_is_its_own_span():
    words = [_word(0, 60, "well-being|"), _word(70, 130, "meta-awareness|")]
    boxes = [(55.0, 100.0, 60.0, 110.0), (125.0, 100.0, 130.0, 110.0)]
    out = repair_words_keeping_separator_pipes(words, boxes)
    assert [w[4] for w in out] == ["well-being|", "meta-awareness|"]


def test_in_run_pipe_still_becomes_ff():
    words = [_word(0, 8, "o|"), _word(20, 80, "di|ered")]
    out = repair_words_keeping_separator_pipes(words, [(300.0, 100.0, 305.0, 110.0)])
    assert [w[4] for w in out] == ["off", "differed"]


def test_only_the_word_holding_the_separator_is_exempt():
    words = [_word(0, 60, "insight|"), _word(70, 78, "o|")]
    out = repair_words_keeping_separator_pipes(words, [(55.0, 100.0, 60.0, 110.0)])
    assert [w[4] for w in out] == ["insight|", "off"]
