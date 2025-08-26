#!/usr/bin/env python3
"""
Generate a PDF from Ticket_Data.JSON with one page per ticket.

What this script does:
- Reads a top-level JSON array of tickets with keys:
  ticket_id, date, subject, problem, solution, image_urls
- Renders one ticket per page:
  - Subject as title
  - "Problem" section
  - "Solution" section
  - Images listed in image_urls embedded below text
- For Jitbit-protected images, uses API-first fetching with Bearer token:
    GET {base}/helpdesk/api/attachment?id={FileID}
  falling back to {base}/api/attachment?id=...
  where {base} is derived from JITBIT_BASE_URL or provided args

Usage:
  1) Ensure .env contains:
       JITBIT_API_TOKEN=...     (Bearer token for Jitbit API)
       JITBIT_BASE_URL=https://support.example.com/helpdesk
     Note: Ticket_Data.JSON usually doesn't contain export_info.api_base_url,
           so we rely on JITBIT_BASE_URL to derive the API root.

  2) Run:
     python tickets_to_pdf.py --input Ticket_Data.JSON --output Ticket_Data.PDF --verbose true
"""

import argparse
import io
import json
import os
import re
import sys
from typing import List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Reuse helpers from kb_to_pdf.py for consistent behavior
from kb_to_pdf import (  # type: ignore
    build_stylesheet,
    make_rl_image,
    sanitize_url,
    resolve_url,
    extract_file_id_from_url,
    derive_api_root,
    JitbitFetcher,
    add_image_placeholder,
    str2bool,
)

from reportlab.lib.pagesizes import A4, LETTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image as RLImage,
    PageBreak,
    ListFlowable,
    ListItem,
    KeepInFrame,
)
from reportlab.lib import colors


def escape_text_preserve_simple_markup(s: str) -> str:
    """
    Escape text for ReportLab Paragraph while preserving simple <b>...</b> tags.
    """
    # Temporarily protect bold tags to avoid escaping them
    s = s.replace("<b>", "___B_OPEN___").replace("</b>", "___B_CLOSE___")
    # Escape XML special characters
    s = (s.replace("&", "&")
           .replace("<", "<")
           .replace(">", ">"))
    # Restore allowed tags
    s = s.replace("___B_OPEN___", "<b>").replace("___B_CLOSE___", "</b>")
    return s


def apply_inline_bold(text: str) -> str:
    """
    Convert **bold** to <b>bold</b> (compatible with ReportLab's mini-HTML).
    Non-greedy, does not span newlines.
    """
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def plain_text_to_flowables(text: str, styles, add_space_before: bool = False) -> List:
    """
    Convert plain text (with optional **bold** and simple lists) into ReportLab flowables.
    Supported lists:
      - Unordered: lines starting with '-', '*', or '•'
      - Ordered: lines starting with '1. ', '2) ', etc.
    Paragraphs are separated by blank lines.
    """
    fl: List = []
    if not (text and text.strip()):
        fl.append(Paragraph("(Kein Inhalt)", styles["body"]))
        return fl

    if add_space_before:
        fl.append(Spacer(1, 6))

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0

    bullet_re = re.compile(r"^\s*[-\*\u2022]\s+(.*)")  # -, *, •
    ordered_re = re.compile(r"^\s*(\d+)[\.\)]\s+(.*)")  # 1. or 1)

    def make_paragraph(txt: str):
        # Apply **bold** then escape while preserving <b> tags
        txt = apply_inline_bold(txt)
        txt = escape_text_preserve_simple_markup(txt)
        return Paragraph(txt, styles["body"])

    while i < len(lines):
        # Skip leading blank lines
        if not lines[i].strip():
            i += 1
            continue

        # Detect list block
        m_b = bullet_re.match(lines[i])
        m_o = ordered_re.match(lines[i])

        if m_b or m_o:
            items: List = []
            is_ordered = bool(m_o)

            while i < len(lines):
                if is_ordered:
                    m = ordered_re.match(lines[i])
                    if not m:
                        break
                    content = m.group(2)
                else:
                    m = bullet_re.match(lines[i])
                    if not m:
                        break
                    content = m.group(1)

                items.append(ListItem(make_paragraph(content)))
                i += 1

            if items:
                fl.append(Spacer(1, 4))
                fl.append(ListFlowable(
                    items,
                    bulletType="1" if is_ordered else "bullet",
                    start="1",
                    leftIndent=12,
                ))
                fl.append(Spacer(1, 4))
            continue

        # Otherwise accumulate a paragraph until blank line or next list
        para_lines = []
        while i < len(lines):
            if not lines[i].strip():
                i += 1
                break
            if bullet_re.match(lines[i]) or ordered_re.match(lines[i]):
                break
            para_lines.append(lines[i].strip())
            i += 1

        paragraph_text = " ".join(para_lines).strip()
        if paragraph_text:
            fl.append(make_paragraph(paragraph_text))

    return fl


def add_ticket_images(
    image_urls: List[str],
    kb_base_url: Optional[str],
    fetcher: JitbitFetcher,
    max_width: float,
    max_height: float,
    add_placeholders: bool,
    styles=None,
) -> List:
    fl: List = []
    if not image_urls:
        return fl

    for raw in image_urls:
        if not raw:
            continue
        clean = sanitize_url(raw)
        if not clean:
            continue
        abs_url = resolve_url(clean, kb_base_url) or clean

        data = None
        fid = extract_file_id_from_url(abs_url)
        if fid:
            data = fetcher.fetch_attachment_by_id(fid)
        if not data:
            # Try generic fetch for external or fallback
            if abs_url.startswith("http://") or abs_url.startswith("https://"):
                data = fetcher.fetch_generic_image(abs_url)

        if not data:
            add_image_placeholder(fl, abs_url, styles, add_placeholders, auth_hint=bool(fid))
            continue

        img: Optional[RLImage] = make_rl_image(data, max_width=max_width, max_height=max_height)
        if img:
            # Wrap in KeepInFrame to avoid LayoutError when near page bottom; shrink if needed
            kif = KeepInFrame(max_width, max_height, [img], mode="shrink")
            fl.append(kif)
            fl.append(Spacer(1, 6))
        else:
            add_image_placeholder(fl, abs_url, styles, add_placeholders, auth_hint=bool(fid))

    return fl


def build_flow_for_tickets(tickets_subset: List[dict], styles, usable_width: float, usable_height: float, env_base: Optional[str], fetcher: JitbitFetcher, args) -> List:
    flow: List = []
    for idx, t in enumerate(tickets_subset, start=1):
        subject = (t.get("subject") or "").strip() or "(Ohne Betreff)"
        problem = (t.get("problem") or "").rstrip()
        solution = (t.get("solution") or "").rstrip()
        image_urls = t.get("image_urls") or []

        # Header
        flow.append(Paragraph(subject, styles["title"]))
        meta_parts = []
        if t.get("ticket_id") is not None:
            meta_parts.append(f"Ticket-ID: {t['ticket_id']}")
        if t.get("date"):
            meta_parts.append(str(t["date"]))
        if meta_parts:
            flow.append(Paragraph(" • ".join(meta_parts), styles["subheader"]))
        else:
            flow.append(Spacer(1, 6))

        # Problem section
        flow.append(Paragraph("Problem", styles["subheader"]))
        flow.extend(plain_text_to_flowables(problem, styles))

        # Images (after Problem)
        if args.include_images:
            img_fl = add_ticket_images(
                image_urls=image_urls,
                kb_base_url=env_base,
                fetcher=fetcher,
                max_width=usable_width,
                max_height=usable_height,
                add_placeholders=args.image_placeholder,
                styles=styles,
            )
            if img_fl:
                flow.append(Spacer(1, 6))
                flow.extend(img_fl)

        # Solution section
        flow.append(Spacer(1, 6))
        flow.append(Paragraph("Lösung", styles["subheader"]))
        flow.extend(plain_text_to_flowables(solution, styles))

        # Page break between tickets within this subset
        if idx != len(tickets_subset):
            flow.append(PageBreak())
    return flow

def main():
    parser = argparse.ArgumentParser(description="Generate a PDF from ticket JSON (API-first image fetching).")
    parser.add_argument("--input", "-i", default="Ticket_Data.JSON", help="Path to JSON file with an array of tickets")
    parser.add_argument("--output", "-o", default="Ticket_Data.PDF", help="Output PDF filename")
    parser.add_argument("--page-size", choices=["A4", "LETTER"], default="A4", help="Page size")
    parser.add_argument("--margin", type=float, default=36.0, help="Margins in points (default ~0.5 inch)")
    parser.add_argument("--include-images", type=str2bool, default=True, help="Include images from image_urls[]")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout seconds for API/generic image downloads")
    parser.add_argument("--image-placeholder", type=str2bool, default=True, help="Insert a textual placeholder with link when image download fails")
    parser.add_argument("--verbose", type=str2bool, default=False, help="Enable verbose logging")
    parser.add_argument("--base-url", default=None, help="Base URL to resolve relative links and derive API root (overrides JITBIT_BASE_URL)")
    parser.add_argument("--token", default=None, help="Bearer token for Jitbit API (overrides JITBIT_API_TOKEN)")
    parser.add_argument("--chunk-size", type=int, default=50, help="Max number of tickets per PDF chunk (default 50). Use 0 or negative to disable chunking.")
    args = parser.parse_args()

    pagesize = A4 if args.page_size.upper() == "A4" else LETTER

    # Load JSON (top-level array)
    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        # Some exports might wrap tickets in a key
        tickets = data.get("tickets") or data.get("data") or []
        if not isinstance(tickets, list):
            print("[WARN] Input JSON is an object but no 'tickets' array found. Expecting a top-level array.", file=sys.stderr)
            tickets = []
    elif isinstance(data, list):
        tickets = data
    else:
        print("[WARN] Input JSON not an array.", file=sys.stderr)
        tickets = []

    env_base = (args.base_url or os.getenv("JITBIT_BASE_URL", "") or "").strip() or None
    api_root = derive_api_root(None, env_base, verbose=args.verbose)
    token = (args.token or os.getenv("JITBIT_API_TOKEN", "") or "").strip()

    if not env_base:
        print("[WARN] JITBIT_BASE_URL not set in environment/.env. Relative Jitbit links cannot be resolved.", file=sys.stderr)
    if not token:
        print("[WARN] JITBIT_API_TOKEN not set in environment/.env. Jitbit-protected images will not load.", file=sys.stderr)

    fetcher = JitbitFetcher(api_root=api_root, token=token, timeout=args.timeout, verbose=args.verbose)

    # Build document(s) with chunking
    styles = build_stylesheet()

    # Determine chunks
    chunk_size = int(args.chunk_size) if isinstance(args.chunk_size, int) else 0
    if chunk_size <= 0 or not tickets:
        chunks = [tickets]
    else:
        chunks = [tickets[i:i + chunk_size] for i in range(0, len(tickets), chunk_size)]

    root, ext = os.path.splitext(args.output)
    if not ext:
        ext = ".pdf"

    for ci, subset in enumerate(chunks, start=1):
        if len(chunks) == 1:
            out_file = args.output
        else:
            out_file = f"{root}_{ci:03d}{ext}"

        doc = SimpleDocTemplate(
            out_file,
            pagesize=pagesize,
            leftMargin=args.margin,
            rightMargin=args.margin,
            topMargin=args.margin,
            bottomMargin=args.margin,
            title="Ticket Export",
            author="Jitbit Tickets (API-first)",
        )
        usable_width = doc.width
        usable_height = doc.height

        flow = build_flow_for_tickets(subset, styles, usable_width, usable_height, env_base, fetcher, args)
        doc.build(flow)
        print(f"[OK] PDF generated: {out_file}")


if __name__ == "__main__":
    main()
