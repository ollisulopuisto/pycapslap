"""Oikolukuputki: Voikko-oikeinkirjoitus + saannot (+ valinnainen neurotaso).

Palauttaa vain ehdotuksia alkuperaisen tekstin merkkisijainneilla;
ei koskaan normalisoi tai muuta kayttajan tekstia.
"""
from dataclasses import asdict
from typing import List, Optional

from .voikko_compat import Token

import threading

from .backend_voikko import get_voikko
from .rules import Suggestion, run_rules
from .voikko_gc import VoikkoGC

_GC = None


def _get_gc():
    global _GC
    if _GC is None:
        _GC = VoikkoGC()
    return _GC


# kieliopintarkistimen koodit -> (kategoria, vakavuus)
# (koodit: libvoikko 4.3.3 src/grammar/error.hpp GCERR_*)
# vakavuudet ovat punakynan valintoja: koodi 6 ja rakenneheuristiikat
# 17/18 tuottavat mitatusti osumia puhtaalla Wikipedia-tekstillä
# (ks. eval/RESULTS.md), siksi style; muut selkeitä virheluokkia.
_GC_KIND = {
    1: ('grammar', 'error'), 2: ('style', 'style'), 3: ('style', 'error'),
    4: ('style', 'error'), 5: ('style', 'style'), 6: ('grammar', 'style'),
    7: ('style', 'style'), 8: ('grammar', 'error'), 9: ('style', 'style'),
    10: ('style', 'error'), 11: ('style', 'style'), 12: ('style', 'style'),
    13: ('grammar', 'error'), 14: ('grammar', 'error'),
    15: ('grammar', 'error'), 16: ('style', 'style'),
    17: ('grammar', 'style'), 18: ('grammar', 'style'),
}


def _voikko_gc_suggestions(text):
    out = []
    for e in _get_gc().check(text):
        if (e.code == 8 and e.start > 0
                and text[e.start:e.start + 1].isupper()):
            continue  # toistuva nimi ("Díaz Díaz", "Sigue Sigue Sputnik")
        cat, sev = _GC_KIND.get(e.code, ('grammar', 'info'))
        out.append(Suggestion(
            rule='VOIKKO_GC', category=cat, severity=sev,
            start=e.start, end=e.start + e.length,
            message=e.message, replacements=e.suggestions))
    return out

_ABBREV = {
    'esim', 'ts', 'ns', 'n', 'v', 'vs', 'vm', 'jne', 'etc', 'ym', 'yms',
    'tms', 'os', 's', 'lkm', 'no', 'huom', 'ks', 'emt', 'ent', 'ekr', 'jkr',
    'mm', 'ml', 'pl', 't', 'hlö', 'tai', 'toim', 'prof', 'FT', 'FM',
}

# Suorituskyky: nopea joukko numeromerkeille numerotarkistusta varten
_DIGITS = set('0123456789')


class _PipelineToken:
    """Kevyt oliomalli tokenille tokenisoinnissa.

    Korvaa dynaamisen type('T', (), ...) -kutsun, joka loi uuden luokan
    jokaiselle tokenille joka kutsulla ja aiheutti merkittävän CPU-kuorman.
    """
    __slots__ = ('text', 'start', 'end', 'ttype', 'is_word', 'lower')

    def __init__(self, text: str, start: int, end: int, ttype: object,
                 is_word: bool, lower: str):
        self.text = text
        self.start = start
        self.end = end
        self.ttype = ttype
        self.is_word = is_word
        self.lower = lower



def _lev(a, b, limit=3):
    """Levenshtein-etaisyys varhaiskatkaisulla."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        best = i
        for j, cb in enumerate(b, 1):
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            cur.append(v)
            best = min(best, v)
        if best > limit:
            return limit + 1
        prev = cur
    return prev[-1]

def _is_probably_name(tok):
    return tok.text[:1].isupper()


def _spelling_suggestions(sent_text, offset, tokens, voikko, spell_cache=None):
    out = []
    for tok in tokens:
        if not tok.is_word:
            continue
        w = tok.text
        # Suorituskyky: 'not _DIGITS.isdisjoint(w)' välttää generaattoriallokoinnin
        # ja any()-kutsujen kuorman jokaiselle sanalle.
        if len(w) < 2 or not _DIGITS.isdisjoint(w):
            continue
        if '@' in w or ':/' in w:
            continue
        # Suorituskyky: käytetään tok.lower (_PipelineToken:in laskema arvo)
        # toistuvan w.lower()-kutsun sijasta.
        if tok.lower in _ABBREV:
            continue
        if w.isupper():
            continue  # lyhenne, esim. EU
        # Suorituskyky: vältetään toistuvat C-FFI / ctypes -kutsut (voikko.spell)
        # samoille sanoille tekstin sisällä käyttämällä dokumenttikohtaista välimuistia.
        if spell_cache is not None:
            ok = spell_cache.get(w)
            if ok is None:
                ok = spell_cache[w] = voikko.spell(w)
            if ok:
                continue
        elif voikko.spell(w):
            continue
        suggs = voikko.suggest(w) or []
        if _is_probably_name(tok):
            out.append(Suggestion(
                rule='SPELL_UNKNOWN', category='spelling', severity='info',
                start=offset + tok.start, end=offset + tok.end,
                message=f'Tuntematon sana "{w}" (nimi tai harvinainen sana?).',
                replacements=suggs[:3]))
        else:
            out.append(Suggestion(
                rule='SPELL', category='spelling', severity='error',
                start=offset + tok.start, end=offset + tok.end,
                message=f'Tuntematon tai virheellinen sana "{w}".',
                replacements=suggs[:3]))
    return out


_ENGINE_LOCK = threading.Lock()


def check_text(text, voikko=None, use_rules=True, use_spelling=True,
               use_gc=True, neural_backend=None, use_parser=False, style_profile=None):
    """Palauttaa listan Suggestion-olioita tekstin merkkisijainneilla.

    Säieturvallinen: libvoikko-instanssi ei kestä rinnakkaisuutta
    (havaittu heap-korruptio), joten tarkistukset sarjallistetaan
    prosessinlaajuisella lukolla.

    use_parser: OPT-IN jäsentävä taso (punakyna.parser_tier) - raskas
    malli, vaatii stanza-asennuksen. Oletus pois: konservatiivinen
    baseline ei muutu.
    """
    with _ENGINE_LOCK:
        return _check_text_unlocked(text, voikko, use_rules, use_spelling,
                                    use_gc, neural_backend, use_parser, style_profile)


def _check_text_unlocked(text, voikko=None, use_rules=True, use_spelling=True,
                         use_gc=True, neural_backend=None, use_parser=False, style_profile=None):
    from .style import StyleProfile, check_style, excluded_text
    profile = StyleProfile.from_value(style_profile)
    voikko = voikko or get_voikko()
    out: List[Suggestion] = []
    cache = {}
    spell_cache = {}
    style_out = []
    style_allowed = profile.enabled and not excluded_text(text)
    pos = 0
    sentences = list(voikko.sentences(text))
    spans = []
    # Suorituskyky: Libvoikko palauttaa peräkkäiset virkkeet järjestyksessä.
    # Vältetään toistuvat text.find()-alimerkkijonohaut vertaamalla suoraan pos-kohtaan.
    for s in sentences:
        stext = s.sentenceText
        slen = len(stext)
        if text.startswith(stext, pos):
            idx = pos
        else:
            idx = text.find(stext, pos)
            if idx < 0:
                idx = pos
        spans.append((stext, idx))
        pos = idx + slen
    for sent_text, s_off in spans:
        toks = []
        tpos = 0
        for t in voikko.tokens(sent_text):
            tt = t.tokenText
            tlen = len(tt)
            if sent_text.startswith(tt, tpos):
                tidx = tpos
            else:
                tidx = sent_text.find(tt, tpos)
                if tidx < 0:
                    tidx = tpos
            # Suorituskykyoptimointi: käytä esialustettua _PipelineToken-luokkaa
            # dynamic type()-metaluokan luonnin sijasta.
            toks.append(_PipelineToken(
                text=tt,
                start=tidx,
                end=tidx + tlen,
                ttype=t.tokenType,
                is_word=t.tokenType == Token.WORD,
                lower=tt.lower()
            ))
            tpos = tidx + tlen
        if use_spelling:
            out += _spelling_suggestions(sent_text, s_off, toks, voikko, spell_cache)
        if use_rules:
            out += run_rules(sent_text, s_off, toks, voikko, cache,
                             before=text[max(0, s_off - 40):s_off])
        if style_allowed:
            style_out += check_style(sent_text, s_off, toks, voikko, cache, profile)
        if neural_backend is not None:
            corr = neural_backend.correct(sent_text)
            if corr is not None:
                out.append(Suggestion(
                    rule='NEURAL', category='grammar', severity='style',
                    start=s_off, end=s_off + len(sent_text),
                    message='Mallin ehdottama muokkaus (tarkista ihmisena).',
                    replacements=[corr.corrected]))
    if use_rules:
        from .rules import check_typography
        out += check_typography(text, 0, clock=True)
    if use_parser:
        from .parser_tier import check as parser_check
        own = [(s.start, s.end) for s in out]
        for s in parser_check(text, voikko=voikko):
            if any(s.start < e and s0 < s.end for s0, e in own):
                continue  # saantotaso kattaa jo saman kohteen (span-osuma)
            out.append(s)
    if use_gc:
        own_spans = [(s.start, s.end) for s in out]
        for s in _voikko_gc_suggestions(text):
            if any(s.start < e and s0 < s.end for s0, e in own_spans):
                continue  # oma saanto kattaa jo saman kohteen (span-osuma)
            out.append(s)
    # Style advice must never hide or replace grammar/spelling diagnostics.
    out += [s for s in style_out if not any(s.start < e.end and e.start < s.end for e in out)]
    out.sort(key=lambda s: (s.start, s.rule))
    return out


def suggestions_as_dicts(suggs):
    return [asdict(s) for s in suggs]
