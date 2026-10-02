"""Skor tablosu isimleri için basit küfür/hakaret filtresi.

Liste bilinçli olarak kısa tutulur ve yanlış pozitiflerden kaçınmak için üç
seviyede eşleşir. Yeni kelime eklerken ASCII'ye indirgenmiş küçük harf yazın
(ı→i, ş→s, ğ→g, ç→c, ö→o, ü→u).
"""

import re

_TR_MAP = str.maketrans(
    {
        "ı": "i", "İ": "i", "I": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
        "ç": "c", "Ç": "c", "ö": "o", "Ö": "o", "ü": "u", "Ü": "u",
        "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s",
    }
)  # fmt: skip

# Kelimenin tamamı eşleşmeli (kısa ve başka kelimelerin içinde geçebilen kökler).
EXACT = {
    "amk", "aq", "oc", "pic", "got", "sik", "sikik", "bok", "ibne", "gavat", "kahpe",
    "dick", "cock", "shit", "fag", "slut", "twat",
}  # fmt: skip

# Kelime bu köklerden biriyle başlıyorsa.
PREFIX = (
    "orospu", "siktir", "sikerim", "sikeyim", "sikis", "yarrak", "yarak", "pezevenk",
    "yavsak", "surtuk", "amina", "amcik", "anani", "gotver", "kaltak",
    "fuck", "bitch", "cunt", "asshole", "whore", "faggot", "nigg", "pussy", "bastard",
)  # fmt: skip

# Boşluk ve noktalama silindikten sonra metnin herhangi bir yerinde geçerse ("o r o s p u").
ANYWHERE = ("orospu", "pezevenk", "yarrak", "siktir", "fuck", "nigger", "faggot", "amina")


def normalize(text: str) -> str:
    return text.translate(_TR_MAP).lower()


def is_profane(text: str) -> bool:
    norm = normalize(text)
    words = re.findall(r"[a-z]+", norm)
    if any(w in EXACT or w.startswith(PREFIX) for w in words):
        return True
    compact = "".join(words)
    return any(bad in compact for bad in ANYWHERE)
