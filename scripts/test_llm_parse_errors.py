#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from pathlib import Path
import sys

# Import the updated parser from the project
import process_tickets_with_llm as m

ERR_DIR = Path("llm_parse_errors")
OUT = Path("parse_results.json")


def extract_raw_block(text: str) -> str:
    start_tag = "=== LLM raw output ==="
    end_tag = "=== User prompt"
    s = text.find(start_tag)
    if s == -1:
        return text
    s += len(start_tag)
    e = text.find(end_tag, s)
    block = text[s:e].strip() if e != -1 else text[s:].strip()
    return block


def main() -> int:
    if not ERR_DIR.exists():
        print(f"No directory found: {ERR_DIR}")
        return 1

    results = []
    ok = 0
    fail = 0

    for p in sorted(ERR_DIR.glob("*.txt")):
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception as e:
            item = {"file": p.name, "status": "READ_ERROR", "error": str(e)}
            results.append(item)
            print(f"[READ_ERROR] {p.name}: {e}")
            fail += 1
            continue

        raw = extract_raw_block(txt)
        parsed = m.parse_and_validate_llm_json(raw)
        if parsed is not None:
            # Compact preview for console
            preview = {
                k: (v[:120] + "…" if isinstance(v, str) and len(v) > 120 else v)
                for k, v in parsed.items()
            }
            item = {"file": p.name, "status": "OK", "parsed": preview}
            results.append(item)
            ok += 1
            print(f"[OK] {p.name}: {json.dumps(preview, ensure_ascii=False)}")
        else:
            item = {"file": p.name, "status": "FAIL"}
            results.append(item)
            fail += 1
            print(f"[FAIL] {p.name}")

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT} with {len(results)} entries. OK={ok}, FAIL={fail}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
