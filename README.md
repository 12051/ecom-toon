
## Gzip Compression for TOON Files

To write a gzip-compressed TOON file:

```python
from ecom_toon.gzip_utils import write_gzip_toon
from ecom_toon.adapters.shopify_like import load_product_json  # or your loader

product = load_product_json('samples/product1.json')
write_gzip_toon(product, 'product1.toon.gz')
```

To read/decompress a TOON file:

```python
from ecom_toon.gzip_utils import read_gzip_toon

toon_str = read_gzip_toon('product1.toon.gz')
print(toon_str)
```

The output is losslessly compressed using gzip. You can also decompress `.toon.gz` files using standard tools like 7-Zip or the `gzip` command-line utility.
