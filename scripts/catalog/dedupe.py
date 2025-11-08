# catalog/dedupe.py
import re
from typing import Dict, Tuple, List
from catalog.models import GameRecord
from catalog.normalize import strip_edition_noise

def canonical_key(name: str) -> str:
   base = strip_edition_noise(name)
   return re.sub(r"[^a-z0-9]+", "", base.lower())

def cluster(records: List[GameRecord]) -> Dict[str, List[GameRecord]]:
   buckets: Dict[str, List[GameRecord]] = {}
   for r in records:
      k = canonical_key(r.name)
      buckets.setdefault(k, []).append(r)
   return buckets
