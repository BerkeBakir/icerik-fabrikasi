from __future__ import annotations

import time


def tekrar_dene(fn, *, deneme: int = 3, bekleme: float = 2.0, carpan: float = 2.0,
                hatalar: tuple = (Exception,), uyku=time.sleep, log=None):
    for i in range(deneme):
        try:
            return fn()
        except hatalar as e:
            if i == deneme - 1:
                raise
            sure = bekleme * carpan ** i
            if log:
                log.warning("Deneme %d/%d başarısız (%s), %.0f sn sonra tekrar", i + 1, deneme, e, sure)
            uyku(sure)
