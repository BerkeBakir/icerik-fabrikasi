from __future__ import annotations

from core.kaynak.reddit import RedditKaynak
from core.kaynak.uretim import UretimKaynak


def kaynak_olustur(kanal, llm, db, log):
    k = kanal.kaynak
    if k.tip == "reddit":
        return RedditKaynak(k.subredditler, k.min, k.max, db, log=log)
    return UretimKaynak(llm, k.prompt, db, log=log)
