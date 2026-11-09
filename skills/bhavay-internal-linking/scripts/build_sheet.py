#!/usr/bin/env python3
"""Turn match.py candidates into the final, prioritized internal linking sheet.

Writes an XLSX with openpyxl when it is installed, otherwise a CSV with the same
columns. Runs the QA checks from the skill and prints a QA report. Rows that fail
a check keep their place but get a flag, so a human sees them.

Topical rows need a drafted sentence in the "draft" column of the candidates CSV.
The anchor must be wrapped in double brackets, for example
  "Teams that automate this step usually start with [[expense approval workflows]]."

Examples:
  python3 build_sheet.py --candidates candidates.csv --out internal-links.xlsx
  python3 build_sheet.py --candidates candidates.csv --summary candidates_summary.json --batch-size 25
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter

COLUMNS = ["#", "Batch", "Status", "Source page", "Source page type", "Paragraph no.", "Find this text",
           "Replacement", "Anchor text", "Link to", "Target page title", "Target page type", "How", "Match",
           "Similarity", "Anchor used site-wide", "Flag", "Priority", "Target in-text links today",
           "Why this link", "Date done", "Notes"]
WIDTHS = {"#": 5, "Batch": 13, "Status": 9, "Source page": 42, "Source page type": 11, "Paragraph no.": 9,
          "Find this text": 60, "Replacement": 50, "Anchor text": 26, "Link to": 42, "Target page title": 34,
          "Target page type": 11, "How": 44, "Match": 9, "Similarity": 10, "Anchor used site-wide": 10,
          "Flag": 22, "Priority": 9, "Target in-text links today": 11, "Why this link": 60, "Date done": 11,
          "Notes": 24}
HOW_EXACT = 'Find the sentence, select "{a}" and link it to the target URL. Do not rewrite the sentence.'
HOW_TOPICAL = ("Add this sentence at the end of the paragraph, link the bracketed words, "
               "then delete the brackets.")
BRACKET = re.compile(r"\[\[(.+?)\]\]")


def norm(u: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", (u or "").strip().lower()).rstrip("/")


def qa(rows: list[dict]) -> list[str]:
    """Apply the skill's QA checks. Adds flags in place and returns report lines."""
    report = []
    seen = Counter((norm(r["source_url"]), norm(r["target_url"])) for r in rows)
    anchor_targets: dict[str, set] = {}
    for r in rows:
        anchor_targets.setdefault(r["anchor"].lower(), set()).add(norm(r["target_url"]))
    for r in rows:
        flags = [f.strip() for f in re.split(r"[;,]", r.get("flag", "")) if f.strip()]
        if norm(r["source_url"]) == norm(r["target_url"]):
            flags.append("self_link")
        if seen[(norm(r["source_url"]), norm(r["target_url"]))] > 1:
            flags.append("duplicate_pair")
        if r["match"] == "Exact":
            if r["anchor"].lower() not in r["find_text"].lower():
                flags.append("anchor_not_in_text")
        else:
            draft = (r.get("draft") or "").strip()
            if not draft:
                flags.append("needs_draft")
            else:
                if "needs_draft" in flags:
                    flags.remove("needs_draft")
                found = BRACKET.findall(draft)
                if len(found) != 1:
                    flags.append("bracket_count")
                elif found[0].strip().lower() != r["anchor"].strip().lower():
                    flags.append("bracket_mismatch")
                if len(draft) > 260:
                    flags.append("needs_copy_edit")
        if len(anchor_targets[r["anchor"].lower()]) > 1 and "anchor_conflict" not in flags:
            flags.append("anchor_conflict")
        r["flag"] = ", ".join(dict.fromkeys(flags))
    counts = Counter(f for r in rows for f in r["flag"].split(", ") if f)
    report.append(f"Rows {len(rows)}. Exact {sum(r['match'] == 'Exact' for r in rows)}. "
                  f"Topical {sum(r['match'] != 'Exact' for r in rows)}.")
    if counts:
        report.append("Flags " + ", ".join(f"{k} {v}" for k, v in counts.most_common()))
    else:
        report.append("No QA flags.")
    return report


def batch_name(r: dict, i: int, batch_size: int) -> str:
    if batch_size:
        return f"Batch {(i - 1) // batch_size + 1}"
    if r["match"] == "Exact" and int(float(r["priority"] or 0)) >= 60:
        return "Quick wins"
    return "Exact matches" if r["match"] == "Exact" else "Needs a sentence"


def to_sheet_rows(rows: list[dict], batch_size: int) -> list[list]:
    out = []
    for i, r in enumerate(rows, 1):
        topical = r["match"] != "Exact"
        out.append([
            i, batch_name(r, i, batch_size), "To do", r["source_url"], r["source_type"], int(r["paragraph_no"]),
            r["find_text"], (r.get("draft") or "") if topical else "", r["anchor"], r["target_url"],
            r["target_title"], r["target_type"], HOW_TOPICAL if topical else HOW_EXACT.format(a=r["anchor"]),
            r["match"], float(r["similarity"]), int(r["anchor_uses"] or 0), r["flag"],
            int(float(r["priority"] or 0)), int(r["target_inlinks"] or 0), r["why"], "", "",
        ])
    return out


def write_xlsx(path: str, rows: list[list], summary: dict, report: list[str]) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Links"
    ws.append(COLUMNS)
    head_fill = PatternFill("solid", fgColor="1F2937")
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = head_fill
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for r in rows:
        ws.append(r)
    wrap = {"Find this text", "Replacement", "How", "Why this link", "Target page title", "Flag"}
    for idx, name in enumerate(COLUMNS, 1):
        letter = get_column_letter(idx)
        ws.column_dimensions[letter].width = WIDTHS.get(name, 14)
        if name in wrap:
            for cell in ws[letter][1:]:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        if name == "Similarity":
            for cell in ws[letter][1:]:
                cell.number_format = "0.000"
    flag_fill = PatternFill("solid", fgColor="FEF3C7")
    flag_col = COLUMNS.index("Flag") + 1
    for row in ws.iter_rows(min_row=2):
        if row[flag_col - 1].value:
            row[flag_col - 1].fill = flag_fill
    ws.freeze_panes = "E2"
    ws.auto_filter.ref = ws.dimensions

    s = wb.create_sheet("Summary")
    s.append(["Item", "Value"])
    for c in s[1]:
        c.font = Font(bold=True)
    for line in report:
        s.append(["QA", line])
    for k, v in summary.items():
        if k == "unreadable_pages":
            continue
        s.append([k, json.dumps(v) if isinstance(v, (dict, list)) else v])
    for item in summary.get("unreadable_pages", []):
        s.append(["unreadable", f"{item.get('url')} status {item.get('status')} {item.get('error') or ''}".strip()])
    s.column_dimensions["A"].width = 32
    s.column_dimensions["B"].width = 100
    wb.save(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the final internal linking sheet (XLSX, CSV fallback).")
    ap.add_argument("--candidates", default="candidates.csv", help="CSV from match.py, drafts filled in")
    ap.add_argument("--summary", help="Summary JSON from match.py. Defaults to <candidates>_summary.json")
    ap.add_argument("--out", default="internal-links.xlsx", help="Output path. .xlsx or .csv")
    ap.add_argument("--batch-size", type=int, default=0,
                    help="Group rows into numbered batches of this size. Default groups by Quick wins and match type")
    ap.add_argument("--drop-flagged", action="store_true", help="Leave out rows with QA flags other than near_floor")
    args = ap.parse_args(argv)

    with open(args.candidates, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        sys.exit(f"{args.candidates} has no rows. Run match.py first or lower its --floor.")
    summary_path = args.summary or os.path.splitext(args.candidates)[0] + "_summary.json"
    summary = json.load(open(summary_path, encoding="utf-8")) if os.path.exists(summary_path) else {}

    report = qa(rows)
    if args.drop_flagged:
        keep = lambda r: all(f in ("", "near_floor") for f in r["flag"].split(", "))
        before = len(rows)
        rows = [r for r in rows if keep(r)]
        report.append(f"Dropped {before - len(rows)} flagged rows.")
    rows.sort(key=lambda r: (-int(float(r["priority"] or 0)), -float(r["similarity"] or 0)))
    sheet = to_sheet_rows(rows, args.batch_size)

    out = args.out
    if out.lower().endswith(".xlsx"):
        try:
            write_xlsx(out, sheet, summary, report)
        except ImportError:
            out = os.path.splitext(out)[0] + ".csv"
            print("openpyxl is not installed, writing CSV instead. pip install openpyxl for XLSX.", file=sys.stderr)
    if out.lower().endswith(".csv"):
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(COLUMNS)
            w.writerows(sheet)
    for line in report:
        print(line, file=sys.stderr)
    print(f"Wrote {out} with {len(sheet)} rows", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
