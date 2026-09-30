from __future__ import annotations

import os
from pathlib import Path

from core import medya
from core.ayar import KOK, client_secret_yolu, eski_token_yolu, profil_yolu, token_yolu


def onkontrol(kanal, kok: Path = KOK, kuru: bool = False) -> list[str]:
    hatalar = []
    if not medya.araclar_var_mi():
        hatalar.append("ffmpeg/ffprobe PATH'te bulunamadı")
    if not os.getenv("GEMINI_API_KEY"):
        hatalar.append(".env içinde GEMINI_API_KEY boş")
    if not Path(kanal.arka_plan).exists():
        hatalar.append(f"Arka plan videosu yok: {kanal.arka_plan}")
    if kanal.kaynak.prompt and not Path(kanal.kaynak.prompt).exists():
        hatalar.append(f"Prompt dosyası yok: {kanal.kaynak.prompt}")
    if kanal.platform == "youtube" and not Path(kanal.ortam_sesi).exists():
        hatalar.append(f"Ortam sesi yok: {kanal.ortam_sesi}")
    if kuru:
        return hatalar
    if kanal.platform == "tiktok":
        if not profil_yolu(kanal, kok).exists():
            hatalar.append(f"TikTok profili yok; önce 'calistir.py {kanal.ad} --giris' çalıştır")
    else:
        if not (token_yolu(kanal, kok).exists() or eski_token_yolu(kanal, kok).exists()):
            if not client_secret_yolu(kok).exists():
                hatalar.append(f"client_secret.json yok: {client_secret_yolu(kok)}")
            hatalar.append(f"YouTube yetkisi yok; önce 'calistir.py {kanal.ad} --giris' çalıştır")
    return hatalar
