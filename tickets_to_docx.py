#!/usr/bin/env python3
"""
Generate DOCX files from Ticket_Data.JSON with configurable tickets per file.

What this script does:
- Reads a top-level JSON array of tickets with keys:
  ticket_id, date, subject, problem, solution, image_urls
- Groups tickets into batches (default: 50 tickets per DOCX file)
- Renders each ticket with one page per ticket in the DOCX file:
  - Subject as heading
  - "Problem" section
  - "Lösung" section
  - Images listed in image_urls embedded below "Problem" (optional)
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
     # Default: 50 tickets per DOCX file
     python tickets_to_docx.py --input Ticket_Data.JSON --verbose true
     
     # Custom: 25 tickets per DOCX file
     python tickets_to_docx.py --input Ticket_Data.JSON --tickets-per-file 25
     
     # One ticket per file (original behavior)
     python tickets_to_docx.py --input Ticket_Data.JSON --tickets-per-file 1
"""

import argparse
import io
import json
import os
import re
import sys
from typing import List, Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from PIL import Image as PILImage

# python-docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor, Emu
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT

# Lightweight helpers and fetcher (decoupled from ReportLab deps)
import requests
from urllib.parse import urljoin, urlparse, parse_qs

def xml_safe(s: Optional[str]) -> str:
    """
    Remove XML 1.0 illegal control characters (except TAB, LF, CR) that cause python-docx to fail.
    """
    if not s:
        return ""
    return re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", s)

def str2bool(v: str) -> bool:
    return str(v).lower() in {"1", "true", "t", "yes", "y"}

def sanitize_url(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Strip surrounding quotes
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
    # Cut at first whitespace
    s = s.split()[0]
    # Remove any embedded tags
    for ch in ("<", ">"):
        pos = s.find(ch)
        if pos != -1:
            s = s[:pos]
    return s or None

def resolve_url(src: str, base: Optional[str]) -> Optional[str]:
    if not src:
        return None
    src = src.strip()
    if src.startswith("http://") or src.startswith("https://"):
        return src
    if base:
        return urljoin(base.rstrip("/") + "/", src.lstrip("/"))
    return None

def extract_file_id_from_url(url_str: str) -> Optional[str]:
    """
    Extracts a numeric FileID from typical Jitbit URLs:
      - /helpdesk/File/Get/26355
      - /helpdesk/File/Get?id=26355
    Returns None if no numeric id present.
    """
    try:
        pu = urlparse(url_str)
        # Query ?id=123
        qs = parse_qs(pu.query or "")
        if "id" in qs:
            v = qs["id"][0]
            if str(v).isdigit():
                return str(v)
        # Path segment
        segs = [s for s in (pu.path or "").split("/") if s]
        if segs:
            last = segs[-1]
            if last.isdigit():
                return last
    except Exception:
        pass
    return None

def derive_api_root(api_base_url: Optional[str], env_base_url: Optional[str], verbose: bool = False) -> Optional[str]:
    """
    Derive the API root:
      If api_base_url path contains '/helpdesk' -> {scheme}://{host}/helpdesk/api
      Else -> {scheme}://{host}/api
    Falls back to env_base_url if api_base_url is missing.
    """
    base = api_base_url or env_base_url
    if not base:
        return None
    try:
        pu = urlparse(base)
        scheme = pu.scheme or "https"
        netloc = pu.netloc
        path = (pu.path or "").lower()
        if not netloc:
            return None
        if "/helpdesk" in path:
            root = f"{scheme}://{netloc}/helpdesk/api"
        else:
            root = f"{scheme}://{netloc}/api"
        if verbose:
            print(f"[INFO] API root derived: {root}", file=sys.stderr)
        return root
    except Exception:
        return None

class JitbitFetcher:
    def __init__(self, api_root: Optional[str], token: Optional[str], timeout: float = 15.0, verbose: bool = False):
        self.api_root = api_root
        self.token = token
        self.timeout = timeout
        self.verbose = verbose

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Tickets-DOCX/1.0",
            "Accept": "*/*",
        })
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def _warn(self, msg: str):
        if self.verbose:
            print(msg, file=sys.stderr)

    def fetch_attachment_by_id(self, file_id: str) -> Optional[bytes]:
        """
        Fetches an attachment by FileID trying the correct API root(s).
        Many Jitbit installs live under '/helpdesk', so we try:
          1) {scheme}://{host}/helpdesk/api/attachment?id=...
          2) {scheme}://{host}/api/attachment?id=...
        We prioritize any '/helpdesk' root if self.api_root includes it.
        """
        if not self.api_root or not self.token:
            self._warn(f"[WARN] Missing API root or token for Jitbit attachment id={file_id}")
            return None

        try:
            p = urlparse(self.api_root)
            scheme = p.scheme or "https"
            netloc = p.netloc
            path = (p.path or "").lower()
            if not netloc:
                self._warn(f"[WARN] Invalid api_root (no host): {self.api_root}")
                return None

            candidates = []
            # Prioritize '/helpdesk/api' if api_root path mentions helpdesk
            if "/helpdesk" in path:
                candidates.append(f"{scheme}://{netloc}/helpdesk/api")
            # Always try '/helpdesk/api' first for safety if not already present
            if f"{scheme}://{netloc}/helpdesk/api" not in candidates:
                candidates.append(f"{scheme}://{netloc}/helpdesk/api")
            # Then plain '/api'
            candidates.append(f"{scheme}://{netloc}/api")

            last_err: Optional[Exception] = None
            for root in candidates:
                url = f"{root.rstrip('/')}/attachment?id={file_id}"
                try:
                    self._warn(f"[INFO] GET {url}")
                    r = self.session.get(url, timeout=self.timeout)
                    r.raise_for_status()
                    return r.content
                except Exception as e:
                    last_err = e
                    self._warn(f"[INFO] Candidate failed: {e}")
                    continue

            if last_err:
                self._warn(f"[WARN] API fetch failed for id={file_id}: {last_err}")
            return None
        except Exception as e:
            self._warn(f"[WARN] API fetch failed for id={file_id}: {e}")
            return None

    def fetch_generic_image(self, url: str) -> Optional[bytes]:
        try:
            self._warn(f"[INFO] GET (external) {url}")
            r = self.session.get(url, timeout=self.timeout)
            r.raise_for_status()
            # Validate image
            with PILImage.open(io.BytesIO(r.content)) as _:
                pass
            return r.content
        except Exception as e:
            self._warn(f"[WARN] External image fetch failed for {url}: {e}")
            return None


# ---- Page setup helpers ----

A4_INCH = (8.27, 11.69)
LETTER_INCH = (8.5, 11.0)


def set_page_size_and_margins(doc: Document, page: str, margin_pt: float) -> None:
    """
    Configure the document's first section to the requested page size and margins.
    margin_pt is in points (1/72 inch).
    """
    section = doc.sections[0]

    if page.upper() == "A4":
        w_in, h_in = A4_INCH
    else:
        w_in, h_in = LETTER_INCH

    section.page_width = Inches(w_in)
    section.page_height = Inches(h_in)

    m_in = float(margin_pt) / 72.0
    section.left_margin = Inches(m_in)
    section.right_margin = Inches(m_in)
    section.top_margin = Inches(m_in)
    section.bottom_margin = Inches(m_in)


def get_usable_emu(doc: Document) -> Tuple[int, int]:
    """
    Return (usable_width_emu, usable_height_emu) for the first section.
    """
    s = doc.sections[0]
    usable_w = int(s.page_width - s.left_margin - s.right_margin)
    usable_h = int(s.page_height - s.top_margin - s.bottom_margin)
    return usable_w, usable_h


# ---- Text rendering helpers ----

_bullet_re = re.compile(r"^\s*[-\*\u2022]\s+(.*)")  # -, *, •
_ordered_re = re.compile(r"^\s*(\d+)[\.\)]\s+(.*)")  # 1. or 1)


def _iter_runs_from_markup(text: str):
    """
    Yields (segment, is_bold) by converting **bold** and <b>...</b> to runs.
    """
    if not text:
        return
    text = xml_safe(text)
    # normalize windows line breaks to avoid surprises
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Convert simple HTML bold to **bold** (handles escaped <b> too)
    text = re.sub(r"<b>(.*?)</b>", r"**\1**", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<b>(.*?)</b>", r"**\1**", text, flags=re.IGNORECASE | re.DOTALL)

    pattern = re.compile(r"\*\*(.+?)\*\*")
    pos = 0
    for m in pattern.finditer(text):
        if m.start() > pos:
            yield text[pos:m.start()], False
        yield m.group(1), True
        pos = m.end()
    if pos < len(text):
        yield text[pos:], False


def add_paragraph_with_inline_formatting(doc: Document, text: str, style: Optional[str] = None, color_rgb: Optional[RGBColor] = None):
    """
    Adds a paragraph to doc, splitting 'text' into bold/non-bold runs based on **...** or <b>...</b>.
    Returns the created paragraph.
    """
    p = doc.add_paragraph()
    if style:
        p.style = style
    for seg, is_bold in _iter_runs_from_markup(text or ""):
        run = p.add_run(seg)
        run.bold = bool(is_bold)
        if color_rgb is not None:
            run.font.color.rgb = color_rgb
    return p


def add_plain_text_block(doc: Document, text: str):
    """
    Convert plain text with paragraphs separated by blank lines.
    Supports simple unordered (-, *, •) and ordered (1., 2)) lists.
    Also supports **bold** inline.
    """
    if not (text and str(text).strip()):
        doc.add_paragraph("(Kein Inhalt)")
        return

    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    n = len(lines)

    while i < n:
        # skip blank lines
        while i < n and not lines[i].strip():
            i += 1
        if i >= n:
            break

        # detect list block
        m_b = _bullet_re.match(lines[i])
        m_o = _ordered_re.match(lines[i])
        if m_b or m_o:
            is_ordered = bool(m_o)
            style = "List Number" if is_ordered else "List Bullet"
            while i < n:
                mb = _bullet_re.match(lines[i])
                mo = _ordered_re.match(lines[i])
                if is_ordered and not mo:
                    break
                if (not is_ordered) and not mb:
                    break
                content = (mo.group(2) if mo else mb.group(1)).strip()
                p = add_paragraph_with_inline_formatting(doc, content)
                p.style = style
                i += 1
            continue

        # otherwise accumulate a paragraph until blank or next list
        para_lines: List[str] = []
        while i < n:
            if not lines[i].strip():
                i += 1
                break
            if _bullet_re.match(lines[i]) or _ordered_re.match(lines[i]):
                break
            para_lines.append(lines[i].strip())
            i += 1

        paragraph_text = " ".join(para_lines).strip()
        if paragraph_text:
            add_paragraph_with_inline_formatting(doc, paragraph_text)


# ---- Image helpers ----

def _bytes_to_image_dims_emu(img_bytes: bytes) -> Optional[Tuple[int, int]]:
    """
    Returns (width_emu, height_emu) using image DPI metadata if available, else assumes 96 DPI.
    """
    try:
        with PILImage.open(io.BytesIO(img_bytes)) as im:
            w_px, h_px = im.width, im.height
            dpi = im.info.get("dpi", (96, 96))
            dpi_x = float(dpi[0] or 96.0)
            dpi_y = float(dpi[1] or 96.0)
            w_in = w_px / dpi_x
            h_in = h_px / dpi_y
            return int(Emu(Inches(w_in))), int(Emu(Inches(h_in)))
    except Exception:
        return None


def add_image_placeholder_docx(doc: Document, url: str, auth_hint: bool = False, label: Optional[str] = None):
    safe_url = xml_safe(str(url or "").strip())
    label_text = f"{label} – " if label else ""
    hint_text = " (evtl. Anmeldung/Cookies erforderlich)" if auth_hint else ""
    p = doc.add_paragraph()
    run = p.add_run(xml_safe(f"{label_text}Bild konnte nicht geladen werden: {safe_url}{hint_text}"))
    run.font.color.rgb = RGBColor(0x80, 0x80, 0x80)


def add_ticket_images_docx(
    doc: Document,
    image_urls: List[str],
    kb_base_url: Optional[str],
    fetcher: JitbitFetcher,
    max_width_emu: int,
    max_height_emu: int,
    add_placeholders: bool,
) -> None:
    if not image_urls:
        return

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
            if abs_url.startswith("http://") or abs_url.startswith("https://"):
                data = fetcher.fetch_generic_image(abs_url)

        if not data:
            if add_placeholders:
                add_image_placeholder_docx(doc, abs_url, auth_hint=bool(fid))
            continue

        dims = _bytes_to_image_dims_emu(data)
        if not dims:
            if add_placeholders:
                add_image_placeholder_docx(doc, abs_url, auth_hint=bool(fid))
            continue

        w_emu, h_emu = dims
        if w_emu <= 0 or h_emu <= 0:
            if add_placeholders:
                add_image_placeholder_docx(doc, abs_url, auth_hint=bool(fid))
            continue

        scale = min(max_width_emu / w_emu, max_height_emu / h_emu, 1.0)
        target_w = int(w_emu * scale)
        # python-docx scales height proportionally when width is provided
        bio = io.BytesIO(data)
        try:
            doc.add_picture(bio, width=Emu(target_w))
        except Exception:
            if add_placeholders:
                add_image_placeholder_docx(doc, abs_url, auth_hint=bool(fid))
            continue


# ---- Ticket rendering ----

def build_doc_for_tickets(
    doc: Document,
    tickets_subset: List[dict],
    env_base: Optional[str],
    fetcher: JitbitFetcher,
    include_images: bool,
    add_placeholders: bool,
) -> None:
    usable_w_emu, usable_h_emu = get_usable_emu(doc)

    for t in tickets_subset:
        subject = (t.get("subject") or "").strip() or "(Ohne Betreff)"
        problem = (t.get("problem") or "").rstrip()
        solution = (t.get("solution") or "").rstrip()
        image_urls = t.get("image_urls") or []

        # Header
        title_p = doc.add_paragraph(xml_safe(subject))
        title_p.style = "Heading 1"

        # Meta line
        meta_parts = []
        if t.get("ticket_id") is not None:
            meta_parts.append(f"Ticket-ID: {t['ticket_id']}")
        if t.get("date"):
            meta_parts.append(str(t["date"]))
        if meta_parts:
            p = add_paragraph_with_inline_formatting(doc, " • ".join(meta_parts))
            for run in p.runs:
                run.font.color.rgb = RGBColor(0x80, 0x80, 0x80)
        else:
            doc.add_paragraph()  # spacer

        # Problem section
        h = doc.add_paragraph("Problem")
        h.style = "Heading 2"
        add_plain_text_block(doc, problem)

        # Images (after Problem)
        if include_images:
            add_ticket_images_docx(
                doc=doc,
                image_urls=image_urls,
                kb_base_url=env_base,
                fetcher=fetcher,
                max_width_emu=usable_w_emu,
                max_height_emu=usable_h_emu,
                add_placeholders=add_placeholders,
            )

        # Solution section
        doc.add_paragraph()  # small spacer
        h2 = doc.add_paragraph("Lösung")
        h2.style = "Heading 2"
        add_plain_text_block(doc, solution)


# ---- CLI ----

def main():
    parser = argparse.ArgumentParser(description="Generate DOCX files with configurable number of tickets per file (API-first image fetching).")
    parser.add_argument("--input", "-i", default="Ticket_Data.JSON", help="Path to JSON file with an array of tickets")
    parser.add_argument("--output-dir", "-o", default="documents", help="Output directory for DOCX files")
    parser.add_argument("--tickets-per-file", "-t", type=int, default=50, help="Number of tickets to combine into one DOCX file (default: 50)")
    parser.add_argument("--page-size", choices=["A4", "LETTER"], default="A4", help="Page size")
    parser.add_argument("--margin", type=float, default=36.0, help="Margins in points (default ~0.5 inch)")
    parser.add_argument("--include-images", type=str2bool, default=True, help="Include images from image_urls[]")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout seconds for API/generic image downloads")
    parser.add_argument("--image-placeholder", type=str2bool, default=True, help="Insert a textual placeholder when image download fails")
    parser.add_argument("--verbose", type=str2bool, default=False, help="Enable verbose logging")
    parser.add_argument("--base-url", default=None, help="Base URL to resolve relative links and derive API root (overrides JITBIT_BASE_URL)")
    parser.add_argument("--token", default=None, help="Bearer token for Jitbit API (overrides JITBIT_API_TOKEN)")
    args = parser.parse_args()

    # Load JSON (top-level array)
    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
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

    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)

    # Validate tickets_per_file parameter
    if args.tickets_per_file < 1:
        print("[ERROR] --tickets-per-file must be at least 1", file=sys.stderr)
        sys.exit(1)

    # Process tickets in batches
    total_tickets = len(tickets)
    if total_tickets == 0:
        print("[INFO] No tickets found in input file.")
        return

    batch_count = 0
    generated_files = 0

    for i in range(0, total_tickets, args.tickets_per_file):
        batch_count += 1
        ticket_batch = tickets[i:i + args.tickets_per_file]
        
        # Create filename for this batch
        start_idx = i + 1
        end_idx = min(i + args.tickets_per_file, total_tickets)
        
        if args.tickets_per_file == 1:
            # Special case: one ticket per file, use original naming pattern
            ticket = ticket_batch[0]
            ticket_id = ticket.get("ticket_id", "unknown")
            subject = ticket.get("subject", "No Subject").strip()
            safe_subject = re.sub(r'[<>:"/\\|?*]', '_', subject)[:50]
            filename = f"ticket_{ticket_id}_{safe_subject}.docx"
        else:
            # Multiple tickets per file
            filename = f"tickets_{start_idx:04d}-{end_idx:04d}_batch_{batch_count:03d}.docx"
        
        out_file = os.path.join(args.output_dir, filename)

        # Create a new document for this batch
        doc = Document()
        set_page_size_and_margins(doc, args.page_size, args.margin)

        # Build document with this batch of tickets
        build_doc_for_tickets(
            doc=doc,
            tickets_subset=ticket_batch,
            env_base=env_base,
            fetcher=fetcher,
            include_images=args.include_images,
            add_placeholders=args.image_placeholder,
        )
        
        doc.save(out_file)
        generated_files += 1
        print(f"[OK] DOCX generated: {out_file} (tickets {start_idx}-{end_idx}, {len(ticket_batch)} tickets)")

    if args.tickets_per_file == 1:
        print(f"[INFO] Generated {generated_files} separate DOCX files in {args.output_dir}/")
    else:
        print(f"[INFO] Generated {generated_files} DOCX files containing {total_tickets} tickets ({args.tickets_per_file} tickets per file) in {args.output_dir}/")


if __name__ == "__main__":
    main()
