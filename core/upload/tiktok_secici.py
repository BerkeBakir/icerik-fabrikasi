"""TikTok Studio DOM seçicileri. Arayüz değişince SADECE burası güncellenir.
Arayüz dili İngilizce'ye sabitlenir (URL'de lang=en)."""
import re

YUKLEME_URL = "https://www.tiktok.com/tiktokstudio/upload?from=upload&lang=en"
GIRIS_URL = "https://www.tiktok.com/login?lang=en"
ICERIK_URL_REGEX = r"/tiktokstudio/content"
GIRIS_YOLU = "/login"
PAYLAS_DEVRE_DISI_ATTR = "aria-disabled"
GORUNURLUK_SECENEK_ROL = "option"

DOSYA_INPUT = 'input[type="file"]'
ACIKLAMA_EDITOR = 'div.public-DraftEditor-content[contenteditable="true"], div[contenteditable="true"]'
ETIKET_ONERI_OGE = 'div.hashtag-suggestion-item, div.mention-list-popover div[role="option"]'
ETIKET_ONERI_METIN = 'span.hash-tag-topic'  # öğe içindeki "#etiket" (yanında "62.2M posts" yazar)
PAYLAS_BUTON = 'button[data-e2e="post_video_button"]'

# Yükleme bitti göstergesi (herhangi biri görününce)
YUKLEME_TAMAM = ['text="Uploaded"', '[data-e2e="upload_status_container"] >> text=/uploaded/i']

# Kapatılacak popup/banner düğmeleri (görünenler tıklanır)
KAPAT_BUTONLARI = [
    'button:has-text("Decline optional cookies")',
    'button:has-text("Got it")',
    'button:has-text("Not now")',
    'div[role="dialog"] button[aria-label="Close"]',
]

# Görünürlük
GORUNURLUK_ACICI = 'div[data-e2e="video_visibility_container"] button, div:has(> span:text("Who can watch this video")) button'
GORUNURLUK_METIN = {"herkes": "Everyone", "arkadaslar": "Friends", "sadece_ben": "Only you"}

# Zamanlama
ZAMANLA_SECENEK = 'label:has(input[value="schedule"])'
ZAMANLA_IZIN = 'button:has-text("Allow")'
ZAMAN_GIRDILERI = 'div.scheduled-picker input.TUXTextInputCore-input'  # [0]=saat "19:05", [1]=tarih "2026-10-01"
TAKVIM_SONRAKI_AY = 'div[class*="calendar"] span[class*="arrow"]:last-child'
TAKVIM_GUN = 'div[class*="calendar"] span[class*="day"][class*="valid"]'
SAAT_SECENEK = 'span[class*="tiktok-timepicker-left"]'
DAKIKA_SECENEK = 'span[class*="tiktok-timepicker-right"]'

# Paylaşım sonrası
SIMDI_PAYLAS = 'button:has-text("Post now")'
BASARI_METINLERI = ['text=/your video (has been|is being) (uploaded|posted|published)/i',
                    'text=/video (scheduled|published)/i', 'text=/Manage your posts/i']


def etiket_oneri_deseni(etiket: str) -> re.Pattern:
    return re.compile(rf"^\s*#?{re.escape(etiket)}\s*$", re.IGNORECASE)


def tam_metin_deseni(metin: str) -> re.Pattern:
    return re.compile(rf"^{re.escape(metin)}$")


# --- Yorumlar (TikTok Studio /tiktokstudio/comment) ---
YORUM_URL = "https://www.tiktok.com/tiktokstudio/comment?lang=en"
ICERIK_URL = "https://www.tiktok.com/tiktokstudio/content?lang=en"
YORUM_HUCRE = 'div[data-tt="components_CommentCell_FlexColumn"]'
YORUM_KULLANICI = 'a[data-tt="components_MessageCell_a"]'
YORUM_METIN = 'span[data-tt="components_TUXTextWithMention_TUXText"]'
YORUM_ZAMAN = 'span[data-tt="components_MessageCell_span_20"]'
YORUM_VIDEO = '[data-tt="components_MessageCell_TUXText"]'  # hücredeki SONUNCUSU video başlığı
YORUM_BEGEN = 'button[data-tt="components_MessageCell_Clickable"]'  # hücredeki İLKİ kalp
YORUM_BEGENILDI = '[data-icon="HeartFill"]:visible'
YORUM_CEVAP_METNI = "Reply"
YORUM_CEVAP_KUTU = "textarea#comment-input"
YORUM_CEVAP_GONDER = 'button:has-text("Post")'  # kutu yanındaki gönder düğmesi (yoksa Enter)
ICERIK_VIDEO_LINK = 'a[href*="/video/"]'
TIKTOK_KOK = "https://www.tiktok.com"
# Video sayfası (tiktok.com/@hesap/video/<id>) — şikayet
VIDEO_YORUM_OGE = '[data-e2e="comment-level-1"]'
VIDEO_YORUM_MENU = '[data-e2e="comment-more-icon"], [aria-label*="more" i]'
VIDEO_SIKAYET_METNI = "Report"
VIDEO_SIKAYET_SEBEP = {"hakaret": ["Harassment or bullying", "Hate and harassment", "Hate speech"],
                       "spam": ["Spam", "Frauds and scams"]}
VIDEO_SIKAYET_GONDER = 'button:has-text("Submit")'
VIDEO_SIKAYET_TAMAM = ['text=/thanks for reporting/i', 'text=/report submitted/i', 'button:has-text("Done")']
