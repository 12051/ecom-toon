from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class VariantCIM:
    id: str
    sku: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    inventory_quantity: Optional[int] = None


@dataclass
class MediaCIM:
    url: str
    alt: Optional[str] = None


@dataclass
class ProductCIM:
    id: str
    title: str
    description: Optional[str] = None
    slug: Optional[str] = None
    brand: Optional[str] = None
    categories: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    variants: List[VariantCIM] = field(default_factory=list)
    media: List[MediaCIM] = field(default_factory=list)
    attrs: Dict[str, Any] = field(default_factory=dict)
