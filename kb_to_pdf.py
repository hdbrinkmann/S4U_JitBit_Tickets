#!/usr/bin/env python3
"""
Generate a single PDF from a Jitbit Knowledgebase JSON export
with a minimal, API-first approach for loading images.

What this script does:
- Renders one article per page with subject + metadata
- Converts Body HTML into simple paragraphs/lists/pre/tables/images
- Loads all Jitbit images/attachments via the official API:
    GET {base}/helpdesk/api/attachment?id={FileID}
  using a Bearer token from the environment (.env: JITBIT_API_TOKEN=...)

- External images (e.g., imgur, teams CDN) are fetched directly without cookies
- No cookie/header hacks, no Referer fallbacks

Usage:
  1) Ensure .env contains:
       JITBIT_API_TOKEN=...
       (optional) JITBIT_BASE_URL=https://support.example.com
     Note: If JITBIT_BASE_URL is not set, the script derives the API base
     from export_info.api_base_url in the JSON.

  2) Run:
     python kb_to_pdf.py --input JitBit_Knowledgebase.json --output Knowledgebase.pdf --verbose true
"""

import argparse
import io
import json
import os
import sys
from typing import Dict, List, Optional, Tuple, Set
from urllib.parse import urljoin, urlparse, parse_qs

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from PIL import Image as PILImage

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image as RLImage,
    PageBreak,
    Table,
    TableStyle,
    ListFlowable,
    ListItem,
    Preformatted,
)


def str2bool(v: str) -> bool:
    return str(v).lower() in {"1", "true", "t", "yes", "y"}


def escape_html(s: str) -> str:
    import html as html_lib
    return html_lib.escape(str(s), quote=True)


def truncate_text(s: str, max_len: int = 300) -> str:
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


def build_styles():
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "KBTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        spaceAfter=6,
        alignment=TA_LEFT,
    )
    subheader_style = ParagraphStyle(
        "KBSubheader",
        parent=styles["Normal"],
        fontSize=11,
        leading=14,
        textColor=colors.grey,
        spaceAfter=10,
    )
    body_style = ParagraphStyle(
        "KBBody",
        parent=styles["Normal"],
        fontSize=10.5,
        leading=14,
        spaceAfter=6,
    )
    pre_style = ParagraphStyle(
        "KBPre",
        parent=styles["Code"] if "Code" in styles else styles["Normal"],
        fontName="Courier",
        fontSize=9,
        leading=12,
        backColor=colors.whitesmoke,
        spaceBefore=6,
        spaceAfter=6,
    )
    table_cell_style = ParagraphStyle(
        "KBTableCell",
        parent=styles["Normal"],
        fontSize=10,
        leading=12,
        spaceAfter=0,
    )

    return {
        "title": title_style,
        "subheader": subheader_style,
        "body": body_style,
        "pre": pre_style,
        "table_cell": table_cell_style,
    }


def make_rl_image(img_bytes: bytes, max_width: float, max_height: float) -> Optional[RLImage]:
    try:
        with PILImage.open(io.BytesIO(img_bytes)) as im:
            w_px, h_px = im.width, im.height
    except Exception:
        return None
    if w_px <= 0 or h_px <= 0:
        return None
    w_pt, h_pt = float(w_px), float(h_px)
    scale = min(max_width / w_pt, max_height / h_pt, 1.0)
    bio = io.BytesIO(img_bytes)
    return RLImage(bio, width=w_pt * scale, height=h_pt * scale)


def add_image_placeholder(fl: List, url: str, styles, add_placeholder: bool, label: Optional[str] = None, auth_hint: bool = False):
    if not add_placeholder:
        return
    safe_href = escape_html(url)
    display_text = truncate_text(safe_href, 300)
    label_text = f"{escape_html(label)} – " if label else ""
    hint_text = " (evtl. Anmeldung/Cookies erforderlich)" if auth_hint else ""
    fl.append(Paragraph(f"{label_text}Bild konnte nicht geladen werden: <a href=\"{safe_href}\">{display_text}</a>{hint_text}", styles["body"]))
    fl.append(Spacer(1, 6))


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
        segs = [s for s in pu.path.split("/") if s]
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


def build_stylesheet():
    return build_styles()


class JitbitFetcher:
    def __init__(self, api_root: Optional[str], token: Optional[str], timeout: float = 15.0, verbose: bool = False):
        self.api_root = api_root
        self.token = token
        self.timeout = timeout
        self.verbose = verbose

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "KB-PDF/1.0",
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


def html_to_flowables(
    html: str,
    styles,
    kb_base_url: Optional[str],
    api_root: Optional[str],
    fetcher: JitbitFetcher,
    include_images: bool,
    max_width: float,
    max_height: float,
    add_placeholders: bool,
) -> List:
    fl: List = []
    if not html:
        return fl

    soup = BeautifulSoup(html, "html.parser")

    def add_image_from_src(src: str):
        if not include_images:
            return
        clean = sanitize_url(src)
        if not clean:
            return
        # Resolve absolute URL for external fetch, but also attempt Jitbit ID first
        abs_url = resolve_url(clean, kb_base_url)
        # Try to extract a Jitbit FileID
        fid = extract_file_id_from_url(abs_url or clean)
        data = None
        if fid:
            data = fetcher.fetch_attachment_by_id(fid)
        # Fallback to generic external download if not a Jitbit file or API fails
        if not data:
            if abs_url and (abs_url.startswith("http://") or abs_url.startswith("https://")):
                data = fetcher.fetch_generic_image(abs_url)

        if not data:
            add_image_placeholder(fl, abs_url or clean, styles, add_placeholders, auth_hint=bool(fid))
            return
        rlimg = make_rl_image(data, max_width=max_width, max_height=max_height)
        if rlimg:
            fl.append(rlimg)
            fl.append(Spacer(1, 6))
        else:
            add_image_placeholder(fl, abs_url or clean, styles, add_placeholders, auth_hint=bool(fid))

    def extract_text_simple(tag: Tag) -> str:
        return tag.get_text(separator=" ", strip=True)

    def build_table_flowable(table_tag: Tag) -> Optional[Table]:
        rows: List[List[str]] = []
        for tr in table_tag.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            row = [extract_text_simple(c) for c in cells]
            if any(cell for cell in row):
                rows.append(row)
        if not rows:
            return None
        tbl = Table(rows, hAlign="LEFT")
        tbl.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0")),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        return tbl

    def process_block(node):
        if isinstance(node, NavigableString):
            text = str(node).strip()
            if text:
                fl.append(Paragraph(text, styles["body"]))
            return
        if not isinstance(node, Tag):
            return

        name = node.name.lower()

        if name in ("p", "div"):
            # Render text first, then images inside
            node_text_only = BeautifulSoup(str(node), "html.parser")
            for it in node_text_only.find_all("img"):
                it.decompose()
            text = node_text_only.get_text(separator=" ", strip=True)
            if text:
                fl.append(Paragraph(text, styles["body"]))
            if include_images:
                for img in node.find_all("img"):
                    src = img.get("src")
                    if src:
                        add_image_from_src(src)

        elif name == "br":
            fl.append(Spacer(1, 6))

        elif name in ("ul", "ol"):
            items = []
            for li in node.find_all("li", recursive=False):
                txt = li.get_text(separator=" ", strip=True)
                if txt:
                    items.append(ListItem(Paragraph(txt, styles["body"])))
            if items:
                bulletType = "1" if name == "ol" else "bullet"
                fl.append(Spacer(1, 4))
                fl.append(ListFlowable(items, bulletType=bulletType, start="1", leftIndent=12))
                fl.append(Spacer(1, 4))

        elif name in ("pre", "code"):
            txt = node.get_text("\n")
            if txt:
                fl.append(Preformatted(txt, styles["pre"]))

        elif name == "table":
            t = build_table_flowable(node)
            if t:
                fl.append(Spacer(1, 6))
                fl.append(t)
                fl.append(Spacer(1, 6))

        elif name == "img":
            src = node.get("src")
            if src:
                add_image_from_src(src)

        else:
            for child in node.children:
                process_block(child)

    for child in soup.contents:
        process_block(child)

    return fl


def add_attachments_images(
    attachments: List[dict],
    kb_base_url: Optional[str],
    fetcher: JitbitFetcher,
    max_width: float,
    max_height: float,
    add_placeholders: bool,
    styles=None,
) -> List:
    fl: List = []
    if not attachments:
        return fl

    seen: Set[str] = set()

    for att in attachments:
        url = (att.get("Url") or att.get("URL") or "").strip()
        if not url:
            continue
        abs_url = resolve_url(url, kb_base_url) or url
        if abs_url in seen:
            continue
        seen.add(abs_url)

        fid = extract_file_id_from_url(abs_url)
        data = None
        if fid:
            data = fetcher.fetch_attachment_by_id(fid)
        else:
            # External attachment link (non-Jitbit) - try generic image download
            # Note: only images will render inline; non-images will show placeholder link
            data = fetcher.fetch_generic_image(abs_url)

        if not data:
            add_image_placeholder(fl, abs_url, styles, add_placeholders, label=att.get("FileName") or None, auth_hint=bool(fid))
            continue

        img = make_rl_image(data, max_width=max_width, max_height=max_height)
        if img:
            fl.append(img)
            fl.append(Spacer(1, 6))
        else:
            add_image_placeholder(fl, abs_url, styles, add_placeholders, label=att.get("FileName") or None, auth_hint=bool(fid))

    return fl


def main():
    parser = argparse.ArgumentParser(description="Generate a PDF from Jitbit Knowledgebase JSON (API-first image fetching).")
    parser.add_argument("--input", "-i", default="JitBit_Knowledgebase.json", help="Path to JSON export file")
    parser.add_argument("--output", "-o", default="Knowledgebase.pdf", help="Output PDF filename")
    parser.add_argument("--page-size", choices=["A4", "LETTER"], default="A4", help="Page size")
    parser.add_argument("--margin", type=float, default=36.0, help="Margins in points (default ~0.5 inch)")
    parser.add_argument("--include-body-images", type=str2bool, default=True, help="Include images from Body HTML")
    parser.add_argument("--include-attachments", type=str2bool, default=True, help="Include images from Attachments")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout seconds for API/generic image downloads")
    parser.add_argument("--image-placeholder", type=str2bool, default=True, help="Insert a textual placeholder with link when image download fails")
    parser.add_argument("--attachments-header", type=str2bool, default=False, help="Insert a small heading before the attachments section")
    parser.add_argument("--verbose", type=str2bool, default=False, help="Enable verbose logging")
    args = parser.parse_args()

    pagesize = A4 if args.page_size.upper() == "A4" else LETTER

    # Load JSON
    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    export_info = data.get("export_info", {}) or {}
    kb_base_url = export_info.get("api_base_url") or os.getenv("JITBIT_BASE_URL", "")
    kb_base_url = kb_base_url.strip() or None

    api_root = derive_api_root(export_info.get("api_base_url"), os.getenv("JITBIT_BASE_URL", "").strip() or None, verbose=args.verbose)
    token = (os.getenv("JITBIT_API_TOKEN", "") or "").strip()

    if not token:
        print("[WARN] JITBIT_API_TOKEN not set in environment/.env. Jitbit-protected images will not load.", file=sys.stderr)

    fetcher = JitbitFetcher(api_root=api_root, token=token, timeout=args.timeout, verbose=args.verbose)

    # Articles
    articles = data.get("articles", [])
    if not isinstance(articles, list) or not articles:
        print("[INFO] No articles found in input JSON.")
        articles = []

    # Build document
    doc = SimpleDocTemplate(
        args.output,
        pagesize=pagesize,
        leftMargin=args.margin,
        rightMargin=args.margin,
        topMargin=args.margin,
        bottomMargin=args.margin,
        title="Knowledgebase Export",
        author="Jitbit Export (API-first)",
    )
    usable_width = doc.width
    usable_height = doc.height

    styles = build_stylesheet()
    flow: List = []

    for idx, art in enumerate(articles, start=1):
        subject = (art.get("Subject") or "").strip() or "(Ohne Betreff)"
        category = (art.get("CategoryName") or "").strip()
        tagstring = (art.get("TagString") or "").strip()

        # Header
        flow.append(Paragraph(subject, styles["title"]))

        # Subheader
        sub_parts = []
        if category:
            sub_parts.append(f"Category: {category}")
        if tagstring:
            sub_parts.append(f"Tags: {tagstring}")
        sub_text = " • ".join(sub_parts) if sub_parts else ""
        if sub_text:
            flow.append(Paragraph(sub_text, styles["subheader"]))
        else:
            flow.append(Spacer(1, 6))

        # Body (API-first image fetching for Jitbit, generic for external)
        body_html = art.get("Body") or art.get("BodyMarkdown") or ""
        body_fl = html_to_flowables(
            body_html,
            styles=styles,
            kb_base_url=kb_base_url,
            api_root=api_root,
            fetcher=fetcher,
            include_images=args.include_body_images,
            max_width=usable_width,
            max_height=usable_height,
            add_placeholders=args.image_placeholder,
        )
        if body_fl:
            flow.extend(body_fl)
        else:
            flow.append(Paragraph("(Kein Inhalt)", styles["body"]))

        # Attachments images
        if args.include_attachments:
            att = art.get("Attachments") or []
            att_fl = add_attachments_images(
                attachments=att,
                kb_base_url=kb_base_url,
                fetcher=fetcher,
                max_width=usable_width,
                max_height=usable_height,
                add_placeholders=args.image_placeholder,
                styles=styles,
            )
            if att_fl:
                if args.attachments_header:
                    flow.append(Paragraph("Anhänge", styles["subheader"]))
                flow.append(Spacer(1, 6))
                flow.extend(att_fl)

        # Page break
        if idx != len(articles):
            flow.append(PageBreak())

    doc.build(flow)
    print(f"[OK] PDF generated: {args.output}")


if __name__ == "__main__":
    main()
