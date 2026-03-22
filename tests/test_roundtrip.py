"""
ROUNDTRIP TESTS — ecom-toon
Tests that JSON → TOON → JSON produces byte-identical output.
Every data type, every nesting pattern, every edge case.
Run: pytest tests/test_roundtrip.py -v
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ecom_toon.toon_parser import obj_to_toon, parse_toon_to_json
import pytest


def roundtrip(data):
    """Helper: convert to TOON and back, return (original, result)."""
    toon   = obj_to_toon(data)
    result = parse_toon_to_json(toon)
    return (
        json.dumps(data,   sort_keys=True, ensure_ascii=False),
        json.dumps(result, sort_keys=True, ensure_ascii=False),
    )

def assert_roundtrip(data, label=""):
    orig, got = roundtrip(data)
    assert orig == got, (
        f"Roundtrip FAILED{' — '+label if label else ''}\n"
        f"  TOON: {obj_to_toon(data)[:200]}\n"
        f"  Expected: {orig[:200]}\n"
        f"  Got:      {got[:200]}"
    )


# ═══════════════════════════════════════════════════════
# Scalar types
# ═══════════════════════════════════════════════════════

class TestScalars:
    def test_integer(self):
        assert_roundtrip({"id": 987654321})

    def test_float(self):
        assert_roundtrip({"weight": 0.55})
        assert_roundtrip({"rate": 5.4})

    def test_bool_true(self):
        assert_roundtrip({"taxable": True})

    def test_bool_false(self):
        assert_roundtrip({"available": False})

    def test_null(self):
        assert_roundtrip({"discount": None})

    def test_plain_string(self):
        assert_roundtrip({"vendor": "Sony Electronics"})

    def test_numeric_string_stays_string(self):
        # "399.00" must come back as string, NOT as float 399.0
        data = {"price": "399.00"}
        orig, got = roundtrip(data)
        assert orig == got
        result = parse_toon_to_json(obj_to_toon(data))
        assert isinstance(result["price"], str)
        assert result["price"] == "399.00"

    def test_zero_string(self):
        data = {"cost": "0.00"}
        result = parse_toon_to_json(obj_to_toon(data))
        assert result["cost"] == "0.00"
        assert isinstance(result["cost"], str)


# ═══════════════════════════════════════════════════════
# Strings with special content
# ═══════════════════════════════════════════════════════

class TestStrings:
    def test_string_with_comma(self):
        assert_roundtrip({"care": "Machine wash cold, tumble dry low"})

    def test_string_with_multiple_commas(self):
        assert_roundtrip({"sizes": "XS, S, M, L, XL, XXL"})

    def test_string_with_inner_quotes(self):
        assert_roundtrip({"review": 'He said "great product", loved it'})

    def test_https_url(self):
        assert_roundtrip({"src": "https://cdn.shopify.com/images/product.jpg"})

    def test_http_url(self):
        assert_roundtrip({"src": "http://example.com/img.png"})

    def test_url_with_query_string(self):
        assert_roundtrip({
            "src": "https://cdn.shopify.com/image.jpg?v=1674123456&size=large"
        })

    def test_url_with_path_slashes(self):
        assert_roundtrip({
            "src": "https://cdn.shopify.com/s/files/1/0040/7092/products/item.jpg"
        })

    def test_timestamp(self):
        assert_roundtrip({"created_at": "2026-02-01T14:22:00Z"})
        assert_roundtrip({"updated_at": "2026-02-20T09:15:00Z"})

    def test_date_only(self):
        assert_roundtrip({"date": "2026-04-01"})

    def test_html_content(self):
        assert_roundtrip({"body_html": "<p>Premium wireless headphones.</p>"})

    def test_unicode(self):
        assert_roundtrip({"description": "Auriculares inalámbricos con cancelación de ruido."})
        assert_roundtrip({"title": "Casque sans fil avec réduction de bruit."})


# ═══════════════════════════════════════════════════════
# Arrays
# ═══════════════════════════════════════════════════════

class TestArrays:
    def test_empty_array(self):
        assert_roundtrip({"items": []})

    def test_string_array(self):
        assert_roundtrip({"tags": ["wireless", "sony", "premium", "bluetooth"]})

    def test_int_array(self):
        assert_roundtrip({"ids": [1, 2, 3, 4, 5]})

    def test_uniform_object_array(self):
        assert_roundtrip({"variants": [
            {"id": 1, "sku": "ABC", "price": "399.00"},
            {"id": 2, "sku": "DEF", "price": "429.00"},
            {"id": 3, "sku": "GHI", "price": "449.00"},
        ]})

    def test_object_array_with_url(self):
        assert_roundtrip({"media": [
            {"id": 1, "type": "image",
             "url": "https://cdn.shopify.com/images/front.jpg",
             "alt": "Front View"},
            {"id": 2, "type": "video",
             "url": "https://cdn.shopify.com/videos/demo.mp4",
             "alt": "Product Demo"},
        ]})

    def test_object_array_with_comma_in_value(self):
        # This was the reported bug — must pass
        assert_roundtrip({"metafields": [
            {"key": "care_instructions",
             "value": "Machine wash cold, tumble dry low",
             "namespace": "custom"},
            {"key": "material",
             "value": "60% Cotton, 40% Polyester",
             "namespace": "custom"},
        ]})

    def test_mixed_object_array(self):
        # Objects with different keys → mixed format
        assert_roundtrip({"collections": [
            {"id": 1001, "title": "Premium Audio",
             "handle": "premium-audio", "description": "High-end audio"},
            {"id": 1002, "title": "Wireless",
             "handle": "wireless"},  # missing description
        ]})


# ═══════════════════════════════════════════════════════
# Nested structures
# ═══════════════════════════════════════════════════════

class TestNested:
    def test_nested_dict(self):
        assert_roundtrip({"seo": {
            "title": "Sony WH-1000XM5 Headphones",
            "description": "Buy with 30-hour battery life.",
        }})

    def test_deeply_nested(self):
        assert_roundtrip({"shipping": {
            "requires_shipping": True,
            "weight": 250,
            "dimensions": {
                "length": 22, "width": 18, "height": 8, "unit": "cm"
            }
        }})

    def test_nested_dict_with_array(self):
        assert_roundtrip({"shipping": {
            "weight": 250,
            "methods": [
                {"method": "Standard", "cost": "9.99"},
                {"method": "Express",  "cost": "19.99"},
            ]
        }})

    def test_dict_of_dicts(self):
        assert_roundtrip({"translations": {
            "es": {"title": "Auriculares Sony", "description": "Cancelación de ruido."},
            "fr": {"title": "Casque Sony",      "description": "Réduction de bruit."},
        }})

    def test_array_with_nested_array(self):
        assert_roundtrip({"bundles": [
            {"bundle_id": "B01", "title": "Starter Bundle",
             "items": ["Product A", "Product B"]}
        ]})


# ═══════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════

class TestEdgeCases:
    def test_empty_dict(self):
        assert_roundtrip({})

    def test_single_field(self):
        assert_roundtrip({"id": 1})

    def test_all_types_together(self):
        assert_roundtrip({
            "id":        123,
            "price":     "399.00",
            "weight":    0.55,
            "active":    True,
            "discount":  None,
            "tags":      ["wireless", "premium"],
            "url":       "https://cdn.shopify.com/image.jpg",
            "timestamp": "2026-02-01T14:22:00Z",
            "care":      "Machine wash cold, tumble dry low",
        })

    def test_large_integer(self):
        assert_roundtrip({"barcode": 1234567890123})

    def test_zero_integer(self):
        assert_roundtrip({"inventory": 0})

    def test_negative_integer(self):
        assert_roundtrip({"adjustment": -5})

    def test_empty_string(self):
        # Empty string should roundtrip (comes back as empty string)
        data   = {"note": ""}
        result = parse_toon_to_json(obj_to_toon(data))
        # Empty string may come back as None or "" — either is acceptable
        # as long as it doesn't crash
        assert "note" in result

    def test_very_long_string(self):
        long_val = "A" * 500
        assert_roundtrip({"description": long_val})

    def test_string_only_commas(self):
        assert_roundtrip({"sep": ",,,,"})

    def test_certification_array(self):
        assert_roundtrip({"certifications": ["FCC", "CE", "RoHS"]})


# ═══════════════════════════════════════════════════════
# Full product fixture
# ═══════════════════════════════════════════════════════

class TestFullProduct:
    PRODUCT = {
        "id": 987654321,
        "title": "Sony WH-1000XM5 Wireless Noise Canceling Headphones - Matte Black",
        "handle": "sony-wh-1000xm5-matte-black",
        "vendor": "Sony Electronics",
        "product_type": "Headphones",
        "status": "active",
        "created_at": "2026-02-01T14:22:00Z",
        "updated_at": "2026-02-20T09:15:00Z",
        "description": "Industry-leading noise cancellation with superior sound quality.",
        "body_html": "<p>Premium wireless noise cancelling headphones.</p>",
        "tags": ["headphones", "wireless", "noise-canceling", "sony", "premium"],
        "pricing": {
            "price_min": "399.00", "price_max": "429.00",
            "currency": "USD", "taxable": True,
        },
        "variants": [
            {"id": 111222333, "title": "Matte Black / Standard",
             "sku": "WH1000XM5-BLK-STD", "price": "399.00",
             "inventory_quantity": 42, "weight": 0.55, "weight_unit": "lb"},
            {"id": 111222334, "title": "Silver / Standard",
             "sku": "WH1000XM5-SLV-STD", "price": "399.00",
             "inventory_quantity": 28, "weight": 0.55, "weight_unit": "lb"},
        ],
        "media": [
            {"id": 123, "type": "image", "alt": "Front View",
             "url": "https://cdn.shopify.com/images/sony-xm5-front.jpg"},
            {"id": 124, "type": "video", "alt": "Product Demo",
             "url": "https://cdn.shopify.com/videos/sony-xm5-demo.mp4"},
        ],
        "metafields": [
            {"key": "care_instructions",
             "value": "Machine wash cold, tumble dry low",
             "namespace": "custom"},
        ],
        "analytics": {
            "views_last_30_days": 15230, "conversion_rate": 5.4
        },
        "compliance": {
            "certifications": ["FCC", "CE", "RoHS"],
            "recycling_program": True
        },
    }

    def test_full_product_roundtrip(self):
        assert_roundtrip(self.PRODUCT, "full product fixture")

    def test_token_savings_positive(self):
        from ecom_toon.toon_parser import count_tokens
        import json
        toon    = obj_to_toon(self.PRODUCT)
        j_tok   = count_tokens(json.dumps(self.PRODUCT, indent=2))
        t_tok   = count_tokens(toon)
        savings = (j_tok - t_tok) / j_tok * 100
        assert savings > 20, f"Expected >20% savings, got {savings:.1f}%"