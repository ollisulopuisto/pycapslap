"""Yhteensopivuuskerros: pip-sidonnan Token tai ctypes-taustan vastaava.

LibreOffice-paketissa pip-sidontaa ei ole; siella Token tulee
voikko_nativesta. Kehitys/palvelinymparistossa pip-sidonta on kaytossa
kuten ennenkin.
"""
try:
    from libvoikko import Token  # noqa: F401
    HAVE_BINDING = True
except ImportError:
    from .voikko_native import Token  # noqa: F401
    HAVE_BINDING = False
