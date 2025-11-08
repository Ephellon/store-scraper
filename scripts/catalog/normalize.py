import re
from typing import Optional

_MARK_RX = re.compile(r"[™®©]", re.U)
_EDITION_RX = re.compile(
   r"\b(deluxe|definitive|gold|ultimate|goty|complete|remastered|hd|bundle|collection|director'?s cut|edition)\b",
   re.I
)

def clean_title(name: str) -> str:
   t = _MARK_RX.sub("", name or "").strip()
   t = re.sub(r"\s{2,}", " ", t)
   return t

def strip_edition_noise(name: str) -> str:
   t = clean_title(name)
   t = _EDITION_RX.sub("", t)
   t = re.sub(r"\s{2,}", " ", t).strip(" -–—")
   return t or clean_title(name)

def price_to_string(amount: Optional[float], currency: Optional[str], *, flags: Optional[str] = None) -> str:
   # Flags can be "Free", "Unavailable", "Announced", etc. If provided, prefer it.
   if flags:
      return flags
   if amount is None or currency is None:
      return "Unavailable"
   # USD-centric examples; format like "$19.99" or "EUR 19.99"
   symbol = "$" if currency.upper() == "USD" else f"{currency.upper()} "
   return f"{symbol}{amount:0.2f}"

def letter_bucket(name: str) -> str:
   ch = (name or "").strip()[:1].lower()
   if ch >= "a" and ch <= "z":
      return ch
   return "_"
