"""Ses seçimi için örnek dosyalar üretir: cikti/ses_ornekleri/."""
from __future__ import annotations

from pathlib import Path

from core.ayar import KOK

ORNEK = ("The rain tapped gently against the old wooden window, and the cabin was warm and quiet.\n\n"
         "Somewhere far away, a river whispered to the stones, slow and patient, as the night settled in.")
KOKORO_SESLER = ["af_heart", "af_bella", "af_nicole", "am_michael", "bf_emma", "bm_george"]
EDGE_SESLER = ["en-US-AndrewMultilingualNeural", "en-US-AvaMultilingualNeural", "en-GB-RyanNeural"]


def uret(kok: Path = KOK) -> list[Path]:
    from core.tts.edge import EdgeTTS
    from core.tts.kokoro import KokoroTTS

    klasor = kok / "cikti" / "ses_ornekleri"
    klasor.mkdir(parents=True, exist_ok=True)
    yollar = []
    for s in KOKORO_SESLER:
        try:
            yollar.append(KokoroTTS(s, 0.85).seslendir(ORNEK, klasor / f"kokoro_{s}.wav").yol)
        except Exception as e:
            print(f"Kokoro {s} başarısız: {e}")
    for s in EDGE_SESLER:
        yollar.append(EdgeTTS(s, "-10%").seslendir(ORNEK, klasor / f"edge_{s}.mp3").yol)
    return yollar
