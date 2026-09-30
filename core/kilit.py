"""Basit dosya kilidi: aynı anda tek TikTok yüklemesi."""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path


class KilitHatasi(Exception):
    pass


@contextmanager
def dosya_kilidi(yol: Path, bekle_sn: float = 1800, eski_sn: float = 7200, uyku=time.sleep):
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    baslangic = time.time()
    while True:
        try:
            fd = os.open(yol, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(os.getpid()).encode())
            finally:
                os.close(fd)
            break
        except FileExistsError:
            try:
                yas = time.time() - yol.stat().st_mtime
            except FileNotFoundError:
                continue
            if yas > eski_sn:
                # Atomik devralma: yalnızca bir bekleyen aynı dosyayı yeniden adlandırabilir.
                gecici = yol.with_name(f"{yol.name}.{os.getpid()}.{time.time_ns()}.eski")
                try:
                    os.replace(yol, gecici)
                except FileNotFoundError:
                    continue
                except PermissionError:
                    pass  # Windows: başka süreç açık tutuyor; kilit hâlâ dolu say
                else:
                    try:
                        gecici.unlink(missing_ok=True)
                    except PermissionError:
                        pass
                    continue
            if time.time() - baslangic > bekle_sn:
                raise KilitHatasi(f"Kilit boşalmadı: {yol}")
            uyku(10)
    try:
        yield
    finally:
        yol.unlink(missing_ok=True)
