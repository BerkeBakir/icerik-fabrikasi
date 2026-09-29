# İçerik Fabrikası — Tasarım

**Tarih:** 2026-09-29
**Durum:** Onaylandı (brainstorming), uygulama planı bekliyor

## Amaç

`Tikok-Otomasyon` ve `Youtube-Otomasyon-GoogleTTS` repolarını tek bir projede birleştirmek:

1. **TikTok:** yüklemeyi güvenilir biçimde otomatikleştirmek; etiketlerin gerçek hashtag olarak girilmesi; çoklu hesap; Part 2'nin Part 1'den 2 saat sonra yayınlanması.
2. **YouTube:** daha insansı ses; 90 dakikalık videoda hikâyenin 4-5 kez tekrar anlatılması (sonda sadece yağmur kalmaması).
3. Bozuk kısımları düzeltmek (eski `openai.ChatCompletion`, thread + `sleep` ile yükleme, çift `mark_as_posted`, sonsuz yükleme döngüsü, kontrolsüz `os.system`).
4. **Tamamen ücretsiz** çalışmak.

## Kapsam dışı

Web paneli, YouTube Shorts, Türkçe içerik, ücretli TTS/LLM. Yapı bunlara açık ama şimdi yapılmayacak.

## Teknoloji seçimleri

| Konu | Seçim | Gerekçe |
|---|---|---|
| Dil | Python 3.11 | Kokoro ve bağımlılıklar için güvenli sürüm |
| LLM | Google Gemini (ücretsiz katman), sağlayıcıdan bağımsız arayüz | Ücretsiz kota yeterli, JSON şema desteği |
| TTS (YouTube) | Kokoro (lokal); yedek Edge-TTS | Ücretsiz, en doğal seslerden |
| TTS (TikTok) | Edge-TTS | Ücretsiz, kelime zaman damgası verir |
| Render | Doğrudan ffmpeg (MoviePy ve ImageMagick kaldırılır) | Hız, daha az bağımlılık |
| Altyazı | `.ass` dosyası, kelime vurgulu | Sesle senkron |
| Reddit | Anahtarsız Atom/RSS akışı (`/r/<sub>/top/.rss?t=week`) | `.json` uç noktası 403; yeni API uygulaması Reddit onayı gerektiriyor. RSS tam metni veriyor (2026-09-29 doğrulandı) |
| TikTok yükleme | Playwright, hesap başına kalıcı Chrome profili | Resmi API onaysız uygulamada sadece gizli paylaşıyor |
| YouTube yükleme | YouTube Data API v3, resumable | Mevcut, çalışıyor |
| Durum | SQLite | Tek dosya, yeniden başlatılabilir işler |
| Zamanlama | Windows Görev Zamanlayıcı (`zamanla.py` kurar) | Ek servis gerektirmez |
| Bildirim | Telegram | Mevcut |

## Mimari

```
icerik-fabrikasi/
  calistir.py                 python calistir.py <kanal> [--kuru] [--giris]
  zamanla.py                  kanal başına Görev Zamanlayıcı kaydı
  kanallar/*.yaml             kanal başına ayar
  prompts/*.txt               kanal prompt'ları
  core/
    ayar.py                   yaml + .env okuma ve doğrulama
    llm.py                    Gemini; JSON şema zorunlu
    kaynak/reddit.py          RSS okuma, HTML→metin, uzunluk filtresi, tekrar kontrolü
    kaynak/uretim.py          kanal prompt'uyla özgün hikâye
    tts/edge.py, tts/kokoro.py  metin → ses + kelime zamanları (ortak arayüz)
    render/tiktok_dikey.py    arka plan kesme + kelime vurgulu altyazı
    render/youtube_uyku.py    hikâye sesi ×N + yağmur + video döngüsü
    upload/tiktok.py          Playwright yükleyici
    upload/tiktok_secici.py   tüm TikTok DOM seçicileri tek yerde
    upload/youtube.py         Data API yükleyici
    db.py                     SQLite
    bildirim.py               Telegram
    tekrar.py                 sınırlı deneme + üstel bekleme
  assets/                     arka plan videoları, ortam sesleri (git dışı)
  veri/                       db, loglar, tokenlar (git dışı)
  profiller/                  TikTok Chrome profilleri (git dışı)
  cikti/                      üretilen videolar, hata ekran görüntüleri (git dışı)
  tests/
```

### İş akışı ve durumlar

Her çalıştırma bir `is` kaydı oluşturur. Adımlar:
`hikaye_secildi → senaryo_hazir → ses_hazir → video_hazir → yuklendi` (herhangi birinden `hata`).

Her adımın çıktısı diske ve DB'ye yazılır. Aynı kanal yeniden çalıştırıldığında yarım kalan iş varsa son başarılı adımdan devam edilir.

### İçerik kaynakları

- `reddit`: yaml'daki subredditlerin haftalık en iyileri RSS'ten okunur (tarayıcı user-agent'ı, istekler arası ≥25 sn, 429/boş cevapta bekleyip bir kez daha dener); HTML gövde düz metne çevrilir; `min`/`max` karakter filtresi; güncelleme/edit notları ve linkler temizlenir; herhangi bir kanalda daha önce kullanılmış hikâye atlanır (DB). Uygun hikâye yoksa `t=month` ile tekrar denenir.
- `uretim`: kanalın prompt dosyası + Gemini ile özgün hikâye (korku, ilginç bilgi, uyku hikâyesi vb.).

LLM çıktısı her zaman JSON şemasıyla alınır. TikTok şeması: `hook, part1, part2, aciklama, etiketler[]`. YouTube şeması: `baslik, aciklama, etiketler[], hikaye`.

## TikTok

### Kanal ayarı örneği

```yaml
platform: tiktok
profil: hikaye1
kaynak: {tip: reddit, subredditler: [AmItheAsshole, TrueOffMyChest], min: 3000, max: 4000}
ses: {motor: edge, ses: en-US-AndrewMultilingualNeural, hiz: "+10%"}
arka_plan: assets/arka_plan/orbital.mp4
etiketler:
  sabit: [storytime, reddit, redditstories]
  llm_ekle: 3
parca2_gecikme_dk: 120
gorunurluk: herkes            # herkes | arkadaslar | sadece_ben
```

### Render

- Arka plan videosundan ses süresi kadar rastgele bölüm kesilir (dosya yeterince uzun değilse döngülenir), 1080×1920'ye kırpılır.
- Edge-TTS kelime zamanlarıyla `.ass` altyazı üretilir: 3-5 kelimelik satırlar, konuşulan kelime vurgulu, ekran ortasında.
- Part 1 sonu: "Follow for Part 2, it's already on my profile!"

### Oturum

`calistir.py <kanal> --giris` Chrome'u `profiller/<profil>/` ile açar; kullanıcı elle giriş yapar. Otomasyon asla şifre girmez. Oturum düşmüşse yükleme hata verir ve bildirim "--giris ile yeniden giriş yap" der.

### Yükleme adımları

1. TikTok Studio yükleme sayfası; popup ve çerez bannerları DOM üzerinden kapatılır (pyautogui kaldırılır).
2. Dosya seçilir, "yüklendi" durumu beklenir.
3. Açıklama yazılır. Etiketler: sabit + LLM'den `llm_ekle` adet, tekrarsız. Her biri için `#etiket` yazılır, öneri listesi beklenir, eşleşen öneri seçilir; öneri gelmezse düz metin bırakılır ve loglanır.
4. Görünürlük ayarlanır.
5. Part 2 için TikTok'un zamanlama özelliği ile `Part 1 yayın anı + parca2_gecikme_dk` seçilir (TikTok sınırı: 15 dk – 10 gün).
6. Paylaş; başarı mesajı veya içerik listesinde görünme ile doğrulanır. Doğrulanmadan "yuklendi" sayılmaz.
7. Adımlar arası rastgele kısa beklemeler, karakter karakter yazma.

Hata: ekran görüntüsü + HTML `cikti/hatalar/` altına, Telegram'a ekran görüntüsüyle bildirim.

### Çoklu hesap

Hesap başına bir yaml + bir profil klasörü. Aynı anda tek TikTok yüklemesi çalışır (kilit dosyası). Bir hikâye tüm hesaplar genelinde bir kez kullanılır.

### Risk

Tarayıcı otomasyonu TikTok kurallarına aykırıdır; hesap kısıtlaması riski vardır. İnsan benzeri davranışla azaltılır, sıfırlanamaz.

## YouTube

### Kanal ayarı örneği

```yaml
platform: youtube
token: slumberlab
kaynak: {tip: uretim, prompt: prompts/uyku_hikayesi.txt, kelime: 2500}
ses: {motor: kokoro, ses: af_heart, hiz: 0.85}
tekrar: 5
tekrar_arasi_sn: 8
hedef_sure_dk: 90
arka_plan: assets/arka_plan/gece.mp4
ortam_sesi: {dosya: assets/yagmur.mp3, seviye: 0.25}
gorunurluk: private
kategori: 22
```

### Ses

- Kokoro paragraf paragraf seslendirir; paragraflar arası ~1.2 sn sessizlik. Hız motor seviyesinde (0.85); `atempo`/`lowpass` hileleri kaldırılır.
- Kokoro yüklenemez/başarısız olursa Edge-TTS'e düşülür ve loglanır.
- Uygulama sırasında 3-4 ses örneği üretilir, kullanıcı seçer.

### Döngü

Tekrar sayısı: `n = min(tekrar, floor((hedef + ara) / (hikaye_suresi + ara)))`, en az 1. Anlatı: `[hikâye] (+ ara sessizlik + [hikâye]) × (n-1)`. Toplam süre `hedef_sure_dk`; anlatı sonrası kalan kısım yağmurla dolar, son 30 sn fade-out. Yağmur tüm video boyunca `seviye` ile altta çalar.

### Render ve yükleme

- ffmpeg tek geçiş: video `-stream_loop -1` + `-c:v copy`; ses karışımı AAC 192k; dönüş kodu kontrol edilir.
- Token `veri/tokenlar/<token>.json` (pickle yerine). İlk yetki `calistir.py <kanal> --giris`.
- Resumable yükleme; hata durumunda en fazla 10 deneme, üstel bekleme; sonra `hata` + bildirim.
- Başlık `"<baslik> - Deep Sleep Story (1.5 Hours)"`, kategori yaml'dan (varsayılan 22).

## Hata yönetimi

- Tüm dış çağrılar `core/tekrar.py` üzerinden: sınırlı deneme, üstel bekleme; çıplak `except:` yok.
- Loglar `veri/log/<kanal>.log`. Telegram: başla / başarı / hata.
- Ön kontrol (iş başlamadan): ffmpeg, arka plan ve ortam sesi dosyaları, gerekli anahtarlar, profil/token. Eksikse açık mesajla çıkış.

## Test

- `pytest` birim testleri: ayar doğrulama, LLM JSON ayrıştırma (sahte cevap), `.ass` üretimi, döngü sayısı/süre hesabı, etiket birleştirme, DB durum geçişleri ve devam etme.
- ffmpeg entegrasyon testi: 5 sn sentetik ses/video ile her iki render.
- `--kuru`: yükleme hariç her şey. İlk gerçek yükleme kullanıcı izlerken: TikTok `sadece_ben`, YouTube `private`.

## Geçiş ve güvenlik

- Yeni private repo `BerkeBakir/icerik-fabrikasi`.
- `.gitignore`: `.env`, `client_secret*.json`, `profiller/`, `veri/`, `cikti/`, `assets/`, medya dosyaları.
- Eski repolardan `.env`, `client_secret.json` ve medya yeni klasöre **kopyalanır**. `token.pickle` bir kerelik JSON'a dönüştürülür.
- Eski repolar, yeni sistem çalıştıktan sonra kullanıcı onayıyla arşivlenir.

## Gerekli ücretsiz hesaplar (kullanıcı)

- Google AI Studio API anahtarı (Gemini).
- Mevcut: Telegram bot, YouTube OAuth client.
- Reddit için anahtar gerekmez (RSS).
