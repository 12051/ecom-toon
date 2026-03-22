"""
UNIT TESTS — ecom-toon
Tests every individual function in toon_parser.py in isolation.
Run: pytest tests/test_unit.py -v
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ecom_toon.toon_parser import (
    obj_to_toon, parse_toon_to_json, _escape, _unescape,
    _is_uniform_object_array, _split_csv, count_tokens, to_toon
)
import pytest


# ═══════════════════════════════════════════════════════
# _escape tests
# ═══════════════════════════════════════════════════════

class TestEscape:
    def test_none(self):
        assert _escape(None) == "null"

    def test_bool_true(self):
        assert _escape(True) == "true"

    def test_bool_false(self):
        assert _escape(False) == "false"

    def test_int(self):
        assert _escape(42)  == "42"
        assert _escape(0)   == "0"
        assert _escape(-5)  == "-5"

    def test_float(self):
        assert _escape(0.55) == "0.55"
        assert _escape(5.4)  == "5.4"

    def test_url_https(self):
        result = _escape("https://cdn.shopify.com/image.jpg")
        assert result == "https~/cdn.shopify.com/image.jpg"
        assert "," not in result

    def test_url_http(self):
        result = _escape("http://example.com/img.png")
        assert result == "http~/example.com/img.png"
        assert "," not in result

    def test_url_with_query_string(self):
        url    = "https://cdn.shopify.com/image.jpg?v=1234&size=large"
        result = _escape(url)
        assert result.startswith("https~/")
        assert "," not in result

    def test_timestamp(self):
        assert _escape("2026-02-01T14:22:00Z") == "2026-02-01T14,22,00Z"

    def test_numeric_string_quoted(self):
        assert _escape("399.00") == '"399.00"'
        assert _escape("0.00")   == '"0.00"'

    def test_string_with_comma_quoted(self):
        result = _escape("Machine wash cold, tumble dry low")
        assert result.startswith('"') and result.endswith('"')

    def test_plain_string(self):
        assert _escape("Sony Electronics") == "Sony Electronics"

    def test_control_chars_replaced(self):
        assert _escape("line1\nline2") == "line1 line2"
        assert _escape("tab\there")   == "tab here"


# ═══════════════════════════════════════════════════════
# _unescape tests
# ═══════════════════════════════════════════════════════

class TestUnescape:
    def test_null(self):
        assert _unescape("null") is None

    def test_bool(self):
        assert _unescape("true")  is True
        assert _unescape("false") is False

    def test_int(self):
        assert _unescape("42") == 42
        assert _unescape("-5") == -5

    def test_float(self):
        assert _unescape("0.55") == 0.55

    def test_quoted_numeric_string(self):
        result = _unescape('"399.00"')
        assert result == "399.00"
        assert isinstance(result, str)

    def test_url_https(self):
        assert _unescape("https~/cdn.shopify.com/image.jpg") == \
               "https://cdn.shopify.com/image.jpg"

    def test_url_http(self):
        assert _unescape("http~/example.com/img.png") == \
               "http://example.com/img.png"

    def test_timestamp(self):
        assert _unescape("2026-02-01T14,22,00Z") == "2026-02-01T14:22:00Z"

    def test_quoted_string_with_comma(self):
        assert _unescape('"Machine wash cold, tumble dry low"') == \
               "Machine wash cold, tumble dry low"

    def test_plain_string(self):
        assert _unescape("Sony Electronics") == "Sony Electronics"


# ═══════════════════════════════════════════════════════
# _split_csv tests
# ═══════════════════════════════════════════════════════

class TestSplitCsv:
    def test_simple(self):
        assert _split_csv("a,b,c", 3) == ["a", "b", "c"]

    def test_quoted_field_with_comma(self):
        row    = '850703873,329678821,"Machine wash cold, tumble dry low",custom'
        result = _split_csv(row, 4)
        assert result[0] == "850703873"
        assert result[2] == '"Machine wash cold, tumble dry low"'
        assert result[3] == "custom"

    def test_url_no_comma(self):
        row    = "123,image,https~/cdn.shopify.com/img.jpg,Front View"
        result = _split_csv(row, 4)
        assert result[2] == "https~/cdn.shopify.com/img.jpg"
        assert result[3] == "Front View"

    def test_fewer_parts_padded(self):
        result = _split_csv("a,b", 4)
        assert len(result) == 4
        assert result[2] == ""
        assert result[3] == ""


# ═══════════════════════════════════════════════════════
# _is_uniform_object_array tests
# ═══════════════════════════════════════════════════════

class TestIsUniformObjectArray:
    def test_uniform(self):
        lst = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        assert _is_uniform_object_array(lst) is True

    def test_different_keys(self):
        lst = [{"id": 1, "name": "a"}, {"id": 2, "title": "b"}]
        assert _is_uniform_object_array(lst) is False

    def test_different_key_order(self):
        lst = [{"id": 1, "name": "a"}, {"name": "b", "id": 2}]
        assert _is_uniform_object_array(lst) is False

    def test_empty_list(self):
        assert _is_uniform_object_array([]) is False

    def test_not_dicts(self):
        assert _is_uniform_object_array([1, 2, 3]) is False

    def test_single_item(self):
        assert _is_uniform_object_array([{"id": 1}]) is True


# ═══════════════════════════════════════════════════════
# Writer + Parser tests
# ═══════════════════════════════════════════════════════

class TestWriter:
    def test_simple_scalar(self):
        assert "status,active" in obj_to_toon({"status": "active"})

    def test_bool_fields(self):
        toon = obj_to_toon({"taxable": True, "available": False})
        assert "taxable,true"    in toon
        assert "available,false" in toon

    def test_null_field(self):
        assert "discount,null" in obj_to_toon({"discount": None})

    def test_empty_array(self):
        assert "items[0]" in obj_to_toon({"items": []})

    def test_uniform_array_header(self):
        data = {"vars": [{"id": 1, "sku": "A"}, {"id": 2, "sku": "B"}]}
        assert "vars[2]{id,sku}" in obj_to_toon(data)

    def test_nested_dict(self):
        toon = obj_to_toon({"seo": {"title": "Buy Now"}})
        assert "seo," in toon
        assert "title,Buy Now" in toon

    def test_url_uses_tilde(self):
        toon = obj_to_toon({"src": "https://cdn.shopify.com/img.jpg"})
        assert "https~/" in toon
        assert "https://" not in toon

    def test_comma_string_quoted(self):
        toon = obj_to_toon({"care": "Machine wash cold, tumble dry low"})
        assert '"Machine wash cold, tumble dry low"' in toon


class TestParser:
    def test_simple_scalar(self):
        r = parse_toon_to_json("id,123\nstatus,active")
        assert r["id"] == 123
        assert r["status"] == "active"

    def test_bool_and_null(self):
        r = parse_toon_to_json("taxable,true\ndiscount,null")
        assert r["taxable"]  is True
        assert r["discount"] is None

    def test_url_restored(self):
        r = parse_toon_to_json("src,https~/cdn.shopify.com/img.jpg")
        assert r["src"] == "https://cdn.shopify.com/img.jpg"

    def test_timestamp_restored(self):
        r = parse_toon_to_json("created_at,2026-02-01T14,22,00Z")
        assert r["created_at"] == "2026-02-01T14:22:00Z"

    def test_quoted_numeric_string(self):
        r = parse_toon_to_json('price,"399.00"')
        assert r["price"] == "399.00"
        assert isinstance(r["price"], str)

    def test_quoted_string_with_comma(self):
        r = parse_toon_to_json('care,"Machine wash cold, tumble dry low"')
        assert r["care"] == "Machine wash cold, tumble dry low"

    def test_nested_dict(self):
        toon = "seo,\n  title,Buy Now\n  description,Great product"
        r    = parse_toon_to_json(toon)
        assert r["seo"]["title"]       == "Buy Now"
        assert r["seo"]["description"] == "Great product"

    def test_uniform_object_array(self):
        toon = 'vars[2]{id,sku,price},\n  1,ABC,"9.99"\n  2,DEF,"19.99"'
        r    = parse_toon_to_json(toon)
        assert len(r["vars"])          == 2
        assert r["vars"][0]["price"]   == "9.99"
        assert r["vars"][1]["sku"]     == "DEF"


# ═══════════════════════════════════════════════════════
# count_tokens tests
# ═══════════════════════════════════════════════════════

class TestCountTokens:
    def test_returns_int(self):
        assert isinstance(count_tokens("hello world"), int)

    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_toon_fewer_tokens_than_json(self):
        data = {
            "id": 123, "title": "Sony Headphones",
            "variants": [
                {"id": 1, "sku": "ABC-001", "price": "399.00"},
                {"id": 2, "sku": "ABC-002", "price": "429.00"},
            ]
        }
        j_tok = count_tokens(json.dumps(data, indent=2))
        t_tok = count_tokens(obj_to_toon(data))
        assert t_tok < j_tok