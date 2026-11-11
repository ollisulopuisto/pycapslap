"""Paikallinen HTTP-rajapinta Punakynälle.

OFFSET-KONVENTIO (lukittu, tests/test_wire_offsets.py): kaikki pinnat
(HTTP-API, CLI --json, native messaging) raportoivat start/end Python-
koodipisteinä subjektoidussa tekstissä. Sovitinkerrokset (UNO UTF-16,
macOS NSRange) muuntavat omalla puolellaan.

Turvamalli: tekstiä ei saa vuotaa koneelta eikä verkkosivujen saa päästä
siihen käsiksi selaimen kautta. Siksi rajapinta:

- sitoutuu vain loopback-osoitteeseen (127.0.0.1 / ::1),
- vaatii Bearer-tunnisteen POST /check -pyynnöiltä (tunnus tiedostossa
  ~/.config/punakyna/token, oikeudet 0600; serve() luo sen tarvittaessa),
- tarkistaa Host-otsakkeen (DNS-rebinding-torjunta),
- hylkää tuntemattomat Origin-otsakkeet,
- ei lähetä mitään CORS-otsakkeita ja hylkää preflight-OPTIONS-pyynnöt,
- vaatii Content-Type: application/json (selain ei voi lähettää sitä
  cross-origin "simple requestina", joten sivusto ei voi kiertää
  Origin-tarkistusta),
- rajoittaa pyynnön koon (1 MB) ja tekstin pituuden (oletus 200 000 merkkiä),
- ei logaa tekstisisältöä.
"""
import hmac
import json
import os
import secrets
import select
import stat
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .pipeline import check_text, suggestions_as_dicts
from .tokenfile import (TOKEN_PATH, TokenError, load_all_tokens,
                        load_or_create_token)

MAX_BODY = 1024 * 1024  # 1 MB
MAX_TEXT = 200_000      # merkkiä
READ_TIMEOUT = 30       # s, rungon luvun aikakatkaisu
DEFAULT_MAX_WORKERS = 4  # samanaikaiset tarkistukset; ylimääräiset jonottavat
MAX_CONNECTIONS = 32     # aktiiviset yhteydet; ylimeneville 503 + sulku

HUOM_TURVAMALLI = (
    'Tunnustiedosto on ensimmäinen paikallinen bearer-todennus, EI '
    'sovelluskohtaista valtuutusta: kuka tahansa paikallinen prosessi, joka '
    'lukee tiedoston, pääsee rajapintaan. Sovitusten erillinen '
    'rekisteröinti/peruutus (enrollment) on tekemättä - ks. ROADMAP.')

LOOPBACK_HOSTS = ('127.0.0.1', 'localhost', '::1')

import re
_HOST_RE = re.compile(
    r'^(?:(?:127\.0\.0\.1|localhost)(?::([0-9]{1,5}))?|'
    r'\[::1\](?::([0-9]{1,5}))?|'
    r'::1)$',
    re.IGNORECASE
)

def _valid_host_header(value):
    """Host on oltava loopback ja mahdollisen portin (1-65535). Torjuu DNS-rebindingin."""
    if not value or not isinstance(value, str):
        return False
    m = _HOST_RE.fullmatch(value.strip())
    if not m:
        return False
    port = m.group(1) or m.group(2)
    if port is not None:
        p = int(port)
        if not (1 <= p <= 65535):
            return False
    return True


def make_server(port=8377, host='127.0.0.1', token=None, allowed_origins=(),
                max_text=MAX_TEXT, max_workers=DEFAULT_MAX_WORKERS,
                max_connections=MAX_CONNECTIONS, token_map=None,
                tokens_provider=None,
                **check_kwargs):
    """Luo palvelin.

    token: vaadittu Bearer-tunnus /check-pyynnöille; None poistaa tunnuksen
    käytöstä (vain testeihin/kehitykseen - serve() käyttää aina tunnusta).
    token_map: {sovellus: tunnus} sovelluskohtainen todennus (staattinen).
    tokens_provider: funktio -> dict {sovellus: tunnus}, kutsutaan JOKA
    pyynnöllä: peruutus (tiedoston poisto) astuu voimaan ILMAN
    uudelleenkäynnistystä. Jos molemmat, provider yliajaa token_mapin.
    HUOM: vanha jaettu perus-tunnus on vain yksi rekisteröity tunnus
    muiden joukossa ('default') - se ei ohita sovelluskohtaista
    hallintaa, mutta sen poistaminen on yhtä tarkoituksellinen toimenpide.
    allowed_origins: sallitut Origin-arvot (esim. selainlaajennoksen tunniste).
    """
    if host not in LOOPBACK_HOSTS:
        raise ValueError(f'kielletty osoite: {host!r} - vain loopback sallittu')
    allowed_origins = frozenset(allowed_origins)
    static_tokens = tuple(token_map.values()) if token_map else ()
    if token is not None:
        static_tokens = (token,) + static_tokens

    def current_tokens():
        """None = todennus pois (dev); tuplu (mahd. tyhjä) = vaaditaan."""
        if tokens_provider is not None:
            try:
                return tuple(tokens_provider().values())
            except Exception:
                return ()  # lukitusvirhe: ei tunnuksia = kaikki evätään
        if static_tokens:
            return static_tokens
        return None
    engine_sem = threading.BoundedSemaphore(max_workers)
    conn_sem = threading.BoundedSemaphore(max_connections)

    class Handler(BaseHTTPRequestHandler):
        server_version = 'Punakyna/0.5'
        protocol_version = 'HTTP/1.1'

        def version_string(self):
            # Älä vuoda Python-alustan versionumeroa Server-otsakkeessa.
            return self.server_version

        def send_error(self, code, message=None, explain=None):
            # Torju oletus-HTML-virhesivujen ja MIME-nuuskinnan riskit sisäänrakennetuissa virheissä.
            # Kuten oletuskäsittelijä: sulje yhteys, koska pyynnön runkoa ei ole
            # luettu ja se rikkoisi seuraavan pyynnön kehystyksen.
            self.close_connection = True
            self._send(code, {'error': message or str(code)}, close=True)

        def setup(self):
            super().setup()
            self.connection.settimeout(READ_TIMEOUT)

        def log_message(self, fmt, *args):
            pass  # tekstisisältöä ei logata

        def _send(self, code, payload, close=False):
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            # Turvaotsakkeet: estä MIME-tyypin nuuskiminen ja upotus kehyksiin selaimessa.
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            if close:
                self.send_header('Connection', 'close')
            # Tietoisesti EI Access-Control-Allow-Origin -otsaketta:
            # sivustojen ei pidä lukea vastauksia selaimessa.
            self.end_headers()
            if self.command != 'HEAD':  # HEAD-vastauksessa ei ole runkoa
                self.wfile.write(body)

        def _reject(self):
            self._send(404, {'error': 'tuntematon polku'})

        def _drain_available(self, cap=MAX_BODY):
            """Lue saapunut runkopuskuri blokkaamatta (estää RST:n, kun
            vastataan virheellä lukematta koko runkoa)."""
            drained = 0
            try:
                while drained < cap:
                    r, _, _ = select.select([self.connection], [], [], 0)
                    if not r:
                        break
                    chunk = self.connection.recv(min(65536, cap - drained))
                    if not chunk:
                        break
                    drained += len(chunk)
            except OSError:
                pass

        def _common_guards(self):
            """Palauttaa virhevastauksen tai None jos pyyntö sallittu."""
            if not _valid_host_header(self.headers.get('Host', '')):
                return 403, {'error': 'virheellinen Host-otsake'}
            origin = self.headers.get('Origin')
            if origin is not None and origin not in allowed_origins:
                return 403, {'error': 'Origin ei sallittu'}
            return None

        def do_OPTIONS(self):
            self._send(404, {'error': 'tuntematon polku'})  # ei preflight-tukea

        def do_GET(self):
            guard = self._common_guards()
            if guard:
                return self._send(*guard)
            if self.path == '/health':
                self._send(200, {'status': 'ok', 'service': 'punakyna'})
            elif self.path == '/check':
                self._send(405, {'error': 'käytä POST /check'})
            else:
                self._reject()

        do_PUT = do_DELETE = do_PATCH = _reject

        def do_POST(self):
            if self.path != '/check':
                return self._reject()
            guard = self._common_guards()
            if guard:
                return self._send(*guard)
            valid = current_tokens()
            if valid is not None:
                auth = self.headers.get('Authorization', '')
                if not any(hmac.compare_digest(auth, f'Bearer {t}')
                           for t in valid):
                    return self._send(401, {'error': 'tunnus puuttuu tai on virheellinen'})
            ctype = (self.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            if ctype != 'application/json':
                # Torjuu selaimen cross-origin "simple requestit"
                # (text/plain, application/x-www-form-urlencoded).
                return self._send(415, {'error': 'vaaditaan Content-Type: application/json'})
            raw_length = self.headers.get('Content-Length')
            if raw_length is None:
                return self._send(411, {'error': 'Content-Length puuttuu'})
            try:
                length = int(raw_length)
            except ValueError:
                self._drain_available()
                self.close_connection = True
                return self._send(400, {'error': 'virheellinen Content-Length'}, close=True)
            if length < 0 or length > MAX_BODY:
                self._drain_available()
                self.close_connection = True
                return self._send(413, {'error': 'liian suuri pyyntö'})
            try:
                payload = json.loads(self.rfile.read(length) or b'{}')
                text = payload['text']
                if not isinstance(text, str):
                    raise TypeError
            except (ValueError, TypeError, KeyError):
                return self._send(400, {'error': 'odotettiin JSON: {"text": "..."}'})
            if len(text) > max_text:
                return self._send(413, {'error': f'teksti yli {max_text} merkkiä'})
            with engine_sem:  # rajaa samanaikaiset tarkistukset
                try:
                    suggs = check_text(
                        text,
                        use_rules=payload.get('use_rules', check_kwargs.get('use_rules', True)),
                        use_spelling=payload.get('use_spelling', check_kwargs.get('use_spelling', True)),
                        use_parser=payload.get('use_parser', check_kwargs.get('use_parser', False)),
                        style_profile=payload.get('style_profile', check_kwargs.get('style_profile')),
                    )
                except (RuntimeError, ValueError) as e:
                    # esim. parser-taso pyydetty mutta stanza puuttuu
                    return self._send(400, {'error': str(e)})
                except Exception as e:
                    # moottorivika (esim. libvoikko-taajama puuttuu):
                    # siisti JSON-virhe, ei tracebackia lokiin per pyyntö
                    return self._send(500, {'error': 'tarkistus epäonnistui: '
                                            f'{type(e).__name__}'})
            self._send(200, {'suggestions': suggestions_as_dicts(suggs)})

    class BoundedServer(ThreadingHTTPServer):
        daemon_threads = True
        request_queue_size = 32  # liikakuorma saa ECONNREFUSEDin äärettömän kasvun sijaan

        def process_request(self, request, client_address):
            # Todellinen rajoitus ENNEN saikeen syntyä: yli rajan yhteys
            # saa 503:n ja suljetaan ilman uutta säiettä.
            if not conn_sem.acquire(blocking=False):
                try:
                    body = json.dumps(
                        {'error': 'palvelin kuormitettu, yrita hetken kuluttua uudelleen'},
                        ensure_ascii=False).encode('utf-8')
                    request.sendall(
                        b'HTTP/1.1 503 Service Unavailable\r\n'
                        b'Content-Type: application/json; charset=utf-8\r\n'
                        + f'Content-Length: {len(body)}\r\n'.encode()
                        + b'Connection: close\r\n\r\n' + body)
                except OSError:
                    pass
                self.shutdown_request(request)
                return
            try:
                super().process_request(request, client_address)
            except Exception:
                conn_sem.release()
                raise

        def process_request_thread(self, request, client_address):
            try:
                super().process_request_thread(request, client_address)
            finally:
                conn_sem.release()

    return BoundedServer((host, port), Handler)


def preflight_engine():
    """Lataa moottori käynnistyksessä: asennusvika näkyy heti, ei vasta
    ensimmäisestä pyynnöstä tracebackina. Onnistuessaan täyttää
    get_voikko:n välimuistin, joten ensimmäinen pyyntö on nopea."""
    try:
        from .backend_voikko import get_voikko
        get_voikko()
    except Exception as e:
        raise SystemExit(
            'Punakynä-palvelin ei käynnisty: libvoikko-taajamaa tai suomen '
            'sanastoa ei löydy.\n'
            f'Virhe: {type(e).__name__}: {e}\n'
            'Asenna (macOS): brew install libvoikko voikko-fi\n'
            'Asenna (Debian/Ubuntu): sudo apt install libvoikko1 voikko-fi\n'
            'Jos asennettuna epävakiopolkuun:\n'
            '  PUNAKYNA_LIBVOIKKO_PATH=/kirjaston/hakemisto\n'
            '  PUNAKYNA_VOIKKO_DICTIONARY_PATH=/polku/jossa/5/mor-standard'
        ) from e


def serve(port=8377, host='127.0.0.1', token_path=TOKEN_PATH):
    load_or_create_token(token_path)  # varmista perus-tunnuksen olemassaolo
    preflight_engine()
    srv = make_server(port=port, host=host,
                      tokens_provider=lambda: load_all_tokens(
                          fallback_path=token_path))
    print(f'Punakynä kuuntelee osoitteessa http://{srv.server_address[0]}:{srv.server_address[1]} (vain loopback)')
    print(f'Tunnus: {Path(token_path)} (oikeudet 0600) - sovitukset lukevat sen sieltä.')
    srv.serve_forever()
