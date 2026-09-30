"""Windows Görev Zamanlayıcı'ya günlük görev ekler/siler.
  python zamanla.py <kanal> --saat 09:00 --saat 18:00
  python zamanla.py <kanal> --saat 09:00 --sil
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent


def _dogrula(saat: str) -> str:
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", saat):
        raise ValueError(f"Saat HH:MM biçiminde olmalı: {saat}")
    return saat


def gorev_adi(kanal: str, saat: str) -> str:
    return f"IcerikFabrikasi_{kanal}_{_dogrula(saat).replace(':', '')}"


def olustur_komutu(kanal: str, saat: str, python: Path, kok: Path) -> list[str]:
    tr = f'"{python}" "{kok / "calistir.py"}" {kanal}'
    return ["schtasks", "/Create", "/F", "/TN", gorev_adi(kanal, saat), "/SC", "DAILY", "/ST", saat, "/TR", tr]


def sil_komutu(kanal: str, saat: str) -> list[str]:
    return ["schtasks", "/Delete", "/F", "/TN", gorev_adi(kanal, saat)]


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("kanal")
    p.add_argument("--saat", action="append", required=True)
    p.add_argument("--sil", action="store_true")
    a = p.parse_args(argv)
    python = KOK / ".venv" / "Scripts" / "python.exe"
    for saat in a.saat:
        komut = sil_komutu(a.kanal, saat) if a.sil else olustur_komutu(a.kanal, saat, python, KOK)
        r = subprocess.run(komut, capture_output=True, text=True, encoding="oem", errors="replace")
        print((r.stdout or r.stderr).strip())
        if r.returncode != 0:
            return r.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
