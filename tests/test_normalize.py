"""Tests for catalog.normalize — verify maps are actually applied."""
import pytest

from catalog.normalize import (
    clean_title,
    normalize_game_name,
    normalize_platform,
    normalize_platforms,
    normalize_rating,
    strip_edition_noise,
    price_to_string,
    letter_bucket,
    parse_price_string,
)


# ─── normalize_game_name (should clean trademarks & invisible chars) ──────

class TestNormalizeGameName:
    def test_strips_trademark(self):
        assert normalize_game_name("Halo™") == "Halo"

    def test_strips_registered(self):
        assert normalize_game_name("God of War®") == "God of War"

    def test_strips_copyright(self):
        assert normalize_game_name("©2024 Game") == "2024 Game"

    def test_invisible_space(self):
        assert normalize_game_name("The\u200bGame") == "The Game"

    def test_empty(self):
        assert normalize_game_name("") == ""

    def test_passthrough_normal(self):
        assert normalize_game_name("Dark Souls III") == "Dark Souls III"


# ─── normalize_platform ──────────────────────────────────────────────────

class TestNormalizePlatform:
    def test_ps4(self):
        assert normalize_platform("PS4") == "PS4"

    def test_playstation5(self):
        assert normalize_platform("PlayStation 5") == "PS5"

    def test_xbox_one(self):
        assert normalize_platform("Xbox One") == "Xbox One"

    def test_xbox_series(self):
        assert normalize_platform("Xbox Series X|S") == "Xbox Series X|S"

    def test_nintendo_switch(self):
        assert normalize_platform("Nintendo Switch") == "Switch"

    def test_windows(self):
        assert normalize_platform("Windows") == "Windows"

    def test_linux(self):
        assert normalize_platform("Linux") == "Linux"

    def test_mac(self):
        assert normalize_platform("Mac") == "Mac"

    def test_steam_maps_to_pc(self):
        assert normalize_platform("Steam") == "PC"

    def test_empty(self):
        assert normalize_platform("") == ""

    def test_unknown_passthrough(self):
        assert normalize_platform("Stadia") == "Stadia"


# ─── normalize_platforms ─────────────────────────────────────────────────

class TestNormalizePlatforms:
    def test_deduplicates(self):
        result = normalize_platforms(["PS4", "ps4", "PlayStation 4"])
        assert result == ["PS4"]

    def test_combo_expansion(self):
        result = normalize_platforms(["PS4/PS5"])
        assert "PS4" in result
        assert "PS5" in result

    def test_mixed(self):
        result = normalize_platforms(["PlayStation 5", "Xbox One", "Nintendo Switch"])
        assert result == ["PS5", "Xbox One", "Switch"]

    def test_empty_list(self):
        assert normalize_platforms([]) == []

    def test_none(self):
        assert normalize_platforms(None) == []

    def test_slash_combo_mapped(self):
        # "ps5ps4" maps to "PS4/PS5" which should expand
        result = normalize_platforms(["ps5ps4"])
        assert "PS4" in result
        assert "PS5" in result


# ─── normalize_rating ────────────────────────────────────────────────────

class TestNormalizeRating:
    def test_none(self):
        assert normalize_rating(None) is None

    def test_empty(self):
        assert normalize_rating("") is None

    def test_everyone(self):
        assert normalize_rating("Everyone") == "everyone"

    def test_esrb_everyone(self):
        assert normalize_rating("ESRB Everyone") == "everyone"

    def test_e10_plus(self):
        assert normalize_rating("E10+") == "everyone 10+"

    def test_teen(self):
        assert normalize_rating("Teen") == "teen"

    def test_mature(self):
        assert normalize_rating("Mature 17+") == "mature 17+"

    def test_pegi_3(self):
        assert normalize_rating("PEGI 3") == "everyone"

    def test_pegi_18(self):
        assert normalize_rating("PEGI 18") == "mature 17+"

    def test_cero_a(self):
        assert normalize_rating("CERO A") == "everyone"

    def test_already_canonical(self):
        assert normalize_rating("teen") == "teen"

    def test_unknown_passthrough(self):
        assert normalize_rating("USK 12") == "USK 12"


# ─── strip_edition_noise ────────────────────────────────────────────────

class TestStripEditionNoise:
    def test_deluxe(self):
        assert strip_edition_noise("Halo: Deluxe Edition") == "Halo"

    def test_goty(self):
        assert strip_edition_noise("Witcher 3: GOTY Edition") == "Witcher 3"

    def test_platform_noise(self):
        assert strip_edition_noise("FIFA 24 (PS5)") == "FIFA 24"

    def test_clean_passthrough(self):
        assert strip_edition_noise("Celeste") == "Celeste"


# ─── price_to_string ────────────────────────────────────────────────────

class TestPriceToString:
    def test_usd(self):
        assert price_to_string(59.99, "USD") == "$59.99"

    def test_eur(self):
        assert price_to_string(49.99, "EUR") == "€49.99"

    def test_jpy(self):
        assert price_to_string(6980.0, "JPY") == "¥6980"

    def test_none_amount(self):
        assert price_to_string(None, "USD") == "Unavailable"

    def test_flags_override(self):
        assert price_to_string(0, "USD", flags="Free") == "Free"

    def test_free(self):
        assert price_to_string(0.0, "USD") == "$0.00"


# ─── GameRecord with child store ─────────────────────────────────────────

class TestGameRecordStore:
    def test_child_store_ps4(self):
        from catalog.models import GameRecord
        rec = GameRecord(
            store="ps4",
            name="Test",
            price="$9.99",
            image="https://example.com/img.png",
            href="https://example.com/game",
        )
        assert rec.store == "ps4"

    def test_child_store_ps5(self):
        from catalog.models import GameRecord
        rec = GameRecord(
            store="ps5",
            name="Test",
            price="$9.99",
            image="https://example.com/img.png",
            href="https://example.com/game",
        )
        assert rec.store == "ps5"

    def test_parent_store_psn(self):
        from catalog.models import GameRecord
        rec = GameRecord(
            store="psn",
            name="Test",
            price="$9.99",
            image="https://example.com/img.png",
            href="https://example.com/game",
        )
        assert rec.store == "psn"
