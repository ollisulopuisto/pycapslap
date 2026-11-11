"""Kytkettava neurokorjaustaso.

Rajapinta on tarkoituksella pieni: mika tahansa sekvensis-malli (esim.
finetunnettu T5-variantti) voidaan kytkea toteuttamalla correct().

HUOM lisenssit: FinnGEC-julkaisun (Vu ym. 2026, aclanthology.org/2026.bea-1.33)
mukana HF-palveluun ladatuilla painoilla (advu/finnish-gec-*) ei ole ilmoitettua
lisenssia, ja opetusaineisto on lisenssirajoitteinen (saatavilla pyynnosta).
Siksi punakyna ei lataa, paketoi eika jaa naita painoja. Kayttaja voi itse
hankkia mallin ja kytkea sen tahan, jos kayttoon on lupa.
"""
from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class NeuralCorrection:
    corrected: str
    backend: str


class GECBackend(Protocol):
    def correct(self, sentence: str) -> Optional[NeuralCorrection]: ...


class TransformersSeq2SeqBackend:
    """Yleisadapteri HF:n tekstista-tekstiin -malleille. Ei oletusmallia."""

    def __init__(self, model_name: str, max_new_tokens: int = 256):
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer  # noqa
        self._tok = AutoTokenizer.from_pretrained(model_name)
        self._model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        self._max = max_new_tokens
        self.name = model_name

    def correct(self, sentence: str) -> Optional[NeuralCorrection]:
        import torch
        ids = self._tok(sentence, return_tensors='pt')
        with torch.no_grad():
            out = self._model.generate(**ids, max_new_tokens=self._max)
        text = self._tok.decode(out[0], skip_special_tokens=True)
        if text.strip() and text.strip() != sentence.strip():
            return NeuralCorrection(corrected=text.strip(), backend=self.name)
        return None
