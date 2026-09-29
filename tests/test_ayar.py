import textwrap

import pytest

from core.ayar import AyarHatasi, kanal_yukle, profil_yolu, token_yolu


def yaz(kok, ad, metin):
    (kok / "kanallar").mkdir(exist_ok=True)
    (kok / "kanallar" / f"{ad}.yaml").write_text(textwrap.dedent(metin), encoding="utf-8")


TIKTOK = """
platform: tiktok
profil: hikaye1
kaynak: {tip: reddit, subredditler: [AmItheAsshole], min: 3000, max: 4000}
ses: {motor: edge, ses: en-US-AndrewMultilingualNeural, hiz: "+10%"}
arka_plan: assets/arka_plan/orbital.mp4
etiketler: {sabit: [storytime, reddit], llm_ekle: 3}
gorunurluk: herkes
"""

YOUTUBE = """
platform: youtube
token: slumberlab
kaynak: {tip: uretim, prompt: prompts/uyku_hikayesi.txt, kelime: 2500}
ses: {motor: kokoro, ses: af_heart, hiz: 0.85}
arka_plan: assets/arka_plan/gece.mp4
ortam_sesi: {dosya: assets/yagmur.mp3, seviye: 0.3}
gorunurluk: private
"""


def test_tiktok_kanali_varsayilanlarla_yuklenir(tmp_path):
    yaz(tmp_path, "t1", TIKTOK)
    k = kanal_yukle("t1", kok=tmp_path)
    assert k.platform == "tiktok"
    assert k.kaynak.subredditler == ["AmItheAsshole"]
    assert k.ses.hiz == "+10%"
    assert k.arka_plan == tmp_path / "assets/arka_plan/orbital.mp4"
    assert k.etiketler.sabit == ["storytime", "reddit"]
    assert k.etiketler.llm_ekle == 3
    assert k.parca2_gecikme_dk == 120
    assert k.parca2_yontem == "tiktok_zamanla"
    assert profil_yolu(k, tmp_path) == tmp_path / "profiller" / "hikaye1"


def test_youtube_kanali_yuklenir(tmp_path):
    yaz(tmp_path, "y1", YOUTUBE)
    k = kanal_yukle("y1", kok=tmp_path)
    assert k.kaynak.prompt == tmp_path / "prompts/uyku_hikayesi.txt"
    assert k.ses.hiz == 0.85
    assert k.tekrar == 5 and k.tekrar_arasi_sn == 8.0 and k.hedef_sure_dk == 90.0
    assert k.ortam_sesi == tmp_path / "assets/yagmur.mp3"
    assert k.ortam_seviye == 0.3
    assert k.kategori == "22"
    assert token_yolu(k, tmp_path) == tmp_path / "veri" / "tokenlar" / "slumberlab.json"


def test_mutlak_arka_plan_yolu_korunur(tmp_path):
    yaz(tmp_path, "t1", TIKTOK.replace("assets/arka_plan/orbital.mp4", "D:/medya/orbital.mp4"))
    k = kanal_yukle("t1", kok=tmp_path)
    assert str(k.arka_plan).replace("\\", "/") == "D:/medya/orbital.mp4"


@pytest.mark.parametrize(
    "eski,yeni,mesaj",
    [
        ("platform: tiktok", "platform: instagram", "platform"),
        ("motor: edge", "motor: kokoro", "edge"),
        ("gorunurluk: herkes", "gorunurluk: public", "gorunurluk"),
        ("tip: reddit, subredditler: [AmItheAsshole]", "tip: reddit, subredditler: []", "subredditler"),
        ("profil: hikaye1", "", "profil"),
    ],
)
def test_gecersiz_tiktok_ayarlari_reddedilir(tmp_path, eski, yeni, mesaj):
    yaz(tmp_path, "t1", TIKTOK.replace(eski, yeni))
    with pytest.raises(AyarHatasi, match=mesaj):
        kanal_yukle("t1", kok=tmp_path)


def test_gecikme_tiktok_sinirinda_olmali(tmp_path):
    yaz(tmp_path, "t1", TIKTOK + "parca2_gecikme_dk: 10\n")
    with pytest.raises(AyarHatasi, match="parca2_gecikme_dk"):
        kanal_yukle("t1", kok=tmp_path)


def test_youtube_reddit_kaynagini_reddeder(tmp_path):
    yaz(tmp_path, "y1", YOUTUBE.replace(
        "{tip: uretim, prompt: prompts/uyku_hikayesi.txt, kelime: 2500}",
        "{tip: reddit, subredditler: [x]}"))
    with pytest.raises(AyarHatasi, match="uretim"):
        kanal_yukle("y1", kok=tmp_path)


def test_olmayan_kanal(tmp_path):
    with pytest.raises(AyarHatasi, match="yok"):
        kanal_yukle("yok", kok=tmp_path)
