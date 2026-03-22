import json
from typing import Any
import re

def escape_csv(value: Any) -> str:
    """Escape for EXACT TOON format - no quotes except when absolutely needed."""
    value = str(value)
    
    # Handle nulls
    if value.lower() in ('none', 'null', ''):
        return 'null'
    
    # Lowercase booleans
    if value.lower() in ('true', 'false'):
        return value.lower()
    
    # Timestamps: replace : with ,
    if 'T' in value and 'Z' in value:
        return value.replace(':', ',')
    
    # URLs: https:// → https,//
    if value.startswith('http'):
        return value.replace('https://', 'https,//').replace('http://', 'http,//')
    
    # Remove spaces after commas in HTML/content
    value = value.replace(', ', ',')
    
    # NO QUOTES for any value, just return as-is after above processing
    return value

def format_array_row(item: dict, fields: list, indent: str) -> str:
    """Single-line array item."""
    values = [escape_csv(item.get(field, 'null')) for field in fields]
    return f"{indent}{','.join(values)}"

def format_nested_option(obj: dict, indent: str) -> str:
    """Special format for options array - exactly as requested."""
    lines = [f"{indent}-"]
    for k, v in obj.items():
        if k == 'values' and isinstance(v, list):
            vals = [escape_csv(str(x)) for x in v]
            lines.append(f"{indent}  {k}[{len(v)}],{','.join(vals)}")
        else:
            lines.append(f"{indent}  {k},{escape_csv(v)}")
    return "\n".join(lines)

def obj_to_toon(obj: Any, indent: str = "") -> str:
    """Main TOON converter."""
    lines = []
    
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == 'options' and isinstance(v, list):
                # Special case for options
                lines.append(f"{indent}{k}[{len(v)}]")
                for item in v:
                    lines.append(format_nested_option(item, indent + "  "))
            elif isinstance(v, list):
                if v and isinstance(v[0], dict):
                    # Array of objects
                    fields = list(v[0].keys())
                    lines.append(f"{indent}{k}[{len(v)}]{{{','.join(fields)}}}")
                    for item in v:
                        lines.append(format_array_row(item, fields, indent + "  "))
                else:
                    # Simple array
                    vals = [escape_csv(str(x)) for x in v]
                    lines.append(f"{indent}{k}[{len(v)}],{','.join(vals)}")
            elif isinstance(v, dict):
                lines.append(f"{indent}{k},")
                lines.append(obj_to_toon(v, indent + "  "))
            else:
                lines.append(f"{indent}{k},{escape_csv(v)}")
    
    return "\n".join(lines)

def json_to_toon(obj: Any) -> str:
    return obj_to_toon(obj)
