"""Sääntörekisteri: jokaiselle säännölle id, lähde, taso ja testit.

Rekisteri on totuuden lähde docs/coverage-map.md:lle (scripts/gen_coverage_map.py).
Sääntö ilman lähdettä ei kuulu rekisteriin (docs/grammar-inventory.md).
`source_status`: 'verified' = pykälän otsikko luettu lähteestä 2026-11-07;
'chapter' = vain luku tunnistettu, pykälä tarkistettava; 'engine' = ulkoisen
moottorin sääntö (Voikko, parseri), ei Punakynän oma.
"""
from dataclasses import dataclass
from typing import Tuple

VISK = 'https://scripta.kotus.fi/visk/sisallys.php?p='
OHJE = 'https://kielitoimistonohjepankki.fi/ohje/'


@dataclass(frozen=True)
class RuleSpec:
    id: str
    category: str          # inventory-taulukon aihepiiri
    layer: str             # 'rules' | 'parser' | 'voikko-gc' | 'spelling' | 'neural'
    severity: str          # 'error' | 'warning' | 'style' | 'info'
    sources: Tuple[str, ...]
    source_status: str     # 'verified' | 'chapter' | 'engine'
    tests: Tuple[str, ...]  # testimoduulit (tests/-hakemisto)
    default_on: bool = True
    summary: str = ''


REGISTRY = (
    RuleSpec('PERFECT_PASSIVE_PARTICIPLE', 'Participle in compound tenses',
             'rules', 'error', (VISK + '1292', VISK + '530'), 'verified',
             ('test_perfect_passive_participle.py',),
             summary='olen menty -> olen mennyt (rajattu intransitiiviverbeihin)'),
    RuleSpec('SV_AGREEMENT', 'Subject-verb agreement', 'rules', 'error',
             (VISK + '1267', VISK + '1270'), 'verified', ('test_rules.py',),
             summary='nominatiivisubjekti + on/ovat'),
    RuleSpec('PRON_VERB_AGREEMENT', 'Subject-verb agreement', 'rules', 'error',
             (VISK + '1268', VISK + '1272', VISK + '1326'), 'verified',
             ('test_pron_verb_agreement.py',),
             summary='asemosana + viereinen finiittiverbi; me + passiivi sallittu'),
    RuleSpec('SV_NUMBER_NONOLLA', 'Subject-verb agreement', 'rules', 'warning',
             (VISK + '1267', VISK + '1270', VISK + '1272'), 'verified',
             ('test_sg_subject_plural_verb.py',),
             summary='yksikkösubjekti + monikon 3. persoonan verbi (ei olla); monikkosubjekti + yksikköverbi jää puhekielenä liputtamatta'),
    RuleSpec('NUM_NOUN_CASE', 'Numeral + noun case', 'rules', 'warning',
             (VISK + '789', VISK + '773'), 'verified',
             ('test_numeral_noun_case.py',),
             summary='kolme lapsi -> kolme lasta; perusluvut 2-19, nominatiivinen yleisnimi'),
    RuleSpec('ATTR_AGREEMENT', 'Adjective attribute number agreement', 'rules', 'warning',
             (VISK + '1302', VISK + '582'), 'verified',
             ('test_attribute_agreement.py',),
             summary='isot talo -> isot talot; adjektiivi + substantiivi nominatiivissa, yksiselitteinen luku; partisiipit, nimet ja määrämääreet ohitetaan'),
    RuleSpec('TYPO_PERCENT_SPACE', 'Space before percent sign', 'rules', 'warning',
             ('https://kielitoimistonohjepankki.fi/ohje/prosenttimerkki/',), 'verified',
             ('test_typography.py',),
             summary='10% -> 10 %; numero + %, välilyönti; URL-koodit ja sanaa seuraavat jäävät pois'),
    RuleSpec('TYPO_CURRENCY_SPACE', 'Space before currency sign', 'rules', 'warning',
             ('https://kielitoimistonohjepankki.fi/ohje/rahasummat/',), 'verified',
             ('test_typography.py',),
             summary='29,90€ -> 29,90 €; € $ £ numeron jälkeen'),
    RuleSpec('TYPO_CLOCK_FORMAT', 'Clock time format (style)', 'rules', 'style',
             ('https://kielitoimistonohjepankki.fi/ohje/ajanilmaukset-kellonajat-merkinta-ja-taivutus/',), 'verified',
             ('test_typography.py',),
             summary='klo 9:15 -> klo 9.15; klo 09 -> klo 9; vain suositus, ohjepankki sallii kaksoispisteen digitaalisissa yhteyksissä'),
    RuleSpec('TYPO_DECIMAL_POINT', 'Decimal comma', 'rules', 'warning',
             ('https://kielitoimistonohjepankki.fi/ohje/luvut-ja-numerot-desimaaliluvut/',), 'verified',
             ('test_typography.py',),
             summary='3.5 kg -> 3,5 kg; vain kun yksikkö seuraa suoraan, ettei päivämäärät, kellonajat ja pykälänumerot liputu'),
    RuleSpec('TYPO_ABBR_DOT', 'Dot after abbreviation', 'rules', 'warning',
             ('https://kielitoimistonohjepankki.fi/ohje/lyhenteet-pisteelliset/',), 'verified',
             ('test_typography.py',),
             summary='esim, jne, tms, yms, huom ilman pistettä; tarkoituksella vain ohjepankin esimerkkilyhenteet'),
    RuleSpec('TYPO_RANGE_HYPHEN', 'En dash in number ranges', 'rules', 'warning',
             ('https://kielitoimistonohjepankki.fi/ohje/ajatusviiva-rajakohdat-ja-osapuolet-20-29-vuotiaat-suomi-ruotsi-maaottelu/',), 'verified',
             ('test_typography.py',),
             summary='20-30 -> 20–30 (ajatusviiva); tunnisteet, viivaketjut ja 3+3-numeroiset mallinumerot ohitetaan'),
    RuleSpec('TYPO_DATE_FORMAT', 'Date format', 'rules', 'warning',
             ('https://kielitoimistonohjepankki.fi/ohje/ajanilmaukset-paivays-ja-vuosiluku/',), 'verified',
             ('test_typography.py',),
             summary='ISO 2025-12-24 ja kauttaviivat 24/12/2025 -> 24.12.2025; kellonaikaleimat ja kaksiselitteiset ohitetaan'),
    RuleSpec('STYLE_SENTENCE_LENGTH', 'Sentence length (style)', 'style', 'style',
             ('https://kotus.fi/valta-pitkia-virkkeita/',
              'https://kielitoimistonohjepankki.fi/vk/ohjeita-saadoskieleen/pitkat-virkkeet/'),
             'verified', ('test_style.py',), default_on=False,
             summary='opt-in: yli N sanaa (Kotus/ohjepankki: 15, ei ehdotonta rajaa)'),
    RuleSpec('STYLE_ACTOR', 'Active voice (style)', 'style', 'style',
             ('https://selkokeskus.fi/selkokieli/nain-kirjoitat-selkokielta/helpot-kielen-rakenteet/',),
             'verified', ('test_style.py',), default_on=False,
             summary='opt-in: passiivin sijaan tekijä näkyviin (Selkokeskus: suosi aktiivia)'),
    RuleSpec('STYLE_PERSON', 'Person consistency (style)', 'style', 'style',
             ('https://kielitoimistonohjepankki.fi/virkakieli/',),
             'chapter', ('test_style.py',), default_on=False,
             summary='opt-in: valittu kertojan/lukijan persoona; lähde luku-tasolla'),
    RuleSpec('NEG_CONNEGATIVE', 'Negation', 'rules', 'error',
             (VISK + '108', VISK + '109', VISK + '1623'), 'verified',
             ('test_rules.py',), summary='en tienneet -> en tiennyt'),
    RuleSpec('NEG_NUMBER', 'Negation', 'rules', 'error',
             (VISK + '108',), 'verified', ('test_rules.py',),
             summary='minä emme -> minä en'),
    RuleSpec('DOUBLE_WORD', 'Repetition (typo-level)', 'rules', 'error',
             (VISK + '1736',), 'chapter', ('test_rules.py',),
             summary='sama sana kahdesti peräkkäin; nimet ja pilkulliset luettelot ohitetaan'),
    RuleSpec('CAP_COMMON_NOUN', 'Capitalisation', 'rules', 'style',
             (OHJE + 'alkukirjain-kuukausien-nimet/',
              OHJE + 'alkukirjain-esimerkkeja-pienesta-alkukirjaimesta/'),
             'verified', ('test_rules.py',),
             summary='kuukaudet, viikonpäivät, vuodenajat pienellä'),
    RuleSpec('SPELL', 'Spelling', 'spelling', 'error', ('https://voikko.puimula.org/',),
             'engine', ('test_rules.py',), summary='Voikko-oikoluku'),
    RuleSpec('SPELL_UNKNOWN', 'Spelling', 'spelling', 'info',
             ('https://voikko.puimula.org/',), 'engine', ('test_rules.py',),
             default_on=False, summary='tuntematon sana ilman ehdotusta'),
    RuleSpec('VOIKKO_GC', 'Voikko grammar checker (codes 1-18)', 'voikko-gc',
             'warning', ('https://voikko.puimula.org/',), 'engine',
             ('test_rules.py',), summary='libvoikko-kieliopintarkistin'),
    RuleSpec('PSV_NUMBER', 'Subject-verb agreement (parser)', 'parser', 'error',
             (VISK + '1267',), 'verified', ('test_parser_tier.py',)),
    RuleSpec('PSV_PERSON', 'Subject-verb agreement (parser)', 'parser', 'error',
             (VISK + '1268',), 'verified', ('test_parser_tier.py',)),
    RuleSpec('PNEG_NUMBER', 'Negation (parser)', 'parser', 'error',
             (VISK + '108',), 'verified', ('test_parser_tier.py',)),
    RuleSpec('PNEG_CONNEG', 'Negation (parser)', 'parser', 'error',
             (VISK + '109',), 'verified', ('test_parser_tier.py',)),
    RuleSpec('PPERF_NUM', 'Participle in compound tenses (parser)', 'parser',
             'error', (VISK + '1292', VISK + '1284'), 'verified',
             ('test_parser_tier.py',)),
    RuleSpec('PRED_NUM', 'Predicative agreement (parser)', 'parser', 'error',
             (VISK + '1284',), 'verified', ('test_pred_num.py',)),
    RuleSpec('NEURAL', 'Neural backend', 'neural', 'style',
             ('https://github.com/ollisulopuisto/punakyna#neurotaso',),
             'engine', ('test_rules.py',), default_on=False,
             summary='ei käytössä; lisenssi ratkaisematta'),
)

BY_ID = {r.id: r for r in REGISTRY}
