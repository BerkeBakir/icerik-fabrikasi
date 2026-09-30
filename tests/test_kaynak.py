import html

from core.db import DB
from core.kaynak.reddit import RedditKaynak, html_to_metin, metni_temizle, rss_ayristir
from core.kaynak.uretim import UretimKaynak


def govde_html(paragraflar):
    """paragraflar: ham HTML parçaları (Reddit'in div.md içeriği gibi)."""
    ic = "".join(f"<p>{p}</p>" for p in paragraflar)
    return f'<!-- SC_OFF --><div class="md">{ic}</div><!-- SC_ON --> &#32; submitted by <a href="x">/u/a</a>'


def feed(girdiler):
    parcalar = []
    for kimlik, baslik, paragraflar in girdiler:
        parcalar.append(
            f"<entry><id>t3_{kimlik}</id><title>{html.escape(baslik)}</title>"
            f'<content type="html">{html.escape(govde_html(paragraflar))}</content></entry>'
        )
    return '<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom">' + "".join(parcalar) + "</feed>"


def test_html_to_metin_paragraflari_korur():
    h = govde_html(["First &amp; line.", "Second<br/>line."])
    assert html_to_metin(h) == "First & line.\n\nSecond\nline."


def test_govdesiz_gonderi_bos_doner():
    assert html_to_metin('<a href="x">[link]</a>') == ""


def test_metni_temizle_edit_ve_linkleri_atar():
    t = "Story here https://x.com/a ok.\n\nMore story.\n\nEDIT: thanks all\n\nlater"
    assert metni_temizle(t) == "Story here  ok.\n\nMore story."


def test_rss_ayristir():
    hs = rss_ayristir(feed([("abc", "AITA &amp; me?", ["Hello."])]))
    assert hs[0].kimlik == "reddit:abc"
    assert hs[0].govde == "Hello."


class Yanit:
    def __init__(self, kod, metin):
        self.status_code = kod
        self.text = metin


class SahteOturum:
    def __init__(self, cevaplar):
        self.cevaplar = cevaplar  # url parcasi -> [Yanit, ...]
        self.urller = []

    def get(self, url, headers=None, timeout=None):
        self.urller.append(url)
        assert "Mozilla" in headers["User-Agent"]
        for anahtar, liste in self.cevaplar.items():
            if anahtar in url:
                return liste.pop(0) if len(liste) > 1 else liste[0]
        return Yanit(404, "")


def test_uzunluk_ve_kullanilmis_filtresi(tmp_path):
    db = DB(tmp_path / "f.db")
    db.hikaye_isaretle("reddit:uygun1", "k")
    uzun = "a" * 3500
    o = SahteOturum({
        "r/A/top/.rss?t=week": [Yanit(200, feed([("kisa", "t", ["a" * 100]), ("uygun1", "t", [uzun]), ("uygun2", "t", [uzun])]))],
    })
    beklemeler = []
    h = RedditKaynak(["A"], 3000, 4000, db, oturum=o, uyku=beklemeler.append).sec()
    assert h.kimlik == "reddit:uygun2"
    assert beklemeler == []


def test_subredditler_arasi_bekler_ve_aya_gecer(tmp_path):
    db = DB(tmp_path / "f.db")
    bos = feed([("k", "t", ["kisa"])])
    o = SahteOturum({
        "r/A/top/.rss?t=week": [Yanit(200, bos)],
        "r/B/top/.rss?t=week": [Yanit(200, bos)],
        "r/A/top/.rss?t=month": [Yanit(200, feed([("ay", "t", ["b" * 3200])]))],
    })
    beklemeler = []
    h = RedditKaynak(["A", "B"], 3000, 4000, db, oturum=o, uyku=beklemeler.append, bekleme=25).sec()
    assert h.kimlik == "reddit:ay"
    assert beklemeler == [25, 25]


def test_429_da_bekleyip_bir_kez_tekrar_dener(tmp_path):
    db = DB(tmp_path / "f.db")
    o = SahteOturum({"r/A/top/.rss?t=week": [Yanit(429, ""), Yanit(200, feed([("x", "t", ["c" * 3100])]))]})
    beklemeler = []
    h = RedditKaynak(["A"], 3000, 4000, db, oturum=o, uyku=beklemeler.append).sec()
    assert h.kimlik == "reddit:x"
    assert beklemeler == [60]


def test_hic_uygun_yoksa_none(tmp_path):
    db = DB(tmp_path / "f.db")
    o = SahteOturum({"rss": [Yanit(200, feed([]))]})
    assert RedditKaynak(["A"], 3000, 4000, db, oturum=o, uyku=lambda s: None).sec() is None


class SahteLLM:
    def __init__(self, govdeler):
        self.govdeler = list(govdeler)

    def json_uret(self, prompt, sema, sicaklik=0.8):
        return {"baslik": "B", "govde": self.govdeler.pop(0)}


def test_uretim_kullanilmis_icerigi_tekrar_uretir(tmp_path):
    db = DB(tmp_path / "f.db")
    p = tmp_path / "p.txt"
    p.write_text("Write horror", encoding="utf-8")
    ilk = UretimKaynak(SahteLLM(["aynı"]), p, db).sec()
    db.hikaye_isaretle(ilk.kimlik, "k")
    ikinci = UretimKaynak(SahteLLM(["aynı", "farklı"]), p, db).sec()
    assert ikinci.govde == "farklı"
