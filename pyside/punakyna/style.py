"""Optional Finnish style prompts, not grammar errors or automatic rewrites.

Sources and limits: docs/style-advice.md. No network/model calls.
"""
from dataclasses import dataclass
import re
from .rules import Suggestion


@dataclass(frozen=True)
class StyleProfile:
    prefer_active: bool = False
    narrator: str = 'any'  # any | mina | me
    reader: str = 'any'    # any | sina | te
    max_sentence_words: int = 0  # 0 = off; Kotus/ohjepankki: yli 15 sanaa -> harkitse jakamista

    @classmethod
    def from_value(cls, value):
        if value is None:
            return cls()
        if isinstance(value, cls):
            value.validate()
            return value
        if not isinstance(value, dict) or set(value) - {'prefer_active', 'narrator', 'reader', 'max_sentence_words'}:
            raise ValueError('invalid style profile')
        p = cls(**value)
        p.validate()
        return p

    def validate(self):
        if (type(self.prefer_active) is not bool
                or self.narrator not in ('any', 'mina', 'me')
                or self.reader not in ('any', 'sina', 'te')
                or type(self.max_sentence_words) is not int
                or not 0 <= self.max_sentence_words <= 200):
            raise ValueError('invalid style profile')

    @property
    def enabled(self):
        return (self.prefer_active or self.narrator != 'any' or self.reader != 'any'
                or self.max_sentence_words > 0)

    @classmethod
    def preset(cls, name):
        """Nimetyt profiilit (docs/grammar-inventory.md). Oletus 'standard' = ei tyylivinkkeja."""
        if name in (None, 'standard'):
            return cls()
        if name == 'virkakieli':
            # Kielitoimiston ohjepankki: Pitkat virkkeet; Kotus virkakielivinkki
            return cls(prefer_active=True, max_sentence_words=15)
        raise ValueError('unknown style preset')


# Conservative exclusion: whole sentences containing quotation/code delimiters
# are skipped. A fragmentary quotation must not change the apparent narrator.
_QUOTED = re.compile(r'["“”«»`]|(?:^|\n)\s*[>–—]')
_PERSON_WORDS = {'minä': ('1', 'singular'), 'me': ('1', 'plural'),
                 'sinä': ('2', 'singular'), 'te': ('2', 'plural')}
_LABELS = {'mina': 'minä', 'me': 'me', 'sina': 'sinä', 'te': 'te'}


def excluded_text(text):
    return bool(_QUOTED.search(text) or re.search(r"[{}]|https?://|www\.", text))


def check_style(sentence, offset, tokens, voikko, cache, profile):
    profile = StyleProfile.from_value(profile)
    if not profile.enabled or excluded_text(sentence):
        return []
    out = []
    flagged_roles = set()
    if profile.max_sentence_words:
        # Lahteet: https://kotus.fi/valta-pitkia-virkkeita/ ja
        # https://kielitoimistonohjepankki.fi/vk/ohjeita-saadoskieleen/pitkat-virkkeet/
        # (yli 15 sanaa: harkitse jakamista; ehdotonta rajaa ei ole).
        words = [t for t in tokens if t.is_word]
        if len(words) > profile.max_sentence_words:
            first_over = words[profile.max_sentence_words]
            out.append(Suggestion('STYLE_SENTENCE_LENGTH', 'style', 'style',
                offset + first_over.start, offset + first_over.end,
                'Tyylivinkki: virkkeessä on %d sanaa (raja %d). Pitkä virke voi olla '
                'hankala lukijalle; harkitse jakamista kahteen virkkeeseen. Ehdotonta '
                'pituusrajaa ei ole, ja pitkäkin virke voi olla selkeä.'
                % (len(words), profile.max_sentence_words), []))
    for tok in tokens:
        if not tok.is_word:
            continue
        if tok.text not in cache:
            cache[tok.text] = voikko.analyze(tok.text)
        analyses = cache[tok.text]
        verbs = [a for a in analyses if a.get('CLASS') == 'teonsana'
                 and a.get('PERSON') and a.get('MOOD') not in ('A-infinitive', 'E-infinitive', 'MA-infinitive')]
        # Only morphologically unanimous passive finite forms. Ambiguous
        # imperative/passive homographs (e.g. lähetä) are intentionally skipped.
        if (profile.prefer_active and verbs and len(verbs) == len(analyses)
                and all(a.get('PERSON') == '4' for a in verbs)):
            out.append(Suggestion('STYLE_ACTOR', 'style', 'style',
                offset + tok.start, offset + tok.end,
                'Tyylivinkki: harkitse tekijän ilmaisemista aktiivimuodolla, jos lukijan pitää tietää, kuka toimii. Passiivi voi olla tässä tarkoituksenmukainen.', []))
        person = _PERSON_WORDS.get(tok.lower)
        if person is None and verbs and len(verbs) == len(analyses):
            values = {(a.get('PERSON'), a.get('NUMBER')) for a in verbs}
            if len(values) == 1:
                person = next(iter(values))
        if person is None:
            # Possessive suffixes only when every analysis agrees. Do not
            # infer a narrator from noun/verb ambiguities such as voimme.
            suffixes = {a.get('POSSESSIVE') for a in analyses}
            if len(suffixes) == 1:
                suffix = next(iter(suffixes))
                person = {'1s': ('1','singular'), '1p': ('1','plural'),
                          '2s': ('2','singular'), '2p': ('2','plural')}.get(suffix)
        choice = profile.narrator if person and person[0] == '1' else profile.reader if person and person[0] == '2' else 'any'
        expected = {'mina': 'singular', 'me': 'plural', 'sina': 'singular', 'te': 'plural'}.get(choice)
        if expected and person[1] != expected and person[0] not in flagged_roles:
            flagged_roles.add(person[0])
            role = 'kertojan' if person[0] == '1' else 'lukijan puhuttelun'
            out.append(Suggestion('STYLE_PERSON', 'style', 'style',
                offset + tok.start, offset + tok.end,
                'Tyylivinkki: valittu %s muoto on %s. Tarkista, viittaako tämä ilmaus samaan henkilöön tai ryhmään. Kyse voi olla tarkoituksellisesta näkökulman vaihdosta.' % (role, _LABELS[choice]), []))
    return out
