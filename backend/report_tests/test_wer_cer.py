import pytest

from report_module.mishearing import cer, corpus_rates, edit_distance, wer
from report_module.textutil import graphemes, normalize


def test_edit_distance():
    assert edit_distance(list("kitten"), list("sitting")) == 3
    assert edit_distance([], ["a"]) == 1


def test_english_wer():
    assert wer("the cat sat on the mat", "the cat sat on the mat") == 0
    assert wer("the cat sat", "the cat sit") == pytest.approx(1 / 3)
    assert wer("forty five", "fifty four") == 1.0
    # punctuation and case are ignored
    assert wer("Yes, go ahead.", "yes go ahead") == 0


def test_hindi_wer_and_cer():
    assert wer("मेरा नाम टेस्ट है", "मेरा नाम टेस्ट हैं") == pytest.approx(0.25)
    # Danda (।) is punctuation, so it does not count as an error.
    assert cer("हाँ, बोलिए।", "हाँ बोलिए") == 0


def test_graphemes_count_visible_letters():
    # "कि" = consonant + vowel sign = 1 visible letter (2 code points)
    assert graphemes("कि") == ["कि"]
    assert len(graphemes("மூணு")) == 2  # Tamil: மூ + ணு


def test_tamil_cer():
    # 3,8 said; 3,7 heard: only the last word differs
    value = cer("மூணு, எட்டு", "மூணு, ஏழு")
    assert 0 < value < 1
    assert wer("மூணு, எட்டு", "மூணு, ஏழு") == 0.5


def test_corpus_rates():
    w, c = corpus_rates([("haan ji", "haan ji"), ("pachees saal", "pachaas saal")])
    assert w == pytest.approx(1 / 4)
    assert 0 < c < 0.2
    assert corpus_rates([]) == (None, None)


def test_normalize():
    assert normalize("  Haan, JI!  ") == "haan ji"
