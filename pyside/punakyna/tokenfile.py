"""Jaettu tunnusten käsittely (palvelin + asiakkaat).

Ei riippuvuuksia moottoriin - sovitukset voivat tuoda tämän erikseen.

Sovelluskohtaiset tunnukset (per-app enrollment): jokaiselle sovellukselle
oma tiedosto ~/.config/punakyna/tokens/<sovellus> (0600). Peruutus =
tiedoston poisto. Yksi perus-tunnus (~/.config/punakyna/token) säilyy
taaksepäin yhteensopivana, kun sovelluksia ei ole eritelty.
"""
import os
import re
import secrets
import stat
from pathlib import Path

MIN_TOKEN_LEN = 32  # lyhyempi tunnus = rikkinäinen/partial, hylätään

TOKEN_PATH = Path.home() / '.config' / 'punakyna' / 'token'
TOKENS_DIR = Path.home() / '.config' / 'punakyna' / 'tokens'

_APP_NAME_RE = re.compile(r'^[a-zA-Z0-9](?:[a-zA-Z0-9_\-\.]{0,62}[a-zA-Z0-9])?$')


class TokenError(RuntimeError):
    """Tunnustiedosto on epäluotettava - älä käytä, pakota uudelleenluonti."""


def _validate_and_read(path):
    path = Path(path)
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        raise TokenError(f'tunnustiedosto on symbolinen linkki: {path}')
    if not stat.S_ISREG(st.st_mode):
        raise TokenError(f'tunnustiedosto ei ole tavallinen tiedosto: {path}')
    if stat.S_IMODE(st.st_mode) != 0o600:
        raise TokenError(
            f'tunnustiedoston oikeudet {oct(stat.S_IMODE(st.st_mode))} '
            f'(vaaditaan 0o600): {path} - korjaa tai poista tiedosto')
    token = path.read_text(encoding='utf-8').strip()
    if len(token) < MIN_TOKEN_LEN:
        raise TokenError(f'tunnus puutteellinen tai liian lyhyt: {path}')
    return token


def _create(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    # Atominen luonti: O_EXCL estää kilpailun, oikeudet syntyvät heti 0600:na.
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(token + '\n')
    return token


def load_or_create_token(path=TOKEN_PATH):
    """Lue tunnus tiedostosta; luo uusi atomisesti (0600) jos puuttuu.

    Hylkää (TokenError): symbolinen linkki, liian väljät oikeudet (!= 0600),
    tyhjä tai liian lyhyt (partial) tunnus. Epäluotettavaa tunnusta ei
    käytetä koskaan - poista tiedosto ja luo uusi.
    """
    path = Path(path)
    try:
        return _validate_and_read(path)
    except FileNotFoundError:
        return _create(path)


def _validate_app_name(app):
    """Tarkista sovellustunniste: sallitut merkit ja pituus, ei polkuhyppayksia."""
    # Turvatarkistus: sallijalista estää hakemistotraversaalin, tiedostonimet
    # ohjausmerkeillä (CRLF/nollatavu), piilotiedostot ja pituuden ylitykset.
    if not isinstance(app, str) or not _APP_NAME_RE.fullmatch(app):
        raise TokenError(f'virheellinen sovellustunniste: {app!r}')
    return app


def load_or_create_app_token(app, tokens_dir=None):
    """Sovelluskohtainen tunnus: tokens/<app> (0600)."""
    _validate_app_name(app)
    return load_or_create_token(Path(tokens_dir or TOKENS_DIR) / app)


def load_all_tokens(tokens_dir=None, fallback_path=None):
    """Palauta {sovellus: tunnus} kaikista hyväksytyistä tunnustiedostoista.

    Perus-tunnus (fallback_path) rekisteröidään nimellä 'default', jos
    se on olemassa; tokens/-hakemiston tiedostot ovolemiaan nimeltään.
    Virheelliset tiedostot ohitetaan (eivät kaada palvelinta) mutta
    jätetään huomiotta - niiden korjaus on käyttäjän tehtävä.
    """
    out = {}
    try:
        out['default'] = _validate_and_read(fallback_path or TOKEN_PATH)
    except (FileNotFoundError, TokenError):
        pass
    tokens_dir = Path(tokens_dir or TOKENS_DIR)
    if tokens_dir.is_dir():
        for p in sorted(tokens_dir.iterdir()):
            try:
                _validate_app_name(p.name)
                out[p.name] = _validate_and_read(p)
            except (FileNotFoundError, TokenError, OSError):
                continue
    return out


def revoke_app_token(app, tokens_dir=None):
    """Peru sovelluksen tunnus poistamalla tiedosto. True jos poistettiin."""
    _validate_app_name(app)
    base_dir = Path(tokens_dir or TOKENS_DIR).resolve()
    p = (base_dir / app).resolve()
    if p.parent != base_dir:
        raise TokenError(f'virheellinen sovelluspolku: {app!r}')
    try:
        p.unlink()
        return True
    except FileNotFoundError:
        return False


def read_app_token(app, tokens_dir=None):
    """Lue sovelluksen tunnus LUOMATTA sitä (asiakaspuoli).

    Enrollment on erillinen hallintatoimi (CLI --enroll-app): asiakas vain
    lukee. Puuttuva/virheellinen tunnus = ei rekisteröity -> FileNotFoundError
    tai TokenError.
    """
    _validate_app_name(app)
    return _validate_and_read(Path(tokens_dir or TOKENS_DIR) / app)
