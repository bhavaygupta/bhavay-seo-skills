#!/usr/bin/env python3
"""Linter for a finished content brief in Markdown.

Checks the rules from the skill's linter pass and prints every hit with its
line number. Exits 1 when anything needs fixing.

  drafted_paragraph   prose blocks that read like article copy, not instructions
  time_estimate       time or effort estimates
  unsourced_stat      numbers that look like claims, with no URL on the line
  banned_phrase       phrases from --banned (the client context file) or the defaults
  em_dash             em or en dashes used as punctuation
  placeholder         unfilled template fields such as <keyword> or TODO

Examples:
  python3 lint_brief.py "expense management software - brief.md"
  python3 lint_brief.py brief.md --banned banned_phrases.txt --max-prose-words 60
"""

from __future__ import annotations

import argparse
import re
import sys

DEFAULT_BANNED = ["delve", "in today's fast-paced", "game-changer", "game changer", "unlock the power",
                  "seamlessly", "revolutionize", "cutting-edge", "in the ever-evolving", "it's important to note"]
TIME = re.compile(r"\b(\d+(\.\d+)?\s*(-|to)?\s*\d*\s*(hours?|hrs?|days?|weeks?|minutes?|mins?)\s*(of work|to write|to complete)?)\b"
                  r"|\b(will take|should take|takes about|estimated time|effort estimate)\b", re.I)
STAT = re.compile(r"(\d[\d,.]*\s?(%|percent|x\b|times\b|million|billion))|(\$\s?\d)|(\b\d+\s+(out of|in)\s+\d+\b)", re.I)
URL = re.compile(r"https?://\S+")
PLACEHOLDER = re.compile(r"<[a-z][a-z _-]{2,40}>|\bTODO\b|\bTBD\b|\[fill[^\]]*\]", re.I)
# Sections where numbers are tool data, not claims, so they need no source URL on the line.
DATA_SECTIONS = re.compile(r"target|word count|evidence|appendix|data sources|summary|metadata", re.I)
INSTRUCTION_START = re.compile(r"^(cover|explain|show|list|compare|define|open|answer|include|use|add|link|"
                               r"write|keep|avoid|do not|don't|mention|cite|state|give|walk|end|start|close|"
                               r"lead|frame|position|name|summarize|summarise|note|tell|make|focus|mark)\b", re.I)


def lint(text: str, banned: list[str], max_prose_words: int, allow_illustrative: bool) -> list[tuple[int, str, str]]:
    hits = []
    section = ""
    in_code = False
    lines = text.splitlines()
    para: list[tuple[int, str]] = []

    def flush():
        if not para:
            return
        block = " ".join(t for _, t in para)
        words = len(block.split())
        first = para[0][1].lstrip("*_> ").strip()
        if words > max_prose_words and not INSTRUCTION_START.match(first):
            hits.append((para[0][0], "drafted_paragraph",
                         f"{words}-word prose block. Briefs carry instructions, not article copy."))
        para.clear()

    for n, raw in enumerate(lines, 1):
        line = raw.rstrip()
        if line.strip().startswith("```"):
            in_code = not in_code
            flush()
            continue
        if in_code:
            continue
        if line.startswith("#"):
            flush()
            section = line.lstrip("# ").strip()
        stripped = line.strip()
        is_prose = bool(stripped) and not re.match(r"^(#|\||[-*+]\s|\d+\.\s|>)", stripped)
        if is_prose:
            para.append((n, stripped))
        else:
            flush()

        if "\u2014" in line or re.search("\\s\u2013\\s", line):
            hits.append((n, "em_dash", "Replace the dash with a period or a comma."))
        if TIME.search(line):
            hits.append((n, "time_estimate", f"'{TIME.search(line).group(0).strip()}'. Briefs carry no time or effort estimates."))
        low = line.lower()
        for b in banned:
            if b and b.lower() in low:
                hits.append((n, "banned_phrase", f"'{b}'"))
        m = PLACEHOLDER.search(line)
        if m:
            hits.append((n, "placeholder", f"'{m.group(0)}' is unfilled."))
        if STAT.search(line) and not URL.search(line) and not DATA_SECTIONS.search(section):
            if allow_illustrative and "illustrative" in low:
                continue
            hits.append((n, "unsourced_stat", f"'{STAT.search(line).group(0).strip()}' has no source URL on the line."))
    flush()
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Lint a content brief before it goes to a writer.")
    ap.add_argument("brief", help="Markdown brief")
    ap.add_argument("--banned", help="File with one banned phrase per line, from the client context file")
    ap.add_argument("--max-prose-words", type=int, default=40,
                    help="Prose blocks longer than this that do not start with an instruction verb are flagged")
    ap.add_argument("--allow-illustrative", action="store_true",
                    help="Skip unsourced_stat on lines marked illustrative. Use for sample briefs only")
    args = ap.parse_args(argv)

    text = open(args.brief, encoding="utf-8").read()
    banned = list(DEFAULT_BANNED)
    if args.banned:
        banned += [l.strip() for l in open(args.banned, encoding="utf-8") if l.strip() and not l.startswith("#")]
    hits = lint(text, banned, args.max_prose_words, args.allow_illustrative)
    for n, kind, msg in hits:
        print(f"{args.brief}:{n}: {kind}: {msg}")
    if hits:
        print(f"\n{len(hits)} issue(s). Fix them before the brief goes out.")
        return 1
    print("Brief passes the linter.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
