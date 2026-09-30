# İçerik Fabrikası

TikTok ve YouTube için ücretsiz, kanal bazlı içerik otomasyonu: Reddit/LLM hikâyesi → Gemini senaryo → Edge-TTS/Kokoro ses → ffmpeg video → otomatik yükleme.

## Kurulum
```bash
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m playwright install chromium
```
`.env`: `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (isteğe bağlı `GEMINI_MODEL`).
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
- Yarım kalan iş bir sonraki çalıştırmada kaldığı yerden devam eder; 3 başarısız denemeden sonra iptal edilir.
- TikTok zamanlama arayüzü sorun çıkarırsa kanal yaml'ında `parca2_yontem: bekle` kullan.
- Aynı kanal zaten çalışıyorsa yeni çalıştırma sessizce çıkar (kanal başına kilit).
- `--kuru` çalıştırmaları gerçek işlerden ayrıdır: her seferinde sıfırdan üretir, hikâyeyi tüketmez, çıktıyı `cikti/<kanal>/is_<id>/` altında bırakır (gerçek işlerle aynı klasör düzeni; kuru iş yalnızca veritabanında `<kanal>__kuru` anahtarıyla ayrılır).
