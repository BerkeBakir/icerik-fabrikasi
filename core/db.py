"""SQLite: kullanılan hikâyeler ve yeniden başlatılabilir işler."""
from __future__ import annotations

import hashlib
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


YORUM_ISLENECEK = ("yeni", "bekliyor", "hata")


def yorum_kimligi(kanal: str, kullanici: str, metin: str, video: str) -> str:
    """Studio yorum kimliği vermediği için içerikten türetilen kararlı kimlik."""
    ham = "\x1f".join([kanal, kullanici.strip().lower(), metin.strip(), video.strip()])
    return hashlib.sha1(ham.encode("utf-8")).hexdigest()[:16]


@dataclass
class Yorum:
    kimlik: str
    kanal: str
    kullanici: str
    metin: str
    video: str
    tur: str | None
    cevap: str | None
    konu: str | None
    oneri: str | None
    durum: str
    hata: str | None
    deneme: int
    tarih: str


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
            CREATE TABLE IF NOT EXISTS yorumlar (
                kimlik TEXT PRIMARY KEY, kanal TEXT NOT NULL, kullanici TEXT NOT NULL, metin TEXT NOT NULL,
                video TEXT NOT NULL, tur TEXT, cevap TEXT, konu TEXT, oneri TEXT,
                durum TEXT NOT NULL, hata TEXT, deneme INTEGER NOT NULL DEFAULT 0,
                tarih TEXT NOT NULL, guncelleme TEXT NOT NULL);
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

    def is_hata(self, is_id: int, mesaj: str, en_fazla: int = 3, say: bool = True) -> Is:
        """say=False: hatayı kaydeder ama deneme sayılmaz (ör. oturum/yetki hatası)."""
        mevcut = self.is_getir(is_id)
        deneme = mevcut.deneme + 1 if say else mevcut.deneme
        durum = "iptal" if say and deneme >= en_fazla else mevcut.durum
        self.bag.execute(
            "UPDATE isler SET durum=?, hata=?, deneme=?, guncelleme=? WHERE id=?",
            (durum, mesaj[:2000], deneme, _simdi(), is_id),
        )
        self.bag.commit()
        return self.is_getir(is_id)

    def is_iptal(self, is_id: int) -> Is:
        self.bag.execute("UPDATE isler SET durum='iptal', guncelleme=? WHERE id=?", (_simdi(), is_id))
        self.bag.commit()
        return self.is_getir(is_id)

    def son_isler(self, kanal: str, adet: int = 60) -> list[Is]:
        satirlar = self.bag.execute("SELECT * FROM isler WHERE kanal=? ORDER BY id DESC LIMIT ?", (kanal, adet))
        return [self._satir(r) for r in satirlar]

    # --- yorumlar ---
    def _yorum(self, r) -> Yorum:
        return Yorum(r["kimlik"], r["kanal"], r["kullanici"], r["metin"], r["video"], r["tur"], r["cevap"],
                     r["konu"], r["oneri"], r["durum"], r["hata"], r["deneme"], r["tarih"])

    def yorum_var_mi(self, kimlik: str) -> bool:
        return self.bag.execute("SELECT 1 FROM yorumlar WHERE kimlik=?", (kimlik,)).fetchone() is not None

    def yorum_getir(self, kimlik: str) -> Yorum:
        return self._yorum(self.bag.execute("SELECT * FROM yorumlar WHERE kimlik=?", (kimlik,)).fetchone())

    def yorum_ekle(self, kimlik: str, kanal: str, kullanici: str, metin: str, video: str) -> Yorum:
        self.bag.execute(
            "INSERT OR IGNORE INTO yorumlar (kimlik, kanal, kullanici, metin, video, durum, tarih, guncelleme) "
            "VALUES (?,?,?,?,?,'yeni',?,?)", (kimlik, kanal, kullanici, metin, video, _simdi(), _simdi()))
        self.bag.commit()
        return self.yorum_getir(kimlik)

    def yorum_karar(self, kimlik: str, tur: str, cevap: str, konu: str, oneri: str) -> Yorum:
        self.bag.execute(
            "UPDATE yorumlar SET tur=?, cevap=?, konu=?, oneri=?, durum='bekliyor', guncelleme=? WHERE kimlik=?",
            (tur, cevap, konu, oneri, _simdi(), kimlik))
        self.bag.commit()
        return self.yorum_getir(kimlik)

    def yorum_bitir(self, kimlik: str, durum: str) -> Yorum:
        self.bag.execute("UPDATE yorumlar SET durum=?, hata=NULL, guncelleme=? WHERE kimlik=?",
                         (durum, _simdi(), kimlik))
        self.bag.commit()
        return self.yorum_getir(kimlik)

    def yorum_hata(self, kimlik: str, mesaj: str) -> Yorum:
        mevcut = self.yorum_getir(kimlik)
        deneme = mevcut.deneme + 1
        durum = "atlandi" if deneme >= 2 else "hata"
        self.bag.execute("UPDATE yorumlar SET durum=?, hata=?, deneme=?, guncelleme=? WHERE kimlik=?",
                         (durum, mesaj[:2000], deneme, _simdi(), kimlik))
        self.bag.commit()
        return self.yorum_getir(kimlik)

    def yorum_belirsiz(self, kimlik: str, mesaj: str) -> Yorum:
        """Eylem gönderildi ama doğrulanamadı: tekrar denenmez (çift cevap/şikayet olmasın)."""
        self.bag.execute("UPDATE yorumlar SET durum='belirsiz', hata=?, guncelleme=? WHERE kimlik=?",
                         (mesaj[:2000], _simdi(), kimlik))
        self.bag.commit()
        return self.yorum_getir(kimlik)

    def yorum_islenecekler(self, kanal: str) -> list[Yorum]:
        satirlar = self.bag.execute(
            f"SELECT * FROM yorumlar WHERE kanal=? AND durum IN ({','.join('?' * len(YORUM_ISLENECEK))}) "
            "ORDER BY rowid", (kanal, *YORUM_ISLENECEK))
        return [self._yorum(r) for r in satirlar]

    def yorum_cevap_mi(self, kanal: str, metin: str) -> bool:
        return self.bag.execute("SELECT 1 FROM yorumlar WHERE kanal=? AND cevap=? AND durum='cevaplandi'",
                                (kanal, metin.strip())).fetchone() is not None

    def yapici_yorumlar(self, kanal: str, baslangic: datetime) -> list[Yorum]:
        satirlar = self.bag.execute(
            "SELECT * FROM yorumlar WHERE kanal=? AND (tur='yapici' OR COALESCE(oneri, '')<>'') AND tarih>=? "
            "ORDER BY rowid",
            (kanal, baslangic.isoformat(timespec="seconds")))
        return [self._yorum(r) for r in satirlar]
