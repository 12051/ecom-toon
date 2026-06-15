# ecom_toon/toon_parser.py
"""
TOON format writer and parser.

Format rules:
  - Simple scalar:          key,value
  - Simple array:           key[N],val1,val2,...
  - Object array (uniform): key[N]{f1,f2,...},
                              val1,val2,...   (one row per object)
  - Object array (mixed):   key[N],
                              -
                                field,value
                                ...
  - Nested dict:            key,
                              child_key,value
                              ...
  - Timestamps:             colons → commas  e.g. 14:22:00 → 14,22,00
  - URLs:                   https:// → https~/  (tilde+slash, NO comma)
  - Numeric JSON strings:   wrapped in double-quotes e.g. "399.00"

URL encoding uses ~/ instead of ,// to avoid comma-splitting bugs
when URLs appear inside object array rows.
"""

import json
import re
import gzip
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Token counting  (module-level, always defined, never returns None)
# ---------------------------------------------------------------------------

try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
    def count_tokens(text: str) -> int:
        return len(_enc.encode(text))
except Exception:
    def count_tokens(text: str) -> int:  # type: ignore[misc]
        tokens = re.findall(r'[a-zA-Z0-9_\-\.]+|[^a-zA-Z0-9_\-\.\s]|\s+', text)
        return sum(max(1, len(t) // 4) if t[0].isalnum() else 1 for t in tokens)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_uniform_object_array(lst: list) -> bool:
    """All items are dicts AND share the exact same keys in the same order."""
    if not lst or not isinstance(lst[0], dict):
        return False
    first_keys = list(lst[0].keys())
    for item in lst[1:]:
        if not isinstance(item, dict) or list(item.keys()) != first_keys:
            return False
    return True


def _escape(value: Any) -> str:
    """Encode a scalar for TOON.

    RULE: any encoded value that contains a comma MUST be wrapped in
    double-quotes so the CSV row parser can split correctly.

    URL:            https:// → https~/  (tilde+slash, no comma introduced)
    Timestamp:      colons   → commas   (unquoted, parsed by timestamp rule)
    Numeric string: "399.00" → quoted   (preserves string type on roundtrip)
    String w/comma: "a, b"   → quoted   (prevents CSV splitting bugs)
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    s = str(value)
    # Timestamps: keep colons as-is (no comma replacement needed)
    # The datetime pattern in _unescape detects and returns it unchanged
    if re.match(r'^\d{4}-\d{2}-\d{2}T', s):
        return s  # return unchanged — no commas introduced
    # URLs: use ~/ so no comma is introduced into the encoded value
    if s.startswith("https://"):
        return "https~/" + s[len("https://"):]
    if s.startswith("http://"):
        return "http~/" + s[len("http://"):]
    # Numeric-looking strings → quote to preserve string type on roundtrip
    if re.match(r'^-?\d+(\.\d+)?$', s):
        return f'"{s}"'
    # Replace control characters with space
    s = re.sub(r'[\n\r\t]', ' ', s)
    # Any string containing a comma → quote it so CSV row splitting stays safe
    if ',' in s:
        s = s.replace('"', '\\"')  # escape any inner double-quotes
        return f'"{s}"'
    return s

def _unescape(value: str) -> Any:
    """Decode a TOON scalar back to its Python type."""
    v = value  # do NOT strip — spaces may be part of the actual value

    # Quoted string -> strip outer quotes and unescape inner \\"
    if len(v) >= 2 and v[0] == chr(34) and v[-1] == chr(34):
        inner = v[1:-1].replace(chr(92)+chr(34), chr(34))
        return inner

    # URLs: restore ~/ back to ://
    if v.startswith("https~/"):
        return "https://" + v[len("https~/"):]
    if v.startswith("http~/"):
        return "http://" + v[len("http~/"):]

    # Timestamps: detect ISO datetime pattern and return as string
    if re.match(r'^\d{4}-\d{2}-\d{2}T[\d:]+Z$', v):
        return v  # already correct, no transformation needed

    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    if v.lower() == "null":
        return None

    if re.match(r"^-?\d+$", v):
        return int(v)
    if re.match(r"^-?\d+\.\d+$", v):
        return float(v)

    return v

def obj_to_toon(obj: Any, _indent: str = "") -> str:
    """Convert a Python object to TOON text (spec-compliant)."""
    lines: List[str] = []
    if isinstance(obj, dict):
        _write_dict(obj, lines, _indent)
    return "\n".join(lines)


def _write_dict(d: dict, lines: List[str], indent: str) -> None:
    for k, v in d.items():
        _write_key_value(k, v, lines, indent)


def _write_key_value(key: str, value: Any, lines: List[str], indent: str) -> None:
    if isinstance(value, dict):
        lines.append(f"{indent}{key},")
        _write_dict(value, lines, indent + "  ")

    elif isinstance(value, list):
        n = len(value)
        if n == 0:
            lines.append(f"{indent}{key}[0],")
        elif _is_uniform_object_array(value):
            fields = list(value[0].keys())
            has_complex = any(
                isinstance(item.get(f), (list, dict))
                for item in value for f in fields
            )
            if has_complex:
                _write_mixed_object_array(key, value, lines, indent)
            else:
                lines.append(f"{indent}{key}[{n}]{{{','.join(fields)}}},")
                for item in value:
                    row = ",".join(_escape(item.get(f, None)) for f in fields)
                    lines.append(f"{indent}  {row}")
        elif all(not isinstance(x, (dict, list)) for x in value):
            vals = ",".join(_escape(x) for x in value)
            lines.append(f"{indent}{key}[{n}],{vals}")
        else:
            _write_mixed_object_array(key, value, lines, indent)

    else:
        lines.append(f"{indent}{key},{_escape(value)}")


def _write_mixed_object_array(key: str, lst: list,
                               lines: List[str], indent: str) -> None:
    lines.append(f"{indent}{key}[{len(lst)}],")
    for item in lst:
        lines.append(f"{indent}  -")
        if isinstance(item, dict):
            _write_dict(item, lines, indent + "    ")
        else:
            lines.append(f"{indent}    {_escape(item)}")


def json_to_toon(obj: Any) -> str:
    return obj_to_toon(obj)


# ---------------------------------------------------------------------------
# Parser  (TOON → JSON)
# ---------------------------------------------------------------------------

def parse_toon_to_json(toon_text: str) -> Dict[str, Any]:
    lines = toon_text.split("\n")
    result, _ = _parse_block(lines, 0, "")
    return result


def _get_indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _parse_block(lines: List[str], start: int,
                 base_indent: str) -> Tuple[dict, int]:
    result: Dict[str, Any] = {}
    i = start
    base_len = len(base_indent)

    while i < len(lines):
        raw = lines[i]
        if not raw.strip():
            i += 1
            continue

        indent_len = _get_indent(raw)
        if indent_len < base_len:
            break
        if indent_len > base_len:
            i += 1
            continue

        line     = raw.strip()   # for pattern matching
        line_raw = raw.lstrip()   # for value extraction (preserves trailing spaces)

        # Uniform object array: key[N]{f1,f2,...},
        m = re.match(r'^(\w+)\[(\d+)\]\{([^}]*)\},\s*$', line)
        if m:
            key    = m.group(1)
            n      = int(m.group(2))
            fields = [f.strip() for f in m.group(3).split(",")]
            i += 1
            items  = []
            for _ in range(n):
                while i < len(lines) and not lines[i].strip():
                    i += 1
                if i >= len(lines):
                    break
                row_line   = lines[i].lstrip()
                raw_values = _split_csv(row_line, len(fields))
                item = {
                    fields[j]: _unescape(raw_values[j])
                    if j < len(raw_values) else None
                    for j in range(len(fields))
                }
                items.append(item)
                i += 1
            result[key] = items
            continue

        # Mixed object array: key[N],   (no {fields})
        m2 = re.match(r'^(\w+)\[(\d+)\],\s*$', line)
        if m2:
            key = m2.group(1)
            n   = int(m2.group(2))
            i  += 1
            items, i = _parse_mixed_array(lines, i, base_indent + "  ", n)
            result[key] = items
            continue

        # Simple scalar array: key[N],v1,v2,...
        m3 = re.match(r'^(\w+)\[(\d+)\],(.+)$', line)
        if m3:
            key      = m3.group(1)
            vals_str = m3.group(3)
            vals     = [_unescape(v)
                        for v in vals_str.split(",") if v.strip()]
            result[key] = vals
            i += 1
            continue

        # Nested dict: key,   (nothing after comma)
        m4 = re.match(r'^([\w]+),\s*$', line)
        if m4:
            key = m4.group(1)
            i  += 1
            child, i = _parse_block(lines, i, base_indent + "  ")
            result[key] = child
            continue

        # Simple key,value
        if "," in line_raw:
            key, _, rest = line_raw.partition(",")
            result[key.strip()] = _unescape(rest)
            i += 1
            continue

        i += 1

    return result, i


def _parse_mixed_array(lines: List[str], start: int,
                       item_indent: str, count: int) -> Tuple[list, int]:
    items = []
    i = start
    item_indent_len = len(item_indent)
    field_indent    = item_indent + "  "

    while i < len(lines) and len(items) < count:
        raw = lines[i]
        if not raw.strip():
            i += 1
            continue
        indent_len = _get_indent(raw)
        if indent_len < item_indent_len:
            break
        line = raw.strip()
        if line == "-":
            i += 1
            item, i = _parse_block(lines, i, field_indent)
            items.append(item)
        else:
            break

    return items, i


def _split_csv(line: str, n_fields: int) -> List[str]:
    """
    Split a TOON row into exactly n_fields values, respecting quoted fields.

    Quoted fields (wrapped in "...") may contain commas safely.
    Example: 850703873,329678821,"Machine wash cold, tumble dry low",custom
    splits into 4 fields correctly.
    """
    parts   = []
    current = []
    in_quote = False
    i = 0
    Q = chr(34)  # double-quote character
    while i < len(line):
        ch = line[i]
        if ch == Q and not in_quote:
            in_quote = True
            current.append(ch)
        elif ch == Q and in_quote:
            # escaped quote: two consecutive double-quotes inside a quoted field
            if i + 1 < len(line) and line[i+1] == Q:
                current.append(Q)
                i += 1
            else:
                in_quote = False
                current.append(ch)
        elif ch == ',' and not in_quote:
            parts.append(''.join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    parts.append(''.join(current))  # last field

    # Pad if fewer parts than expected
    while len(parts) < n_fields:
        parts.append('')

    # Overflow: re-join into last field (safety net)
    if len(parts) > n_fields:
        parts = parts[:n_fields - 1] + [','.join(parts[n_fields - 1:])]

    return parts

def compress_toon_gzip(toon_text: str, output_file: Path) -> None:
    data       = toon_text.encode("utf-8")
    compressed = gzip.compress(data)
    output_file.write_bytes(compressed)
    print(f"[OK] Compressed {len(data)}B -> {len(compressed)}B ({output_file})")


def decompress_gzip_to_toon(gzip_file: Path) -> str:
    return gzip.decompress(gzip_file.read_bytes()).decode("utf-8")


def compress_json_gzip(json_data: dict, output_file: Path) -> None:
    data       = json.dumps(json_data).encode("utf-8")
    compressed = gzip.compress(data)
    output_file.write_bytes(compressed)
    print(f"[OK] Compressed JSON -> {output_file}")


# ---------------------------------------------------------------------------
# File-level helpers
# ---------------------------------------------------------------------------

def do_toon_to_json(input_file: Path, output_file: Path) -> None:
    toon_text = input_file.read_text(encoding="utf-8")
    json_data = parse_toon_to_json(toon_text)
    output_file.write_text(
        json.dumps(json_data, indent=2, ensure_ascii=False),
        encoding="utf-8")
    print(f"[OK] Converted {input_file} -> {output_file}")


def validate_roundtrip(json_file: Path) -> None:
    data      = json.loads(json_file.read_text(encoding="utf-8"))
    toon_text = obj_to_toon(data)
    roundtrip = parse_toon_to_json(toon_text)
    orig = json.dumps(data,      sort_keys=True, ensure_ascii=False)
    rt   = json.dumps(roundtrip, sort_keys=True, ensure_ascii=False)
    if orig == rt:
        print("[OK] Roundtrip: PASS")
    else:
        print("[FAIL] Roundtrip: FAIL")
        for a, b in zip(orig.split(","), rt.split(",")):
            if a != b:
                print(f"  Expected: {a}")
                print(f"  Got:      {b}")
                break


def parse_object_array(lines: List[str], start_idx: int,
                       fields: List[str], count: int) -> List[Dict]:
    array = []
    i = start_idx
    for _ in range(count):
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i >= len(lines):
            break
        row  = _split_csv(lines[i].strip(), len(fields))
        item = {
            fields[j]: _unescape(row[j]) if j < len(row) else None
            for j in range(len(fields))
        }
        array.append(item)
        i += 1
    return array


def parse_value(value: str) -> Any:
    return _unescape(value)


# ---------------------------------------------------------------------------
# to_toon() — single entry point for main.py
# ---------------------------------------------------------------------------

def to_toon(data: Any, mode: str = "pretty") -> str:
    """Convert data to TOON (spec-compliant pretty format)."""
    return obj_to_toon(data)