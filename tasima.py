"""Eski repolardan tek seferlik taşıma. Tekrar çalıştırmak güvenlidir (var olanı atlar).
Büyük medya hardlink ile bağlanır (ek disk alanı yok); sırlar kopyalanır; hiçbir şey silinmez."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from core.ayar import KOK, db_yolu
from core.db import DB

TIKTOK = KOK.parent / "Tikok-Otomasyon"
YOUTUBE = KOK.parent / "Youtube-Otomasyon-GoogleTTS"

BAGLANTILAR = [
    (TIKTOK / "assets/background_videos/orbital_full_video.mp4", KOK / "assets/arka_plan/orbital.mp4"),
    (YOUTUBE / "assets/arka_plan.mp4", KOK / "assets/arka_plan/gece.mp4"),
    (YOUTUBE / "assets/yagmur.mp3", KOK / "assets/yagmur.mp3"),
]
KOPYALAR = [
    (YOUTUBE / "client_secret.json", KOK / "client_secret.json"),
    (YOUTUBE / "token.pickle", KOK / "veri/tokenlar/slumberlab.pickle"),
]


def bagla(kaynak: Path, hedef: Path) -> None:
    if hedef.exists():
        print(f"var, atlandı: {hedef}")
        return
    hedef.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(kaynak, hedef)
        print(f"hardlink: {hedef}")
    except OSError:
        shutil.copy2(kaynak, hedef)
        print(f"kopyalandı: {hedef}")


def main() -> None:
    for k, h in BAGLANTILAR:
        bagla(k, h) if k.exists() else print(f"KAYNAK YOK: {k}")
    for k, h in KOPYALAR:
        if not k.exists():
            print(f"KAYNAK YOK: {k}")
        elif h.exists():
            print(f"var, atlandı: {h}")
        else:
            h.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(k, h)
            print(f"kopyalandı: {h}")
    gecmis = TIKTOK / "database/posted_stories.json"
    if gecmis.exists():
        db = DB(db_yolu())
        kimlikler = set(json.loads(gecmis.read_text(encoding="utf-8")))
        for pid in kimlikler:
            db.hikaye_isaretle(f"reddit:{pid}", "eski_tiktok")
        print(f"{len(kimlikler)} eski hikâye kimliği DB'ye işlendi")


if __name__ == "__main__":
    main()
