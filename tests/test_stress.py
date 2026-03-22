"""
STRESS TESTS — ecom-toon
Push the converter to its limits. Find breaking points.
These tests are EXPECTED to be slow — run with -s to see progress.
Run: pytest tests/test_stress.py -v -s
"""
import sys, os, json, time, gc, tracemalloc
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ecom_toon.toon_parser import obj_to_toon, parse_toon_to_json, count_tokens
import pytest


def make_product(i):
    v = ["Sony","Apple","Samsung","Bose","Jabra"][i % 5]
    return {
        "id": i, "title": f"{v} Product {i}", "vendor": v,
        "status": "active",
        "created_at": f"2026-01-{(i%28)+1:02d}T10:00:00Z",
        "description": f"Product {i} description with some extra text for realism.",
        "tags": ["wireless", "bluetooth", v.lower()],
        "variants": [
            {"id": i*10+j, "sku": f"SKU-{i:06d}-{j}", "price": f"{99+j*10}.00",
             "inventory_quantity": (i*3+j) % 200, "weight": 0.5+j*0.1,
             "weight_unit": "lb"}
            for j in range(3)
        ],
        "media": [
            {"id": i*100+k, "type": "image", "alt": f"View {k}",
             "url": f"https://cdn.shopify.com/images/{v.lower()}-{i}-{k}.jpg"}
            for k in range(2)
        ],
        "analytics": {"views": i*100, "purchases": i*5, "conversion_rate": 4.5},
    }


class TestStress:

    def test_10k_products_does_not_crash(self):
        """10,000 products must complete without error."""
        print("\n  Generating 10k products...", flush=True)
        products = [make_product(i) for i in range(10000)]
        print("  Converting...", flush=True)
        t0 = time.perf_counter()
        results = [obj_to_toon(p) for p in products]
        elapsed = time.perf_counter() - t0
        rate    = 10000 / elapsed * 60
        print(f"  ✅ 10k products: {elapsed:.1f}s ({rate:.0f}/min)")
        assert len(results) == 10000
        assert all(isinstance(r, str) and len(r) > 0 for r in results)

    def test_deeply_nested_structure(self):
        """Structure nested 10 levels deep must not crash."""
        def nest(depth):
            if depth == 0:
                return {"value": "leaf", "id": 999}
            return {"level": depth, "child": nest(depth - 1)}

        data = {"root": nest(10)}
        toon = obj_to_toon(data)
        rt   = parse_toon_to_json(toon)
        assert rt["root"]["level"] == 10

    def test_very_long_string_value(self):
        """A 10,000 character string must survive roundtrip."""
        long_str = "A" * 5000 + ", some text with comma " + "B" * 4000
        data     = {"description": long_str}
        toon     = obj_to_toon(data)
        rt       = parse_toon_to_json(toon)
        assert rt["description"] == long_str

    def test_large_variant_array(self):
        """Product with 100 variants must roundtrip correctly."""
        data = {
            "id": 1,
            "title": "Product with many variants",
            "variants": [
                {"id": i, "sku": f"SKU-{i:04d}",
                 "price": f"{9+i}.99",
                 "color": f"Color {i}",
                 "size":  ["XS","S","M","L","XL","XXL"][i%6],
                 "inventory_quantity": i * 3 % 200}
                for i in range(100)
            ]
        }
        toon = obj_to_toon(data)
        rt   = parse_toon_to_json(toon)
        assert len(rt["variants"]) == 100
        assert rt["variants"][50]["sku"] == "SKU-0050"

    def test_many_fields_per_product(self):
        """Product with 50 top-level fields must roundtrip correctly."""
        data = {f"field_{i}": f"value_{i}" for i in range(50)}
        data["id"]    = 999
        data["price"] = "399.00"
        toon = obj_to_toon(data)
        rt   = parse_toon_to_json(toon)
        assert rt["id"]    == 999
        assert rt["price"] == "399.00"
        for i in range(50):
            assert rt[f"field_{i}"] == f"value_{i}"

    def test_all_special_characters_in_values(self):
        """Values with special chars must survive."""
        data = {
            "with_comma":       "red, blue, green",
            "with_url":         "https://cdn.shopify.com/s/files/img.jpg?v=123",
            "with_timestamp":   "2026-02-01T14:22:00Z",
            "with_price":       "399.00",
            "with_html":        "<p>Hello <b>World</b></p>",
            "with_unicode":     "Auriculares inalámbricos",
            "with_quotes":      'He said "great", she agreed',
            "with_apostrophe":  "Best I've owned",
            "with_slash":       "path/to/resource",
            "with_ampersand":   "cotton & polyester",
        }
        toon = obj_to_toon(data)
        rt   = parse_toon_to_json(toon)
        for key, val in data.items():
            assert rt.get(key) == val, f"Field '{key}' failed: expected {val!r}, got {rt.get(key)!r}"

    def test_memory_under_stress_10k(self):
        """10k products must use < 500MB RAM (blueprint §15 equivalent)."""
        gc.collect()
        tracemalloc.start()
        products = [make_product(i) for i in range(10000)]
        _        = [obj_to_toon(p) for p in products]
        snap     = tracemalloc.take_snapshot()
        mem_mb   = sum(s.size for s in snap.statistics("lineno")) / 1024 / 1024
        tracemalloc.stop()
        print(f"\n  10k products memory: {mem_mb:.0f} MB")
        assert mem_mb < 500, f"Memory {mem_mb:.0f}MB exceeded 500MB limit"

    def test_empty_and_null_heavy_product(self):
        """Product with many null/empty fields must not crash."""
        data = {
            "id":           None,
            "title":        "",
            "description":  None,
            "tags":         [],
            "variants":     [],
            "media":        [],
            "price":        None,
            "vendor":       None,
        }
        toon = obj_to_toon(data)
        rt   = parse_toon_to_json(toon)
        assert rt is not None

    def test_unicode_heavy_catalog(self):
        """Catalog with heavy unicode must roundtrip correctly."""
        data = {
            "products": [
                {"id": i, "title": f"Auriculares {i} inalámbricos — réduction bruit",
                 "description": "Casque sans fil avec réduction de bruit активный.",
                 "tags": ["inalámbrico", "bluetooth", "über-quality"]}
                for i in range(20)
            ]
        }
        toon = obj_to_toon(data)
        rt   = parse_toon_to_json(toon)
        assert len(rt["products"]) == 20
        assert "inalámbricos" in rt["products"][0]["title"]