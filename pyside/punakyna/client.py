"""Jaettu asiakaskirjasto paikalliselle Punakynä-rajapinnalle.

Sovitukset (LibreOffice-lisäosa, selainlaajennos, muut työkalut) käyttävät
tätä: lukee tunnuksen ~/.config/punakyna/token ja kutsuu POST /check:ia.
Ei riippuvuuksia standardikirjaston ulkopuolelle.
"""
import json
import urllib.request
from pathlib import Path

from .tokenfile import TOKEN_PATH, TokenError, load_or_create_token


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # tunnus ei saa seurata uudelleenohjausta toiseen osoitteeseen


# Ei ymparistoproxyja (http_proxy): loopback-liikenne ei saa vuotaa proxylle,
# eika tunnus sen mukana. Ei redirecteja.
_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), _NoRedirect)

DEFAULT_PORT = 8377
LOOPBACK_HOSTS = frozenset(('127.0.0.1', 'localhost', '::1', '[::1]'))


def read_token(path=TOKEN_PATH):
    """Lue tunnus samalla validoinnilla kuin palvelin (symlink/oikeudet/pituus)."""
    return load_or_create_token(path)


def check(text, port=DEFAULT_PORT, host='127.0.0.1', token=None,
          use_rules=True, use_spelling=True, timeout=30):
    """Tarkista teksti paikallisella palvelimella. Palauttaa ehdotuslistan.

    Heittää ConnectionErrorin jos palvelin ei vastaa (käynnistä:
    python -m punakyna --serve).
    """
    # Turvatarkistus: teksti ja tunnus eivät saa koskaan lähteä koneelta ulos.
    if host not in LOOPBACK_HOSTS:
        raise ValueError(f'kielletty osoite: {host!r} - vain loopback sallittu')
    if token is None:
        token = read_token()
    payload = json.dumps({
        'text': text, 'use_rules': use_rules, 'use_spelling': use_spelling,
    }).encode('utf-8')
    req = urllib.request.Request(
        f'http://{host}:{port}/check', data=payload,
        headers={'Content-Type': 'application/json',
                 'Authorization': f'Bearer {token}'})
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            return json.loads(resp.read())['suggestions']
    except urllib.error.HTTPError:
        raise  # 4xx/5xx: palvelin vastasi - älä kaanna yhteysvirheeksi
    except OSError as e:
        raise ConnectionError(
            f'Punakynä-palvelin ei vastaa osoitteessa {host}:{port} '
            f'(käynnistettykö? python -m punakyna --serve): {e}') from e
