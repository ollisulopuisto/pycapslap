from app.models.captions import CaptionSegment, WordSpan
from app.services.spellcheck import SpellChecker


class _Voikko:
    """Rejects one word, and counts how often it is asked."""

    def __init__(self):
        self.calls = 0

    def spell(self, word):
        self.calls += 1
        return word != "kaupppa"


def _checker() -> tuple[SpellChecker, _Voikko]:
    checker = SpellChecker()
    checker._voikko = _Voikko()
    checker._loaded = True
    return checker, checker._voikko


def test_spans_come_from_the_cache_until_the_text_changes():
    checker, voikko = _checker()
    seg = CaptionSegment(0, 1000, "Tämä on kaupppa")
    assert checker.misspelled_spans(seg) == [(8, 15, "kaupppa")]
    asked = voikko.calls

    # Same text again, even on another segment object: nothing is looked up.
    assert checker.misspelled_spans(CaptionSegment(5, 9, "Tämä on kaupppa")) == [
        (8, 15, "kaupppa")
    ]
    assert voikko.calls == asked

    # An edit is seen at once.
    seg.update_text("Tämä on kauppa")
    assert checker.misspelled_spans(seg) == []


def test_a_glued_first_syllable_is_cached_apart_from_a_whole_word():
    checker, _ = _checker()
    glued = CaptionSegment(
        0, 1000, "kaupppa on", words=[WordSpan(0, 500, "kaupppa", True)]
    )
    whole = CaptionSegment(0, 1000, "kaupppa on", words=[WordSpan(0, 500, "kaupppa")])
    assert checker.misspelled_spans(glued) == []
    assert checker.misspelled_spans(whole) == [(0, 7, "kaupppa")]


def test_callers_get_their_own_list():
    checker, _ = _checker()
    seg = CaptionSegment(0, 1000, "kaupppa")
    first = checker.misspelled_spans(seg)
    first.clear()
    assert checker.misspelled_spans(seg) == [(0, 7, "kaupppa")]
