# TikTok Yorum Yöneticisi — Tasarım

Tarih: 2026-10-04 · Proje: icerik-fabrikasi · Durum: onaylandı (kullanıcı)

## Amaç

TikTok kanalına gelen yorumları otomatik işlemek: soruları ve yapıcı yorumları yanıtlamak, sıradan
yorumları beğenmek, hakaret ve spam yorumları şikayet etmek, yapıcı geri bildirimleri toplayıp
haftalık rapor olarak sunmak. Tamamen ücretsiz (Gemini + Playwright), onay adımı yok; kullanıcı
Telegram bildirimleriyle izler.

## Davranış

`python calistir.py <kanal> --yorumlar` (yalnız TikTok kanalları). Her çalıştırma:

1. TikTok Studio Comments sayfasını açar (`/tiktokstudio/comment`), son 7 günün yorumlarını okur.
   Kendi (kanal sahibi) yorumları ve veritabanında zaten kayıtlı yorumlar atlanır.
2. Her yeni yorumu Gemini ile sınıflandırır; tür ve (gerekiyorsa) cevap tek JSON çağrısında üretilir.
3. Türe göre eylem:

| Tür | Tanım | Eylem |
|---|---|---|
| `soru` | hikâye/kanal hakkında soru | cevap verir |
| `yapici` | iyileştirme önerisi, eleştiri (ses, altyazı, video, hikâye, uzunluk) | kaydeder (konu + tek cümle öneri) ve cevap verir |
| `yorum` | övgü, fikir, tepki | beğenir |
| `hakaret` | küfür, aşağılama, nefret söylemi | şikayet eder, cevap vermez |
| `spam` | reklam, "follow me", link, anlamsız | şikayet eder, cevap vermez |

4. Çalıştırma sonunda Telegram özeti: `🧾 [kanal] 3 cevap, 5 beğeni, 1 şikayet (1 hata)`.

### Küfür çift kontrolü
Gemini kararından bağımsız: yorum metni küçük bir küfür listesiyle (İngilizce + Türkçe, kelime sınırıyla)
eşleşirse tür zorla `hakaret` olur. Üretilen cevap da aynı listeden geçer; eşleşirse cevap gönderilmez
(yorum `hata` değil `atlandi` olur).

### Cevap kuralları (Gemini istemi)
- Girdi: yorum metni, yorum sahibinin kullanıcı adı, videonun açıklaması (Studio satırındaki video başlığı).
  Varsa bu açıklamayla eşleşen işin hikâye kancası/açıklaması da bağlam olarak verilir.
- Yorumun dilinde, en fazla 150 karakter, link/etiket yok, en fazla 1 emoji.
- Kanal bir hikâye anlatım kanalıdır; hikâyeler Reddit'ten uyarlanır. Hikâyeyi kanal sahibinin
  yaşadığını iddia etmez, kişisel bilgi vermez, tartışmaya girmez.
- JSON şeması: `{"tur": str, "cevap": str, "konu": str, "oneri": str}`; `cevap` yalnız soru/yapıcı için
  dolu, `konu`/`oneri` yalnız yapıcı için. `konu` ∈ {ses, altyazi, video, hikaye, uzunluk, diger}.
  Geçersiz `tur` → `yorum` (en zararsız eylem: beğeni) sayılır.

### Sınırlar (spam'e karşı)
- Çalıştırma başına en fazla `en_fazla` cevap (varsayılan 10), en fazla 5 şikayet, en fazla 30 beğeni.
- Her eylem arasında rastgele bekleme: cevap/şikayet 20-60 sn, beğeni 3-8 sn.
- Sınırı aşan yorumlar `bekliyor` olarak kalır, sonraki çalıştırmada işlenir (Gemini tekrar çağrılmaz).

### Telegram bildirimleri
- Her gönderilen cevap: `💬 [kanal] @kullanici (video başlığı…)\n"yorum"\n↳ "cevap"`
- Her şikayet: `🚩 [kanal] @kullanici şikayet edildi (hakaret|spam): "yorum"`
- Beğeniler tek tek bildirilmez, özette sayılır.
- Haftalık rapor: `--yorum-raporu` komutu, son 7 günün `yapici` kayıtlarını konuya göre gruplar:
  `📊 Haftalık yapıcı yorumlar (6)\n• ses (3): "…", "…"\n• hikaye (2): "…"`. Kayıt yoksa
  "Bu hafta yapıcı yorum yok" gönderilir.

## Bileşenler

| Dosya | Sorumluluk |
|---|---|
| `core/yorum/siniflandir.py` | Gemini istemi + JSON şeması, küfür listesi, `siniflandir(llm, yorum, baglam) -> Karar` |
| `core/yorum/tiktok_yorum.py` | Playwright: yorumları oku, cevapla, beğen, şikayet et (seçiciler `tiktok_secici.py`'de) |
| `core/yorum/yonetici.py` | Akış: oku → kaydet → sınıflandır → sınırlar dahilinde eylem → bildirim/özet; `rapor()` |
| `core/db.py` | Yeni `yorumlar` tablosu ve erişim metotları |
| `core/ayar.py` | Kanal ayarı `yorum: {aktif, en_fazla}` |
| `calistir.py` | `--yorumlar`, `--yorum-raporu` bayrakları |
| `zamanla.py` | `--ek "<bayrak>"` (komuta eklenecek bayrak, görev adına da eklenir) ve `--haftalik SUN` (haftalık görev) desteği |

`--yorumlar --kuru`: yorumları okur ve sınıflandırır, sonuçları ekrana/loga yazar; hiçbir eylem
yapmaz ve veritabanına yazmaz.

### Veri modeli — `yorumlar` tablosu
`kimlik TEXT PK` (kanal + kullanıcı + metin + video başlığının sha1'i; Studio yorum kimliği vermiyor),
`kanal, kullanici, metin, video, tur, cevap, konu, oneri, durum, hata, tarih, guncelleme`.
`durum` ∈ {`yeni`, `bekliyor`, `cevaplandi`, `begenildi`, `sikayet_edildi`, `atlandi`, `hata`}.
`hata` durumundakiler bir sonraki çalıştırmada bir kez daha denenir; ikinci hatada `atlandi`.

### Kilit
Yorum çalıştırması TikTok yüklemesiyle aynı küresel TikTok kilidini kullanır (aynı Chrome profili iki
süreçte açılamaz). Kilit 30 dk içinde boşalmazsa çalıştırma atlanır (exit 0, Telegram notu).

### Zamanlama
Yorumlar: her gün 10:00, 14:00, 17:00, 23:00. Rapor: pazar 12:00 (haftalık görev).
Yüklemeler (19:00, 02:00) ile çakışmaz.

## Hata yönetimi
- Oturum kapalı → `yetki` hatası, Telegram uyarısı, exit 1 (yükleyiciyle aynı mesaj).
- Tek bir yorumdaki eylem hatası çalıştırmayı durdurmaz: yorum `hata` olur, ekran görüntüsü kaydedilir,
  sıradakine geçilir. Üst üste 3 eylem hatası → çalıştırma durur (arayüz değişmiş olabilir), Telegram'a
  ekran görüntüsüyle bildirilir.
- Gemini hatası → o yorum `yeni` kalır, sonraki çalıştırmada tekrar denenir.

## Test
- Birim: sınıflandırma ayrıştırma (geçersiz tür, eksik alan), küfür çift kontrolü (yorum ve cevap),
  kimlik üretimi, sınırlar ve `bekliyor` taşması, `hata` → tekrar → `atlandi`, haftalık rapor gruplaması,
  ayar doğrulaması, CLI bayrakları. Playwright katmanı sahte sayfa/yükleyiciyle izole edilir.
- Canlı: önce yalnız okuma + sınıflandırma (eylemsiz `--kuru`), sonra kullanıcı gözetiminde ilk gerçek tur.
  Şikayet akışının (video sayfası ⋯ → Report) varlığı kalibrasyonda doğrulanır; yoksa şikayet
  yerine Studio'daki Delete kullanılması kullanıcıya sorulur.

## Kapsam dışı
YouTube yorumları, kullanıcı onaylı mod, ayarların yorumlara göre otomatik değiştirilmesi.
