"""LLM prompt'ları, JSON şemaları ve etiket yardımcıları."""
from __future__ import annotations

import hashlib
import logging
import re

from core.modeller import Hikaye, TiktokSenaryo, YoutubePaketi

PART1_SON = "Follow for Part 2, it's already on my profile!"

_METIN = {"type": "string"}
_LISTE = {"type": "array", "items": {"type": "string"}}

TIKTOK_SEMA = {
    "type": "object",
    "properties": {"hook": _METIN, "part1": _METIN, "part2": _METIN, "aciklama": _METIN, "etiketler": _LISTE},
    "required": ["hook", "part1", "part2", "aciklama", "etiketler"],
}
SERBEST_SEMA = {
    "type": "object",
    "properties": {"baslik": _METIN, "govde": _METIN},
    "required": ["baslik", "govde"],
}
YOUTUBE_SEMA = {
    "type": "object",
    "properties": {"baslik": _METIN, "aciklama": _METIN, "etiketler": _LISTE, "hikaye": _METIN},
    "required": ["baslik", "aciklama", "etiketler", "hikaye"],
}

TIKTOK_PROMPT = """Prepare this story for a high-quality, long-form TikTok video split into two parts.

STRICT INSTRUCTIONS:
1. DO NOT SUMMARIZE: keep the emotional depth, the crucial dialogue and the specific details.
2. "hook": one viral opening sentence (3-5 seconds when spoken) that grabs attention immediately.
3. "part1": starts with the hook sentence, tells the first half, and stops on a cliffhanger. It MUST end exactly with: "{part1_son}"
4. "part2": starts with a one-sentence recap, then the second half, the resolution and a short closing thought.
5. Tone: immersive, dramatic, first-person storytelling. Plain spoken English, no emojis, no hashtags, no stage directions.
6. "aciklama": an engaging one or two sentence TikTok caption WITHOUT hashtags.
7. "etiketler": exactly {etiket_sayisi} relevant TikTok hashtags for this specific story, without the # sign.

TITLE: {baslik}
STORY:
{govde}
"""

SERBEST_EK = """

Respond as JSON: "baslik" is a short title, "govde" is the complete story text in plain English with paragraphs separated by blank lines. No emojis, no hashtags."""

YOUTUBE_EK = """

Respond as JSON:
- "baslik": a calm, catchy YouTube title (max 70 characters, no quotes, no emojis)
- "aciklama": a 3-paragraph SEO description
- "etiketler": 10-15 relevant tags without the # sign
- "hikaye": the full story text, paragraphs separated by blank lines, no headings, no markdown"""


def etiket_temizle(e: str) -> str:
    return re.sub(r"[^\w]", "", e.strip().lstrip("#")).lower()


def etiketleri_birlestir(sabit: list[str], llm: list[str], llm_ekle: int) -> list[str]:
    sonuc: list[str] = []
    for e in sabit:
        t = etiket_temizle(e)
        if t and t not in sonuc:
            sonuc.append(t)
    eklenen = 0
    for e in llm:
        if eklenen >= llm_ekle:
            break
        t = etiket_temizle(e)
        if t and t not in sonuc:
            sonuc.append(t)
            eklenen += 1
    return sonuc


def tiktok_aciklama(parca: int, aciklama: str) -> str:
    temiz = re.sub(r"\s+", " ", re.sub(r"#\w+", "", aciklama)).strip()
    on_ek = "PART 1 | " if parca == 1 else "PART 2 (Final) | "
    return (on_ek + temiz)[:2000]


def tiktok_senaryo(llm, hikaye: Hikaye, etiket_sayisi: int) -> TiktokSenaryo:
    prompt = TIKTOK_PROMPT.format(part1_son=PART1_SON, etiket_sayisi=etiket_sayisi,
                                  baslik=hikaye.baslik, govde=hikaye.govde)
    v = llm.json_uret(prompt, TIKTOK_SEMA, sicaklik=0.7)
    hook = v["hook"].strip()
    part1 = v["part1"].strip().replace("’", "'")
    if not part1.lower().startswith(hook.lower()[:30]):
        part1 = f"{hook} {part1}"
    govde = part1.rstrip()
    if govde.endswith(PART1_SON):
        part1 = govde
    elif govde.endswith(PART1_SON.rstrip("!")):
        part1 = govde[:-len(PART1_SON.rstrip("!"))].rstrip() + " " + PART1_SON
    else:
        part1 = f"{part1} {PART1_SON}"
    etiketler = [t for t in (etiket_temizle(e) for e in v["etiketler"]) if t]
    return TiktokSenaryo(hook, part1.strip(), v["part2"].strip(), v["aciklama"].strip(), etiketler)


def serbest_hikaye(llm, prompt_metni: str) -> Hikaye:
    v = llm.json_uret(prompt_metni + SERBEST_EK, SERBEST_SEMA, sicaklik=0.9)
    govde = v["govde"].strip()
    kimlik = "uretim:" + hashlib.sha1(govde.encode("utf-8")).hexdigest()[:12]
    return Hikaye(kimlik, v["baslik"].strip(), govde)


def youtube_paketi(llm, prompt_metni: str, kelime: int, log: logging.Logger | None = None) -> YoutubePaketi:
    prompt = prompt_metni.replace("{kelime}", str(kelime)) + YOUTUBE_EK
    v = llm.json_uret(prompt, YOUTUBE_SEMA, sicaklik=0.9)
    hikaye = v["hikaye"].replace("**", "").strip()
    sayi = len(hikaye.split())
    if log and sayi < kelime * 0.6:
        log.warning("Hikâye kısa geldi: %d kelime (hedef %d)", sayi, kelime)
    baslik = re.sub(r'["*]', "", v["baslik"]).strip()
    etiketler = [t for t in (etiket_temizle(e) for e in v["etiketler"]) if t]
    return YoutubePaketi(baslik, v["aciklama"].strip(), etiketler, hikaye)
