"""libvoikko-tausta. Kirjasto ladataan annetusta polusta tai jarjestelmasta.

Kaksi toteutusta, eksplisiittinen valinta:
1. pip-paketin libvoikko-sidonta (kehitys/palvelinymparisto), jos se on
   asennettuna. Jos sidonta loytyy mutta natiivikirjaston lataus epaonnistuu,
   virhe nousee kuten ennenkin (ei vaihtoa toiseen taustaan hiljaa).
2. ctypes-natiivitausta (voikko_native), kun sidontaa ei ole asennettuna
   (esim. LibreOffice-laajennuksen sisainen Python).

ACTIVE_BACKEND kertoo, kumpi on kaytossa (diagnoosit/preflight).
"""
import os

_VOIKKO = None
ACTIVE_BACKEND = None
ACTIVE_LIBFILE = None


def get_voikko(lang='fi', lib_path=None, dict_path=None):
    global _VOIKKO, ACTIVE_BACKEND, ACTIVE_LIBFILE
    if _VOIKKO is None:
        lib_path = lib_path or os.environ.get('PUNAKYNA_LIBVOIKKO_PATH')
        dict_path = dict_path or os.environ.get('PUNAKYNA_VOIKKO_DICTIONARY_PATH')
        try:
            import libvoikko
        except ImportError:
            libvoikko = None
        if libvoikko is not None:
            if lib_path:
                libvoikko.Voikko.setLibrarySearchPath(lib_path)
            kwargs = {}
            if dict_path:
                kwargs['path'] = dict_path
            _VOIKKO = libvoikko.Voikko(lang, **kwargs)
            # Oikolukijan kayttotapaus: kappaleet voivat olla keskeneraisia
            # (muuten jokaiseen syotteeseen tulee haamuvika "loppuvalimerkki puuttuu").
            _VOIKKO.setAcceptUnfinishedParagraphsInGc(True)
            ACTIVE_BACKEND = 'libvoikko-binding'
        else:
            from .voikko_native import NativeVoikko
            _VOIKKO = NativeVoikko(lang, lib_path=lib_path,
                                   dict_path=dict_path)
            _VOIKKO.setAcceptUnfinishedParagraphsInGc(True)
            ACTIVE_BACKEND = 'ctypes-native'
            ACTIVE_LIBFILE = _VOIKKO._libfile
    return _VOIKKO
