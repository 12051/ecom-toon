from typing import List

from ecom_toon.schemas import ProductCIM, VariantCIM, MediaCIM


def product_to_toon_text(product: ProductCIM) -> str:
    """Very simple, placeholder TOON-like text.

    Later this will be replaced by a real TOON encoder.
    """
    lines: List[str] = []

    lines.append(f"product:{product.id}")
    lines.append(f"  title: {product.title}")
    if product.slug:
        lines.append(f"  slug: {product.slug}")
    if product.brand:
        lines.append(f"  brand: {product.brand}")
    if product.description:
        lines.append(f"  description: {product.description}")

    if product.tags:
        tags_str = ", ".join(product.tags)
        lines.append(f"  tags: [{tags_str}]")

    if product.variants:
        lines.append("  variants:")
        for v in product.variants:
            lines.append(f"    - id: {v.id}")
            if v.sku:
                lines.append(f"      sku: {v.sku}")
            if v.price is not None:
                lines.append(f"      price: {v.price}")
            if v.currency:
                lines.append(f"      currency: {v.currency}")
            if v.inventory_quantity is not None:
                lines.append(f"      inventory_quantity: {v.inventory_quantity}")

    if product.media:
        lines.append("  media:")
        for m in product.media:
            lines.append(f"    - url: {m.url}")
            if m.alt:
                lines.append(f"      alt: {m.alt}")

    return "\n".join(lines)
