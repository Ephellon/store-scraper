"""Tests for catalog.adapters.epic — normalization, helpers, and curl_cffi gating."""
import pytest

from catalog.adapters.epic import (
   EpicAdapter,
   EpicEndpoints,
   HAS_CURL_CFFI,
   _pick_image,
   _extract_platforms,
   _extract_rating,
   _FALLBACK_IMAGE,
   SEARCH_STORE_HASH,
   CATALOG_OFFER_HASH,
)
from catalog.adapters.base import AdapterConfig


# ─── _pick_image ─────────────────────────────────────────────────────────

class TestPickImage:
   def test_prefers_offer_image_wide(self):
      images = [
         {"type": "Thumbnail", "url": "https://ex.com/thumb.png"},
         {"type": "OfferImageWide", "url": "https://ex.com/wide.png"},
         {"type": "DieselGameBoxTall", "url": "https://ex.com/tall.png"},
      ]
      assert _pick_image(images) == "https://ex.com/wide.png"

   def test_falls_back_to_diesel_wide(self):
      images = [
         {"type": "DieselStoreFrontWide", "url": "https://ex.com/diesel.png"},
         {"type": "Thumbnail", "url": "https://ex.com/thumb.png"},
      ]
      assert _pick_image(images) == "https://ex.com/diesel.png"

   def test_uses_first_when_no_priority_match(self):
      images = [
         {"type": "UnknownType", "url": "https://ex.com/unknown.png"},
      ]
      assert _pick_image(images) == "https://ex.com/unknown.png"

   def test_empty_list_returns_fallback(self):
      assert _pick_image([]) == _FALLBACK_IMAGE

   def test_none_url_returns_fallback(self):
      assert _pick_image([{"type": "Thumbnail"}]) == _FALLBACK_IMAGE


# ─── _extract_platforms ──────────────────────────────────────────────────

class TestExtractPlatforms:
   def test_from_custom_attributes(self):
      attrs = [{"key": "com.epicgames.app.platforms", "value": "Windows,Mac"}]
      result = _extract_platforms(attrs, [])
      assert "Windows" in result
      assert "Mac" in result

   def test_from_json_array_attribute(self):
      attrs = [{"key": "platforms", "value": '["Windows", "Linux"]'}]
      result = _extract_platforms(attrs, [])
      assert "Windows" in result
      assert "Linux" in result

   def test_from_tags(self):
      tags = [{"name": "Windows"}, {"name": "Mac"}, {"name": "Action"}]
      result = _extract_platforms([], tags)
      assert "Windows" in result
      assert "Mac" in result
      assert "Action" not in result

   def test_default_windows(self):
      result = _extract_platforms([], [])
      assert result == ["Windows"]

   def test_deduplicates(self):
      attrs = [{"key": "platforms", "value": "Windows"}]
      tags = [{"name": "Windows"}]
      result = _extract_platforms(attrs, tags)
      assert result.count("Windows") == 1


# ─── _extract_rating ─────────────────────────────────────────────────────

class TestExtractRating:
   def test_esrb_tag(self):
      tags = [{"name": "Action"}, {"name": "ESRB Teen"}]
      assert _extract_rating(tags) == "teen"

   def test_pegi_tag(self):
      tags = [{"name": "PEGI 18"}]
      assert _extract_rating(tags) == "mature 17+"

   def test_no_rating_tags(self):
      tags = [{"name": "Action"}, {"name": "RPG"}]
      assert _extract_rating(tags) is None

   def test_empty_tags(self):
      assert _extract_rating([]) is None


# ─── EpicEndpoints defaults ─────────────────────────────────────────────

class TestEpicEndpoints:
   def test_default_graphql_url(self):
      ep = EpicEndpoints()
      assert ep.graphql_url == "https://store.epicgames.com/graphql"

   def test_default_category_includes_demo(self):
      ep = EpicEndpoints()
      assert "games/demo" in ep.category
      assert "games/edition/base" in ep.category
      assert "|" in ep.category

   def test_default_impersonate(self):
      ep = EpicEndpoints()
      assert ep.impersonate == "chrome"


# ─── curl_cffi gating ───────────────────────────────────────────────────

class TestCurlCffiGating:
   def test_graphql_availability_tracks_curl_cffi(self):
      adapter = EpicAdapter(config=AdapterConfig(country="US", locale="en-US"))
      assert adapter._graphql_available == HAS_CURL_CFFI

   def test_cffi_session_none_before_aenter(self):
      adapter = EpicAdapter(config=AdapterConfig(country="US", locale="en-US"))
      assert adapter._cffi_session is None


# ─── EpicAdapter._normalize_element ─────────────────────────────────────

class TestNormalizeElement:
   def _make_adapter(self):
      return EpicAdapter(config=AdapterConfig(country="US", locale="en-US"))

   def test_basic_element(self):
      adapter = self._make_adapter()
      elem = {
         "title": "Fortnite\u2122",
         "id": "abc123",
         "productSlug": "fortnite",
         "keyImages": [
            {"type": "OfferImageWide", "url": "https://ex.com/fortnite.png"},
         ],
         "customAttributes": [
            {"key": "com.epicgames.app.platforms", "value": "Windows,Mac"},
         ],
         "tags": [
            {"name": "ESRB Teen"},
            {"name": "Action"},
         ],
         "categories": [
            {"path": "games/edition/base"},
         ],
         "price": {
            "totalPrice": {
               "originalPrice": 0,
               "discountPrice": 0,
               "discount": 0,
               "currencyCode": "USD",
               "currencyInfo": {"decimals": 2},
               "fmtPrice": {
                  "originalPrice": "0",
                  "discountPrice": "0",
                  "intermediatePrice": "0",
               },
            },
         },
      }
      rec = adapter._normalize_element(elem)
      assert rec is not None
      assert rec.name == "Fortnite"  # trademark stripped
      assert rec.store == "epic"
      assert rec.uuid == "abc123"
      assert rec.image == "https://ex.com/fortnite.png"
      assert "Windows" in rec.platforms
      assert "Mac" in rec.platforms
      assert rec.rating == "teen"
      assert rec.type == "game"
      assert "https://store.epicgames.com/en-us/p/fortnite" == str(rec.href)

   def test_demo_category(self):
      adapter = self._make_adapter()
      elem = {
         "title": "Some Demo",
         "id": "demo1",
         "urlSlug": "some-demo",
         "keyImages": [],
         "customAttributes": [],
         "tags": [],
         "categories": [
            {"path": "games/demo"},
         ],
         "price": {
            "totalPrice": {
               "originalPrice": 0,
               "discountPrice": 0,
               "discount": 0,
               "currencyCode": "USD",
               "currencyInfo": {"decimals": 2},
               "fmtPrice": {
                  "originalPrice": "0",
                  "discountPrice": "0",
                  "intermediatePrice": "0",
               },
            },
         },
      }
      rec = adapter._normalize_element(elem)
      assert rec is not None
      assert rec.type == "demo"

   def test_paid_game_price(self):
      adapter = self._make_adapter()
      elem = {
         "title": "Cyberpunk 2077",
         "id": "cyber1",
         "productSlug": "cyberpunk-2077",
         "keyImages": [{"type": "Thumbnail", "url": "https://ex.com/cp.png"}],
         "customAttributes": [],
         "tags": [],
         "categories": [{"path": "games/edition/base"}],
         "price": {
            "totalPrice": {
               "originalPrice": 5999,
               "discountPrice": 2999,
               "discount": 3000,
               "currencyCode": "USD",
               "currencyInfo": {"decimals": 2},
               "fmtPrice": {
                  "originalPrice": "$59.99",
                  "discountPrice": "$29.99",
                  "intermediatePrice": "$59.99",
               },
            },
         },
      }
      rec = adapter._normalize_element(elem)
      assert rec is not None
      assert rec.price == "$59.99"

   def test_empty_title_skipped(self):
      adapter = self._make_adapter()
      assert adapter._normalize_element({"title": "", "id": "x"}) is None

   def test_missing_title_skipped(self):
      adapter = self._make_adapter()
      assert adapter._normalize_element({}) is None


# ─── EpicAdapter._build_product_url ─────────────────────────────────────

class TestBuildProductUrl:
   def _make_adapter(self):
      return EpicAdapter(config=AdapterConfig(country="US", locale="en-US"))

   def test_resolved_slug_preferred(self):
      adapter = self._make_adapter()
      assert adapter._build_product_url({
         "_resolved_slug": "jack-move-8f3b25",
         "productSlug": "3dc025fd3ef6481d9fbba62d67f652ea",
         "title": "Jack Move",
      }) == "https://store.epicgames.com/en-us/p/jack-move-8f3b25"

   def test_resolved_slug_codename_rejected(self):
      adapter = self._make_adapter()
      result = adapter._build_product_url({
         "_resolved_slug": "anning",
         "title": "Jurassic World Evolution 3",
      })
      assert "/browse?q=" in result
      assert "Jurassic" in result

   def test_product_slug_matching_title(self):
      adapter = self._make_adapter()
      assert adapter._build_product_url({
         "productSlug": "jurassic-world-evolution",
         "title": "Jurassic World Evolution",
      }) == "https://store.epicgames.com/en-us/p/jurassic-world-evolution"

   def test_uuid_product_slug_falls_back_to_search(self):
      adapter = self._make_adapter()
      result = adapter._build_product_url(
         {"productSlug": "3dc025fd3ef6481d9fbba62d67f652ea", "title": "Jack Move"}
      )
      assert "/browse?q=" in result
      assert "Jack" in result

   def test_uuid_with_dashes_falls_back_to_search(self):
      adapter = self._make_adapter()
      result = adapter._build_product_url(
         {"urlSlug": "3dc025fd-3ef6-481d-9fbb-a62d67f652ea", "title": "Jack Move"}
      )
      assert "/browse?q=" in result

   def test_codename_generalaudience_detected(self):
      adapter = self._make_adapter()
      result = adapter._build_product_url(
         {"productSlug": "phosphorusgeneralaudience", "title": "Just Die Already"}
      )
      assert "/browse?q=" in result
      assert "Just" in result

   def test_codename_grouse_detected(self):
      adapter = self._make_adapter()
      result = adapter._build_product_url(
         {"productSlug": "grousegeneralaudience", "title": "Jotun: Valhalla Edition"}
      )
      assert "/browse?q=" in result

   def test_codename_with_common_suffix_detected(self):
      adapter = self._make_adapter()
      result = adapter._build_product_url(
         {"productSlug": "kakopo-reloaded", "title": "Just Cause 4 Reloaded"}
      )
      assert "/browse?q=" in result

   def test_real_slug_passes_validation(self):
      adapter = self._make_adapter()
      assert adapter._build_product_url({
         "urlSlug": "journey-to-the-savage-planet",
         "title": "Journey to the Savage Planet",
      }) == "https://store.epicgames.com/en-us/p/journey-to-the-savage-planet"

   def test_direct_url_full_https(self):
      adapter = self._make_adapter()
      assert adapter._build_product_url({"url": "https://store.epicgames.com/custom"}) == \
         "https://store.epicgames.com/custom"

   def test_url_field_codename_rejected(self):
      adapter = self._make_adapter()
      result = adapter._build_product_url({
         "url": "/p/anning",
         "title": "Jurassic World Evolution 3",
      })
      assert "/browse?q=" in result
      assert "Jurassic" in result

   def test_url_field_valid_slug_accepted(self):
      adapter = self._make_adapter()
      result = adapter._build_product_url({
         "url": "/p/jurassic-world-evolution",
         "title": "Jurassic World Evolution",
      })
      assert result == "https://store.epicgames.com/en-us/p/jurassic-world-evolution"

   def test_no_slug_with_name_returns_search(self):
      adapter = self._make_adapter()
      result = adapter._build_product_url({"title": "Some Game"})
      assert "/browse?q=" in result

   def test_no_slug_no_name_returns_base(self):
      adapter = self._make_adapter()
      assert adapter._build_product_url({}) == "https://store.epicgames.com/en-us"


# ─── EpicAdapter._slug_looks_valid ───────────────────────────────────────

class TestSlugLooksValid:
   def test_matching_slug(self):
      assert EpicAdapter._slug_looks_valid("jurassic-world-evolution", "Jurassic World Evolution")

   def test_codename_no_overlap(self):
      assert not EpicAdapter._slug_looks_valid("phosphorusgeneralaudience", "Just Die Already")

   def test_codename_with_stop_word_overlap_only(self):
      # "reloaded" is a stop word — shouldn't count
      assert not EpicAdapter._slug_looks_valid("kakopo-reloaded", "Just Cause 4 Reloaded")

   def test_single_word_title(self):
      assert EpicAdapter._slug_looks_valid("hades", "Hades")

   def test_slug_with_hash_suffix(self):
      assert EpicAdapter._slug_looks_valid("jack-move-8f3b25", "Jack Move")

   def test_partial_slug(self):
      # "just-cause-4" for "Just Cause 4 Reloaded" — good enough
      assert EpicAdapter._slug_looks_valid("just-cause-4", "Just Cause 4 Reloaded")

   def test_empty_name_trusts_slug(self):
      assert EpicAdapter._slug_looks_valid("anything", "")

   def test_empty_slug(self):
      assert not EpicAdapter._slug_looks_valid("", "Some Game")


# ─── EpicAdapter._normalize_element extras ───────────────────────────────

class TestNormalizeElementExtra:
   def _make_adapter(self):
      return EpicAdapter(config=AdapterConfig(country="US", locale="en-US"))

   def test_offerId_used_as_uuid(self):
      adapter = self._make_adapter()
      elem = {
         "title": "Test Game",
         "id": "elem-id-123",
         "offerId": "offer-id-456",
         "namespace": "sandbox-789",
         "keyImages": [],
         "customAttributes": [],
         "tags": [],
         "categories": [],
         "price": {"totalPrice": {"originalPrice": 0, "currencyCode": "USD",
                   "currencyInfo": {"decimals": 2}, "fmtPrice": {"originalPrice": "0"}}},
      }
      rec = adapter._normalize_element(elem)
      assert rec is not None
      assert rec.uuid == "offer-id-456"
      assert rec.extra.get("sandboxId") == "sandbox-789"
      assert rec.extra.get("offerId") == "offer-id-456"

   def test_falls_back_to_id_when_no_offerId(self):
      adapter = self._make_adapter()
      elem = {
         "title": "Test Game",
         "id": "elem-id-123",
         "namespace": "sandbox-789",
         "keyImages": [],
         "customAttributes": [],
         "tags": [],
         "categories": [],
         "price": {"totalPrice": {"originalPrice": 0, "currencyCode": "USD",
                   "currencyInfo": {"decimals": 2}, "fmtPrice": {"originalPrice": "0"}}},
      }
      rec = adapter._normalize_element(elem)
      assert rec is not None
      assert rec.uuid == "elem-id-123"


# ─── Persisted query hashes ──────────────────────────────────────────────

class TestPersistedHashes:
   def test_search_hash_length(self):
      assert len(SEARCH_STORE_HASH) == 64

   def test_catalog_offer_hash_length(self):
      assert len(CATALOG_OFFER_HASH) == 64

   def test_hashes_are_different(self):
      assert SEARCH_STORE_HASH != CATALOG_OFFER_HASH


# ─── EpicAdapter._extract_price ─────────────────────────────────────────

class TestExtractPrice:
   def _make_adapter(self):
      return EpicAdapter(config=AdapterConfig(country="US", locale="en-US"))

   def test_formatted_price(self):
      adapter = self._make_adapter()
      elem = {
         "price": {
            "totalPrice": {
               "originalPrice": 4999,
               "currencyCode": "USD",
               "currencyInfo": {"decimals": 2},
               "fmtPrice": {"originalPrice": "$49.99", "discountPrice": "$29.99"},
            },
         },
      }
      assert adapter._extract_price(elem) == "$49.99"

   def test_free_game(self):
      adapter = self._make_adapter()
      elem = {
         "price": {
            "totalPrice": {
               "originalPrice": 0,
               "currencyCode": "USD",
               "currencyInfo": {"decimals": 2},
               "fmtPrice": {"originalPrice": "0", "discountPrice": "0"},
            },
         },
      }
      assert adapter._extract_price(elem) == "Free"

   def test_no_price_info(self):
      adapter = self._make_adapter()
      assert adapter._extract_price({}) == "Unavailable"

   def test_numeric_fallback_eur(self):
      adapter = self._make_adapter()
      elem = {
         "price": {
            "totalPrice": {
               "originalPrice": 3999,
               "currencyCode": "EUR",
               "currencyInfo": {"decimals": 2},
               "fmtPrice": {},
            },
         },
      }
      assert adapter._extract_price(elem) == "\u20ac39.99"

   def test_jpy_no_decimals(self):
      adapter = self._make_adapter()
      elem = {
         "price": {
            "totalPrice": {
               "originalPrice": 6980,
               "currencyCode": "JPY",
               "currencyInfo": {"decimals": 0},
               "fmtPrice": {},
            },
         },
      }
      assert adapter._extract_price(elem) == "\u00a56980"


# ─── Headers ────────────────────────────────────────────────────────────

class TestHeaders:
   def test_graphql_headers_include_xhr(self):
      adapter = EpicAdapter(config=AdapterConfig(country="US", locale="en-US"))
      headers = adapter._graphql_headers()
      assert headers.get("x-requested-with") == "XMLHttpRequest"
      assert "Referer" in headers

   def test_graphql_headers_include_age_gate(self):
      adapter = EpicAdapter(config=AdapterConfig(country="US", locale="en-US"))
      headers = adapter._graphql_headers()
      assert "egs_age_gate_dob" in headers.get("Cookie", "")

   def test_rest_headers_have_origin(self):
      adapter = EpicAdapter(config=AdapterConfig(country="US", locale="en-US"))
      headers = adapter._rest_headers()
      assert headers.get("Origin") == "https://store.epicgames.com"
