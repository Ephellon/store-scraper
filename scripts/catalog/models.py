from __future__ import annotations
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, HttpUrl, Field

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
   rating: Optional[str] = None



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
   rating: Optional[str] = None
   type: Optional[str] = None
   extra: Dict[str, Any] = Field(default_factory=dict)
