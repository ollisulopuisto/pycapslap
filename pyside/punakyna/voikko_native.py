"""Nativoitu libvoikko-tausta suoraan C-rajapinnasta (ctypes, ei pip-sidontaa).

Mahdollistaa moottorin ajamisen LibreOfficen omassa Pythonissa ilman
pip-asennusta: sama C-rajapinta, jota voikko_gc.py jo kayttaa
kieliopintarkistukseen. Kattaa pipeline-tason tarpeet: spell, suggest,
tokens, sentences ja analyze.

Kirjaston ja sanaston loytaminen:
1. PUNAKYNA_LIBVOIKKO_PATH / PUNAKYNA_VOIKKO_DICTIONARY_PATH (kuten muualla)
2. Homebrew-oletukset ja LibreOfficen mukana tulevat/sijoitetut kopiot (macOS)
3. alustan lataaja (find_library) ja natiivioletukset sanastolle
"""
import ctypes as C
import ctypes.util
import os
import sys
from typing import Dict, Iterator, List, Optional

from .voikko_gc import (VOIKKO_OPT_ACCEPT_UNFINISHED_PARAGRAPHS_IN_GC,
                        _resolve_libfile, discover_dict_path,
                        discover_libfile, load_voikko_library)

TOKEN_NONE = 0
TOKEN_WORD = 1
TOKEN_PUNCTUATION = 2
TOKEN_WHITESPACE = 3
TOKEN_UNKNOWN = 4

SENTENCE_NONE = 0
SENTENCE_START = 1
SENTENCE_NO_START = 2


class Token:
    """Yhteensopiva libvoikko-sidonnan Token-luokan kanssa (vakiot)."""
    NONE = TOKEN_NONE
    WORD = TOKEN_WORD
    PUNCTUATION = TOKEN_PUNCTUATION
    WHITESPACE = TOKEN_WHITESPACE
    UNKNOWN = TOKEN_UNKNOWN


class _Tok:
    __slots__ = ('tokenText', 'tokenType')

    def __init__(self, text, ttype):
        self.tokenText = text
        self.tokenType = ttype


class _Sent:
    __slots__ = ('sentenceText',)

    def __init__(self, text):
        self.sentenceText = text


class NativeVoikko:
    """libvoikko-instanssi C-rajapinnasta. Sama rajapintapinta kuin
    pip-sidonnaisella Voikko-oliolla pipeline-tason kayttotapauksissa."""

    def __init__(self, lang='fi', lib_path=None, dict_path=None):
        lib_path = lib_path or os.environ.get('PUNAKYNA_LIBVOIKKO_PATH')
        if lib_path:
            libfile = _resolve_libfile(lib_path)
        else:
            libfile = discover_libfile()
        dict_path = (dict_path
                     or os.environ.get('PUNAKYNA_VOIKKO_DICTIONARY_PATH')
                     or discover_dict_path(libfile))
        L = load_voikko_library(libfile)
        self._libfile = libfile
        L.voikkoInit.argtypes = [C.POINTER(C.c_char_p), C.c_char_p, C.c_char_p]
        L.voikkoInit.restype = C.c_void_p
        L.voikkoTerminate.argtypes = [C.c_void_p]
        L.voikkoTerminate.restype = None
        L.voikkoSetBooleanOption.argtypes = [C.c_void_p, C.c_int, C.c_int]
        L.voikkoSetBooleanOption.restype = C.c_int
        L.voikkoSpellCstr.argtypes = [C.c_void_p, C.c_char_p]
        L.voikkoSpellCstr.restype = C.c_int
        L.voikkoSuggestCstr.argtypes = [C.c_void_p, C.c_char_p]
        L.voikkoSuggestCstr.restype = C.POINTER(C.c_char_p)
        L.voikkoFreeCstrArray.argtypes = [C.POINTER(C.c_char_p)]
        L.voikkoFreeCstrArray.restype = None
        # tokenisointi ja virkejaot UCS4-rajapinnasta, kuten pip-sidonta
        # tekee (proven calling convention: buffer + position-wchar pointer)
        L.voikkoNextTokenUcs4.argtypes = [C.c_void_p, C.c_wchar_p,
                                          C.c_size_t,
                                          C.POINTER(C.c_size_t)]
        L.voikkoNextTokenUcs4.restype = C.c_int
        L.voikkoNextSentenceStartUcs4.argtypes = [C.c_void_p, C.c_wchar_p,
                                                  C.c_size_t,
                                                  C.POINTER(C.c_size_t)]
        L.voikkoNextSentenceStartUcs4.restype = C.c_int
        L.voikkoAnalyzeWordCstr.argtypes = [C.c_void_p, C.c_char_p]
        L.voikkoAnalyzeWordCstr.restype = C.POINTER(C.c_void_p)
        L.voikko_mor_analysis_value_cstr.argtypes = [C.c_void_p, C.c_char_p]
        L.voikko_mor_analysis_value_cstr.restype = C.c_void_p
        L.voikko_free_mor_analysis_value_cstr.argtypes = [C.c_void_p]
        L.voikko_free_mor_analysis_value_cstr.restype = None
        L.voikko_mor_analysis_keys.argtypes = [C.c_void_p]
        L.voikko_mor_analysis_keys.restype = C.POINTER(C.c_char_p)
        L.voikko_free_mor_analysis.argtypes = [C.POINTER(C.c_void_p)]
        L.voikko_free_mor_analysis.restype = None
        err = C.c_char_p()
        self._h = L.voikkoInit(C.byref(err), lang.encode('utf-8'),
                               dict_path.encode('utf-8') if dict_path else None)
        if err.value is not None:
            raise RuntimeError('voikkoInit failed: '
                               + err.value.decode('utf-8'))
        self._L = L

    def setAcceptUnfinishedParagraphsInGc(self, value):
        self._L.voikkoSetBooleanOption(
            self._h, VOIKKO_OPT_ACCEPT_UNFINISHED_PARAGRAPHS_IN_GC,
            1 if value else 0)

    def spell(self, word: str) -> bool:
        return bool(self._L.voikkoSpellCstr(self._h, word.encode('utf-8')))

    def suggest(self, word: str) -> List[str]:
        arr = self._L.voikkoSuggestCstr(self._h, word.encode('utf-8'))
        if not arr:
            return []
        out = []
        i = 0
        while arr[i]:
            out.append(arr[i].decode('utf-8'))
            i += 1
        self._L.voikkoFreeCstrArray(arr)
        return out

    def tokens(self, text: str) -> Iterator[_Tok]:
        buf = C.create_unicode_buffer(text)
        wsize = C.sizeof(C.c_wchar)
        text_len = len(text)
        tlen = C.c_size_t()
        pos = 0
        while text_len > 0:
            t = self._L.voikkoNextTokenUcs4(
                self._h, C.c_wchar_p(C.addressof(buf) + pos * wsize),
                text_len, C.byref(tlen))
            if t == TOKEN_NONE:
                break
            yield _Tok(text[pos:pos + tlen.value], t)
            pos += tlen.value
            text_len -= tlen.value

    def sentences(self, text: str) -> Iterator[_Sent]:
        if not text:
            return
        buf = C.create_unicode_buffer(text)
        wsize = C.sizeof(C.c_wchar)
        text_len = len(text)
        slen = C.c_size_t()
        pos = 0
        while text_len > 0:
            t = self._L.voikkoNextSentenceStartUcs4(
                self._h, C.c_wchar_p(C.addressof(buf) + pos * wsize),
                text_len, C.byref(slen))
            if slen.value == 0:
                break
            # pip-sidonta palauttaa myos loppufragmentin (SENTENCE_NONE):
            # se on silti tarkistettavaa tekstia
            yield _Sent(text[pos:pos + slen.value])
            if t == SENTENCE_NONE:
                break
            pos += slen.value
            text_len -= slen.value

    def analyze(self, word: str) -> List[Dict[str, str]]:
        arr = self._L.voikkoAnalyzeWordCstr(self._h, word.encode('utf-8'))
        if not arr:
            return []
        out = []
        i = 0
        while arr[i]:
            d = {}
            keys = self._L.voikko_mor_analysis_keys(arr[i])
            if keys:
                k = 0
                while keys[k]:
                    key = keys[k].decode('utf-8')
                    # arvo on kutsujan vapautettava (voikko.h:
                    # voikko_free_mor_analysis_value_cstr)
                    vp = self._L.voikko_mor_analysis_value_cstr(
                        arr[i], keys[k])
                    if vp:
                        d[key] = C.string_at(vp).decode('utf-8')
                        self._L.voikko_free_mor_analysis_value_cstr(vp)
                    else:
                        d[key] = ''
                    k += 1
            out.append(d)
            i += 1
        self._L.voikko_free_mor_analysis(arr)
        return out

    def terminate(self):
        if getattr(self, '_h', None):
            self._L.voikkoTerminate(self._h)
            self._h = None

    def __del__(self):
        try:
            self.terminate()
        except Exception:
            pass
