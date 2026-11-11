"""Valinnainen jäsentävä taso (OPT-IN, oletuksena pois).

Rakenneperusteiset kielioppitarkistukset riippuvuusparsinnalla:
  PSV_NUMBER   monikollinen nominatiivisubjekti + yksiköllinen persoonaverbi
  PRED_NUM     monikollinen subjekti + yksiköllinen nominatiivipredikatiivi
               (VISK §1284: predikatiivi kongruoi subjektin kanssa luvussa,
               myös puhekielessä kun verbin kongruenssi lipsuu - "Nää
               kriminaalit oli ääritapauksia"; yksipersoonaisen passiivin
               predikatiivi monikossa - "oltu kilttejä")
  PSV_PERSON   subjektin ja verbin persoonaero
  PNEG_CONNEG  kieltoverbi + persoonallinen pääverbin muoto
  PNEG_NUMBER  monikollinen kieltoverbi + yksiköllinen menneen ajan partisiippi
  PPERF_NUM    perfektin partisiipin lukukongruenssi: monikollinen menneen
               ajan partisiippi, vaikka subjekti on yksiköllinen (nom.) tai
               eksistentiaalin partitiivisubjekti ("on osallistunut
               seitsemän kilpailijaa", ei *"osallistuneet")

Tausta ja provenienssi (TÄRKEÄÄ, ei sekoitettava):
- Backend NYT: Stanza (Stanford NLP Group, Apache-2.0-koodi) fin_tdt-malli,
  joka on opetettu UD_Finnish-TDT-puupankilla (TurkuNLP:n ylläpitämä aineisto,
  CC BY-SA 4.0). Mallin itsensä lisenssi varmistettava ennen jakelua.
- TurkuNLP:n OMA pipeline (Turku-neural-parser-pipeline) on arkistoitu
  5/2024; TurkuNLP suosittelee Trankit + Finnish-TDT -mallia seuraajaksi
  (http://turkunlp.org/Turku-neural-parser-pipeline/). Trankit-paikka on
  varattu backendiksi, mutta sitä EI ole mitattu: xlm-roberta-base ei
  mahdu hiekkalaatikon muistiin (1,75 Gt) - vaatii isomman koneen/Macin.
- MITATUT luvut (2026-11-03, ks. docs/research.md): MultiBLiMP-fi
  sääntö+parseri - SV-P 122/400 virhettä (30,5 %) / 3 oikeaa (0,8 %),
  SV-# 75/400 (18,8 %) / 0, SP-# 123/300 (41,0 %) / 3 (1,0 %);
  PPERF_NUM yksin SP-# 102/300. TDT dev (1364): kongruenssimittari
  4 (0,29 %), PPERF_NUM 0, PRED_NUM 1. Herkkyys minimaalipareissa
  ylittää todellisen käytön löydösprosentin.
"""
import threading

from .rules import Suggestion

# Jäsentävä taso on raskas (satoja Mt muistia, ~s/luokka CPU:ta):
# syötteen koko rajataan erikseen yleisestä MAX_TEXT-rajasta.
PARSER_MAX_TEXT = 20_000

_lock = threading.Lock()
_nlp = None


class ParserUnavailable(RuntimeError):
    """Jäsentävää tasoa pyydettiin, mutta backendiä ei ole asennettu."""


def get_parser():
    """Lataa Stanza-pipeline laiskasti. Heittää ParserUnavailable jos puuttuu."""
    global _nlp
    with _lock:
        if _nlp is None:
            try:
                import stanza
            except ImportError as e:
                raise ParserUnavailable(
                    'stanza ei asennettu: pip install stanza '
                    '(ja lataa fin_tdt-malli: stanza.download("fi", package="tdt"))'
                ) from e
            try:
                # download_method=None: EI koskaan hiljaista mallilatausta -
                # fin_tdt-mallin jakelulisenssi on varmistamatta, joten
                # painoksia ei haeta automaattisesti käyttäjän koneelle.
                _nlp = stanza.Pipeline(
                    'fi', package='tdt',
                    processors='tokenize,mwt,pos,lemma,depparse',
                    use_gpu=False, verbose=False,
                    download_method=None)
            except Exception as e:
                msg = (
                    'fin_tdt-mallia ei löydy paikallisesti. Mallin '
                    'jakelulisenssi on varmistamatta, joten Punakynä ei '
                    'lataa sitä automaattisesti. Asenna itse: '
                    "python -c \"import stanza; stanza.download('fi', "
                    "package='tdt')\""
                )
                raise ParserUnavailable(msg) from e
        return _nlp


def _feats(word):
    d = {}
    if word.feats:
        for kv in word.feats.split('|'):
            k, v = kv.split('=', 1)
            d[k] = v
    return d


def _span(word):
    """Sanan merkkipaikat koko tekstissä (Python-koodipisteet)."""
    tok = getattr(word, 'parent', None)
    if tok is not None and tok.start_char is not None:
        return tok.start_char, tok.end_char
    return 0, 0  # ei sijaintitietoa - ei pitäisi tapahtua raakatekstillä


def _voikko_participle_number(voikko, text):
    for a in voikko.analyze(text):
        if a.get('PARTICIPLE') == 'past_active':
            return a.get('NUMBER')
    return None


def check(text, voikko=None):
    """Palauta parsintapohjaiset ehdotukset tekstille.

    voikko: jaettu Voikko-instanssi morfologian varmistukseen (pakollinen:
    jäsentimen piirteet normalisoituvat virheellisellä syötteellä).
    """
    if voikko is None:
        raise ValueError('parser_tier.check vaatii voikko-instanssin')
    if len(text) > PARSER_MAX_TEXT:
        raise ParserUnavailable(
            f'jäsentävä taso: teksti {len(text)} merkkiä ylittää '
            f'{PARSER_MAX_TEXT} merkin rajan')
    doc = get_parser()(text)
    out = []
    for sent in doc.sentences:
        words = sent.words
        by_id = {w.id: w for w in words}
        for w in words:
            f = _feats(w)
            if w.deprel and w.deprel.startswith('nsubj'):
                head = by_id.get(w.head)
                if head is None or head.upos not in ('VERB', 'AUX'):
                    continue
                hf = _feats(head)
                if hf.get('Voice') == 'Pass':
                    continue
                if f.get('Case') == 'Par':
                    continue  # eksistentiaalilauseen partitiivi: yksikkö OK
                start, end = _span(head)
                if f.get('Number') == 'Plur' and f.get('Case') == 'Nom' \
                        and hf.get('Number') == 'Sing' \
                        and hf.get('Person') not in (None, '0'):
                    out.append(Suggestion(
                        rule='PSV_NUMBER', category='grammar', severity='error',
                        start=start, end=end,
                        message=f'Monikollinen subjekti "{w.text}", mutta verbi '
                                f'"{head.text}" yksikössä.',
                        replacements=[]))
                if f.get('Person') in ('1', '2', '3') \
                        and hf.get('Person') in ('1', '2', '3') \
                        and f['Person'] != hf['Person']:
                    out.append(Suggestion(
                        rule='PSV_PERSON', category='grammar', severity='error',
                        start=start, end=end,
                        message=f'Subjektin "{w.text}" persoona ({f["Person"]}.) '
                                f'ei vastaa verbiä "{head.text}" ({hf["Person"]}.).',
                        replacements=[]))
            # kieltoverbi -> pääverbi
            if f.get('Polarity') == 'Neg':
                head = by_id.get(w.head)
                if head is None or head.upos not in ('VERB', 'AUX'):
                    continue
                while head.lemma == 'olla' and _feats(head).get('VerbForm') == 'Fin':
                    nxt = by_id.get(head.head)
                    if nxt is None or nxt.upos not in ('VERB', 'AUX'):
                        break
                    head = nxt
                hf = _feats(head)
                start, end = _span(head)
                if hf.get('VerbForm') == 'Part':
                    if f.get('Number') == 'Plur' and hf.get('PartForm') == 'Past':
                        vn = _voikko_participle_number(voikko, head.text)
                        if vn == 'singular':
                            out.append(Suggestion(
                                rule='PNEG_NUMBER', category='grammar',
                                severity='error', start=start, end=end,
                                message=f'Monikollinen kieltoverbi "{w.text}", '
                                        f'mutta partisiippi "{head.text}" yksikössä.',
                                replacements=[]))
                elif hf.get('VerbForm') == 'Fin':
                    if hf.get('Person') in ('1', '2', '3') \
                            and hf.get('Person') != f.get('Person'):
                        out.append(Suggestion(
                            rule='PNEG_CONNEG', category='grammar',
                            severity='error', start=start, end=end,
                            message=f'Kieltoverbin "{w.text}" jälkeen '
                                    f'persoonallinen muoto "{head.text}".',
                            replacements=[]))
                # VerbForm == Inf: ketju OK ("ei voinut maksaa")
            # perfektin partisiipin lukukongruenssi: monikollinen partisiippi
            # yksiköllisen tai partitiivisen (eksistentiaali) subjektin kanssa.
            # Liittomuodoissa lukukongruenssi pätee kaikissa persoonissa
            # (VISK §1284 asetelma 167; "Me olemme tulleet").
            wf = _feats(w)
            if w.upos in ('VERB', 'AUX') \
                    and wf.get('VerbForm') == 'Part' \
                    and wf.get('PartForm') == 'Past' \
                    and wf.get('Voice') != 'Pass':
                children = [c for c in words if c.head == w.id]
                auxes = [c for c in children
                         if c.deprel == 'aux' and c.lemma == 'olla']
                # me-passiivi ("me ollaan tultu"): passiiviapuverbi ->
                # puhekielen muoto, ei liputeta kumpaankaan suuntaan
                if auxes and not any(_feats(a).get('Voice') == 'Pass'
                                     for a in auxes):
                    pnum = _voikko_participle_number(voikko, w.text)
                    if pnum == 'plural':
                        for subj in children:
                            if not (subj.deprel or '').startswith('nsubj'):
                                continue
                            sf = _feats(subj)
                            if subj.upos == 'PROPN' or any(
                                    c.upos == 'PROPN' for c in words
                                    if c.head == subj.id):
                                continue
                            if sf.get('Case') == 'Nom' \
                                    and sf.get('Number') == 'Sing':
                                start, end = _span(w)
                                out.append(Suggestion(
                                    rule='PPERF_NUM', category='grammar',
                                    severity='error', start=start, end=end,
                                    message=f'Yksiköllinen subjekti '
                                            f'"{subj.text}", mutta partisiippi '
                                            f'"{w.text}" monikossa.',
                                    replacements=[]))
                            elif sf.get('Case') == 'Par':
                                start, end = _span(w)
                                out.append(Suggestion(
                                    rule='PPERF_NUM', category='grammar',
                                    severity='error', start=start, end=end,
                                    message=f'Eksistentiaalilauseen '
                                            f'partitiivisubjekti "{subj.text}" '
                                            f'vaatii yksiköllisen partisiipin, '
                                            f'ei "{w.text}".',
                                    replacements=[]))
            # predikatiivin lukukongruenssi (VISK §1284)
            if w.upos == 'ADJ':
                pf = _feats(w)
                if pf.get('Case') == 'Nom' and pf.get('Number') == 'Sing':
                    children = [c for c in words if c.head == w.id]
                    if any(c.deprel == 'cop' and c.lemma == 'olla'
                           for c in children):
                        for subj in children:
                            if not (subj.deprel or '').startswith('nsubj'):
                                continue
                            sf = _feats(subj)
                            if subj.upos not in ('NOUN', 'PRON'):
                                continue  # PROPN: yhteisnimi yksikössä OK
                            if sf.get('Number') != 'Plur':
                                continue
                            if sf.get('Case') not in ('Nom', 'Acc', None):
                                continue
                            subj_children = [c for c in words
                                             if c.head == subj.id]
                            if any(c.deprel == 'nummod'
                                   for c in subj_children):
                                continue  # numeraalisubjekti: part. OK (§1285)
                            if any(c.upos == 'PROPN'
                                   for c in subj_children):
                                continue  # kollektiivierisnimi:
                                # "Helsingin Sanomat on varovainen" (§1284c)
                            start, end = _span(w)
                            out.append(Suggestion(
                                rule='PRED_NUM', category='grammar',
                                severity='error', start=start, end=end,
                                message=f'Monikollinen subjekti "{subj.text}", '
                                        f'mutta predikatiivi "{w.text}" '
                                        'yksikön nominatiivissa; yleiskielen '
                                        'mukaan monikko (VISK §1284).',
                                replacements=[]))
    return out
