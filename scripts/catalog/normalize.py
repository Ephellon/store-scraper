import re
from typing import Optional

_MARK_RX = re.compile(r"[™®©]", re.U)

# Some storefronts inject non-breaking / zero-width separators inside titles.
# Treat them as regular spaces so names like "The\u200bGame" don't collapse.
_INVISIBLE_SPACE_RX = re.compile(r"[\u00A0\u200B\u200C\u200D\u2060\uFEFF]", re.U)

# Some APIs return collapsed CamelCase / alnum titles (e.g. "DarkQuestRemastered").
# Re-insert likely token boundaries before further normalization.
_TOKEN_BOUNDARY_RX = re.compile(
   r"(?<=[a-z])(?=[A-Z])"          # darkQuest -> dark Quest
   r"|(?<=[A-Z])(?=[A-Z][a-z])"    # XMLParser -> XML Parser
   r"|(?<=[a-zA-Z])(?=[0-9])"      # game2 / PS5 -> game 2 / PS 5
   r"|(?<=[0-9])(?=[a-zA-Z])",     # 2game / 5PS -> 2 game / 5 PS
)

_EDITION_RX = re.compile(
   r"(?:\s*[:\-–—]\s*|\s+)"
   r"("
      r"deluxe|definitive|silver|gold|platinum|ultimate|goty|complete|remastered|hd|bundle|collection|edition|standard|launch|classic"
      r"|game(?:\s*[\-–—:]\s*|\s+)of(?:\s*[\-–—:]\s*|\s+)the(?:\s*[\-–—:]\s*|\s+)year"
      r"|director[’']?s(?:\s*[\-–—:]\s*|\s+)cut"
   r")"
   r"(?:\s+edition)?\b",
   re.I
)

_PLATFORM_NOISE_RX = re.compile(
   r"""
   \s*                          # eat leading whitespace
   \(?                          # optional opening paren
   \s*
   (?:(?:for|on)\s+)?           # optional "for " / "on "
   \b
   (?:
      # PlayStation variants
      (?:
         (?:playstation|ps)\s*[1-5]
         (?:\s*(?:[&+]|and)\s*(?:playstation|ps)?\s*[1-5])*
      )
      |
      # Xbox variants
      xbox(?:\s+one|\s+series(?:\s+[sx](?:\|?[sx])?)?)?
      |
      series\s+[sx](?:\|?[sx])?
      |
      # Nintendo variants
      (?:nintendo\s+)?switch(?:\s*[12])?
   )
   \b
   \s*
   \)?                          # optional closing paren
   """,
   re.I | re.X
)

_TAIL_END_RX = re.compile(
   r"([ &:-]+|\([&\+\s]*\)|\[[&\+\s]*\]) *$",
   re.I | re.X
)

_CURRENCY_SYMBOLS = {
   "USD": "$",
   "CAD": "$",
   "AUD": "$",
   "NZD": "$",
   "EUR": "€",
   "GBP": "£",
   "JPY": "¥",
   "CNY": "¥",
   "HKD": "$",
   "TWD": "$",
   "KRW": "₩",
}

_PLATFORM_MAP = {
   "psp": "PSP",
   "playstationportable": "PSP",
   "psv": "PS Vita",
   "playstationvita": "PS Vita",
   "playstation3": "PS3",
   "playstation4": "PS4",
   "playstation5": "PS5",
   "ps3": "PS3",
   "ps3ps4": "PS3/PS4",
   "ps3ps4ps5": "PS3/PS4/PS5",
   "ps4": "PS4",
   "ps4ps5": "PS4/PS5",
   "ps5": "PS5",
   "ps5ps4": "PS4/PS5",
   "ps5ps4ps3": "PS3/PS4/PS5",

   "xbox": "Xbox",
   "xboxone": "Xbox One",
   "xboxseries": "Xbox Series X|S",
   "xboxseriess": "Xbox Series X|S",
   "xboxseriesx": "Xbox Series X|S",
   "xboxseriesxs": "Xbox Series X|S",
   "xboxplayanywhere": "Xbox Play Anywhere",

   "switch": "Switch",
   "switch2": "Switch 2",
   "nintendoswitch": "Switch",
   "nintendoswitch2": "Switch 2",

   "linux": "Linux",
   "nix": "Linux",
   "unix": "Unix",

   "mac": "Mac",

   "pc": "PC",
   "steam": "PC",
   "win32": "Windows",
   "windows": "Windows",
}

_RATING_MAP = {
   "ratingpending": "rating pending",
   "rp": "rating pending",

   "e10+": "everyone 10+",
   "e10plus": "everyone 10+",
   "eforeveryone": "everyone",
   "esrbeveryone": "everyone",
   "esrbeveryone10+": "everyone 10+",
   "everyone": "everyone",
   "everyone10+": "everyone 10+",

   "esrbteen": "teen",
   "t": "teen",
   "teen": "teen",

   "esrbmature": "mature 17+",
   "m": "mature 17+",
   "mature": "mature 17+",
   "mature17+": "mature 17+",

   "pegi3": "everyone",
   "pegi7": "everyone 10+",
   "pegi12": "teen",
   "pegi16": "mature 17+",
   "pegi18": "mature 17+",

   "ceroa": "everyone",
   "cerob": "teen",
   "ceroc": "mature 17+",
   "cerod": "mature 17+",
   "ceroz": "mature 17+",
}


def _sub_space(rx: re.Pattern, s: str) -> str:
   # Replace matches with a single space to prevent word-joining.
   return rx.sub(" ", s)

def _normalize_ws(s: str) -> str:
   return re.sub(r"\s{2,}", " ", s).strip()

def clean_title(name: str) -> str:
   t = _MARK_RX.sub("", name or "")
   t = _INVISIBLE_SPACE_RX.sub(" ", t)
   t = _TOKEN_BOUNDARY_RX.sub(" ", t)
   t = _normalize_ws(t)

   # Trim tail AFTER whitespace normalization, then normalize again
   # (because removing tail can leave trailing spaces).
   t = _TAIL_END_RX.sub("", t)
   t = _normalize_ws(t)
   return t

def strip_edition_noise(name: str) -> str:
   original = clean_title(name)
   t = original

   # Replace with spaces so we don't glue words together.
   t = _sub_space(_PLATFORM_NOISE_RX, t)
   t = _sub_space(_EDITION_RX, t)

   # Now clean up new dangling punctuation created by removals.
   t = _TAIL_END_RX.sub("", t)

   t = _normalize_ws(t)
   return t or original


def price_to_string(amount: Optional[float], currency: Optional[str], *, flags: Optional[str] = None) -> str:
   # Flags can be "Free", "Unavailable", "Announced", etc. If provided, prefer it.
   if flags:
      return flags
   if amount is None or currency is None:
      return "Unavailable"
   cur = (currency or "").upper()
   symbol = _CURRENCY_SYMBOLS.get(cur)
   if symbol in {"¥", "₩"}:
      return f"{symbol}{int(round(amount))}"
   if symbol:
      return f"{symbol}{amount:0.2f}"
   return f"{cur} {amount:0.2f}".strip()

def letter_bucket(name: str) -> str:
   ch = (name or "").strip()[:1].lower()
   if ch >= "a" and ch <= "z":
      return ch
   return "_"

def normalize_rating(value: Optional[str]) -> Optional[str]:
   if not value:
      return None
   v = re.sub(r"[^a-z0-9+]+", "", value.lower()).strip()
   return _RATING_MAP.get(v)

def normalize_platform(value: str) -> str:
   if not value:
      return ""
   key = re.sub(r"[^a-z0-9]+", "", value.lower()).strip()
   return _PLATFORM_MAP.get(key, value.strip())

def normalize_platforms(values) -> list[str]:
   out = []
   seen = set()
   for v in values or []:
      norm = normalize_platform(str(v))
      if not norm:
         continue
      key = norm.lower()
      if key in seen:
         continue
      seen.add(key)
      out.append(norm)
   return out

def parse_price_string(value: str) -> Optional[float]:
   if not value or value.lower() in {"free", "free+", "unavailable"}:
      return 0.0 if value and value.lower() in {"free", "free+"} else None
   m = re.search(r"([0-9]+(?:[\.,][0-9]{2})?)", value)
   if not m:
      return None
   amt = m.group(1).replace(",", "")
   try:
      return float(amt)
   except ValueError:
      return None
