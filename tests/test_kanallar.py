from core.ayar import KOK, kanal_yukle


def test_repodaki_tum_kanallar_gecerli():
    adlar = [p.stem for p in (KOK / "kanallar").glob("*.yaml")]
    assert {"tiktok_hikaye1", "ornek_tiktok_korku", "youtube_slumberlab"} <= set(adlar)
    for ad in adlar:
        kanal_yukle(ad)
