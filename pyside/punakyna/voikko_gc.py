"""Kieliopintarkistus suoraan libvoikko:n C-rajapinnasta (ctypes).

Pip-paketin `libvoikko`-sidonnan grammarErrors on rikki ainakin
libvoikko 4.3.3:n kanssa: se palauttaa haamuvirheen
"Terminating punctuation is missing" (code=9, stpos=0, len=2) kaikesta
syotteesta tai ei mitaan, ja syvemmat kutsut kaatavat prosessin.
Sama kirjasto saman sanaston kanssa toimii oikein C-rajapinnasta
(voikkogc-ohjelma ja suorat ctypes-kutsut; verifioitu 2026-11-03
upstream-korjepaketilla tests/voikkotest/fi-x-vfst/grammar.txt).
Tama moduuli kiertaa sidonnan bugin kayttamatta sita.
"""
import ctypes as C
import ctypes.util
import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional

VOIKKO_OPT_ACCEPT_UNFINISHED_PARAGRAPHS_IN_GC = 14

# virhekoodit ja suomenkieliset viestit: libvoikko 4.3.3
# src/grammar/error.hpp (GCERR_*) ja error.cpp (voikko_error_message_cstr, fi)
CODE_MESSAGES = {
    1: 'Virheellinen kirjoitusasu.',
    2: 'Poista ylimääräinen väli.',
    3: 'Ylimääräinen väli välimerkin edessä.',
    4: 'Poista ylimääräinen pilkku.',
    5: 'Virheellinen virkkeen aloittava merkki.',
    6: 'Harkitse sanan kirjoittamista pienellä alkukirjaimella.',
    7: 'Sana on kirjoitettava isolla alkukirjaimella.',
    8: 'Sana on kirjoitettu kahteen kertaan.',
    9: 'Välimerkki puuttuu virkkeen lopusta.',
    10: 'Virheelliset välimerkit lainauksen lopussa.',
    11: 'Suomenkieliseen tekstiin sopimaton lainausmerkki.',
    12: 'Väärin sijoitettu sulkumerkki.',
    13: 'Kieltoverbi ja pääverbi eivät sovi yhteen.',
    14: 'Jälkimmäisen verbin tulisi olla a/ä-päätteisessä infinitiivissä.',
    15: 'Jälkimmäisen verbin tulisi olla maan/mään-päätteisessä infinitiivissä.',
    16: 'Sidesana (ja, tai, mutta, ...) ei voi olla virkkeen viimeinen sana.',
    17: 'Tarkista, puuttuuko virkkeestä pääverbi tai -verbejä.',
    18: 'Virkkeestä saattaa puuttua pilkku, tai siinä voi olla ylimääräinen verbi.',
}


@dataclass
class GcError:
    code: int
    start: int  # merkkisijainti (UCS-4/merkki, kuten rajapinnassa)
    length: int
    suggestions: List[str] = field(default_factory=list)
    message: str = ''


# Kirjaston tiedostonimet alustojen mukaan: Linux .so.1, macOS .1.dylib.
_CANDIDATES = ('libvoikko.so.1', 'libvoikko.1.dylib', 'libvoikko.dylib',
               'libvoikko.so')


def _resolve_libfile(lib_path):
    """Selvita ladattava tiedosto.

    lib_path voi olla hakemisto (etsitaan tunnetut nimet jarjestyksessa)
    tai suora tiedostopolku (kaytetaan sellaisenaan). Ilman lib_pathia
    kysytaan alustan lataajalta (ctypes.util.find_library); viimeinen
    varavaihtoehto on alustakohtainen oletusnimi.
    """
    if lib_path:
        if os.path.isfile(lib_path):
            return lib_path
        for name in _CANDIDATES:
            p = os.path.join(lib_path, name)
            if os.path.isfile(p):
                return p
        # Ei loytynyt: palautetaan ensimmainen yritys, jotta lataajan
        # virheilmoitus nayttaa konkreettisen polun.
        return os.path.join(lib_path, _CANDIDATES[0])
    found = ctypes.util.find_library('voikko')
    if found:
        return found
    return ('libvoikko.1.dylib' if sys.platform == 'darwin'
            else 'libvoikko.so.1')




def _bundled_native_dir():
    """Paketin mukana tuleva natiivikirjastohakemisto (.oxt) tai None.

    Asettelu: <paketti>/../native/<alusta>/lib/libvoikko.* ja
    <paketti>/../native/dict/5/mor-standard. punakyna-paketti on
    laajennuksen juuressa, joten native/ on sen sisarhakemisto.
    """
    pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    plat = 'macos' if sys.platform == 'darwin' else 'linux'
    d = os.path.join(pkg_parent, 'native', plat, 'lib')
    return d if os.path.isdir(d) else None


def load_voikko_library(libfile):
    """Lataa libvoikko; pakatun .oxt:n riippuvuuskirjastot ensin.

    Pakattu laajennus sisaltaa libhfstospell ym. samassa hakemistossa:
    ne ladattava eksplisiittisesti ennen libvoikkoa, koska ajonaikaiseen
    rpathiin ei voi luottaa (macOS: CI korjaa install namet
    @loader_path-osoitteiksi erikseen; tama ennakkolataus riittaa
    Linuxissa).
    """
    bundled = _bundled_native_dir()
    if bundled and os.path.realpath(os.path.dirname(libfile)) ==                 os.path.realpath(bundled):
        for name in sorted(os.listdir(bundled)):
            p = os.path.join(bundled, name)
            if not os.path.isfile(p) or os.path.realpath(p) ==                 os.path.realpath(libfile):
                continue
            if name.endswith('.dylib') or '.so' in name:
                try:
                    C.CDLL(p, mode=C.RTLD_GLOBAL)
                except OSError:
                    pass  # varsinainen CDLL(libfile) nayttaa todellisen virheen
    return C.CDLL(libfile)


def _candidate_lib_dirs():
    """Hakemistot, joista libvoikko-taajamaa etsitaan (jarjestyksessa)."""
    dirs = []
    env = os.environ.get('PUNAKYNA_LIBVOIKKO_PATH')
    if env:
        dirs.append(env)
    bundled = _bundled_native_dir()
    if bundled:
        dirs.append(bundled)
    if sys.platform == 'darwin':
        dirs.append('/opt/homebrew/lib')      # Apple Silicon Homebrew
        dirs.append('/usr/local/lib')         # Intel Homebrew
        dirs.append('/Applications/LibreOffice.app/Contents/Frameworks')
    else:
        dirs.append('/usr/lib/x86_64-linux-gnu')
        dirs.append('/usr/lib')
        dirs.append('/usr/lib64')
        dirs.append('/usr/local/lib')
    return dirs


def _extension_lib_dirs():
    """Asennetun Voikko-lisaosan (LibreOffice) mukana tuleva taajama, macOS."""
    if sys.platform != 'darwin':
        return []
    import glob
    home = os.path.expanduser('~')
    roots = [
        os.path.join(home, 'Library', 'Application Support', 'LibreOffice'),
        '/Applications/LibreOffice.app',
        os.path.join('/Library', 'Application Support', 'LibreOffice'),
    ]
    found = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for name in ('libvoikko.1.dylib', 'libvoikko.dylib'):
            for p in glob.glob(os.path.join(root, '**', name),
                               recursive=True):
                found.append(os.path.dirname(p))
    return found


def discover_libfile():
    """Paras arvaus ladattavasta libvoikko-tiedostosta.

    Jarjestys: PUNAKYNA_LIBVOIKKO_PATH, Homebrew-oletukset, LibreOffice-
    asennuksen ja Voikko-lisaosan sijainnit (macOS), alustan lataaja,
    lopuksi alustakohtainen oletusnimi (virhepolku nayttaa konkreettisen
    polun).
    """
    for d in _candidate_lib_dirs() + _extension_lib_dirs():
        if not d:
            continue
        if os.path.isfile(d):
            return d
        for name in _CANDIDATES:
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
    found = ctypes.util.find_library('voikko')
    if found:
        return found
    return _resolve_libfile(None)


def _dict_ok(path):
    return any(os.path.isdir(os.path.join(path, v))
               for v in ('5', '4', '3', '2'))


def discover_dict_path(libfile=None):
    """Sanastohakemisto (sisaltaa version alihakemistot) tai None.

    None = libvoikko:n oma koottu oletus, joka toimii esim. Homebrew-
    asennuksissa sellaisenaan.
    """
    env = os.environ.get('PUNAKYNA_VOIKKO_DICTIONARY_PATH')
    if env:
        return env
    cands = []
    if libfile:
        libdir = os.path.dirname(os.path.realpath(libfile))
        cands.append(os.path.join(libdir, 'voikko'))
        # pakattu .oxt: native/dict on alustahakemiston ylapuolella
        cands.append(os.path.join(libdir, '..', 'dict'))
        cands.append(os.path.join(libdir, '..', '..', 'dict'))
    if sys.platform == 'darwin':
        cands += ['/opt/homebrew/lib/voikko', '/usr/local/lib/voikko',
                  '/opt/homebrew/share/voikko', '/usr/local/share/voikko']
    else:
        cands += ['/usr/lib/voikko', '/usr/local/lib/voikko']
    for c in cands:
        if os.path.isdir(c) and _dict_ok(c):
            return c
    return None


class VoikkoGC:
    def __init__(self, lang='fi', lib_path=None, dict_path=None):
        lib_path = lib_path or os.environ.get('PUNAKYNA_LIBVOIKKO_PATH')
        self._libfile = (_resolve_libfile(lib_path) if lib_path
                         else discover_libfile())
        dict_path = (dict_path
                     or os.environ.get('PUNAKYNA_VOIKKO_DICTIONARY_PATH')
                     or discover_dict_path(self._libfile))
        self._lib = load_voikko_library(self._libfile)
        L = self._lib
        L.voikkoInit.argtypes = [C.POINTER(C.c_char_p), C.c_char_p, C.c_char_p]
        L.voikkoInit.restype = C.c_void_p
        L.voikkoTerminate.argtypes = [C.c_void_p]
        L.voikkoTerminate.restype = None
        L.voikkoSetBooleanOption.argtypes = [C.c_void_p, C.c_int, C.c_int]
        L.voikkoSetBooleanOption.restype = C.c_int
        L.voikkoNextGrammarErrorCstr.argtypes = [C.c_void_p, C.c_char_p, C.c_size_t, C.c_size_t, C.c_int]
        L.voikkoNextGrammarErrorCstr.restype = C.c_void_p
        L.voikkoGetGrammarErrorCode.argtypes = [C.c_void_p]
        L.voikkoGetGrammarErrorCode.restype = C.c_int
        L.voikkoGetGrammarErrorStartPos.argtypes = [C.c_void_p]
        L.voikkoGetGrammarErrorStartPos.restype = C.c_size_t
        
        L.voikkoGetGrammarErrorLength.argtypes = [C.c_void_p]
        L.voikkoGetGrammarErrorLength.restype = C.c_size_t
        L.voikkoGetGrammarErrorSuggestions.argtypes = [C.c_void_p]
        L.voikkoGetGrammarErrorSuggestions.restype = C.POINTER(C.c_char_p)
        L.voikkoFreeGrammarError.argtypes = [C.c_void_p]
        L.voikkoFreeGrammarError.restype = None
        err = C.c_char_p()
        self._h = L.voikkoInit(C.byref(err), lang.encode('utf-8'),
                               dict_path.encode('utf-8') if dict_path else None)
        if err.value is not None:
            raise RuntimeError('voikkoInit failed: ' + err.value.decode('utf-8'))
        L.voikkoSetBooleanOption(self._h, VOIKKO_OPT_ACCEPT_UNFINISHED_PARAGRAPHS_IN_GC, 1)

    def check(self, text: str) -> List[GcError]:
        """Koko teksti; palauttaa virheet merkkisijainneilla (python-merkit)."""
        out: List[GcError] = []
        data = text.encode('utf-8')
        skip = 0
        while True:
            e = self._lib.voikkoNextGrammarErrorCstr(self._h, data, len(data), 0, skip)
            if not e:
                break
            # sijainnit ovat merkkeina (ei tavuina, vaikka syotteen pituus on tavuina)
            start = self._lib.voikkoGetGrammarErrorStartPos(e)
            frag_len = self._lib.voikkoGetGrammarErrorLength(e)
            suggs = []
            s = self._lib.voikkoGetGrammarErrorSuggestions(e)
            if s:
                i = 0
                while s[i]:
                    suggs.append(s[i].decode('utf-8'))
                    i += 1
            code = self._lib.voikkoGetGrammarErrorCode(e)
            out.append(GcError(code=code, start=start, length=frag_len,
                               suggestions=suggs,
                               message=CODE_MESSAGES.get(code, 'Kielioppivirhe.')))
            self._lib.voikkoFreeGrammarError(e)
            skip += 1
        return out

    def close(self):
        if getattr(self, '_h', None):
            self._lib.voikkoTerminate(self._h)
            self._h = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
