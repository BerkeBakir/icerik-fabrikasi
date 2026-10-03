"""Yorum sınıflandırma ve cevap üretimi (Gemini) + küfür çift kontrolü."""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.yorum import HamYorum

TURLER = ("soru", "yapici", "yorum", "hakaret", "spam")
KONULAR = ("ses", "altyazi", "video", "hikaye", "uzunluk", "diger")
CEVAPLI = ("soru", "yapici")
CEVAP_SINIR = 150

# Genel argo ("holy shit") değil; hakaret/aşağılama kalıpları. Kelime sınırıyla eşleşir.
_KUFUR = [
    r"f+\W*u+\W*c+\W*k+\W*(you|u|off|yourself)", r"cunts?", r"bitch(es)?", r"whores?", r"sluts?",
    r"retard(ed|s)?", r"kys", r"kill\s+your\s*self", r"n[i1]gg(a|er)s?", r"f[a@]gg?ots?", r"motherfucker",
    r"amk", r"aq", r"orospu\w*", r"siktir\w*", r"sikeyim", r"s[iı]k[iı]m", r"piç(ler)?", r"yarra[kğ]\w*",
    r"anan[iı]\s*s\w*", r"g[oö]t\s*veren", r"gerizekal[iı]\w*", r"şerefsiz\w*", r"serefsiz\w*",
]
_KUFUR_DESENI = re.compile(r"(?<!\w)(" + "|".join(_KUFUR) + r")(?!\w)", re.IGNORECASE)

SEMA = {
    "type": "object",
    "properties": {
        "tur": {"type": "string", "enum": list(TURLER)},
        "cevap": {"type": "string"},
        "konu": {"type": "string", "enum": list(KONULAR)},
        "oneri": {"type": "string"},
    },
    "required": ["tur"],
}

ISTEM = """You manage comments for a TikTok storytelling channel. The channel narrates stories adapted from Reddit
over gameplay footage, usually in two parts (Part 1 / Part 2).

Classify the comment and, when needed, write a reply.

"tur" (exactly one):
- "soru": a question about the story, the characters or the channel.
- "yapici": constructive feedback or a suggestion about the videos (voice, subtitles, video, story, length).
- "yorum": praise, an opinion, a reaction, a judgment like NTA/YTA, an emoji, anything else harmless.
- "hakaret": insults, slurs, harassment or hate aimed at anyone.
- "spam": ads, self-promotion, "follow me", links, scams, gibberish.

"cevap": ONLY for "soru" and "yapici", otherwise empty. Rules:
- Same language as the comment, friendly and natural, at most {sinir} characters, at most one emoji.
- No links, no hashtags, no @mentions.
- Never claim the story happened to you; the stories come from Reddit. Never share personal information.
- Do not argue. For "yapici" thank them and say you'll consider it.

"konu" and "oneri": ONLY for "yapici". "konu" is one of {konular}. "oneri" is the suggestion as one short
English sentence. Otherwise empty.

Video caption: {video}
Story context: {baglam}
Comment by @{kullanici}: {metin}
"""


@dataclass
class Karar:
    tur: str
    cevap: str
    konu: str
    oneri: str


def kufurlu(metin: str) -> bool:
    return bool(_KUFUR_DESENI.search(metin or ""))


def _temiz_cevap(metin: str) -> str:
    metin = re.sub(r"https?://\S+|www\.\S+", "", metin or "")
    metin = re.sub(r"[#@]\w+", "", metin)
    metin = re.sub(r"\s+", " ", metin).strip()
    if len(metin) > CEVAP_SINIR:
        metin = metin[:CEVAP_SINIR].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return metin


def istem(yorum: HamYorum, baglam: str | None) -> str:
    return ISTEM.format(sinir=CEVAP_SINIR, konular=", ".join(KONULAR), video=yorum.video,
                        baglam=baglam or "(none)", kullanici=yorum.kullanici, metin=yorum.metin)


def siniflandir(llm, yorum: HamYorum, baglam: str | None = None) -> Karar:
    if kufurlu(yorum.metin):
        return Karar("hakaret", "", "", "")
    v = llm.json_uret(istem(yorum, baglam), SEMA, sicaklik=0.4)
    tur = v.get("tur") if v.get("tur") in TURLER else "yorum"
    konu = oneri = ""
    if tur == "yapici":
        konu = v.get("konu") if v.get("konu") in KONULAR else "diger"
        oneri = (v.get("oneri") or "").strip()[:200]
    cevap = _temiz_cevap(v.get("cevap") or "") if tur in CEVAPLI else ""
    if tur in CEVAPLI and (not cevap or kufurlu(cevap)):
        tur, cevap = "yorum", ""
    return Karar(tur, cevap, konu, oneri)
