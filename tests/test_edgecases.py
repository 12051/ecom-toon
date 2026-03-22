"""
EDGE CASE TESTS — ecom-toon
Tests unusual, malformed, or tricky real-world inputs.
Run: pytest tests/test_edge_cases.py -v
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ecom_toon.toon_parser import obj_to_toon, parse_toon_to_json
import pytest


class TestEdgeCases:

    # ── Empty / minimal inputs ─────────────────────────────────

    def test_empty_dict(self):
        toon = obj_to_toon({})
        assert isinstance(toon, str)

    def test_single_key(self):
        rt = parse_toon_to_json(obj_to_toon({"id": 1}))
        assert rt["id"] == 1

    def test_all_null_values(self):
        data = {"a": None, "b": None, "c": None}
        rt   = parse_toon_to_json(obj_to_toon(data))
        assert rt["a"] is None
        assert rt["b"] is None

    def test_empty_arrays(self):
        data = {"tags": [], "variants": [], "media": []}
        toon = obj_to_toon(data)
        rt   = parse_toon_to_json(toon)
        assert rt["tags"]     == []
        assert rt["variants"] == []

    # ── Comma in various positions ─────────────────────────────

    def test_comma_at_start_of_value(self):
        data = {"note": ", starts with comma"}
        rt   = parse_toon_to_json(obj_to_toon(data))
        assert rt["note"] == ", starts with comma"

    def test_comma_at_end_of_value(self):
        data = {"note": "ends with comma,"}
        rt   = parse_toon_to_json(obj_to_toon(data))
        assert rt["note"] == "ends with comma,"

    def test_multiple_commas_in_value(self):
        data = {"sizes": "XS, S, M, L, XL, XXL"}
        rt   = parse_toon_to_json(obj_to_toon(data))
        assert rt["sizes"] == "XS, S, M, L, XL, XXL"

    def test_comma_in_object_array_middle_field(self):
        # The original reported bug
        data = {"metafields": [
            {"key": "care", "value": "Machine wash cold, tumble dry low", "ns": "custom"},
        ]}
        rt = parse_toon_to_json(obj_to_toon(data))
        assert rt["metafields"][0]["value"]  == "Machine wash cold, tumble dry low"
        assert rt["metafields"][0]["ns"]     == "custom"

    def test_comma_in_first_field_of_array(self):
        data = {"items": [
            {"desc": "Red, Blue, Green", "id": 1, "price": "9.99"},
            {"desc": "Standard edition",  "id": 2, "price": "19.99"},
        ]}
        rt = parse_toon_to_json(obj_to_toon(data))
        assert rt["items"][0]["desc"] == "Red, Blue, Green"
        assert rt["items"][1]["desc"] == "Standard edition"

    # ── URLs ──────────────────────────────────────────────────

    def test_url_in_object_array(self):
        data = {"images": [
            {"id": 1, "src": "https://cdn.shopify.com/s/files/1/0040/product.jpg?v=123", "alt": "Front"},
            {"id": 2, "src": "https://cdn.shopify.com/s/files/1/0040/product2.jpg",      "alt": "Back"},
        ]}
        rt = parse_toon_to_json(obj_to_toon(data))
        assert rt["images"][0]["src"] == "https://cdn.shopify.com/s/files/1/0040/product.jpg?v=123"
        assert rt["images"][1]["alt"] == "Back"

    def test_http_url(self):
        data = {"url": "http://example.com/product"}
        rt   = parse_toon_to_json(obj_to_toon(data))
        assert rt["url"] == "http://example.com/product"

    def test_url_followed_by_string_field(self):
        # URL must not bleed into the next field
        data = {"images": [
            {"id": 1, "type": "image",
             "url": "https://cdn.shopify.com/images/product.jpg",
             "alt": "Premium Waterproof Rain Coat - Front View Black"}
        ]}
        rt = parse_toon_to_json(obj_to_toon(data))
        assert rt["images"][0]["url"] == "https://cdn.shopify.com/images/product.jpg"
        assert rt["images"][0]["alt"] == "Premium Waterproof Rain Coat - Front View Black"

    # ── Type preservation ─────────────────────────────────────

    def test_price_stays_string_not_float(self):
        for price in ["399.00", "0.00", "1499.99", "9.99"]:
            data   = {"price": price}
            result = parse_toon_to_json(obj_to_toon(data))
            assert isinstance(result["price"], str), f"{price} became {type(result['price'])}"
            assert result["price"] == price

    def test_integer_stays_integer(self):
        data = {"id": 987654321, "qty": 0, "neg": -5}
        rt   = parse_toon_to_json(obj_to_toon(data))
        assert isinstance(rt["id"],  int) and rt["id"]  == 987654321
        assert isinstance(rt["qty"], int) and rt["qty"] == 0
        assert isinstance(rt["neg"], int) and rt["neg"] == -5

    def test_float_stays_float(self):
        data = {"weight": 0.55, "rate": 5.4}
        rt   = parse_toon_to_json(obj_to_toon(data))
        assert isinstance(rt["weight"], float) and rt["weight"] == 0.55
        assert isinstance(rt["rate"],   float) and rt["rate"]   == 5.4

    def test_bool_stays_bool(self):
        data = {"taxable": True, "available": False}
        rt   = parse_toon_to_json(obj_to_toon(data))
        assert rt["taxable"]   is True
        assert rt["available"] is False

    # ── Unicode ───────────────────────────────────────────────

    def test_spanish_unicode(self):
        data = {"desc": "Auriculares inalámbricos con cancelación de ruido."}
        rt   = parse_toon_to_json(obj_to_toon(data))
        assert rt["desc"] == data["desc"]

    def test_french_unicode(self):
        data = {"desc": "Casque sans fil avec réduction de bruit."}
        rt   = parse_toon_to_json(obj_to_toon(data))
        assert rt["desc"] == data["desc"]

    def test_emoji_in_value(self):
        data = {"title": "Best headphones 🎧 ever made ✅"}
        rt   = parse_toon_to_json(obj_to_toon(data))
        assert rt["title"] == data["title"]

    # ── Special characters ────────────────────────────────────

    def test_html_tags(self):
        data = {"body": "<p>Hello <b>World</b></p><br/><a href='x'>link</a>"}
        rt   = parse_toon_to_json(obj_to_toon(data))
        assert rt["body"] == data["body"]

    def test_apostrophe(self):
        data = {"review": "Best I've ever owned. Wouldn't trade it."}
        rt   = parse_toon_to_json(obj_to_toon(data))
        assert rt["review"] == data["review"]

    def test_slash_in_value(self):
        data = {"variant": "Black / Standard", "path": "s/files/1/0040/product"}
        rt   = parse_toon_to_json(obj_to_toon(data))
        assert rt["variant"] == "Black / Standard"
        assert rt["path"]    == "s/files/1/0040/product"

    def test_percent_in_value(self):
        data = {"discount": "10% launch discount"}
        rt   = parse_toon_to_json(obj_to_toon(data))
        assert rt["discount"] == "10% launch discount"

    def test_question_mark_in_url_field(self):
        data = {"url": "https://example.com/path?v=123&size=large"}
        rt   = parse_toon_to_json(obj_to_toon(data))
        assert rt["url"] == "https://example.com/path?v=123&size=large"

    # ── Timestamps ────────────────────────────────────────────

    def test_various_timestamps(self):
        timestamps = [
            "2026-02-01T14:22:00Z",
            "2026-02-20T09:15:00Z",
            "2026-01-01T00:00:00Z",
            "2026-12-31T23:59:59Z",
        ]
        for ts in timestamps:
            data = {"ts": ts}
            rt   = parse_toon_to_json(obj_to_toon(data))
            assert rt["ts"] == ts, f"Timestamp failed: {ts}"

    # ── Non-standard catalog shapes ───────────────────────────

    def test_flat_product_no_nested(self):
        data = {"id": 1, "title": "T-Shirt", "price": "29.00",
                "vendor": "ACME", "status": "active"}
        rt   = parse_toon_to_json(obj_to_toon(data))
        assert rt["title"]  == "T-Shirt"
        assert rt["price"]  == "29.00"
        assert rt["status"] == "active"

    def test_product_with_only_scalars(self):
        data = {"id": 1, "score": 4.5, "active": True, "note": None}
        rt   = parse_toon_to_json(obj_to_toon(data))
        assert rt == data

    def test_large_number_of_tags(self):
        tags = [f"tag-{i}" for i in range(50)]
        data = {"tags": tags}
        rt   = parse_toon_to_json(obj_to_toon(data))
        assert rt["tags"] == tags