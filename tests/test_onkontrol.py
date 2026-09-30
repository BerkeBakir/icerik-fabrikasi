from core.ayar import Etiketler, Kanal, Kaynak, Ses
from core.onkontrol import onkontrol


def tiktok(tmp_path):
    return Kanal(ad="t", platform="tiktok", kaynak=Kaynak("reddit", ["A"]), ses=Ses("edge", "v", "+0%"),
                 arka_plan=tmp_path / "bg.mp4", gorunurluk="herkes", etiketler=Etiketler(), profil="p1")


def test_eksikler_listelenir(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    hatalar = onkontrol(tiktok(tmp_path), kok=tmp_path)
    metin = "\n".join(hatalar)
    assert "GEMINI_API_KEY" in metin and "bg.mp4" in metin and "--giris" in metin


def test_kuru_modda_oturum_istenmez(tmp_path, monkeypatch):
    monkeypatch.setattr("core.onkontrol.medya.araclar_var_mi", lambda: True)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    (tmp_path / "bg.mp4").write_bytes(b"x")
    assert onkontrol(tiktok(tmp_path), kok=tmp_path, kuru=True) == []
