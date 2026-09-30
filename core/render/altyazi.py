"""Kelime vurgulu TikTok altyazısı (.ass)."""
from __future__ import annotations

from core.tts import Kelime

VURGU = r"{\c&H00FFFF&}"   # sarı (BGR)
NORMAL = r"{\c&HFFFFFF&}"  # beyaz

BASLIK = """[Script Info]
ScriptType: v4.00+
PlayResX: {genislik}
PlayResY: {yukseklik}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{boyut},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _zaman(sn: float) -> str:
    cs = max(0, round(sn * 100))
    s, cs = divmod(cs, 100)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _kacis(t: str) -> str:
    return t.replace("\\", "").replace("{", "(").replace("}", ")")


def satirlara_bol(kelimeler: list[Kelime], en_fazla: int = 4) -> list[list[Kelime]]:
    satirlar, mevcut = [], []
    for k in kelimeler:
        mevcut.append(k)
        if len(mevcut) >= en_fazla or k.metin[-1:] in ".!?,;:":
            satirlar.append(mevcut)
            mevcut = []
    if mevcut:
        satirlar.append(mevcut)
    return satirlar


def ass_olustur(kelimeler: list[Kelime], genislik: int = 1080, yukseklik: int = 1920,
                font: str = "Arial", boyut: int = 88, en_fazla: int = 4) -> str:
    olaylar = []
    for satir in satirlara_bol(kelimeler, en_fazla):
        metinler = [_kacis(k.metin.upper()) for k in satir]
        for i, k in enumerate(satir):
            bitis = satir[i + 1].baslangic if i + 1 < len(satir) else k.bitis
            if bitis <= k.baslangic:
                bitis = k.baslangic + 0.05
            parcalar = [f"{VURGU}{m}{NORMAL}" if j == i else m for j, m in enumerate(metinler)]
            olaylar.append(f"Dialogue: 0,{_zaman(k.baslangic)},{_zaman(bitis)},Default,,0,0,0,,{' '.join(parcalar)}")
    return BASLIK.format(genislik=genislik, yukseklik=yukseklik, font=font, boyut=boyut) + "\n".join(olaylar) + "\n"
