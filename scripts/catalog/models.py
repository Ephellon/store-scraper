from __future__ import annotations
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, HttpUrl, Field, field_validator

# Ratings used in your child-project’s examples (lowercase)
Rating = Literal[
   "everyone",
   "everyone 10+",
   "rating pending",
   "teen",
   "mature 17+",
   "none",
]

class LetterItem(BaseModel):
   """
   Shape for per-letter arrays (_.json, a.json ... z.json)
   """
   name: str
   type: Optional[str] = None
   price: str
   image: HttpUrl
   href: HttpUrl
   uuid: Optional[str] = None
   platforms: List[str] = Field(default_factory=list)
   rating: Optional[Rating] = None

   # --- normalizers to keep the JSON shape tidy ---
   @field_validator("price")
   @classmethod
   def _price_nonempty(cls, v: str) -> str:
      v = (v or "").strip()
      return v if v else "Unavailable"

   @field_validator("platforms")
   @classmethod
   def _platforms_clean(cls, v: List[str]) -> List[str]:
      seen, out = set(), []
      for p in v or []:
         p = str(p).strip()
         if p and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
      return out

   @field_validator("rating")
   @classmethod
   def _rating_lower(cls, v: Optional[str]) -> Optional[str]:
      return v.lower() if isinstance(v, str) else v


class GameRecord(BaseModel):
   """
   Internal normalized record yielded by adapters.
   This maps 1:1 to LetterItem when writing per-letter files,
   and to [name, {..}] pairs for the bang file.
   """
   store: Literal["steam", "psn", "xbox", "nintendo"]
   name: str
   price: str
   image: HttpUrl
   href: HttpUrl
   uuid: Optional[str] = None
   platforms: List[str] = Field(default_factory=list)
   rating: Optional[Rating] = None
   type: Optional[str] = None
   extra: Dict[str, Any] = Field(default_factory=dict)

   @field_validator("price")
   @classmethod
   def _price_nonempty(cls, v: str) -> str:
      v = (v or "").strip()
      return v if v else "Unavailable"

   @field_validator("platforms")
   @classmethod
   def _platforms_clean(cls, v: List[str]) -> List[str]:
      seen, out = set(), []
      for p in v or []:
         p = str(p).strip()
         if p and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
      return out

   @field_validator("rating")
   @classmethod
   def _rating_lower(cls, v: Optional[str]) -> Optional[str]:
      return v.lower() if isinstance(v, str) else v
