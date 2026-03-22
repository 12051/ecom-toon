#!/usr/bin/env python
"""ecom-toon CLI - Production Ready"""
import json
import argparse
import glob
import csv
import gzip
import sys
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ecom_toon.toon_parser import (
    to_toon, do_toon_to_json, validate_roundtrip,
    parse_object_array, parse_value, parse_toon_to_json,
    compress_toon_gzip, decompress_gzip_to_toon,
    compress_json_gzip, count_tokens,
)

console = Console()

try:
    import tiktoken
    _TOKENIZER_LABEL = "tiktoken cl100k"
except ImportError:
    _TOKENIZER_LABEL = "approx (install tiktoken for exact counts)"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_products(data):
    """Extract list of items from any catalog shape."""
    for key in ("products", "items", "catalog", "data"):
        if key in data and isinstance(data[key], list):
            return data[key]
    if isinstance(data, list):
        return data
    return [data]


def _fmt_time(s: float) -> str:
    if s < 1:   return f"{s*1000:.0f} ms"
    if s < 60:  return f"{s:.1f} sec"
    return f"{int(s//60)} min {int(s%60)} sec"


# ── Preflight ─────────────────────────────────────────────────────────────────

def _preflight_single(input_path: Path, concurrency: int = 4) -> dict:
    """
    Sample ONE file and return raw estimate numbers.
    Does NOT print anything.
    """
    import time, tracemalloc, gc

    file_size_bytes = input_path.stat().st_size
    file_size_kb    = file_size_bytes / 1024

    raw_text = input_path.read_text(encoding="utf-8")
    data     = json.loads(raw_text)
    products = _get_products(data)
    n_products  = len(products)
    sample_size = min(10, n_products)
    sample      = products[:sample_size]

    # Memory
    gc.collect()
    tracemalloc.start()
    sample_json_texts = [json.dumps(p, indent=2) for p in sample]
    snap = tracemalloc.take_snapshot()
    sample_mem_bytes = sum(s.size for s in snap.statistics("lineno"))
    tracemalloc.stop()

    # Timing
    t0 = time.perf_counter()
    sample_toon = [to_toon(p) for p in sample]
    t1 = time.perf_counter()
    sample_time_s = t1 - t0

    # Token savings
    savings_list = []
    for jt, tt in zip(sample_json_texts, sample_toon):
        jc = count_tokens(jt); tc = count_tokens(tt)
        if jc > 0: savings_list.append((jc - tc) / jc)
    avg_savings = sum(savings_list) / len(savings_list) if savings_list else 0.40

    ms_per_product      = (sample_time_s / sample_size) * 1000
    est_time_single_s   = (ms_per_product * n_products) / 1000
    parallel_speedup    = min(concurrency * 0.7, max(1.0, n_products / 20))
    est_time_parallel_s = est_time_single_s / max(parallel_speedup, 1.0)
    est_memory_load_mb  = (file_size_kb * 3.2) / 1024
    est_memory_peak_mb  = est_memory_load_mb * 1.4
    full_json_tokens    = count_tokens(raw_text)
    est_toon_tokens     = int(full_json_tokens * (1 - avg_savings))

    return {
        "file":                 input_path.name,
        "file_size_kb":         file_size_kb,
        "n_products":           n_products,
        "sample_size":          sample_size,
        "ms_per_product":       ms_per_product,
        "est_time_single_s":    est_time_single_s,
        "est_time_parallel_s":  est_time_parallel_s,
        "est_memory_load_mb":   est_memory_load_mb,
        "est_memory_peak_mb":   est_memory_peak_mb,
        "avg_savings":          avg_savings,
        "full_json_tokens":     full_json_tokens,
        "est_toon_tokens":      est_toon_tokens,
        "est_tokens_saved":     full_json_tokens - est_toon_tokens,
    }


def _run_preflight(files: list, concurrency: int = 4,
                   skip_confirm: bool = False) -> bool:
    """
    Run preflight across ALL files, aggregate totals, display report,
    then ask to confirm.
    """
    from rich.table import Table
    from rich import box
    from rich.progress import Progress, SpinnerColumn, TextColumn

    console.print()
    console.print(f"[bold cyan]🔍 Pre-flight analysis across {len(files)} file(s)[/]")
    console.print(f"[dim]Sampling each file before processing...[/]\n")

    estimates = []
    with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}"),
                  transient=True) as prog:
        task = prog.add_task("Analysing files...", total=None)
        for f in files:
            prog.update(task, description=f"Sampling {Path(f).name}...")
            try:
                est = _preflight_single(Path(f), concurrency)
                estimates.append(est)
            except Exception as e:
                console.print(f"[yellow]  ⚠ Could not sample {Path(f).name}: {e}[/]")

    if not estimates:
        console.print("[red]No files could be sampled.[/]")
        return False

    # ── Aggregate totals ──────────────────────────────────────
    total_size_kb        = sum(e["file_size_kb"]        for e in estimates)
    total_products       = sum(e["n_products"]          for e in estimates)
    total_time_single_s  = sum(e["est_time_single_s"]   for e in estimates)
    total_time_parallel_s= sum(e["est_time_parallel_s"] for e in estimates)
    total_memory_load    = sum(e["est_memory_load_mb"]  for e in estimates)
    total_memory_peak    = sum(e["est_memory_peak_mb"]  for e in estimates)
    total_json_tokens    = sum(e["full_json_tokens"]    for e in estimates)
    total_toon_tokens    = sum(e["est_toon_tokens"]     for e in estimates)
    total_saved          = sum(e["est_tokens_saved"]    for e in estimates)
    avg_savings          = (total_json_tokens - total_toon_tokens) / total_json_tokens \
                           if total_json_tokens > 0 else 0

    tc = "green" if total_time_parallel_s<=60  else "yellow" if total_time_parallel_s<=300 else "red"
    mc = "green" if total_memory_peak<=100     else "yellow" if total_memory_peak<=500      else "red"
    sc = "green" if avg_savings>=0.35          else "yellow" if avg_savings>=0.20           else "red"

    # ── Per-file table ────────────────────────────────────────
    per_file = Table(box=box.SIMPLE, show_header=True, padding=(0,1))
    per_file.add_column("File",        style="white",      width=18)
    per_file.add_column("Size",        style="dim",        width=10)
    per_file.add_column("Products",    style="dim",        width=10)
    per_file.add_column("Est. Time",   width=12)
    per_file.add_column("Memory",      width=10)
    per_file.add_column("Savings",     width=10)

    for e in estimates:
        sc2 = "green" if e["avg_savings"]>=0.35 else "yellow" if e["avg_savings"]>=0.20 else "red"
        tc2 = "green" if e["est_time_parallel_s"]<=60 else "yellow" if e["est_time_parallel_s"]<=300 else "red"
        per_file.add_row(
            e["file"],
            f"{e['file_size_kb']:.0f} KB",
            str(e["n_products"]),
            f"[{tc2}]~{_fmt_time(e['est_time_parallel_s'])}[/]",
            f"~{e['est_memory_peak_mb']:.1f} MB",
            f"[{sc2}]{e['avg_savings']*100:.1f}%[/]",
        )

    # Totals row
    per_file.add_section()
    per_file.add_row(
        "[bold]TOTAL[/]",
        f"[bold]{total_size_kb:.0f} KB[/]",
        f"[bold]{total_products}[/]",
        f"[bold][{tc}]~{_fmt_time(total_time_parallel_s)}[/][/]",
        f"[bold]~{total_memory_peak:.1f} MB[/]",
        f"[bold][{sc}]{avg_savings*100:.1f}%[/][/]",
    )

    # ── Summary panel ─────────────────────────────────────────
    summary = Table(box=box.SIMPLE, show_header=False, padding=(0,1))
    summary.add_column("Label",  style="bold white", width=34)
    summary.add_column("Value",  width=18)
    summary.add_column("Note",   style="dim",  width=30)

    summary.add_row("📁  Files to process",
                    str(len(estimates)),
                    f"{total_size_kb:.1f} KB total")
    summary.add_row("🛒  Total products",
                    str(total_products),
                    "across all files")
    summary.add_section()
    summary.add_row(f"[{mc}]🧠  Est. total memory[/]",
                    f"[{mc}]~{total_memory_peak:.1f} MB[/]",
                    "peak during conversion")
    summary.add_row(f"[{tc}]⚡  Est. total time ({concurrency} workers)[/]",
                    f"[{tc}]~{_fmt_time(total_time_parallel_s)}[/]",
                    "all files combined")
    summary.add_section()
    summary.add_row("📊  Total JSON tokens",
                    f"{total_json_tokens:,}",
                    "all files combined")
    summary.add_row(f"[{sc}]📊  Est. TOON tokens[/]",
                    f"[{sc}]{total_toon_tokens:,}[/]",
                    f"saving ~{total_saved:,} tokens")
    summary.add_row(f"[{sc}]✨  Est. avg token savings[/]",
                    f"[{sc}]{avg_savings*100:.1f}%[/]",
                    "weighted across all files")

    console.print(Panel(per_file,
        title="[bold cyan]📋 Per-File Breakdown[/]",
        border_style="cyan"))

    console.print(Panel(summary,
        title="[bold cyan]📋 Pre-flight Summary — All Files[/]",
        border_style="cyan"))

    # Warnings
    if total_time_parallel_s > 300:
        console.print(f"  [red]⚠️  Total time > 5 min — consider splitting into smaller batches[/]")
    if total_memory_peak > 500:
        console.print(f"  [red]⚠️  High memory expected — ensure ≥{total_memory_peak:.0f} MB RAM free[/]")
    console.print()

    if skip_confirm:
        return True

    try:
        answer = console.input(
            f"[bold]Proceed with full conversion of {len(estimates)} file(s)?[/] "
            f"[dim](~{_fmt_time(total_time_parallel_s)} with {concurrency} workers)[/] "
            f"[bold cyan][y/n][/]: "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print("\n[yellow]Cancelled.[/]")
        return False

    if answer in ("y", "yes"):
        console.print(f"[green]✅ Starting conversion...[/]\n")
        return True
    console.print("[yellow]⏹  Conversion cancelled.[/]")
    return False


# ── Commands ──────────────────────────────────────────────────────────────────

def do_stats(input_file: Path) -> None:
    data    = json.loads(input_file.read_text(encoding="utf-8"))
    pretty  = json.dumps(data, indent=2)
    compact = json.dumps(data, separators=(",", ":"))
    toon_text = to_toon(data)

    pj_tok = count_tokens(pretty)
    cj_tok = count_tokens(compact)
    t_tok  = count_tokens(toon_text)
    savings_pretty  = (pj_tok - t_tok) / pj_tok * 100
    savings_compact = (cj_tok - t_tok) / cj_tok * 100
    j_gz = len(gzip.compress(compact.encode()))
    t_gz = len(gzip.compress(toon_text.encode()))
    gz_savings = (j_gz - t_gz) / j_gz * 100

    def sc(p): return "bold green" if p>=60 else "yellow" if p>=25 else "red"
    console.print(Panel.fit(
        f"[bold]Tokenizer        :[/]  {_TOKENIZER_LABEL}\n\n"
        f"[bold]Pretty JSON tokens :[/]  {pj_tok}\n"
        f"[bold]Compact JSON tokens:[/]  {cj_tok}\n"
        f"[bold]TOON tokens        :[/]  {t_tok}\n\n"
        f"[{sc(savings_pretty)}]Savings vs pretty JSON :[/]  [{sc(savings_pretty)}]{savings_pretty:.1f}%[/]\n"
        f"[{sc(savings_compact)}]Savings vs compact JSON:[/]  [{sc(savings_compact)}]{savings_compact:.1f}%[/]\n\n"
        f"[bold]Pretty JSON chars :[/]  {len(pretty)}\n"
        f"[bold]TOON chars        :[/]  {len(toon_text)}\n"
        f"[dim]Char savings      :   {(len(pretty)-len(toon_text))/len(pretty)*100:.1f}% (for reference)[/]\n\n"
        f"[dim]Gzip JSON  : {j_gz} bytes  |  Gzip TOON : {t_gz} bytes  |  Gzip savings: {gz_savings:.1f}%[/]",
        title="📊 Token Report", subtitle=str(input_file)))


def do_convert(input_file: Path, output_file: Path,
               preflight: bool = False, yes: bool = False) -> None:
    if preflight:
        if not _run_preflight([str(input_file)], skip_confirm=yes):
            return
    data = json.loads(input_file.read_text(encoding="utf-8"))
    toon_text = to_toon(data)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(toon_text, encoding="utf-8")
    print(f"✅ Converted {input_file} → {output_file}")


def _convert_one_json(json_path: Path, out_dir: Optional[Path]) -> dict:
    """Convert a single JSON file → .toon, save to out_dir (or same folder)."""
    try:
        data      = json.loads(json_path.read_text(encoding="utf-8"))
        pretty    = json.dumps(data, indent=2)
        toon_text = to_toon(data)
        j_tok     = count_tokens(pretty)
        t_tok     = count_tokens(toon_text)
        savings   = (j_tok - t_tok) / j_tok * 100

        # Output path: same name but .toon extension
        dest_dir  = out_dir if out_dir else json_path.parent
        dest_dir.mkdir(parents=True, exist_ok=True)
        out_path  = dest_dir / (json_path.stem + ".toon")
        out_path.write_text(toon_text, encoding="utf-8")

        return {"file": json_path.name, "output": str(out_path),
                "json_tokens": j_tok, "toon_tokens": t_tok,
                "savings": savings, "status": "ok"}
    except Exception as e:
        return {"file": json_path.name, "output": "", "status": "error", "error": str(e)}


def _convert_one_toon(toon_path: Path, out_dir: Optional[Path]) -> dict:
    """Convert a single .toon file → -tojson.json, save to out_dir."""
    try:
        toon_text = toon_path.read_text(encoding="utf-8")
        json_data = parse_toon_to_json(toon_text)

        dest_dir  = out_dir if out_dir else toon_path.parent
        dest_dir.mkdir(parents=True, exist_ok=True)
        out_path  = dest_dir / (toon_path.stem + "-tojson.json")
        out_path.write_text(
            json.dumps(json_data, indent=2, ensure_ascii=False),
            encoding="utf-8")

        return {"file": toon_path.name, "output": str(out_path), "status": "ok"}
    except Exception as e:
        return {"file": toon_path.name, "output": "", "status": "error", "error": str(e)}


def do_batch_json_to_toon(glob_pattern: str, out_dir: Optional[Path],
                          min_reduction: float, concurrency: int,
                          quiet: bool = False, preflight: bool = False,
                          yes: bool = False) -> None:
    """Batch convert all JSON files → .toon files."""
    files = glob.glob(glob_pattern, recursive=True)
    if not files:
        console.print("[red]No JSON files matched the pattern.[/]")
        return

    # Preflight across ALL matched files
    if preflight:
        if not _run_preflight(files, concurrency=concurrency, skip_confirm=yes):
            return

    console.print(f"[cyan]Converting {len(files)} JSON → TOON file(s)...[/]")
    results = []
    with Progress(SpinnerColumn(),
                  TextColumn("[progress.description]{task.description}"),
                  BarColumn(), TaskProgressColumn()) as progress:
        task = progress.add_task("Converting...", total=len(files))
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {
                executor.submit(_convert_one_json, Path(f), out_dir): f
                for f in files
            }
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                progress.advance(task)

    # Filter by savings threshold
    ok      = [r for r in results if r["status"] == "ok"]
    errors  = [r for r in results if r["status"] == "error"]
    passing = [r for r in ok if r.get("savings", 0) >= min_reduction]

    total_saved = sum(r["json_tokens"] - r["toon_tokens"] for r in passing)
    avg_savings = sum(r["savings"] for r in passing) / len(passing) if passing else 0

    if not quiet:
        tbl = Table(title=f"Batch JSON → TOON  [{_TOKENIZER_LABEL}]")
        tbl.add_column("Input JSON",  style="white",  width=20)
        tbl.add_column("Output TOON", style="cyan",   width=25)
        tbl.add_column("JSON tokens", width=12)
        tbl.add_column("TOON tokens", width=12)
        tbl.add_column("Savings",     width=10)

        for r in ok:
            color = "green" if r["savings"]>=40 else "yellow" if r["savings"]>=25 else "red"
            tbl.add_row(
                r["file"],
                Path(r["output"]).name,
                str(r["json_tokens"]),
                str(r["toon_tokens"]),
                f"[{color}]{r['savings']:.1f}%[/]",
            )
        for r in errors:
            tbl.add_row(r["file"], "—", "—", "—",
                        f"[red]ERROR: {r.get('error','')}[/]")

        console.print(tbl)
        console.print(
            f"[bold green]✅ {len(ok)}/{len(files)} files converted[/]  "
            f"· Total saved: [green]{total_saved:,}[/] tokens "
            f"· Avg savings: [green]{avg_savings:.1f}%[/]"
        )
        if errors:
            console.print(f"[red]❌ {len(errors)} file(s) failed[/]")

    # CSV report
    csv_rows = [
        {"file": r["file"], "output": Path(r["output"]).name,
         "json_tokens": r.get("json_tokens",""), "toon_tokens": r.get("toon_tokens",""),
         "savings": f"{r['savings']:.1f}%" if "savings" in r else "ERROR"}
        for r in results
    ]
    with open("toon-report.csv", "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["file","output","json_tokens","toon_tokens","savings"])
        writer.writeheader(); writer.writerows(csv_rows)

    if not quiet:
        console.print("[blue]📄 Report saved: toon-report.csv[/]")


def _preflight_toon(files: list, concurrency: int = 4,
                    skip_confirm: bool = False) -> bool:
    """Pre-flight for TOON → JSON: estimate time + size, then confirm."""
    import time
    from rich.table import Table
    from rich import box

    console.print()
    console.print(f"[bold cyan]🔍 Pre-flight analysis across {len(files)} TOON file(s)[/]")
    console.print(f"[dim]Sampling each file before processing...[/]\n")

    # Sample parse speed on first file
    sample_path = Path(files[0])
    t0 = time.perf_counter()
    try:
        sample_text = sample_path.read_text(encoding="utf-8")
        parse_toon_to_json(sample_text)
        t1 = time.perf_counter()
        ms_per_kb = ((t1 - t0) * 1000) / max(len(sample_text) / 1024, 0.1)
    except Exception:
        ms_per_kb = 2.0  # fallback: 2ms per KB

    total_size_bytes = sum(Path(f).stat().st_size for f in files)
    total_size_kb    = total_size_bytes / 1024
    est_time_single  = (ms_per_kb * total_size_kb) / 1000
    speedup          = min(concurrency * 0.7, max(1.0, len(files) / 4))
    est_time_parallel= est_time_single / max(speedup, 1.0)

    tc = "green" if est_time_parallel <= 60 else "yellow" if est_time_parallel <= 300 else "red"

    # Per-file table
    tbl = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    tbl.add_column("TOON File",    style="cyan",  width=25)
    tbl.add_column("Size",         style="dim",   width=10)
    tbl.add_column("Output JSON",  style="white", width=28)

    for f in files:
        p = Path(f)
        size_kb = p.stat().st_size / 1024
        out_name = p.stem + "-tojson.json"
        tbl.add_row(p.name, f"{size_kb:.1f} KB", out_name)

    console.print(tbl)

    # Summary panel
    from rich.table import Table as T2
    summary = T2(box=box.SIMPLE, show_header=False, padding=(0, 1))
    summary.add_column("Label", style="bold white", width=34)
    summary.add_column("Value", width=18)
    summary.add_column("Note",  style="dim", width=30)

    summary.add_row("📁  Files to convert",
                    str(len(files)),
                    f"{total_size_kb:.1f} KB total")
    summary.add_row(f"[{tc}]⚡  Est. time ({concurrency} workers)[/]",
                    f"[{tc}]~{_fmt_time(est_time_parallel)}[/]",
                    f"speedup: {speedup:.1f}x")
    summary.add_row("📄  Output naming",
                    "filename-tojson.json",
                    "one per .toon file")

    console.print(Panel(summary,
        title="[bold cyan]📋 Pre-flight Summary — TOON → JSON[/]",
        border_style="cyan"))

    if est_time_parallel > 300:
        console.print(f"  [red]⚠️  Estimated time > 5 min — consider smaller batches[/]")
    console.print()

    if skip_confirm:
        return True

    try:
        answer = console.input(
            f"[bold]Proceed with converting {len(files)} TOON file(s) to JSON?[/] "
            f"[dim](~{_fmt_time(est_time_parallel)} with {concurrency} workers)[/] "
            f"[bold cyan][y/n][/]: "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print("\n[yellow]Cancelled.[/]")
        return False

    if answer in ("y", "yes"):
        console.print(f"[green]✅ Starting conversion...[/]\n")
        return True
    console.print("[yellow]⏹  Conversion cancelled.[/]")
    return False


def do_batch_toon_to_json(glob_pattern: str, out_dir: Optional[Path],
                          concurrency: int, quiet: bool = False,
                          preflight: bool = False, yes: bool = False) -> None:
    """Batch convert all .toon files → -tojson.json files."""
    files = glob.glob(glob_pattern, recursive=True)
    if not files:
        console.print("[red]No TOON files matched the pattern.[/]")
        return

    if preflight:
        if not _preflight_toon(files, concurrency=concurrency, skip_confirm=yes):
            return

    console.print(f"[cyan]Converting {len(files)} TOON → JSON file(s)...[/]")
    results = []
    with Progress(SpinnerColumn(),
                  TextColumn("[progress.description]{task.description}"),
                  BarColumn(), TaskProgressColumn()) as progress:
        task = progress.add_task("Converting...", total=len(files))
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {
                executor.submit(_convert_one_toon, Path(f), out_dir): f
                for f in files
            }
            for future in as_completed(futures):
                results.append(future.result())
                progress.advance(task)

    ok     = [r for r in results if r["status"] == "ok"]
    errors = [r for r in results if r["status"] == "error"]

    if not quiet:
        tbl = Table(title="Batch TOON → JSON")
        tbl.add_column("Input TOON",  style="cyan",  width=25)
        tbl.add_column("Output JSON", style="white", width=28)
        tbl.add_column("Status",      width=10)

        for r in ok:
            tbl.add_row(r["file"], Path(r["output"]).name, "[green]✅ OK[/]")
        for r in errors:
            tbl.add_row(r["file"], "—", f"[red]❌ {r.get('error','')}[/]")

        console.print(tbl)
        console.print(
            f"[bold green]✅ {len(ok)}/{len(files)} files converted[/]"
        )
        if errors:
            console.print(f"[red]❌ {len(errors)} file(s) failed[/]")


def do_compress_toon(toon_path: Path, output_path: Optional[Path]) -> None:
    if output_path is None:
        output_path = toon_path.with_suffix(".toon.gz")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    compress_toon_gzip(toon_path.read_text(encoding="utf-8"), output_path)


def do_decompress(gzip_path: Path, output_path: Path) -> None:
    toon_text = decompress_gzip_to_toon(gzip_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(toon_text, encoding="utf-8")
    print(f"✅ Decompressed {gzip_path} → {output_path}")


def do_compress_json(json_path: Path, output_path: Optional[Path]) -> None:
    if output_path is None:
        output_path = json_path.with_suffix(".json.gz")
    compress_json_gzip(json.loads(json_path.read_text(encoding="utf-8")), output_path)


def do_compress_pipeline(json_path: Path, output_path: Optional[Path],
                         preflight: bool = False, yes: bool = False) -> None:
    if preflight:
        if not _run_preflight([str(json_path)], skip_confirm=yes):
            return
    if output_path is None:
        output_path = json_path.with_suffix(".toon.gz")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data      = json.loads(json_path.read_text(encoding="utf-8"))
    toon_text = to_toon(data)
    compress_toon_gzip(toon_text, output_path)
    j_tok   = count_tokens(json.dumps(data, indent=2))
    t_tok   = count_tokens(toon_text)
    savings = (j_tok - t_tok) / j_tok * 100
    console.print(
        f"[green]✅ Pipeline complete:[/]\n"
        f"  JSON ({j_tok:,} tokens) → TOON ({t_tok:,} tokens, "
        f"{savings:.1f}% savings) → {output_path}\n"
        f"  [dim]Tokenizer: {_TOKENIZER_LABEL}[/]")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="ecom-toon: JSON ↔ TOON converter")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # stats
    sp = subparsers.add_parser("stats", help="Show token report for a JSON file")
    sp.add_argument("input_file")

    # convert  (single file)
    sp = subparsers.add_parser("convert", help="Convert one JSON → TOON")
    sp.add_argument("input_file")
    sp.add_argument("-o", "--output", default="output.toon")
    sp.add_argument("--preflight", action="store_true",
                    help="Show memory/time/savings estimate before converting")
    sp.add_argument("-y", "--yes", action="store_true",
                    help="Skip confirmation prompt after preflight")

    # batch  (JSON → TOON, ALL files in folder)
    sp = subparsers.add_parser(
        "batch",
        help='Batch convert ALL JSON files → .toon  (e.g. "samples/*.json")')
    sp.add_argument("glob_pattern",
                    help='File pattern, e.g. "samples/*.json"')
    sp.add_argument("--out-dir", default=None,
                    help="Output folder for .toon files (default: same folder as input)")
    sp.add_argument("--min-reduction", type=float, default=0.0,
                    help="Only report files above this %% savings (default: 0)")
    sp.add_argument("--concurrency", type=int, default=4)
    sp.add_argument("--quiet", "-q", action="store_true")
    sp.add_argument("--preflight", action="store_true",
                    help="Show estimate for ALL files before starting")
    sp.add_argument("-y", "--yes", action="store_true",
                    help="Skip confirmation prompt after preflight")

    # batch-to-json  (TOON → JSON, ALL files in folder)
    sp = subparsers.add_parser(
        "batch-to-json",
        help='Batch convert ALL .toon files → -tojson.json  (e.g. "samples/*.toon")')
    sp.add_argument("glob_pattern",
                    help='File pattern, e.g. "samples/*.toon"')
    sp.add_argument("--out-dir", default=None,
                    help="Output folder for .json files (default: same folder as input)")
    sp.add_argument("--concurrency", type=int, default=4)
    sp.add_argument("--quiet", "-q", action="store_true")
    sp.add_argument("--preflight", action="store_true",
                    help="Show estimate for all files before starting")
    sp.add_argument("-y", "--yes", action="store_true",
                    help="Skip confirmation prompt after preflight")

    # to-json  (single file)
    sp = subparsers.add_parser("to-json", help="Convert one TOON → JSON")
    sp.add_argument("input_file")
    sp.add_argument("-o", "--output", default="output.json")

    # roundtrip
    sp = subparsers.add_parser("roundtrip", help="Test JSON → TOON → JSON integrity")
    sp.add_argument("json_file")

    # parse-object-array
    sp = subparsers.add_parser("parse-object-array",
                               help="Parse object array from TOON lines")
    sp.add_argument("lines_file"); sp.add_argument("fields")
    sp.add_argument("count", type=int)

    # parse-value
    sp = subparsers.add_parser("parse-value", help="Parse a single TOON value")
    sp.add_argument("value")

    # compress-toon
    sp = subparsers.add_parser("compress-toon", help="TOON → .toon.gz")
    sp.add_argument("toon_file"); sp.add_argument("-o", "--output", default=None)

    # decompress
    sp = subparsers.add_parser("decompress", help=".toon.gz → TOON")
    sp.add_argument("gzip_file")
    sp.add_argument("-o", "--output", default="decompressed.toon")

    # compress-json
    sp = subparsers.add_parser("compress-json", help="JSON → .json.gz")
    sp.add_argument("json_file"); sp.add_argument("-o", "--output", default=None)

    # compress-pipeline
    sp = subparsers.add_parser("compress-pipeline", help="JSON → TOON → .toon.gz")
    sp.add_argument("json_file"); sp.add_argument("-o", "--output", default=None)
    sp.add_argument("--preflight", action="store_true")
    sp.add_argument("-y", "--yes", action="store_true")

    args = parser.parse_args()

    if args.command == "stats":
        do_stats(Path(args.input_file))

    elif args.command == "convert":
        do_convert(Path(args.input_file), Path(args.output),
                   preflight=args.preflight, yes=args.yes)

    elif args.command == "batch":
        do_batch_json_to_toon(
            args.glob_pattern,
            Path(args.out_dir) if args.out_dir else None,
            args.min_reduction, args.concurrency, args.quiet,
            preflight=args.preflight, yes=args.yes)

    elif args.command == "batch-to-json":
        do_batch_toon_to_json(
            args.glob_pattern,
            Path(args.out_dir) if args.out_dir else None,
            args.concurrency, args.quiet,
            preflight=args.preflight, yes=args.yes)

    elif args.command == "to-json":
        do_toon_to_json(Path(args.input_file), Path(args.output))

    elif args.command == "roundtrip":
        validate_roundtrip(Path(args.json_file))

    elif args.command == "parse-object-array":
        lines  = Path(args.lines_file).read_text().splitlines()
        fields = [f.strip() for f in args.fields.split(",")]
        print(json.dumps(parse_object_array(lines, 0, fields, args.count), indent=2))

    elif args.command == "parse-value":
        print(parse_value(args.value))

    elif args.command == "compress-toon":
        do_compress_toon(Path(args.toon_file),
                         Path(args.output) if args.output else None)

    elif args.command == "decompress":
        do_decompress(Path(args.gzip_file), Path(args.output))

    elif args.command == "compress-json":
        do_compress_json(Path(args.json_file),
                         Path(args.output) if args.output else None)

    elif args.command == "compress-pipeline":
        do_compress_pipeline(
            Path(args.json_file),
            Path(args.output) if args.output else None,
            preflight=args.preflight, yes=args.yes)


if __name__ == "__main__":
    main()