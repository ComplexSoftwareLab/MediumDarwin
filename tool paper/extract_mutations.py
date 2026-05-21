#!/usr/bin/env python3
"""
Compare LittleDarwin vs MediumDarwin -m mutant files (paper Table I style).

Paper "refined mutation operators" (Section 4.4):
  - Reduced: mutants LD generates that MD does not (non-compilable filtered, etc.)
  - Added: mutants MD generates that LD skipped
  - Count identity: len(MD) = len(LD) - Reduced + Added

Important: LD and MD use different RelationalOperatorReplacement maps
  LD:  '<' -> '>='     MD:  '<' -> '<='
So strict before/after matching falsely reports 33 removed + 33 added on commons-cli.
Paper-aligned counting uses mutation *sites* for relational ops (same line + before text).

Outputs:
  summary.txt  — Table I style (Original, Reduced, Added, delta %)
  removed_in_mediumdarwin.csv / added_in_mediumdarwin.csv — paper-aligned rows
  strict_removed.csv / strict_added.csv — naive strict diff (debug only)
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

MUTATION_BLOCK = re.compile(
    r"mutant type:\s*(?P<operator>.+?)\s*\n"
    r"---->\s*before:\s*(?P<before>.+?)\s*\n"
    r"---->\s*after:\s*(?P<after>.+?)\s*\n"
    r"---->\s*line number in original file:\s*(?P<line>\d+)",
    re.MULTILINE,
)
MUT_TAG = re.compile(r"/\*MUT\d*\*/")

# Operators where LD/MD may pick different replacements at the same site (not net Reduced+Added).
SITE_LEVEL_OPERATORS = frozenset(
    {
        "RelationalOperatorReplacement",
        "ConditionalOperatorReplacement",
        "LogicalOperatorReplacement",
        "ArithmeticOperatorReplacementBinary",
        "ArithmeticOperatorReplacementUnary",
        "ArithmeticOperatorReplacementShortcut",
        "AssignmentOperatorReplacementShortcut",
        "ShiftOperatorReplacement",
    }
)

CSV_FIELDS = [
    "file",
    "line",
    "operator",
    "before",
    "after",
    "mutant_id",
    "paper_category",
]


def norm(s: str) -> str:
    return " ".join(MUT_TAG.sub("", s).split())


def normalize_file_path(file_name: str) -> str:
    p = file_name.replace("\\", "/")
    for marker in ("/src/main/java/", "/src/test/java/"):
        if marker in p:
            return p.split(marker, 1)[1]
    parts = p.split("/")
    for i, part in enumerate(parts):
        if part and part[0].islower() and "." not in part:
            return "/".join(parts[i:])
    return p.lstrip("/")


def method_signature(before: str) -> str:
    return norm(before.split("\n", 1)[0])


def nullify_target(after: str) -> str:
    m = re.search(r"(\w+)\s*=\s*null", after)
    return m.group(1) if m else ""


def strict_key(row: dict) -> tuple:
    return (
        normalize_file_path(row["file"]),
        int(row["line"]),
        row["operator"].strip(),
        norm(row.get("before", "")),
        norm(row.get("after", "")),
    )


def site_key(row: dict) -> tuple:
    """Mutation site for paper-aligned pairing."""
    op = row["operator"].strip()
    base = (
        normalize_file_path(row["file"]),
        int(row["line"]),
        op,
        method_signature(row.get("before", "")),
    )
    if op == "NullifyInputVariable":
        return base + (nullify_target(row.get("after", "")),)
    if op in SITE_LEVEL_OPERATORS:
        return base
    return base + (norm(row.get("before", "")), norm(row.get("after", "")))


def classify_removed(row: dict) -> str:
    op = row["operator"]
    before = row.get("before", "")
    if op == "NullifyInputVariable":
        if re.search(r"\bfinal\b", before):
            return "reduced_nullify_final_param_non_compilable"
        return "reduced_nullify_input_other_filter"
    if op == "RemoveMethod":
        if "return null" in row.get("after", ""):
            return "reduced_remove_method_untyped_fallback"
        return "reduced_remove_method_other"
    if op in SITE_LEVEL_OPERATORS:
        return "reduced_excess_at_shared_site"
    return "reduced_other"


def classify_added(row: dict) -> str:
    op = row["operator"]
    if op == "RemoveMethod" and "[" in method_signature(row.get("before", "")):
        return "added_remove_method_array_return"
    if op in SITE_LEVEL_OPERATORS:
        return "added_excess_at_shared_site"
    return "added_other"


def extract_from_mutant_file(path: Path, results_dir: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel_file = path.parent.name
    pkg = path.parent.parent.relative_to(results_dir)
    file_key = normalize_file_path(str(pkg / rel_file))
    mutant_id = path.stem

    rows = []
    for m in MUTATION_BLOCK.finditer(text):
        rows.append(
            {
                "file": file_key,
                "line": int(m.group("line")),
                "operator": m.group("operator").strip(),
                "before": norm(m.group("before")),
                "after": norm(m.group("after")),
                "mutant_id": mutant_id,
            }
        )
    return rows


def extract_results(results_dir: Path) -> list[dict]:
    rows = []
    missing_header = 0
    for java_path in sorted(results_dir.rglob("*.java")):
        if java_path.name == "original.java":
            continue
        if not java_path.parent.name.endswith(".java"):
            continue
        parsed = extract_from_mutant_file(java_path, results_dir)
        if parsed:
            rows.extend(parsed)
        else:
            missing_header += 1
    if missing_header:
        print(
            f"  Warning: {missing_header} numbered .java files had no mutation header"
        )
    return rows


def write_csv(rows: Iterable[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in CSV_FIELDS})


def paper_diff(ld_rows: list[dict], md_rows: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """
    Paper Table I counting:
      - LD-only site -> all LD rows are Reduced
      - MD-only site -> all MD rows are Added
      - Shared site -> excess LD rows Reduced, excess MD rows Added
        (pair strict matches first at shared sites)
    """
    ld_by_site: dict[tuple, list[dict]] = defaultdict(list)
    md_by_site: dict[tuple, list[dict]] = defaultdict(list)
    for r in ld_rows:
        ld_by_site[site_key(r)].append(r)
    for r in md_rows:
        md_by_site[site_key(r)].append(r)

    removed: list[dict] = []
    added: list[dict] = []
    in_both_strict = 0

    all_sites = set(ld_by_site) | set(md_by_site)

    for site in all_sites:
        ld_list = ld_by_site.get(site, [])
        md_list = md_by_site.get(site, [])

        if not md_list:
            for r in ld_list:
                r = dict(r)
                r["paper_category"] = classify_removed(r)
                removed.append(r)
            continue

        if not ld_list:
            for r in md_list:
                r = dict(r)
                r["paper_category"] = classify_added(r)
                added.append(r)
            continue

        md_remaining = list(md_list)
        ld_unmatched: list[dict] = []

        for lr in ld_list:
            sk = strict_key(lr)
            matched = None
            for i, mr in enumerate(md_remaining):
                if strict_key(mr) == sk:
                    matched = md_remaining.pop(i)
                    in_both_strict += 1
                    break
            if matched is None:
                ld_unmatched.append(lr)

        # Same site but different replacement (e.g. LD '<'->'>=' vs MD '<'->'<='):
        # we do not consider this as a reduced or added mutant
        while ld_unmatched and md_remaining:
            ld_unmatched.pop(0)
            md_remaining.pop(0)

        for lr in ld_unmatched:
            r = dict(lr)
            r["paper_category"] = classify_removed(r)
            removed.append(r)

        for mr in md_remaining:
            r = dict(mr)
            r["paper_category"] = classify_added(r)
            added.append(r)

    stats = {
        "in_both_strict": in_both_strict,
        "ld_only_sites": len(set(ld_by_site) - set(md_by_site)),
        "md_only_sites": len(set(md_by_site) - set(ld_by_site)),
    }
    return removed, added, stats


def strict_diff(ld_rows: list[dict], md_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    ld_keys = {strict_key(r) for r in ld_rows}
    md_keys = {strict_key(r) for r in md_rows}
    removed = [r for r in ld_rows if strict_key(r) not in md_keys]
    added = [r for r in md_rows if strict_key(r) not in ld_keys]
    return removed, added


def category_table(rows: list[dict], label: str) -> str:
    if not rows:
        return f"  {label}: (none)"
    counts = Counter(r.get("paper_category", "") for r in rows)
    lines = [f"  {label}:"]
    for cat, n in counts.most_common():
        lines.append(f"    {cat}: {n}")
    return "\n".join(lines)


def operator_table(rows: list[dict], label: str) -> str:
    if not rows:
        return f"  {label}: (none)"
    counts = Counter(r["operator"] for r in rows)
    lines = [f"  {label}:"]
    for op, n in counts.most_common(8):
        lines.append(f"    {op}: {n}")
    return "\n".join(lines)


def diff_csv(ld_path: Path, md_path: Path, out_dir: Path) -> None:
    with ld_path.open(encoding="utf-8") as f:
        ld_rows = list(csv.DictReader(f))
    with md_path.open(encoding="utf-8") as f:
        md_rows = list(csv.DictReader(f))

    removed, added, stats = paper_diff(ld_rows, md_rows)
    strict_removed, strict_added = strict_diff(ld_rows, md_rows)

    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(removed, out_dir / "removed_in_mediumdarwin.csv")
    write_csv(added, out_dir / "added_in_mediumdarwin.csv")
    write_csv(strict_removed, out_dir / "strict_removed.csv")
    write_csv(strict_added, out_dir / "strict_added.csv")

    n_ld, n_md = len(ld_rows), len(md_rows)
    n_reduced, n_added = len(removed), len(added)
    delta_pct = ((n_md - n_ld) / n_ld * 100) if n_ld else 0.0
    check = n_ld - n_reduced + n_added

    summary_parts = [
        "=== Paper Table I (refined mutation operators) ===",
        f"Original (LittleDarwin): {n_ld}",
        f"MediumDarwin: {n_md}",
        f"Reduced: {n_reduced}",
        f"Added: {n_added}",
        f"delta_percent: {delta_pct:.2f}",
        f"check MD = Original - Reduced + Added: {check} (should equal {n_md})",
        "",
        f"in_both_strict_match: {stats['in_both_strict']}",
        f"ld_only_sites: {stats['ld_only_sites']}",
        f"md_only_sites: {stats['md_only_sites']}",
        "",
        category_table(removed, "Reduced categories"),
        operator_table(removed, "Reduced by operator"),
        "",
        category_table(added, "Added categories"),
        operator_table(added, "Added by operator"),
        "",
        "=== Strict before/after diff (misleading for relational ops) ===",
        f"strict_removed: {len(strict_removed)}",
        f"strict_added: {len(strict_added)}",
        "  (LD uses '<'->'>='; MD uses '<'->'<=' — same site, not Reduced+Added)",
        "",
        "# Listing 1 examples:",
        "#   reduced_nullify_final_param_non_compilable -> MUT0 (final param nullify)",
        "#   added_remove_method_array_return -> MUT1 (array return RemoveMethod)",
    ]
    summary = "\n".join(summary_parts) + "\n"
    (out_dir / "summary.txt").write_text(summary, encoding="utf-8")

    print(f"Comparison written to {out_dir}")
    print(f"  Original (LD): {n_ld}")
    print(f"  MediumDarwin: {n_md}")
    print(f"  Reduced: {n_reduced}  Added: {n_added}  delta: {delta_pct:.2f}%")
    if check != n_md:
        print(f"  WARN: count check mismatch ({check} != {n_md})")
    if len(strict_removed) != n_reduced or len(strict_added) != n_added:
        print(
            f"  (strict diff would show removed={len(strict_removed)}, "
            f"added={len(strict_added)} — see strict_*.csv)"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_extract = sub.add_parser(
        "extract", help="Extract from results directory")
    p_extract.add_argument("results_dir", type=Path)
    p_extract.add_argument("-o", "--output", type=Path, required=True)

    p_diff = sub.add_parser("diff")
    p_diff.add_argument("littledarwin_csv", type=Path)
    p_diff.add_argument("mediumdarwin_csv", type=Path)
    p_diff.add_argument("-o", "--output-dir", type=Path, required=True)

    args = ap.parse_args()

    if args.cmd == "extract":
        rows = extract_results(args.results_dir.resolve())
        write_csv(rows, args.output)
        print(f"Extracted {len(rows)} mutants -> {args.output}")
    else:
        diff_csv(
            args.littledarwin_csv.resolve(),
            args.mediumdarwin_csv.resolve(),
            args.output_dir.resolve(),
        )


if __name__ == "__main__":
    main()
