import argparse
import json
import sys

from .pipeline import check_text, suggestions_as_dicts


def main(argv=None):
    p = argparse.ArgumentParser(
        prog='punakyna', description='Suomen kielen oikolukija: tarkistaa tekstin '
        'ja palauttaa ehdotuksia (ei muuta tekstia).')
    p.add_argument('file', nargs='?', help='tekstitiedosto (oletus: stdin)')
    p.add_argument('--json', action='store_true', help='tulosta JSON')
    p.add_argument('--serve', action='store_true', help='käynnistä paikallinen HTTP-rajapinta (vain loopback)')
    p.add_argument('--port', type=int, default=8377, help='rajapinnan portti (oletus 8377)')
    p.add_argument('--no-rules', action='store_true', help='vain oikeinkirjoitus')
    p.add_argument('--parser', action='store_true',
                   help='kokeellinen jäsentävä taso (vaatii stanza+fin_tdt, raskas)')
    p.add_argument('--enroll-app', metavar='NIMI',
                   help='rekisteröi sovelluksen tunnus (tulostaa tiedostopolun)')
    p.add_argument('--revoke-app', metavar='NIMI',
                   help='peruu sovelluksen tunnuksen (voimaan heti, palvelinta ei käynnistetä uudelleen)')
    p.add_argument('--list-apps', action='store_true',
                   help='listaa rekisteröidyt sovellukset')
    p.add_argument('--no-spelling', action='store_true', help='vain saannot')
    p.add_argument('--prefer-active', action='store_true', help='valinnainen tyylivinkki: tuo tekijä näkyviin')
    p.add_argument('--narrator', choices=['any', 'mina', 'me'], default='any', help='valittu kertojan persoona (tyylivinkit)')
    p.add_argument('--reader', choices=['any', 'sina', 'te'], default='any', help='valittu lukijan puhuttelu (tyylivinkit)')
    p.add_argument('--max-sentence-words', type=int, default=0, metavar='N',
                   help='tyylivinkki: huomauta yli N sanan virkkeistä (0 = pois; Kotus: 15)')
    p.add_argument('--profile', choices=['standard', 'virkakieli'], default='standard',
                   help='nimetty tyyliprofiili (virkakieli: aktiivi + virkkeet enintaan 15 sanaa)')
    args = p.parse_args(argv)
    from dataclasses import asdict
    from .style import StyleProfile
    base = asdict(StyleProfile.preset(args.profile))
    style = dict(prefer_active=args.prefer_active or base['prefer_active'],
                 narrator=args.narrator, reader=args.reader,
                 max_sentence_words=args.max_sentence_words or base['max_sentence_words'])
    if args.enroll_app or args.revoke_app or args.list_apps:
        from .tokenfile import (load_or_create_app_token, load_all_tokens,
                                revoke_app_token)
        if args.enroll_app:
            load_or_create_app_token(args.enroll_app)
            from .tokenfile import TOKENS_DIR
            print(f'Sovellus "{args.enroll_app}" rekisteröity: '
                  f'{TOKENS_DIR / args.enroll_app} (0600). Sovitin lukee '
                  f'tunnuksen tiedostosta. Voimaan heti.')
            return 0
        if args.revoke_app:
            ok = revoke_app_token(args.revoke_app)
            print((f'Sovelluksen "{args.revoke_app}" tunnus peruttu - voimaan '
                   f'heti ilman uudelleenkäynnistystä.' if ok else
                   f'Sovellusta "{args.revoke_app}" ei ollut rekisteröitynä.'))
            return 0 if ok else 1
        apps = load_all_tokens()
        print('Rekisteröidyt sovellukset: ' + (', '.join(sorted(apps)) or '(ei mitään)'))
        return 0
    if args.serve:
        from .api import serve
        serve(port=args.port, style_profile=style)
        return 0
    text = open(args.file, encoding='utf-8').read() if args.file else sys.stdin.read()
    suggs = check_text(text, use_rules=not args.no_rules,
                       use_parser=args.parser,
                       use_spelling=not args.no_spelling,
                       style_profile=style)
    if args.json:
        print(json.dumps(suggestions_as_dicts(suggs), ensure_ascii=False, indent=2))
    else:
        if not suggs:
            print('Ei havaittuja virheitä.')
        for s in suggs:
            frag = text[s.start:s.end]
            print(f'[{s.severity}/{s.rule}] merkit {s.start}-{s.end}: "{frag}"')
            print(f'    {s.message}')
            if s.replacements:
                print(f'    ehdotukset: {", ".join(s.replacements)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
