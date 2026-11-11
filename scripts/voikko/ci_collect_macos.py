#!/usr/bin/env python3
"""CI-apuri (macOS): kokoaa brew-asennetun voikko-pinon bundle-valmisteluun.

Tehdaan GitHub Actions macos-ajajalla (brew saatavilla):
  1. kopioi libvoikko + libhfstospell + NIIDEN reaaliaikaiset dylib-
     riippuvuudet (otool -L -sulkeuma, pois lukien /usr/lib ja /System)
  2. kopioi voikko-fi-sanasto (brew:n libvoikko-formula asentaa sen
     resourcesta $PREFIX/lib/voikko)
  3. hakee KAIKKIEN mukana tulevien komponenttien lahdepaketit
     dist/corresponding-sources/-hakemistoon (pinatut URLit + sha256
     brew:n kaavoista) ja kopioi niiden lisenssitiedostot bundleen
  4. kirjoittaa licenses/SOURCES.txt:n TODELLISILLA versioilla ja
     tarkistussummilla
  5. kutsuu bundle_native.py --platform macos (install_name_tool -korjaukset)

Ei suoriteta kehityskoneella: ajaa vain CI:n macos-latest -ajajalla.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
STAGING_LIBS = os.path.join(HERE, '.ci-staging', 'lib')
STAGING_LIC = os.path.join(HERE, '.ci-staging', 'licenses')
DIST_SRC = os.path.normpath(os.path.join(HERE, '..', '..',
                                         'dist', 'corresponding-sources'))
SYSTEM_PREFIXES = ('/usr/lib/', '/System/', '@loader_path/', '@rpath/',
                   '@executable_path/')
BREW_PKGS = ['libvoikko', 'hfstospell']  # sanasto tulee libvoikko-resurssista


def sh(*args):
    return subprocess.run(list(args), check=True, capture_output=True,
                          text=True).stdout.strip()


def brew_prefix(pkg):
    return sh('brew', '--prefix', pkg)


def brew_info(pkg):
    out = sh('brew', 'info', '--json=v2', pkg)
    return json.loads(out)['formulae'][0]


def _otool_deps(lib):
    out = sh('otool', '-L', lib)
    return [line.strip().split(' ', 1)[0]
            for line in out.splitlines()[1:] if line.strip()]


def _resolve_rpath(ref, referrer):
    """@rpath-vittaus: etsi ensin vittaavan kirjaston hakemistosta."""
    name = ref.split('/', 1)[1]
    cand = os.path.join(os.path.dirname(referrer), name)
    return cand if os.path.isfile(cand) else None


def stage_dylibs():
    """Kopioi voikko-dylibit + TAYSI riippuvuussulkeuma aliaksineen.

    - @rpath-vittaukset (esim. ICU:n libicudata) ratkaistaan vittaavan
      kirjaston hakemistosta
    - jokainen VIITATTU tiedostonimi (soname, esim. liblz4.1.dylib)
      kopioidaan myos, vaikka todellinen tiedosto olisi versioidumpi
      (liblz4.1.10.0.dylib): dyld etsii tasan viittattya nimea
    """
    os.makedirs(STAGING_LIBS, exist_ok=True)
    seeds = []
    for pkg in BREW_PKGS:
        libdir = os.path.join(brew_prefix(pkg), 'lib')
        for name in sorted(os.listdir(libdir)):
            if name.endswith('.dylib'):
                seeds.append(os.path.join(libdir, name))

    staged = {}          # basename -> True
    # jono pareina (viitattu nimi, polku): jokainen kirjasto kopioidaan
    # vain SILLA NIMELLA jolla jokin viittaa siihen (dyld etsii tasan
    # viitattua nimea). Nain esim. libicudata paattyy pakettiin vain
    # kerran (libicudata.79.dylib), ei seka versionimella etta sonamella.
    queue = [(os.path.basename(s), s) for s in seeds]
    seen_real = set()
    while queue:
        ref_name, path = queue.pop()
        real = os.path.realpath(path)
        if not os.path.isfile(real):
            continue
        if ref_name not in staged:
            shutil.copyfile(real, os.path.join(STAGING_LIBS, ref_name))
            staged[ref_name] = True
        if real in seen_real:
            continue
        seen_real.add(real)
        deps = _otool_deps(real)
        print('deps(%s): %s' % (os.path.basename(real),
                                ', '.join(deps) or '-'))
        for dep in deps:
            if not dep or dep.startswith(('/usr/lib/', '/System/')):
                continue
            if dep.startswith(('@rpath/', '@loader_path/',
                               '@executable_path/')):
                tgt = _resolve_rpath(dep, real)
                if not tgt:
                    print('VAROITUS: dynaaminen viittaus ratkaisematta:',
                          dep, 'viittaajalta', real, file=sys.stderr)
                    continue
            elif dep.startswith('@'):
                continue
            else:
                tgt = dep if os.path.isfile(dep) else None
                if not tgt:
                    print('VAROITUS: riippuvuutta ei loydy:', dep,
                          file=sys.stderr)
                    continue
            queue.append((os.path.basename(dep), tgt))
    return sorted(os.listdir(STAGING_LIBS))


def fetch_sources_and_licenses(pkgs_extra):
    """Hae lahdepaketit + poimi lisenssitiedostot. Palauta rivit SOURCES.txt:aan."""
    os.makedirs(DIST_SRC, exist_ok=True)
    os.makedirs(STAGING_LIC, exist_ok=True)
    rows = []
    seen_pkgs = set()
    for pkg in BREW_PKGS + pkgs_extra:
        if pkg in seen_pkgs:
            continue
        seen_pkgs.add(pkg)
        info = brew_info(pkg)
        name = info['name']
        version = info['versions']['stable']
        license_id = info.get('license') or 'tuntematon'
        url = info['urls']['stable']['url']
        sha = info['urls']['stable'].get('checksum', '')
        fn = os.path.basename(url)
        dst = os.path.join(DIST_SRC, fn)
        if not os.path.exists(dst):
            print('ladataan', url)
            urllib.request.urlretrieve(url, dst)
        import hashlib
        got = hashlib.sha256(open(dst, 'rb').read()).hexdigest()
        if sha and got != sha:
            sys.exit('sha256-virhe %s: %s != %s' % (fn, got, sha))
        rows.append((name, version, license_id, url, sha or got))
        # lisenssitiedostot lahdepaketista
        with tempfile.TemporaryDirectory() as td:
            try:
                with tarfile.open(dst) as tf:
                    tf.extractall(td, filter='data')
            except Exception as e:
                print('VAROITUS: purku epaonnistui %s: %s' % (fn, e),
                      file=sys.stderr)
                continue
            for root, _d, files in os.walk(td):
                for f in files:
                    if re.match(r'(?i)^(copying|license|licence|notice)'
                                r'(\.\w+)?$', f):
                        src_f = os.path.join(root, f)
                        if os.path.getsize(src_f) == 0:
                            continue  # esim. zstd:n tyhja LICENSE-tayte
                        dstname = '%s.%s' % (name, f)
                        if not os.path.exists(os.path.join(STAGING_LIC,
                                                           dstname)):
                            shutil.copyfile(src_f, os.path.join(STAGING_LIC,
                                                                dstname))
    return rows


def fetch_voikko_fi_resource():
    """voikko-fi-sanaston lahdepaketti libvoikko-kaavan resourcesta.

    brew-formula asentaa sanaston resourcesta, joten se ei nay pakettien
    riippuvuuksissa eika formula-API:n resources-kentassa - luetaan
    kaavan .rb-tiedostosta suoraan (url + sha256).
    """
    rb = urllib.request.urlopen(
        'https://raw.githubusercontent.com/Homebrew/homebrew-core/HEAD/'
        'Formula/lib/libvoikko.rb').read().decode('utf-8')
    m = re.search(r'resource "voikko-fi" do.*?url "([^"]+)".*?'
                  r'sha256 "([0-9a-f]{64})"', rb, re.S)
    if not m:
        sys.exit('voikko-fi-resurssia ei loydy libvoikko-kaavasta')
    url, sha = m.group(1), m.group(2)
    dst = os.path.join(DIST_SRC, os.path.basename(url))
    if not os.path.exists(dst):
        print('ladataan', url)
        urllib.request.urlretrieve(url, dst)
    import hashlib
    got = hashlib.sha256(open(dst, 'rb').read()).hexdigest()
    if got != sha:
        sys.exit('sha256-virhe voikko-fi: %s != %s' % (got, sha))
    version = re.search(r'voikko-fi[._-]v?(\d+(?:\.\d+)+)',
                        os.path.basename(url)).group(1)
    # lisenssitiedosto paketista bundleen
    with tempfile.TemporaryDirectory() as td:
        with tarfile.open(dst) as tf:
            tf.extractall(td, filter='data')
        for root, _d, files in os.walk(td):
            for f in files:
                if re.match(r'(?i)^(copying|license|licence)(\.\w+)?$', f):
                    src_f = os.path.join(root, f)
                    if os.path.getsize(src_f) > 0:
                        shutil.copyfile(src_f, os.path.join(
                            STAGING_LIC, 'voikko-fi.%s' % f))
                        return ('voikko-fi', version, 'GPL-2.0-or-later',
                                url, sha)
    return ('voikko-fi', version, 'GPL-2.0-or-later', url, sha)


def main():
    libs = stage_dylibs()
    print('dylib-kirjastot mukana:', ', '.join(libs))

    # sanasto: libvoikko-formula asentaa voikko-fi-resurssin prefixin alle
    prefix = brew_prefix('libvoikko')
    dict_src = os.path.join(prefix, 'lib', 'voikko')
    if not os.path.isdir(os.path.join(dict_src, '5')):
        alt = os.path.join(prefix, 'share', 'voikko')
        if os.path.isdir(os.path.join(alt, '5')):
            dict_src = alt
        else:
            sys.exit('voikko-fi-sanastoa ei loydy: %s' % dict_src)

    # riippuvuusdylibien omistavat brew-paketit lisenssitietoja varten
    extra = []
    for lib in libs:
        if 'libb2' in lib:
            extra.append('libb2')
        if 'libarchive' in lib:
            extra.append('libarchive')
        if 'libicu' in lib:
            extra.append('icu4c@79')
        if 'libzstd' in lib:
            extra.append('zstd')
        if 'liblz4' in lib:
            extra.append('lz4')
        if 'liblzma' in lib or 'libxz' in lib:
            extra.append('xz')
    rows = fetch_sources_and_licenses(sorted(set(extra)))
    rows.append(fetch_voikko_fi_resource())

    lines = [
        'Tekstitys proofreading: mukana tulevat binäärit ja '
        'niiden lähteet',
        '=' * 74,
        '',
        'Tämä paketti sisältää alla luetellut käännetyt komponentit '
        '(macOS/arm64)',
        'sekä voikko-fi-sanaston. Vastaava lähdekoodi on vapaasti '
        'saatavilla',
        'kustakin osoitteesta; tarkat lähdepaketit toimitetaan '
        'paketin mukana',
        'jakelukanavassa (corresponding-sources/). Paketin täsmällinen',
        'rakennusohje on Tekstitys-lähdevarastossa:',
        'scripts/voikko/ci_collect_macos.py,',
        'bundle_native.py sekä .github/workflows/release.yml.',
        '',
    ]
    for name, version, license_id, url, sha in rows:
        lines.append('%s %s (%s)' % (name, version, license_id))
        lines.append('  Lähde: %s' % url)
        lines.append('  sha256: %s' % sha)
        lines.append('')
    with open(os.path.join(STAGING_LIC, 'SOURCES.txt'), 'w',
              encoding='utf-8') as f:
        f.write('\n'.join(lines))

    r = subprocess.run(
        [sys.executable, os.path.join(HERE, 'bundle_native.py'),
         '--platform', 'macos', '--libs', STAGING_LIBS,
         '--dict', dict_src, '--licenses', STAGING_LIC])
    sys.exit(r.returncode)


if __name__ == '__main__':
    main()
