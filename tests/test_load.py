"""
LOAD TESTS — ecom-toon
Tests performance, memory, and throughput under heavy workloads.
Blueprint targets (§22): ≥5,000 products/min, 250MB without OOM.
Run: pytest tests/test_load.py -v -s
"""
import sys, os, json, time, gc, tracemalloc, random, string
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ecom_toon.toon_parser import obj_to_toon, parse_toon_to_json, count_tokens
from concurrent.futures import ThreadPoolExecutor
import pytest


# ── Fixture generator ─────────────────────────────────────────────────────────

def make_product(i: int) -> dict:
    """Generate a realistic eCommerce product dict."""
    vendors = ["Sony","Apple","Samsung","Bose","Jabra","JBL","Anker","Beats"]
    types   = ["Headphones","Earbuds","Headset","Speaker"]
    vendor  = vendors[i % len(vendors)]
    ptype   = types[i % len(types)]
    return {
        "id":           100000000 + i,
        "title":        f"{vendor} Product {i} Wireless {ptype}",
        "handle":       f"{vendor.lower()}-product-{i}",
        "vendor":       vendor,
        "product_type": ptype,
        "status":       "active" if i % 3 != 0 else "draft",
        "created_at":   f"2026-0{(i%9)+1}-{(i%28)+1:02d}T10:00:00Z",
        "updated_at":   f"2026-0{(i%9)+1}-{(i%28)+1:02d}T12:00:00Z",
        "description":  f"High quality {ptype} from {vendor}. Product number {i}.",
        "tags":         ["wireless", "bluetooth", vendor.lower(), ptype.lower()],
        "pricing": {
            "price_min":        f"{99 + (i % 400)}.00",
            "price_max":        f"{199 + (i % 400)}.00",
            "compare_at_price": f"{299 + (i % 400)}.00",
            "currency": "USD", "taxable": True,
        },
        "variants": [
            {"id": 100000000 + i*10 + j,
             "title": f"Color {j}",
             "sku":   f"{vendor[:3].upper()}-{i:06d}-{j:02d}",
             "price": f"{99 + (i % 400) + j*10}.00",
             "inventory_quantity": (i * 3 + j * 7) % 200,
             "weight": 0.5 + j * 0.05,
             "weight_unit": "lb"}
            for j in range(3)
        ],
        "inventory_locations": [
            {"location_id": "WH-A", "name": "Warehouse A",
             "country": "USA", "quantity": (i * 5) % 100},
            {"location_id": "WH-B", "name": "Warehouse B",
             "country": "USA", "quantity": (i * 3) % 80},
        ],
        "media": [
            {"id": 200000000 + i*10 + k,
             "type": "image",
             "alt":  f"View {k}",
             "url":  f"https://cdn.shopify.com/images/{vendor.lower()}-{i}-{k}.jpg"}
            for k in range(2)
        ],
        "seo": {
            "title":       f"{vendor} {ptype} - Buy Online",
            "description": f"Shop {vendor} {ptype} with free shipping.",
            "keywords":    ["wireless", vendor.lower(), ptype.lower()],
        },
        "reviews": [
            {"review_id":     300000000 + i*10 + r,
             "customer_name": f"Customer {i*10+r}",
             "rating":        (r % 3) + 3,
             "title":         f"Review {r} for product {i}",
             "comment":       f"Great product. Highly recommend. Rating: {(r%3)+3}/5",
             "date":          f"2026-0{(r%9)+1}-{(r%28)+1:02d}"}
            for r in range(2)
        ],
        "analytics": {
            "views_last_30_days":     (i * 137) % 50000,
            "purchases_last_30_days": (i * 53)  % 2000,
            "conversion_rate":        round(((i * 7) % 100) / 10, 1),
            "wishlist_count":         (i * 29)  % 5000,
        },
        "compliance": {
            "certifications":  ["FCC", "CE", "RoHS"],
            "battery_safety":  "UN38.3 certified",
            "recycling_program": True,
        }
    }


# ═══════════════════════════════════════════════════════
# Throughput tests
# ═══════════════════════════════════════════════════════

class TestThroughput:
    """Blueprint §22 target: ≥5,000 products/min."""

    TARGET_PRODUCTS_PER_MIN = 5000

    def test_100_products_throughput(self):
        products = [make_product(i) for i in range(100)]
        t0       = time.perf_counter()
        _        = [obj_to_toon(p) for p in products]
        elapsed  = time.perf_counter() - t0
        rate     = len(products) / elapsed * 60
        print(f"\n  100 products: {elapsed*1000:.1f}ms  ({rate:.0f} products/min)")
        assert rate >= self.TARGET_PRODUCTS_PER_MIN, \
            f"Throughput {rate:.0f}/min below target {self.TARGET_PRODUCTS_PER_MIN}/min"

    def test_1000_products_throughput(self):
        products = [make_product(i) for i in range(1000)]
        t0       = time.perf_counter()
        _        = [obj_to_toon(p) for p in products]
        elapsed  = time.perf_counter() - t0
        rate     = len(products) / elapsed * 60
        print(f"\n  1000 products: {elapsed*1000:.1f}ms  ({rate:.0f} products/min)")
        assert rate >= self.TARGET_PRODUCTS_PER_MIN, \
            f"Throughput {rate:.0f}/min below target {self.TARGET_PRODUCTS_PER_MIN}/min"

    def test_parallel_vs_single_thread(self):
        products   = [make_product(i) for i in range(500)]

        t0         = time.perf_counter()
        single_out = [obj_to_toon(p) for p in products]
        t_single   = time.perf_counter() - t0

        t0         = time.perf_counter()
        with ThreadPoolExecutor(max_workers=4) as ex:
            parallel_out = list(ex.map(obj_to_toon, products))
        t_parallel = time.perf_counter() - t0

        # Both must produce the same number of outputs
        assert len(single_out) == len(parallel_out) == 500
        print(f"\n  Single:   {t_single*1000:.1f}ms")
        print(f"  Parallel: {t_parallel*1000:.1f}ms")
        print(f"  Note: parallel may be slower for small CPU-bound tasks")


# ═══════════════════════════════════════════════════════
# Memory tests
# ═══════════════════════════════════════════════════════

class TestMemory:
    """Blueprint §15: 250MB catalog without OOM."""

    def test_memory_stays_reasonable_100_products(self):
        gc.collect()
        tracemalloc.start()
        products  = [make_product(i) for i in range(100)]
        _         = [obj_to_toon(p) for p in products]
        snap      = tracemalloc.take_snapshot()
        mem_bytes = sum(s.size for s in snap.statistics("lineno"))
        tracemalloc.stop()
        mem_mb    = mem_bytes / 1024 / 1024
        print(f"\n  100 products memory: {mem_mb:.1f} MB")
        assert mem_mb < 100, f"Memory {mem_mb:.1f}MB exceeded 100MB limit"

    def test_memory_linear_scaling(self):
        """Memory should scale linearly — not exponentially."""
        gc.collect()
        sizes = [100, 500]
        mems  = []
        for n in sizes:
            tracemalloc.start()
            products = [make_product(i) for i in range(n)]
            _        = [obj_to_toon(p) for p in products]
            snap     = tracemalloc.take_snapshot()
            mem      = sum(s.size for s in snap.statistics("lineno")) / 1024 / 1024
            tracemalloc.stop()
            mems.append(mem)
            gc.collect()

        ratio    = mems[1] / mems[0] if mems[0] > 0 else 0
        scale    = sizes[1] / sizes[0]
        print(f"\n  {sizes[0]} products: {mems[0]:.1f}MB")
        print(f"  {sizes[1]} products: {mems[1]:.1f}MB")
        print(f"  Scale factor: {ratio:.1f}x for {scale}x more data")
        # Should scale roughly linearly (within 3x of linear is fine)
        assert ratio < scale * 3, \
            f"Memory scaled {ratio:.1f}x for {scale}x data — possible memory leak"

    def test_no_memory_leak_repeated_calls(self):
        """Converting same product 1000 times should not grow memory."""
        product = make_product(1)
        gc.collect()
        tracemalloc.start()

        for _ in range(1000):
            toon = obj_to_toon(product)

        snap  = tracemalloc.take_snapshot()
        mem   = sum(s.size for s in snap.statistics("lineno")) / 1024 / 1024
        tracemalloc.stop()
        print(f"\n  1000 repeated conversions: {mem:.1f} MB")
        assert mem < 50, f"Possible memory leak: {mem:.1f}MB after 1000 calls"


# ═══════════════════════════════════════════════════════
# Correctness under load
# ═══════════════════════════════════════════════════════

class TestCorrectnessUnderLoad:
    """Conversion must be correct even when processing thousands of products."""

    def test_roundtrip_100_products(self):
        failures = []
        for i in range(100):
            p    = make_product(i)
            toon = obj_to_toon(p)
            rt   = parse_toon_to_json(toon)
            orig = json.dumps(p,  sort_keys=True)
            got  = json.dumps(rt, sort_keys=True)
            if orig != got:
                failures.append(i)
        assert not failures, \
            f"Roundtrip failed for product indices: {failures[:5]}"

    def test_token_savings_consistent_across_products(self):
        """Token savings should be consistently above 20% for all products."""
        low_savings = []
        for i in range(50):
            p       = make_product(i)
            j_tok   = count_tokens(json.dumps(p, indent=2))
            t_tok   = count_tokens(obj_to_toon(p))
            savings = (j_tok - t_tok) / j_tok * 100
            if savings < 20:
                low_savings.append((i, savings))
        assert not low_savings, \
            f"Low savings products: {low_savings[:3]}"

    def test_parallel_output_matches_single_thread(self):
        """Parallel results must be identical to single-thread results."""
        products = [make_product(i) for i in range(200)]
        single   = [obj_to_toon(p) for p in products]
        with ThreadPoolExecutor(max_workers=4) as ex:
            parallel = list(ex.map(obj_to_toon, products))
        assert single == parallel, "Parallel output differs from single-thread"


# ═══════════════════════════════════════════════════════
# Catalog-level tests (whole file at once)
# ═══════════════════════════════════════════════════════

class TestCatalogLevel:
    def test_catalog_500_products(self):
        catalog   = {"store": {"id": "shop_001"}, "products": [make_product(i) for i in range(500)]}
        t0        = time.perf_counter()
        toon      = obj_to_toon(catalog)
        elapsed   = time.perf_counter() - t0
        j_tok     = count_tokens(json.dumps(catalog, indent=2))
        t_tok     = count_tokens(toon)
        savings   = (j_tok - t_tok) / j_tok * 100
        rate      = 500 / elapsed * 60
        print(f"\n  500-product catalog:")
        print(f"    Time    : {elapsed*1000:.0f}ms ({rate:.0f} products/min)")
        print(f"    Savings : {savings:.1f}%")
        assert savings > 20
        assert rate >= 5000

    def test_catalog_1000_products(self):
        catalog = {"store": {"id": "shop_001"}, "products": [make_product(i) for i in range(1000)]}
        t0      = time.perf_counter()
        toon    = obj_to_toon(catalog)
        elapsed = time.perf_counter() - t0
        rate    = 1000 / elapsed * 60
        print(f"\n  1000-product catalog: {elapsed*1000:.0f}ms ({rate:.0f} products/min)")
        assert rate >= 5000, f"Rate {rate:.0f}/min below 5000/min target"