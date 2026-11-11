#!/usr/bin/env python3
"""Kokoa natiivikirjastot + sanasto + lisenssit bundle/-valmisteluun.

Käyttö:
    bundle_native.py --platform linux|macos \
        --libs DIR --dict DIR --licenses DIR

--libs:       hakemisto, jossa libvoikko + sen ajonaikaiset riippuvuudet
              (esim. libhfstospell). Symbolilinkit kopioidaan sisältönä.
--dict:       hakemisto, joka sisältää mor-standard-hakemiston (5/).
--licenses:   hakemisto, jonka lisenssi-/lähde­tiedostot kopioidaan sellaisenaan
              paketin licenses/-polkuun (GPL-2.0+-ohjelmatekstit, Apache-2.0,
              copyright-tiedostot, SOURCES.txt lähdepaketteineen).

macOS: kirjoittaa dylibien install namet @loader_path-suhteisiksi
(ajetaan macOS:ssä / CI:ssä). Linux: riippuvuudet lataa
voikko_gc.load_voikko_library ennakolta; rpath-muutoksia ei tarvita.
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = os.path.join(HERE, 'bundle')


def _copy_real(src, dst_dir, also_as=()):
    """Kopioi kirjasto todellisena tiedostona + halutut linkkinimet."""
    real = os.path.realpath(src)
    name = os.path.basename(src)
    os.makedirs(dst_dir, exist_ok=True)
    target = os.path.join(dst_dir, name)
    shutil.copyfile(real, target)
    for alias in also_as:
        if alias != name:
            shutil.copyfile(real, os.path.join(dst_dir, alias))
    return target


def _macos_fixups(libdir):
    """@loader_path-korjaukset jokaiseen bundlehakemiston dylibiin."""
    libs = [os.path.join(libdir, f) for f in sorted(os.listdir(libdir))
            if f.endswith('.dylib')]
    for lib in libs:
        name = os.path.basename(lib)
        subprocess.run(['install_name_tool', '-id', '@loader_path/' + name,
                        lib], check=True)
        out = subprocess.run(['otool', '-L', lib], check=True,
                             capture_output=True, text=True).stdout
        for line in out.splitlines()[1:]:
            dep = line.strip().split(' ', 1)[0]
            if not dep or dep.startswith(('/usr/lib/', '/System/',
                                          '@loader_path/',
                                          '@executable_path/')):
                continue
            # myos @rpath/... kirjoitetaan: dyld etsii tasan viitattua
            # nimea, ja viitattu basename on staging-kopioitu mukaan
            dep_name = os.path.basename(dep)
            if os.path.isfile(os.path.join(libdir, dep_name)):
                subprocess.run(['install_name_tool', '-change', dep,
                                '@loader_path/' + dep_name, lib], check=True)
            else:
                print('VAROITUS: riippuvuudelle ei pakattua tiedostoa:',
                      dep, 'kirjastossa', lib, file=sys.stderr)


def _macos_verify(libdir):
    """Varmista: jokaisen dylibin jokainen riippuvuus on @loader_path
    (pakattu) tai jarjestelmakirjasto. Muuten kaataa ajon. """
    bad = []
    for f in sorted(os.listdir(libdir)):
        if not f.endswith('.dylib'):
            continue
        lib = os.path.join(libdir, f)
        out = subprocess.run(['otool', '-L', lib], check=True,
                             capture_output=True, text=True).stdout
        for line in out.splitlines()[2:]:  # otsake + id ohitetaan
            dep = line.strip().split(' ', 1)[0]
            if not dep:
                continue
            if dep.startswith(('/usr/lib/', '/System/', '@loader_path/')):
                continue
            bad.append('%s -> %s' % (f, dep))
    if bad:
        for b in bad:
            print('KATKONAINEN VIITTAUS:', b, file=sys.stderr)
        sys.exit('dylib-sulkeuma epataydellinen: %d viittausta' % len(bad))



def _macos_sign_and_verify(libdir):
    """Sign final bytes AFTER every install_name_tool edit.

    Relinking invalidates Homebrew's existing ad-hoc page hashes. On arm64
    macOS this can SIGKILL the host at dlopen, outside Python exceptions.
    """
    from verify_macos_signatures import verify_bytes
    libs = [os.path.join(libdir, name) for name in sorted(os.listdir(libdir))
            if name.endswith('.dylib')]
    for lib in libs:
        subprocess.run(['codesign', '--force', '--sign', '-',
                        '--timestamp=none', lib], check=True)
    for lib in libs:
        subprocess.run(['codesign', '--verify', '--strict', '--verbose=2',
                        lib], check=True)
        with open(lib, 'rb') as source:
            verify_bytes(source.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--platform', choices=('linux', 'macos'), required=True)
    ap.add_argument('--libs', required=True)
    ap.add_argument('--dict', required=True)
    ap.add_argument('--licenses', required=True)
    args = ap.parse_args()

    libdir = os.path.join(BUNDLE, 'native', args.platform, 'lib')
    shutil.rmtree(os.path.join(BUNDLE, 'native', args.platform),
                  ignore_errors=True)

    # Kukin kirjasto kerran, todellisen tiedoston nimella (soname).
    # Symbolilinkien aliaset ohitetaan: loytyminen toimii, koska
    # _CANDIDATES kattaa seka .so.1- etta .1.dylib-nimet.
    seen = set()
    copied = []
    for entry in sorted(os.listdir(args.libs)):
        p = os.path.join(args.libs, entry)
        if not (entry.endswith('.dylib') or '.so' in entry):
            continue
        if not os.path.isfile(p):
            continue
        real = os.path.realpath(p)
        real_name = os.path.basename(real)
        if real_name in seen:
            continue
        seen.add(real_name)
        copied.append(_copy_real(p, libdir))
    if not any('libvoikko' in os.path.basename(c) for c in copied):
        sys.exit('libvoikko puuttuu --libs-hakemistosta')

    dict_dst = os.path.join(BUNDLE, 'native', 'dict', '5')
    shutil.rmtree(os.path.join(BUNDLE, 'native', 'dict'), ignore_errors=True)
    os.makedirs(dict_dst, exist_ok=True)
    src_dict = args.dict
    if os.path.isdir(os.path.join(src_dict, '5')):
        src_dict = os.path.join(src_dict, '5')
    for name in sorted(os.listdir(src_dict)):
        shutil.copytree(os.path.join(src_dict, name),
                        os.path.join(dict_dst, name))
    if not os.path.isdir(os.path.join(dict_dst, 'mor-standard')):
        sys.exit('mor-standard puuttuu --dict-hakemistosta')

    lic_dst = os.path.join(BUNDLE, 'licenses')
    shutil.rmtree(lic_dst, ignore_errors=True)
    shutil.copytree(args.licenses, lic_dst)

    if args.platform == 'macos':
        _macos_fixups(libdir)
        _macos_verify(libdir)
        _macos_sign_and_verify(libdir)
    print(BUNDLE)


if __name__ == '__main__':
    main()
