from typing import Any, Dict, List

from ecom_toon.schemas import ProductCIM, VariantCIM, MediaCIM


def to_cim_product(raw: Dict[str, Any]) -> ProductCIM:
    """Convert a Shopify-like product JSON into ProductCIM."""

    # Basic fields
    product_id = str(raw.get("id"))
    title = raw.get("title", "").strip()

    description = raw.get("body_html") or raw.get("description") or None
    slug = raw.get("handle") or None
    brand = raw.get("vendor") or raw.get("brand") or None

    raw_tags = raw.get("tags") or []
    if isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    else:
        tags = [str(t).strip() for t in raw_tags]

    # Variants
    variants: List[VariantCIM] = []
    for v in raw.get("variants", []):
        variants.append(
            VariantCIM(
                id=str(v.get("id")),
                sku=v.get("sku"),
                price=float(v["price"]) if "price" in v and v["price"] not in (None, "") else None,
                currency=v.get("currency"),
                inventory_quantity=v.get("inventory_quantity"),
            )
        )

    # Media (images only for now)
    media: List[MediaCIM] = []
    for img in raw.get("images", []):
        url = img.get("src")
        if not url:
            continue
        media.append(
            MediaCIM(
                url=url,
                alt=img.get("alt"),
            )
        )

    # attrs: extra fields you don't model yet
    attrs: Dict[str, Any] = {}
    metafields = raw.get("metafields") or []
    for mf in metafields:
        namespace = mf.get("namespace") or "default"
        key = mf.get("key") or "unknown"
        value = mf.get("value")
        attrs[f"{namespace}.{key}"] = value

    return ProductCIM(
        id=product_id,
        title=title,
        description=description,
        slug=slug,
        brand=brand,
        tags=tags,
        variants=variants,
        media=media,
        attrs=attrs,
    )
