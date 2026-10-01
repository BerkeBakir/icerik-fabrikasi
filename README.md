# İçerik Fabrikası

TikTok ve YouTube için ücretsiz, kanal bazlı içerik otomasyonu: Reddit/LLM hikâyesi → Gemini senaryo → Edge-TTS/Kokoro ses → ffmpeg video → otomatik yükleme.

## Kurulum
```bash
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m playwright install chromium
```
`.env`: `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (isteğe bağlı `GEMINI_MODELLER`: virgülle ayrılmış yedek model sırası).
ffmpeg/ffprobe PATH'te olmalı. Eski repolardan taşıma: `.venv/Scripts/python.exe tasima.py`.

## Kullanım
```bash
.venv/Scripts/python.exe calistir.py tiktok_hikaye1 --giris   # bir kerelik TikTok girişi
.venv/Scripts/python.exe calistir.py tiktok_hikaye1 --kuru    # yüklemeden üret
.venv/Scripts/python.exe calistir.py tiktok_hikaye1           # tam çalıştırma
.venv/Scripts/python.exe calistir.py --ses-ornekleri          # ses örnekleri
.venv/Scripts/python.exe zamanla.py tiktok_hikaye1 --saat 19:00
```

## Yeni hesap / kanal
`kanallar/` altına yeni bir yaml koy (örnek: `ornek_tiktok_korku.yaml`), `--giris` ile oturum aç, `zamanla.py` ile saat ver.

## Sorun giderme
- Loglar: `veri/log/<kanal>.log`. TikTok hataları: `cikti/hatalar/` (ekran görüntüsü + HTML).
- TikTok arayüzü değiştiyse sadece `core/upload/tiktok_secici.py` güncellenir.
- Yarım kalan iş bir sonraki çalıştırmada kaldığı yerden devam eder; 3 başarısız denemeden sonra iptal edilir. Video render edildiyse iptalde klasör silinmez (yol Telegram mesajında).
- Oturum/yetki hataları (TikTok oturumu kapalı, YouTube token geçersiz) deneme sayılmaz; `--giris` çalıştırıp tekrar dene.
- TikTok zamanlama arayüzü sorun çıkarırsa kanal yaml'ında `parca2_yontem: bekle` kullan.
- Aynı kanal zaten çalışıyorsa yeni çalıştırma çıkar ve Telegram'a "atlandı" notu düşer (kanal başına kilit).
- `--kuru` çalıştırmaları gerçek işlerden ayrıdır: her seferinde sıfırdan üretir, hikâyeyi tüketmez, çıktıyı `cikti/<kanal>/is_<id>/` altında bırakır (gerçek işlerle aynı klasör düzeni; kuru iş yalnızca veritabanında `<kanal>__kuru` anahtarıyla ayrılır).

## Zamanlama notları
- Zamanlanmış görevler yalnızca Windows'ta oturumun açıkken çalışır (TikTok görünür bir tarayıcı açar).
- Dizüstünde Görev Zamanlayıcı'da bu görevler için "Koşullar" sekmesindeki "Yalnızca bilgisayar AC gücündeyse başlat" seçeneğini kapat.
- TikTok paylaşımı yapıldı ama doğrulanamadıysa iş durur ve Telegram'a uyarı gelir; iş tekrar yüklenmez. TikTok hesabını kontrol et:
  - video yayındaysa: `.venv/Scripts/python.exe calistir.py <kanal> --onayla` (iş ilerler; Part 1 ise sonraki çalıştırma sadece Part 2'yi yükler)
  - yayında değilse: `.venv/Scripts/python.exe calistir.py <kanal> --yeniden-dene` (sonraki çalıştırma aynı part'ı tekrar yükler)
- Google OAuth uygulaması "Testing" modundaysa refresh token'lar 7 günde bir geçersiz olur; her hafta `--giris` gerekmemesi için Google Cloud Console'da uygulamayı yayınla ("In production").

Çıkış kodları (`calistir.py`):

| Kod | Anlamı |
|---|---|
| 0 | başarılı ya da kanal zaten çalıştığı için atlandı |
| 1 | hata |
| 2 | ön kontrol / ayar hatası |
| 3 | elle onay gerekli (`--onayla` / `--yeniden-dene`) |
