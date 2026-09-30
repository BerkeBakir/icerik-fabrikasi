"""SQLite: kullanılan hikâyeler ve yeniden başlatılabilir işler."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ADIMLAR = ["yeni", "hikaye_secildi", "senaryo_hazir", "ses_hazir", "video_hazir", "parca1_yuklendi", "yuklendi"]
BITMIS = ("yuklendi", "iptal")


def _simdi() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Is:
    id: int
    kanal: str
    durum: str
    veri: dict
    hata: str | None
    deneme: int

    def gecti_mi(self, adim: str) -> bool:
        if self.durum not in ADIMLAR:
            return False
        return ADIMLAR.index(self.durum) >= ADIMLAR.index(adim)


class DB:
    def __init__(self, yol: Path):
        Path(yol).parent.mkdir(parents=True, exist_ok=True)
        self.bag = sqlite3.connect(str(yol))
        self.bag.row_factory = sqlite3.Row
        self.bag.executescript(
            """
            CREATE TABLE IF NOT EXISTS hikayeler (
                kimlik TEXT PRIMARY KEY, kanal TEXT NOT NULL, tarih TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS isler (
                id INTEGER PRIMARY KEY AUTOINCREMENT, kanal TEXT NOT NULL, durum TEXT NOT NULL,
                veri TEXT NOT NULL, hata TEXT, deneme INTEGER NOT NULL DEFAULT 0,
                olusturma TEXT NOT NULL, guncelleme TEXT NOT NULL);
            """
        )
        self.bag.commit()

    def hikaye_kullanildi_mi(self, kimlik: str) -> bool:
        return self.bag.execute("SELECT 1 FROM hikayeler WHERE kimlik=?", (kimlik,)).fetchone() is not None

    def hikaye_isaretle(self, kimlik: str, kanal: str) -> None:
        self.bag.execute("INSERT OR IGNORE INTO hikayeler VALUES (?,?,?)", (kimlik, kanal, _simdi()))
        self.bag.commit()

    def _satir(self, r) -> Is:
        return Is(r["id"], r["kanal"], r["durum"], json.loads(r["veri"]), r["hata"], r["deneme"])

    def is_getir(self, is_id: int) -> Is:
        return self._satir(self.bag.execute("SELECT * FROM isler WHERE id=?", (is_id,)).fetchone())

    def is_olustur(self, kanal: str) -> Is:
        c = self.bag.execute(
            "INSERT INTO isler (kanal, durum, veri, olusturma, guncelleme) VALUES (?,?,?,?,?)",
            (kanal, "yeni", "{}", _simdi(), _simdi()),
        )
        self.bag.commit()
        return self.is_getir(c.lastrowid)

    def yarim_is(self, kanal: str) -> Is | None:
        r = self.bag.execute(
            f"SELECT * FROM isler WHERE kanal=? AND durum NOT IN ({','.join('?' * len(BITMIS))}) "
            "ORDER BY id DESC LIMIT 1",
            (kanal, *BITMIS),
        ).fetchone()
        return self._satir(r) if r else None

    def is_ilerlet(self, is_id: int, durum: str, **veri) -> Is:
        mevcut = self.is_getir(is_id)
        mevcut.veri.update(veri)
        self.bag.execute(
            "UPDATE isler SET durum=?, veri=?, hata=NULL, guncelleme=? WHERE id=?",
            (durum, json.dumps(mevcut.veri, ensure_ascii=False), _simdi(), is_id),
        )
        self.bag.commit()
        return self.is_getir(is_id)

    def is_hata(self, is_id: int, mesaj: str, en_fazla: int = 3) -> Is:
        mevcut = self.is_getir(is_id)
        deneme = mevcut.deneme + 1
        durum = "iptal" if deneme >= en_fazla else mevcut.durum
        self.bag.execute(
            "UPDATE isler SET durum=?, hata=?, deneme=?, guncelleme=? WHERE id=?",
            (durum, mesaj[:2000], deneme, _simdi(), is_id),
        )
        self.bag.commit()
        return self.is_getir(is_id)
