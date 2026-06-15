# ecom-toon: JSON → TOON Converter

Convert eCommerce JSON to TOON format — save 38-44% LLM tokens with zero data loss. Right-click any .json file to convert instantly.

## Features

- ✅ Right-click any `.json` file → **Convert JSON → TOON**
- ✅ Right-click any `.toon` file → **Convert TOON → JSON**
- ✅ **Token savings report** — see exactly how many tokens you save
- ✅ **Batch convert** an entire folder at once
- ✅ **Roundtrip validation** — prove zero data loss
- ✅ Status bar button — convert with one click

## Setup (First Time)

1. Install this extension
2. Open VS Code Settings (`Ctrl+Shift+X`)
3. Search for `ecom-toon`
4. Install

## How to Use

### Convert a single JSON file
1. Right-click any `.json` file in the Explorer panel
2. Click **"ecom-toon: Convert JSON → TOON"**
3. A `.toon` file appears next to your JSON file
4. A notification shows your token savings %

### Convert back to JSON
1. Right-click any `.toon` file
2. Click **"ecom-toon: Convert TOON → JSON"**
3. A `-tojson.json` file appears

### See token savings report
1. Right-click any `.json` file
2. Click **"ecom-toon: Show Token Savings Report"**
3. An Output panel opens with full stats

### Batch convert a folder
1. Right-click any folder in Explorer
2. Click **"ecom-toon: Batch Convert Folder (JSON → TOON)"**
3. All `.json` files in the folder get converted

### Validate zero data loss
1. Right-click any `.json` file
2. Click **"ecom-toon: Validate Roundtrip"**
3. Confirms JSON → TOON → JSON produces identical output

## What is TOON?

TOON is a compact text format for eCommerce data. It removes JSON's structural
overhead (`"`, `{`, `}`, `:`, indentation) while keeping all data intact.

**Example:**

JSON (1,927 tokens):
```json
{
  "id": 987654321,
  "title": "Sony WH-1000XM5",
  "variants": [
    {
      "id": 111222333,
      "sku": "WH1000XM5-BLK",
      "price": "399.00"
    }
  ]
}
```

TOON (1,184 tokens — 38.6% fewer):
```
id,987654321
title,Sony WH-1000XM5
variants[1]{id,sku,price},
  111222333,WH1000XM5-BLK,"399.00"
```

## Token Savings by Catalog Size

| Catalog | JSON tokens | TOON tokens | Savings |
|---|---|---|---|
| 1 product | 551 | 346 | 37.2% |
| 3 products | 1,457 | 992 | 31.9% |
| 141 products | 214,403 | 124,969 | 41.7% |
| 500 products | 1,471,066 | 811,907 | 44.8% |

## License

MIT