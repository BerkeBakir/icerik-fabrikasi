"""Windows Görev Zamanlayıcı'ya günlük/haftalık görev ekler/siler.
  python zamanla.py <kanal> --saat 09:00 --saat 18:00
  python zamanla.py <kanal> --saat 10:00 --ek=--yorumlar
  python zamanla.py <kanal> --saat 12:00 --ek=--yorum-raporu --haftalik SUN
  python zamanla.py <kanal> --saat 09:00 --sil
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
GUNLER = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def _dogrula(saat: str) -> str:
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", saat):
        raise ValueError(f"Saat HH:MM biçiminde olmalı: {saat}")
    return saat


def _gun(gun: str | None) -> str | None:
    if gun is not None and gun not in GUNLER:
        raise ValueError(f"Gün şunlardan biri olmalı: {', '.join(GUNLER)}")
    return gun


def gorev_adi(kanal: str, saat: str, ek: str = "", gun: str | None = None) -> str:
    parcalar = ["IcerikFabrikasi", kanal]
    if ek:
        parcalar.append(re.sub(r"[^a-z0-9]", "", ek.lower()))
    if _gun(gun):
        parcalar.append(gun)
    parcalar.append(_dogrula(saat).replace(":", ""))
    return "_".join(parcalar)


def olustur_komutu(kanal: str, saat: str, python: Path, kok: Path, ek: str = "", gun: str | None = None) -> list[str]:
    tr = f'"{python}" "{kok / "calistir.py"}" {kanal}' + (f" {ek}" if ek else "")
    siklik = ["/SC", "WEEKLY", "/D", gun] if _gun(gun) else ["/SC", "DAILY"]
    return ["schtasks", "/Create", "/F", "/TN", gorev_adi(kanal, saat, ek, gun), *siklik, "/ST", saat, "/TR", tr]


def sil_komutu(kanal: str, saat: str, ek: str = "", gun: str | None = None) -> list[str]:
    return ["schtasks", "/Delete", "/F", "/TN", gorev_adi(kanal, saat, ek, gun)]


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("kanal")
    p.add_argument("--saat", action="append", required=True)
    p.add_argument("--ek", default="", help="calistir.py'ye eklenecek bayrak, ör. --ek=--yorumlar")
    p.add_argument("--haftalik", choices=GUNLER, help="haftalık görev günü (yoksa günlük)")
    p.add_argument("--sil", action="store_true")
    a = p.parse_args(argv)
    python = KOK / ".venv" / "Scripts" / "python.exe"
    for saat in a.saat:
        if a.sil:
            komut = sil_komutu(a.kanal, saat, a.ek, a.haftalik)
        else:
            komut = olustur_komutu(a.kanal, saat, python, KOK, a.ek, a.haftalik)
        r = subprocess.run(komut, capture_output=True, text=True, encoding="oem", errors="replace")
        print((r.stdout or r.stderr).strip())
        if r.returncode != 0:
            return r.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
