from __future__ import annotations
import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict, Any, List, Optional, Set
from urllib.parse import quote

from catalog.adapters.base import Adapter, AdapterConfig, Capabilities
from catalog.models import GameRecord
from catalog.normalize import (
   normalize_game_name,
   price_to_string,
   normalize_platforms,
   normalize_rating,
)
from catalog.http import DomainLimiter

# ── curl_cffi: optional, used to bypass Cloudflare TLS fingerprinting ────
# pip install curl_cffi
# Without it the adapter falls back to the Akamai REST endpoints only.
try:
   from curl_cffi.requests import AsyncSession as CffiSession
   HAS_CURL_CFFI = True
except ImportError:
   HAS_CURL_CFFI = False

# Epic Games Store adapter
#
# Strategy:
#  1) (Primary) Persisted-query GET to store.epicgames.com/graphql via
#     curl_cffi (impersonates Chrome TLS to pass Cloudflare).
#  2) (Supplement) REST endpoints on Akamai CDN (no CF) via httpx.
#
# store.epicgames.com is behind Cloudflare with TLS fingerprint checks.
# Standard httpx / aiohttp / requests all fail with 403 because their
# TLS handshake (JA3 hash) doesn't match a known browser.  curl_cffi
# links against libcurl-impersonate which reproduces Chrome's exact TLS
# and HTTP/2 fingerprint.

EPIC_LIMIT = DomainLimiter(2.0)

# ── Persisted query hashes (from browser traffic) ────────────────────────
SEARCH_STORE_HASH = "29d49ab31d438cd90be2d554d2d54704951e4223a8fcd290fcf68308841a1979"
CATALOG_OFFER_HASH = "ec112951b1824e1e215daecae17db4069c737295d4a697ddb9832923f93a326e"

# ── REST endpoints (Akamai CDN, no CF) ───────────────────────────────────
FREE_GAMES_URL = "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions"
STOREFRONT_URL = "https://store-site-backend-static-ipv4.ak.epicgames.com/storefrontLayout"

# ── Image type preference (best first) ───────────────────────────────────
_IMAGE_PRIORITY = (
   "OfferImageWide",
   "DieselStoreFrontWide",
   "DieselGameBoxTall",
   "Thumbnail",
   "OfferImageTall",
   "DieselGameBox",
   "DieselGameBoxLogo",
   "CodeRedemption_340x440",
)

_FALLBACK_IMAGE = (
   "https://static-assets-prod.epicgames.com/epic-store/static/favicon.ico"
)


@dataclass(slots=True)
class EpicEndpoints:
   graphql_url: str = "https://store.epicgames.com/graphql"
   free_games_url: str = FREE_GAMES_URL
   storefront_url: str = STOREFRONT_URL
   page_size: int = 40
   # Pipe-separated category filter: base games + demos
   category: str = "games/edition/base|games/demo"
   # Chrome version to impersonate (curl_cffi)
   impersonate: str = "chrome"


def _pick_image(key_images: List[Dict[str, Any]]) -> str:
   """Select the best image from keyImages by priority."""
   if not key_images:
      return _FALLBACK_IMAGE
   by_type: Dict[str, str] = {}
   for img in key_images:
      if not isinstance(img, dict):
         continue
      img_type = img.get("type") or ""
      url = img.get("url")
      if url:
         by_type[img_type] = url
   for preferred in _IMAGE_PRIORITY:
      if preferred in by_type:
         return by_type[preferred]
   first = key_images[0] if key_images else {}
   return (first.get("url") if isinstance(first, dict) else None) or _FALLBACK_IMAGE


def _extract_platforms(
   custom_attrs: List[Dict[str, Any]],
   tags: List[Dict[str, Any]],
) -> List[str]:
   """Pull platform info from customAttributes and tags."""
   platforms: List[str] = []

   for attr in custom_attrs or []:
      if not isinstance(attr, dict):
         continue
      key = (attr.get("key") or "").lower()
      value = attr.get("value") or ""
      if "platform" in key and value:
         if value.startswith("["):
            try:
               parsed = json.loads(value)
               if isinstance(parsed, list):
                  platforms.extend(str(v) for v in parsed)
                  continue
            except Exception:
               pass
         for part in value.split(","):
            part = part.strip()
            if part:
               platforms.append(part)

   platform_tag_names = {"windows", "mac", "macos", "linux"}
   for tag in tags or []:
      if not isinstance(tag, dict):
         continue
      name = (tag.get("name") or "").strip()
      if name.lower() in platform_tag_names:
         platforms.append(name)

   if not platforms:
      platforms = ["Windows"]

   return normalize_platforms(platforms)


def _extract_rating(tags: List[Dict[str, Any]]) -> Optional[str]:
   """Pull rating from tags (ESRB / PEGI / IARC labels)."""
   rating_prefixes = ("esrb", "pegi", "usk", "cero", "iarc")
   for tag in tags or []:
      if not isinstance(tag, dict):
         continue
      name = (tag.get("name") or "").strip()
      low = name.lower()
      for prefix in rating_prefixes:
         if low.startswith(prefix):
            return normalize_rating(name)
   return None


class EpicAdapter(Adapter):
   store = "epic"
   capabilities = Capabilities(pagination=True, returns_partial_price=False)

   def __init__(self, *, config: AdapterConfig | None = None,
                endpoints: EpicEndpoints | None = None, **kw):
      # Pop unknown kwargs so base class doesn't choke on adapter-specific keys
      kw.pop("cf_cookies", None)
      super().__init__(config=config, **kw)
      self.endpoints = endpoints or EpicEndpoints()
      self._resume_keys: Set[str] = set()
      self._graphql_available = HAS_CURL_CFFI
      self._cffi_session: Optional[CffiSession] = None if not HAS_CURL_CFFI else None
      self._slug_cache: Dict[str, Optional[str]] = {}  # "sandboxId:offerId" → urlSlug

   # ── lifecycle: manage curl_cffi session alongside the httpx client ────

   async def __aenter__(self) -> "EpicAdapter":
      await super().__aenter__()
      if HAS_CURL_CFFI:
         self._cffi_session = CffiSession(impersonate=self.endpoints.impersonate)
      return self

   async def __aexit__(self, exc_type, exc, tb):
      if self._cffi_session is not None:
         try:
            await self._cffi_session.close()
         except Exception:
            pass
         self._cffi_session = None
      await super().__aexit__(exc_type, exc, tb)

   # ── headers ───────────────────────────────────────────────────────────

   def _graphql_headers(self) -> Dict[str, str]:
      locale = self.config.locale.replace("_", "-").lower()
      return {
         "Accept": "application/json, text/plain, */*",
         "Accept-Language": "en-US,en;q=0.9",
         "DNT": "1",
         "Referer": f"https://store.epicgames.com/{locale}/browse",
         "x-requested-with": "XMLHttpRequest",
         "Cookie": "egs_age_gate_dob=2000-1-21; HasAcceptedAgeGates=ESRB%3A18",
      }

   def _rest_headers(self) -> Dict[str, str]:
      locale = self.config.locale.replace("_", "-").lower()
      return {
         "Accept": "application/json, text/plain, */*",
         "Accept-Language": "en-US,en;q=0.9",
         "DNT": "1",
         "Origin": "https://store.epicgames.com",
         "Referer": f"https://store.epicgames.com/{locale}",
         "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36"
         ),
         "x-requested-with": "XMLHttpRequest",
      }

   # ── public contract ───────────────────────────────────────────────────

   async def iter_games(self) -> AsyncIterator[GameRecord]:
      seen: Set[str] = set()

      # Strategy A: GraphQL via curl_cffi (bypasses CF TLS fingerprinting)
      if self._graphql_available and self._cffi_session is not None:
         async for rec in self._iter_graphql():
            if rec and self._should_emit(rec, seen):
               yield rec
         await asyncio.sleep(0.2)
      else:
         if not HAS_CURL_CFFI:
            self.log.warning(
               "epic: curl_cffi not installed — GraphQL catalog unavailable. "
               "Install with: pip install curl_cffi"
            )
         else:
            self.log.warning(
               "epic: GraphQL session not available, using REST fallback only."
            )

      # Strategy B: REST free games promotions (Akamai, no CF)
      async for rec in self._iter_free_games():
         if rec and self._should_emit(rec, seen):
            yield rec

      # Strategy C: REST storefront layout (Akamai, no CF)
      async for rec in self._iter_storefront():
         if rec and self._should_emit(rec, seen):
            yield rec

   def resume(self, records: List[GameRecord]) -> None:
      super().resume(records)
      for record in records:
         if record.store != self.store:
            continue
         key = self._record_key(record)
         if key:
            self._resume_keys.add(key)

   def _record_key(self, rec: GameRecord) -> Optional[str]:
      candidates = (
         rec.uuid,
         rec.href,
         rec.name and f"{rec.store}:{rec.name}",
      )
      return next((v for v in candidates if v), None)

   def _should_emit(self, rec: GameRecord, seen: Set[str]) -> bool:
      key = self._record_key(rec)
      if not key:
         return True
      if key in self._resume_keys:
         self._resume_keys.discard(key)
         seen.add(key)
         return False
      if key in seen:
         return False
      seen.add(key)
      return True

   # ── Strategy A: GraphQL via curl_cffi ─────────────────────────────────

   async def _resolve_offer_slug(self, offer_id: str, sandbox_id: str) -> Optional[str]:
      """Call getCatalogOffer to resolve the real urlSlug for a game."""
      cache_key = f"{sandbox_id}:{offer_id}"
      if cache_key in self._slug_cache:
         return self._slug_cache[cache_key]

      country = self.config.country.upper()
      locale = self.config.locale.replace("_", "-")

      variables = {
         "country": country,
         "locale": locale,
         "offerId": offer_id,
         "sandboxId": sandbox_id,
      }
      extensions = {
         "persistedQuery": {
            "version": 1,
            "sha256Hash": CATALOG_OFFER_HASH,
         }
      }

      url = (
         f"{self.endpoints.graphql_url}"
         f"?operationName=getCatalogOffer"
         f"&variables={quote(json.dumps(variables, separators=(',', ':')))}"
         f"&extensions={quote(json.dumps(extensions, separators=(',', ':')))}"
      )

      try:
         resp = await self._cffi_session.get(
            url,
            headers=self._graphql_headers(),
            timeout=15,
         )
         if resp.status_code != 200:
            self._slug_cache[cache_key] = None
            return None
         js = resp.json()
         offer = (js.get("data") or {}).get("Catalog", {}).get("catalogOffer") or {}
         slug = offer.get("urlSlug")
         self._slug_cache[cache_key] = slug or None
         return slug or None
      except Exception as exc:
         self.log.debug("epic: getCatalogOffer failed for %s/%s: %s", sandbox_id, offer_id, exc)
         self._slug_cache[cache_key] = None
         return None

   async def _hydrate_slugs(self, elements: List[Dict[str, Any]]) -> None:
      """Resolve real URL slugs for a batch of elements concurrently."""
      sem = asyncio.Semaphore(5)

      async def resolve_one(elem: Dict[str, Any]) -> None:
         async with sem:
            offer_id = elem.get("offerId") or elem.get("id")
            sandbox_id = elem.get("sandboxId") or elem.get("namespace")
            if not offer_id or not sandbox_id:
               return
            slug = await self._resolve_offer_slug(str(offer_id), str(sandbox_id))
            if slug:
               elem["_resolved_slug"] = slug
            await asyncio.sleep(0.05)

      await asyncio.gather(*(resolve_one(e) for e in elements if isinstance(e, dict)))

   async def _iter_graphql(self) -> AsyncIterator[Optional[GameRecord]]:
      assert self._cffi_session is not None

      country = self.config.country.upper()
      locale = self.config.locale.replace("_", "-")
      page_size = self.endpoints.page_size
      start = 0

      while True:
         variables = {
            "allowCountries": country,
            "category": self.endpoints.category,
            "comingSoon": False,
            "count": page_size,
            "country": country,
            "keywords": "",
            "locale": locale,
            "sortBy": "releaseDate",
            "sortDir": "DESC",
            "start": start,
            "tag": "",
            "withPrice": True,
         }
         extensions = {
            "persistedQuery": {
               "version": 1,
               "sha256Hash": SEARCH_STORE_HASH,
            }
         }

         url = (
            f"{self.endpoints.graphql_url}"
            f"?operationName=searchStoreQuery"
            f"&variables={quote(json.dumps(variables, separators=(',', ':')))}"
            f"&extensions={quote(json.dumps(extensions, separators=(',', ':')))}"
         )

         try:
            resp = await self._cffi_session.get(
               url,
               headers=self._graphql_headers(),
               timeout=30,
            )
            if resp.status_code == 403:
               self.log.warning(
                  "epic: GraphQL returned 403 despite curl_cffi. "
                  "CF may have updated fingerprint checks."
               )
               self._graphql_available = False
               break
            resp.raise_for_status()
            js = resp.json()
         except Exception as exc:
            self.log.warning("epic: GraphQL request failed at start=%d: %s", start, exc)
            self._graphql_available = False
            break

         errors = js.get("errors")
         search_store = (
            (js.get("data") or {})
            .get("Catalog", {})
            .get("searchStore", {})
         )
         elements = search_store.get("elements") or []

         if errors:
            if elements:
               self.log.debug("epic: GraphQL returned %d partial errors at start=%d (continuing)", len(errors), start)
            else:
               self.log.warning("epic: GraphQL returned errors with no data: %s", errors)
               self._graphql_available = False
               break

         paging = search_store.get("paging") or {}
         total = paging.get("total")

         # Hydrate real URL slugs via getCatalogOffer (batched, concurrent)
         await self._hydrate_slugs(elements)

         produced = 0
         for elem in elements:
            rec = self._normalize_element(elem)
            if rec:
               produced += 1
               yield rec

         self.metrics["fetched"] += 1
         start += len(elements) if elements else page_size
         if not elements or produced == 0:
            break
         if total is not None and start >= total:
            break

         await asyncio.sleep(0.15)

   # ── Strategy B: REST free games promotions (Akamai, via httpx) ────────

   async def _iter_free_games(self) -> AsyncIterator[Optional[GameRecord]]:
      country = self.config.country.upper()
      locale = self.config.locale.replace("_", "-")
      params = {
         "locale": locale,
         "country": country,
         "allowCountries": country,
      }

      try:
         resp = await self.request(
            "GET", self.endpoints.free_games_url,
            params=params, headers=self._rest_headers(),
         )
         js = resp.json()
      except Exception as exc:
         self.log.warning("epic: freeGamesPromotions request failed: %s", exc)
         return

      elements = (
         (js.get("data") or {})
         .get("Catalog", {})
         .get("searchStore", {})
         .get("elements", [])
      )
      for elem in elements:
         rec = self._normalize_element(elem)
         if rec:
            yield rec

   # ── Strategy C: REST storefront layout (Akamai, via httpx) ────────────

   async def _iter_storefront(self) -> AsyncIterator[Optional[GameRecord]]:
      country = self.config.country.upper()
      locale = self.config.locale.replace("_", "-")
      start = 0
      count = 40

      while True:
         params = {
            "locale": locale,
            "country": country,
            "start": start,
            "count": count,
         }

         try:
            resp = await self.request(
               "GET", self.endpoints.storefront_url,
               params=params, headers=self._rest_headers(),
            )
            js = resp.json()
         except Exception as exc:
            self.log.warning("epic: storefrontLayout request failed at start=%d: %s", start, exc)
            break

         data = js.get("data") or []
         if not isinstance(data, list):
            data = [data] if isinstance(data, dict) else []

         produced = 0
         for module in data:
            if not isinstance(module, dict):
               continue
            offers = module.get("offers") or module.get("items") or []
            if not isinstance(offers, list):
               continue
            for offer in offers:
               if not isinstance(offer, dict):
                  continue
               rec = self._normalize_storefront_item(offer)
               if rec:
                  produced += 1
                  yield rec

         if produced == 0 or produced < count:
            break
         start += count
         await asyncio.sleep(0.15)

   # ── Normalization ─────────────────────────────────────────────────────

   def _normalize_element(self, elem: Dict[str, Any]) -> Optional[GameRecord]:
      """Normalize a GraphQL searchStore element into a GameRecord."""
      if not isinstance(elem, dict):
         return None

      name = normalize_game_name(elem.get("title") or "")
      if not name:
         return None

      offer_id = elem.get("offerId") or elem.get("id")
      sandbox_id = elem.get("sandboxId") or elem.get("namespace")
      key_images = elem.get("keyImages") or []
      image = _pick_image(key_images)
      href = self._build_product_url(elem)
      price_str = self._extract_price(elem)

      custom_attrs = elem.get("customAttributes") or []
      tags = elem.get("tags") or []
      platforms = _extract_platforms(custom_attrs, tags)
      rating = _extract_rating(tags)

      categories = elem.get("categories") or []
      record_type = "game"
      for cat in categories:
         if isinstance(cat, dict):
            path = (cat.get("path") or "").lower()
            if "demo" in path:
               record_type = "demo"
               break

      extra: Dict[str, Any] = {}
      if sandbox_id:
         extra["sandboxId"] = str(sandbox_id)
      if offer_id:
         extra["offerId"] = str(offer_id)

      return GameRecord(
         store="epic",
         name=name,
         price=price_str,
         image=image,
         href=href,
         uuid=str(offer_id) if offer_id else None,
         platforms=platforms,
         rating=rating,
         type=record_type,
         extra=extra,
      )

   def _normalize_storefront_item(self, item: Dict[str, Any]) -> Optional[GameRecord]:
      """Normalize an item from the REST storefrontLayout endpoint."""
      if not isinstance(item, dict):
         return None

      name = normalize_game_name(
         item.get("title") or item.get("name") or ""
      )
      if not name:
         return None

      key_images = item.get("keyImages") or []
      image = _pick_image(key_images) if key_images else _FALLBACK_IMAGE

      slug = item.get("productSlug") or item.get("urlSlug") or item.get("url")
      loc = self.config.locale.replace("_", "-").lower()
      if slug and isinstance(slug, str):
         if slug.startswith("http"):
            href = slug
         elif slug.startswith("/"):
            href = f"https://store.epicgames.com{slug}"
         else:
            href = f"https://store.epicgames.com/{loc}/p/{slug}"
      else:
         href = f"https://store.epicgames.com/{loc}"

      price_str = self._extract_price(item)
      if price_str == "Unavailable":
         price_obj = item.get("price") or item.get("currentPrice")
         if isinstance(price_obj, (int, float)):
            if price_obj == 0:
               price_str = "Free"
            else:
               price_str = price_to_string(float(price_obj), "USD")
         elif isinstance(price_obj, str):
            price_str = price_obj

      elem_id = item.get("id") or item.get("offerId")

      return GameRecord(
         store="epic",
         name=name,
         price=price_str,
         image=str(image),
         href=str(href),
         uuid=str(elem_id) if elem_id else None,
         platforms=normalize_platforms(["Windows"]),
         rating=None,
         type="game",
      )

   def _build_product_url(self, elem: Dict[str, Any]) -> str:
      loc = self.config.locale.replace("_", "-").lower()
      base = f"https://store.epicgames.com/{loc}"

      # Prefer the hydrated slug from getCatalogOffer
      resolved = elem.get("_resolved_slug")
      if resolved and isinstance(resolved, str):
         return f"{base}/p/{resolved}"

      url = elem.get("url")
      if url and isinstance(url, str):
         if url.startswith("http"):
            return url
         return f"{base}{url}" if url.startswith("/") else f"{base}/{url}"

      # productSlug and urlSlug from searchStoreQuery are often UUIDs — use
      # only if they look like a real slug (contain a dash or lowercase letter
      # run, not a bare hex UUID).
      for key in ("productSlug", "urlSlug"):
         slug = elem.get(key)
         if not slug or not isinstance(slug, str) or slug == "[]":
            continue
         # Skip values that look like bare UUIDs (32 hex chars with optional dashes)
         stripped = slug.replace("-", "")
         if len(stripped) == 32 and all(c in "0123456789abcdef" for c in stripped.lower()):
            continue
         return f"{base}/p/{slug}"

      return base

   def _extract_price(self, elem: Dict[str, Any]) -> str:
      """Extract formatted price from a GraphQL element."""
      price_info = elem.get("price")
      if not isinstance(price_info, dict):
         return "Unavailable"

      total_price = price_info.get("totalPrice")
      if not isinstance(total_price, dict):
         return "Unavailable"

      fmt = total_price.get("fmtPrice")
      if isinstance(fmt, dict):
         original_fmt = fmt.get("originalPrice")
         if isinstance(original_fmt, str) and original_fmt.strip():
            stripped = original_fmt.strip()
            if stripped != "0":
               return stripped

      original = total_price.get("originalPrice")
      currency_code = total_price.get("currencyCode")

      if original is not None and isinstance(original, (int, float)):
         decimals = 2
         currency_info = total_price.get("currencyInfo")
         if isinstance(currency_info, dict):
            dec = currency_info.get("decimals")
            if isinstance(dec, int):
               decimals = dec

         amount = original / (10 ** decimals) if decimals > 0 else float(original)

         if amount == 0:
            return "Free"

         return price_to_string(amount, currency_code)

      return "Unavailable"
