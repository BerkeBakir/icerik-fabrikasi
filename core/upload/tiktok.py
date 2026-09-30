"""TikTok Studio'ya Playwright ile yükleme (hesap başına kalıcı Chrome profili)."""
from __future__ import annotations

import logging
import random
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

from core.upload import tiktok_secici as s


class TikTokHatasi(Exception):
    """gonderildi=True: Post'a tıklandıktan sonra hata; video yayında olabilir, tekrar yüklenmemeli.
    yetki=True: oturum kapalı; kullanıcının '--giris' çalıştırması gerekir."""

    def __init__(self, mesaj: str, ekran: Path | None = None, gonderildi: bool = False, yetki: bool = False):
        super().__init__(mesaj)
        self.ekran = ekran
        self.gonderildi = gonderildi
        self.yetki = yetki


def zamani_yuvarla(dt: datetime) -> datetime:
    temel = dt.replace(second=0, microsecond=0)
    if temel == dt and dt.minute % 5 == 0:
        return temel
    eksik = 5 - (temel.minute % 5)
    return temel + timedelta(minutes=eksik)


def zamanlama_dogrula(zaman: datetime, simdi: datetime) -> datetime:
    """Zamanlama penceresini (15 dk - 10 gün) doğrular, 5 dk'ya yuvarlar, üst sınırı aşmaz."""
    if zaman < simdi + timedelta(minutes=15):
        raise TikTokHatasi(f"Zamanlama en az 15 dakika sonrası olmalı: {zaman:%Y-%m-%d %H:%M}")
    ust = simdi + timedelta(minutes=14400)
    if zaman > ust:
        raise TikTokHatasi(f"Zamanlama en fazla 10 gün sonrası olabilir: {zaman:%Y-%m-%d %H:%M}")
    yuvarlak = zamani_yuvarla(zaman)
    if yuvarlak > ust:
        yuvarlak = yuvarlak - timedelta(minutes=5)
    return yuvarlak


def zamani_tazele(zaman: datetime, simdi: datetime) -> datetime:
    """Yükleme uzadıysa ve zaman 15 dk'dan yakınsa, 16 dk sonrasına (5 dk yuvarlı) ileri alır."""
    if zaman >= simdi + timedelta(minutes=15):
        return zaman
    return zamani_yuvarla(simdi + timedelta(minutes=16))


class TikTokYukleyici:
    def __init__(self, profil_dir: Path, hata_dir: Path, log: logging.Logger | None = None, headless: bool = False):
        self.profil_dir = Path(profil_dir)
        self.hata_dir = Path(hata_dir)
        self.log = log or logging.getLogger(__name__)
        self.headless = headless
        self._tiklandi = False

    # --- tarayıcı ---
    def _baslat(self, p):
        self.profil_dir.mkdir(parents=True, exist_ok=True)
        ayar = dict(headless=self.headless, viewport={"width": 1366, "height": 900}, locale="en-US",
                    args=["--disable-blink-features=AutomationControlled"])
        try:
            ctx = p.chromium.launch_persistent_context(str(self.profil_dir), channel="chrome", **ayar)
        except Exception as e:
            m = str(e).lower()
            if not ("chrome" in m and ("not found" in m or "executable" in m or "distribution" in m)):
                raise
            self.log.warning("Sistem Chrome'u açılamadı (%s), Playwright Chromium kullanılıyor", e)
            ctx = p.chromium.launch_persistent_context(str(self.profil_dir), **ayar)
        sayfa = ctx.pages[0] if ctx.pages else ctx.new_page()
        sayfa.set_default_timeout(30_000)
        return ctx, sayfa

    def _baslat_sarmali(self, p):
        try:
            return self._baslat(p)
        except Exception as e:
            raise TikTokHatasi(
                f"TikTok tarayıcısı açılamadı: {e} (profil başka bir pencerede açıksa kapatın)") from e

    def giris(self) -> None:
        with sync_playwright() as p:
            ctx, sayfa = self._baslat_sarmali(p)
            try:
                sayfa.goto(s.GIRIS_URL)
                input("Açılan pencerede TikTok'a giriş yap, bitince bu pencereye dönüp Enter'a bas... ")
            finally:
                ctx.close()

    # --- yardımcılar ---
    def _gorunurse(self, locator, sure_ms: int) -> bool:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        try:
            locator.wait_for(state="visible", timeout=sure_ms)
            return True
        except PlaywrightTimeout:
            return False

    def _bekle(self, a: float = 0.6, b: float = 1.8) -> None:
        time.sleep(random.uniform(a, b))

    def _yaz(self, sayfa, metin: str) -> None:
        for harf in metin:
            sayfa.keyboard.type(harf)
            time.sleep(random.uniform(0.03, 0.11))

    def _popuplari_kapat(self, sayfa) -> None:
        for secici in s.KAPAT_BUTONLARI:
            try:
                b = sayfa.locator(secici).first
                if self._gorunurse(b, 500):
                    b.click()
                    self._bekle(0.3, 0.8)
            except Exception:
                pass

    def _ekran_kaydet(self, sayfa, ad: str) -> Path | None:
        try:
            self.hata_dir.mkdir(parents=True, exist_ok=True)
            yol = self.hata_dir / f"{datetime.now():%Y%m%d_%H%M%S}_{ad}.png"
            sayfa.screenshot(path=str(yol), full_page=True)
            yol.with_suffix(".html").write_text(sayfa.content(), encoding="utf-8")
            return yol
        except Exception as e:
            self.log.warning("Ekran görüntüsü kaydedilemedi: %s", e)
            return None

    # --- adımlar ---
    def _dosya_sec(self, sayfa, video: Path) -> None:
        sayfa.locator(s.DOSYA_INPUT).first.set_input_files(str(video))
        paylas = sayfa.locator(s.PAYLAS_BUTON)
        bitis = time.time() + 600
        while time.time() < bitis:
            tamam = any(sayfa.locator(x).count() for x in s.YUKLEME_TAMAM)
            aktif = (paylas.count() > 0 and paylas.first.is_enabled()
                     and paylas.first.get_attribute(s.PAYLAS_DEVRE_DISI_ATTR) != "true")
            if tamam and aktif:
                return
            time.sleep(2)
        raise TikTokHatasi("Video 10 dakikada yüklenmedi")

    def _aciklama_ve_etiketler(self, sayfa, aciklama: str, etiketler: list[str]) -> None:
        editor = sayfa.locator(s.ACIKLAMA_EDITOR).first
        editor.click()
        sayfa.keyboard.press("Control+A")
        sayfa.keyboard.press("Delete")
        self._yaz(sayfa, aciklama)
        for etiket in etiketler:
            self._yaz(sayfa, f" #{etiket}")
            oneriler = sayfa.locator(s.ETIKET_ONERI_OGE)
            if self._gorunurse(oneriler.first, 5000):
                self._bekle(0.4, 0.9)
                eslesen = oneriler.filter(has_text=s.etiket_oneri_deseni(etiket))
                if eslesen.count():
                    try:
                        eslesen.first.click()
                        self._bekle()
                        continue
                    except Exception as e:
                        self.log.warning("Etiket önerisi tıklanamadı (#%s): %s", etiket, e)
            self.log.warning("Etiket önerisi bulunamadı, düz metin kaldı: #%s", etiket)
            sayfa.keyboard.type(" ")

    def _gorunurluk(self, sayfa, gorunurluk: str) -> None:
        metin = s.GORUNURLUK_METIN[gorunurluk]
        sayfa.locator(s.GORUNURLUK_ACICI).first.click()
        self._bekle(0.4, 0.9)
        sayfa.get_by_role(s.GORUNURLUK_SECENEK_ROL, name=metin).or_(sayfa.get_by_text(metin, exact=True)).first.click()
        self._bekle()

    def _zamanla(self, sayfa, zaman: datetime) -> datetime:
        yeni = zamani_tazele(zaman, datetime.now())
        if yeni != zaman:
            self.log.warning("Yükleme uzadı, zamanlama %s -> %s olarak ileri alındı", zaman, yeni)
            zaman = yeni
        sayfa.locator(s.ZAMANLA_SECENEK).first.click()
        self._bekle()
        izin = sayfa.locator(s.ZAMANLA_IZIN).first
        if self._gorunurse(izin, 1500):
            izin.click()
            self._bekle()
        girdiler = sayfa.locator(s.ZAMAN_GIRDILERI)
        # tarih
        girdiler.nth(1).click()
        bugun = datetime.now()
        for _ in range((zaman.year * 12 + zaman.month) - (bugun.year * 12 + bugun.month)):
            sayfa.locator(s.TAKVIM_SONRAKI_AY).first.click()
            self._bekle(0.3, 0.6)
        sayfa.locator(s.TAKVIM_GUN).filter(has_text=s.tam_metin_deseni(str(zaman.day))).first.click()
        self._bekle()
        # saat ve dakika
        girdiler.nth(0).click()
        sayfa.locator(s.SAAT_SECENEK).filter(has_text=s.tam_metin_deseni(f"{zaman.hour:02d}")).first.click()
        self._bekle(0.3, 0.6)
        sayfa.locator(s.DAKIKA_SECENEK).filter(has_text=s.tam_metin_deseni(f"{zaman.minute:02d}")).first.click()
        self._bekle()
        beklenen = f"{zaman.hour:02d}:{zaman.minute:02d}"
        if girdiler.nth(0).input_value() != beklenen:
            raise TikTokHatasi(f"Zamanlama saati ayarlanamadı: {girdiler.nth(0).input_value()} != {beklenen}")
        return zaman

    def _paylas_ve_dogrula(self, sayfa) -> None:
        self._tiklandi = True  # click() dispatch sonrası fırlatsa bile paylaşım gitmiş olabilir
        sayfa.locator(s.PAYLAS_BUTON).first.click()
        try:
            simdi = sayfa.locator(s.SIMDI_PAYLAS).first
            try:
                if self._gorunurse(simdi, 5000):
                    simdi.click()
            except Exception:
                pass
            bitis = time.time() + 180
            while time.time() < bitis:
                if re.search(s.ICERIK_URL_REGEX, sayfa.url):
                    return
                if any(sayfa.locator(x).count() for x in s.BASARI_METINLERI):
                    return
                time.sleep(2)
            raise TikTokHatasi("Paylaşım 3 dakika içinde doğrulanamadı", gonderildi=True)
        except TikTokHatasi as e:
            e.gonderildi = True
            raise
        except Exception as e:
            raise TikTokHatasi(f"Paylaşım sonrası hata: {e}", gonderildi=True) from e

    def _tarayici_kapat(self, ctx) -> None:
        try:
            ctx.close()
        except Exception as e:
            self.log.warning("Tarayıcı kapatılamadı: %s", e)

    def yukle(self, video: Path, aciklama: str, etiketler: list[str], gorunurluk: str,
              zaman: datetime | None = None) -> datetime | None:
        """Yükler; zamanlandıysa etkin (doğrulanmış/tazelenmiş) zamanı, hemen yayınsa None döner."""
        if gorunurluk not in s.GORUNURLUK_METIN:
            raise TikTokHatasi(f"Geçersiz görünürlük: {gorunurluk}")
        if zaman is not None:
            zaman = zamanlama_dogrula(zaman, datetime.now())
        self._tiklandi = False
        bitti = False
        sonuc = None
        ilk_hata: TikTokHatasi | None = None  # gövdeden çıkan asıl hata (kapanış hatası ezmesin)
        try:
            with sync_playwright() as p:
                ctx, sayfa = self._baslat_sarmali(p)
                try:
                    sayfa.goto(s.YUKLEME_URL)
                    self._bekle(2, 4)
                    if s.GIRIS_YOLU in sayfa.url:
                        raise TikTokHatasi("TikTok oturumu kapalı; 'calistir.py <kanal> --giris' ile giriş yap",
                                           yetki=True)
                    self._popuplari_kapat(sayfa)
                    self.log.info("Video seçiliyor: %s", Path(video).name)
                    self._dosya_sec(sayfa, Path(video))
                    self._popuplari_kapat(sayfa)
                    self._aciklama_ve_etiketler(sayfa, aciklama, etiketler)
                    self._gorunurluk(sayfa, gorunurluk)
                    if zaman:
                        zaman = self._zamanla(sayfa, zaman)
                    self._popuplari_kapat(sayfa)
                    self._paylas_ve_dogrula(sayfa)
                    self.log.info("TikTok paylaşımı doğrulandı")
                    self._bekle(3, 5)
                    sonuc = zaman
                    bitti = True
                except TikTokHatasi as e:
                    e.ekran = e.ekran or self._ekran_kaydet(sayfa, "tiktok")
                    ilk_hata = e
                    raise
                except Exception as e:
                    ilk_hata = TikTokHatasi(f"TikTok yükleme hatası: {e}", self._ekran_kaydet(sayfa, "tiktok"))
                    raise ilk_hata from e
                finally:
                    self._tarayici_kapat(ctx)
        except Exception as e:
            if bitti:
                self.log.warning("Playwright kapanışında hata (yükleme başarılı): %s", e)
                return sonuc
            if ilk_hata is not None and e is not ilk_hata:
                self.log.warning("Playwright kapanışında hata: %s", e)
                e = ilk_hata
            if self._tiklandi:
                if isinstance(e, TikTokHatasi):
                    e.gonderildi = True
                    raise e
                raise TikTokHatasi(f"Paylaşım sonrası hata: {e}", gonderildi=True) from e
            raise e
        return sonuc
