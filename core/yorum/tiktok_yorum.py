"""TikTok Studio yorumları: okuma, cevap, beğeni; video sayfasından şikayet. Seçiciler tiktok_secici.py'de."""
from __future__ import annotations

import random
import re
import time
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

from core.upload import tiktok_secici as s
from core.upload.tiktok import TikTokHatasi, TikTokYukleyici
from core.yorum import HamYorum, YorumIslemHatasi

AZAMI_YAS_GUN = 7
CEVAP_BOSALMA_SN = 10  # gönderimden sonra cevap kutusunun boşalması için azami bekleme
_BIRIM = {"m": 1 / 1440, "min": 1 / 1440, "mins": 1 / 1440, "minute": 1 / 1440, "minutes": 1 / 1440,
          "h": 1 / 24, "hr": 1 / 24, "hrs": 1 / 24, "hour": 1 / 24, "hours": 1 / 24,
          "d": 1.0, "day": 1.0, "days": 1.0,
          "w": 7.0, "wk": 7.0, "wks": 7.0, "week": 7.0, "weeks": 7.0}
_YAS_RE = re.compile(r"(\d+)\s*(" + "|".join(sorted(_BIRIM, key=len, reverse=True)) + r")\s+ago")


def yas_gun(metin: str) -> float | None:
    """'2h ago' → 0.083; 'Just now' → 0; tarih ('10-01'), ay/yıl ('3mo ago') ya da bilinmeyen → None (eski sayılır)."""
    m = (metin or "").strip().lower()
    if m in ("just now", "now"):
        return 0.0
    r = _YAS_RE.fullmatch(m)
    return int(r.group(1)) * _BIRIM[r.group(2)] if r else None


def tam_desen(metin: str, at: bool = False) -> re.Pattern:
    """Tam metin eşlemesi: çapalı, büyük/küçük harf duyarlı, boşluk farklarına toleranslı.
    at=True: başta isteğe bağlı tek '@' (kullanıcı adları)."""
    return re.compile(r"^\s*" + ("@?" if at else "") + r"\s+".join(map(re.escape, metin.split())) + r"\s*$")


def _govde(metin: str) -> str:
    return re.sub(r"\s+", " ", metin).strip().rstrip("…").rstrip(".").strip().lower()


def video_yolu_bul(satirlar: list[tuple[str, str]], video: str) -> str | None:
    """İçerik listesindeki (href, açıklama) satırlarından yorumun videosunu bulur (kesik başlık önek eşleşir)."""
    hedef = _govde(video)
    if len(hedef) < 10:
        return None
    for href, aciklama in satirlar:
        if _govde(aciklama).startswith(hedef):
            return href
    return None


class TikTokYorumcu(TikTokYukleyici):
    """Yükleyicinin tarayıcı/profil yardımcılarını yeniden kullanır."""

    def __init__(self, profil_dir: Path, hata_dir: Path, log=None, hesap: str | None = None, headless: bool = False):
        super().__init__(profil_dir, hata_dir, log, headless)
        self.hesap = hesap

    @contextmanager
    def oturum(self):
        with sync_playwright() as p:
            try:
                ctx, sayfa = self._baslat_sarmali(p)
            except TikTokHatasi as e:
                raise YorumIslemHatasi(str(e)) from e
            try:
                try:
                    sayfa.goto(s.YORUM_URL)
                    time.sleep(random.uniform(4, 6))
                    if s.GIRIS_YOLU in sayfa.url:
                        raise YorumIslemHatasi("TikTok oturumu kapalı", yetki=True)
                    self._popuplari_kapat(sayfa)
                except YorumIslemHatasi:
                    raise
                except Exception as e:
                    raise YorumIslemHatasi(f"Yorum sayfası açılamadı: {e}",
                                           ekran=self._ekran_kaydet(sayfa, "yorum_acilis")) from e
                yield YorumSayfasi(self, ctx, sayfa)
            finally:
                self._tarayici_kapat(ctx)


class YorumSayfasi:
    def __init__(self, yorumcu: TikTokYorumcu, ctx, sayfa):
        self.y = yorumcu
        self.ctx = ctx
        self.sayfa = sayfa
        self._video_satirlari: list[tuple[str, str]] | None = None

    # --- yardımcılar ---
    def _hata(self, mesaj: str, ad: str, gonderildi: bool = False) -> YorumIslemHatasi:
        return YorumIslemHatasi(mesaj, ekran=self.y._ekran_kaydet(self.sayfa, ad), gonderildi=gonderildi)

    def _sifirla(self) -> None:
        """Başarısız eylemden sonra yarım kalmış cevap kutusu/menü bir sonrakine sızmasın.
        Kendi hatası asıl hatayı örtmez (yalnız loglanır)."""
        try:
            self.sayfa.goto(s.YORUM_URL)
            time.sleep(random.uniform(3, 5))
            self.y._popuplari_kapat(self.sayfa)
        except Exception as e:
            self.y.log.warning("Yorum sayfası sıfırlanamadı: %s", e)

    def _hucre(self, y: HamYorum):
        try:
            hucreler = self.sayfa.locator(s.YORUM_HUCRE).filter(
                has=self.sayfa.locator(s.YORUM_KULLANICI).filter(has_text=tam_desen(y.kullanici, at=True))
            ).filter(has=self.sayfa.locator(s.YORUM_METIN).filter(has_text=tam_desen(y.metin)))
            adet = hucreler.count()
        except Exception as e:
            raise self._hata(f"Yorum aranamadı (@{y.kullanici}): {e}", "yorum_ara") from e
        if adet == 0:
            raise self._hata(f"Yorum sayfada bulunamadı: @{y.kullanici}", "yorum_yok")
        if adet > 1:
            raise self._hata(f"Yorum tek değil ({adet} eşleşme): @{y.kullanici}", "yorum_coklu")
        return hucreler.first

    # --- okuma ---
    def oku(self, en_fazla: int = 100) -> list[HamYorum]:
        hucreler = self.sayfa.locator(s.YORUM_HUCRE)
        try:
            gorunur = self.y._gorunurse(hucreler.first, 10_000)
            adet = hucreler.count() if gorunur else 0
        except Exception as e:
            raise self._hata(f"Yorumlar okunamadı: {e}", "yorum_oku") from e
        if not gorunur:
            try:
                bos = self.y._gorunurse(self.sayfa.locator(s.YORUM_BOS_METIN).first, 2000)
            except Exception as e:
                raise self._hata(f"Yorumlar okunamadı: {e}", "yorum_oku") from e
            if bos:
                return []  # gerçekten yorum yok
            raise self._hata("Yorum listesi görünmedi (arayüz değişmiş ya da hiç yorum yok)", "yorum_bos")
        sonuc: list[HamYorum] = []
        okunan = bozuk = 0
        for i in range(min(adet, en_fazla)):
            h = hucreler.nth(i)
            try:
                if not h.inner_text(timeout=2000).strip():
                    self.y.log.debug("Boş yorum hücresi atlandı (%d)", i)
                    continue
                yas = yas_gun(h.locator(s.YORUM_ZAMAN).first.inner_text(timeout=2000))
                if yas is None or yas > AZAMI_YAS_GUN:
                    okunan += 1
                    continue
                kullanici = h.locator(s.YORUM_KULLANICI).first.inner_text(timeout=2000).strip().lstrip("@")
                metin = h.locator(s.YORUM_METIN).first.inner_text(timeout=2000).strip()
                video = h.locator(s.YORUM_VIDEO).last.inner_text(timeout=2000).strip()
            except Exception as e:
                bozuk += 1
                self.y.log.warning("Yorum satırı okunamadı (%d): %s", i, e)
                continue
            okunan += 1
            if kullanici and metin:
                sonuc.append(HamYorum(kullanici, metin, video))
        if bozuk and not okunan:  # hücre var ama hiçbiri ayrıştırılamadı: "yorum yok" sanılmasın
            raise self._hata("Yorum satırları okunamadı (arayüz değişmiş olabilir)", "yorum_satir")
        return sonuc

    # --- eylemler ---
    def cevapla(self, y: HamYorum, metin: str) -> None:
        try:
            self._cevapla(y, metin)
        except Exception:
            self._sifirla()
            raise
        self._sifirla()  # cevap arayüzü kapansın; sonraki "Reply" tek kutu bulsun (kendi hatasını yutar)

    @staticmethod
    def _bosaldi(kutular) -> bool:
        try:
            return kutular.count() == 0 or kutular.first.input_value(timeout=1000) == ""
        except Exception:  # kutu count ile okuma arasında DOM'dan kalkmış olabilir: yeniden say
            try:
                return kutular.count() == 0
            except Exception:
                return False

    def _cevapla(self, y: HamYorum, metin: str) -> None:
        hucre = self._hucre(y)
        gonderildi = False
        try:
            hucre.get_by_text(s.YORUM_CEVAP_METNI, exact=True).first.click()
            kutular = self.sayfa.locator(s.YORUM_CEVAP_KUTU).filter(visible=True)
            kutular.first.wait_for(state="visible", timeout=5000)
            adet = kutular.count()
            if adet != 1:
                raise self._hata(f"Cevap kutusu tek değil ({adet}): @{y.kullanici}", "yorum_cevap_kutu")
            kutu = kutular.first
            if kutu.input_value(timeout=2000) != "":
                raise self._hata(f"Cevap kutusu boş değil (bayat taslak): @{y.kullanici}", "yorum_cevap_kutu")
            kutu.click()
            self.y._yaz(self.sayfa, metin)
            time.sleep(random.uniform(0.5, 1.2))
            gonder = self.sayfa.get_by_role("button", name=s.YORUM_CEVAP_GONDER_METNI, exact=True).first
            if self.y._gorunurse(gonder, 1000):
                gonder.click()
            else:
                self.sayfa.keyboard.press("Enter")
            gonderildi = True
            son = time.monotonic() + CEVAP_BOSALMA_SN
            while not self._bosaldi(kutular):
                if time.monotonic() >= son:
                    raise RuntimeError(f"cevap kutusu {CEVAP_BOSALMA_SN} sn içinde boşalmadı")
                time.sleep(0.3)
        except YorumIslemHatasi:
            raise
        except Exception as e:
            raise self._hata(f"Cevap gönderilemedi (@{y.kullanici}): {e}", "yorum_cevap", gonderildi) from e

    def begen(self, y: HamYorum) -> None:
        try:
            hucre = self._hucre(y)
            try:
                if hucre.locator(s.YORUM_BEGENILDI).count():
                    return
                hucre.locator(s.YORUM_BEGEN).first.click()
                hucre.locator(s.YORUM_BEGENILDI).first.wait_for(state="attached", timeout=5000)
            except Exception as e:
                raise self._hata(f"Beğenilemedi (@{y.kullanici}): {e}", "yorum_begen") from e
        except Exception:
            self._sifirla()
            raise

    def _video_yolu(self, video: str) -> str | None:
        """İçerik listesine ayrı sekmede bakar; yorum sayfası (self.sayfa) yerinde kalır."""
        if not self._video_satirlari:
            sekme = self.ctx.new_page()
            try:
                sekme.goto(s.ICERIK_URL)
                time.sleep(random.uniform(4, 6))
                linkler = sekme.locator(s.ICERIK_VIDEO_LINK)
                satirlar = []
                for i in range(linkler.count()):
                    a = linkler.nth(i)
                    href = a.get_attribute("href") or ""
                    if self.y.hesap and f"/@{self.y.hesap}/video/" not in href:
                        continue
                    satirlar.append((href, a.inner_text(timeout=2000)))
            except Exception as e:
                raise YorumIslemHatasi(f"İçerik listesi okunamadı: {e}",
                                       ekran=self.y._ekran_kaydet(sekme, "sikayet_icerik")) from e
            finally:
                sekme.close()
            if satirlar:
                self._video_satirlari = satirlar
            return video_yolu_bul(satirlar, video)
        return video_yolu_bul(self._video_satirlari, video)

    def sikayet_et(self, y: HamYorum, tur: str) -> None:
        try:
            yol = self._video_yolu(y.video)
        except YorumIslemHatasi:
            raise
        except Exception as e:
            raise self._hata(f"İçerik listesi açılamadı: {e}", "sikayet_icerik") from e
        if not yol:
            raise self._hata(f"Yorumun videosu bulunamadı: {y.video[:40]}", "sikayet_video")
        vs = self.ctx.new_page()
        gonderildi = False
        try:
            vs.goto(s.TIKTOK_KOK + yol)
            time.sleep(random.uniform(5, 7))
            # Hedef: yazar linki VE tam metin aynı kapta; tek değilse hiçbir şeye tıklanmaz
            ogeler = vs.locator(s.VIDEO_YORUM_OGE).filter(
                has=vs.locator(s.VIDEO_YORUM_YAZAR.format(kullanici=y.kullanici))
            ).filter(has=vs.locator(s.VIDEO_YORUM_METIN).filter(has_text=tam_desen(y.metin)))
            adet = ogeler.count() if self.y._gorunurse(ogeler.first, 15_000) else 0
            if adet != 1:
                raise YorumIslemHatasi(f"Şikayet hedefi tek değil/bulunamadı ({adet} eşleşme): @{y.kullanici}",
                                       ekran=self.y._ekran_kaydet(vs, "sikayet_hedef"))
            oge = ogeler.first
            oge.hover()
            oge.locator(s.VIDEO_YORUM_MENU).first.click()
            menu = vs.locator(s.VIDEO_SIKAYET_MENU).filter(visible=True).last
            rapor = menu.get_by_text(s.VIDEO_SIKAYET_METNI, exact=True).first
            if not self.y._gorunurse(rapor, 3000):
                raise YorumIslemHatasi(f"Açılan menüde '{s.VIDEO_SIKAYET_METNI}' yok: @{y.kullanici}",
                                       ekran=self.y._ekran_kaydet(vs, "sikayet_menu"))
            rapor.click()
            time.sleep(random.uniform(1, 2))
            for sebep in s.VIDEO_SIKAYET_SEBEP[tur]:
                secenek = vs.get_by_text(sebep, exact=True).first
                if self.y._gorunurse(secenek, 1500):
                    secenek.click()
                    break
            else:
                raise RuntimeError(f"şikayet sebebi bulunamadı: {tur}")
            time.sleep(random.uniform(1, 2))
            vs.locator(s.VIDEO_SIKAYET_GONDER).first.click()
            gonderildi = True
            if not any(self.y._gorunurse(vs.locator(x).first, 8000) for x in s.VIDEO_SIKAYET_TAMAM):
                raise RuntimeError("şikayet onayı görülmedi")
        except YorumIslemHatasi:
            raise
        except Exception as e:
            raise YorumIslemHatasi(f"Şikayet edilemedi (@{y.kullanici}): {e}",
                                   ekran=self.y._ekran_kaydet(vs, "yorum_sikayet"), gonderildi=gonderildi) from e
        finally:
            vs.close()
