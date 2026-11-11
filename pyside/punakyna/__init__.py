"""Punakynä - suomen kielen oikolukija (proofreading pipeline).

Kerrosarkkitehtuuri:
1. Voikko-taso: oikeinkirjoitus ja morfologinen analyysi (libvoikko).
2. Saantotaso: tarkat kielioppisaannot, joita Voikko ei kata.
3. Neurotaso (valinnainen, kytkettava): sekvensis-malli kieliopin korjaukseen.
   Oletuksena pois paalta; mukana ei jaeta kolmannen osapuolen painoja.
Pipeline ei koskaan kirjoita tekstia uudelleen: se palauttaa vain ehdotuksia.
"""
__version__ = '0.1.16'
