#!/usr/bin/env python3
import os
import sys
import argparse
import requests
from urllib.parse import urlparse
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from PIL import Image as PILImage
except Exception:
    PILImage = None


def build_urls(base: str, fid: str):
    base = base.rstrip("/")
    # Try helpdesk/api first (most common for sub-path installations), then /api
    return [
        f"{base}/helpdesk/api/attachment?id={fid}",
        f"{base}/api/attachment?id={fid}",
    ]


def validate_image(data: bytes) -> Optional[str]:
    if not PILImage:
        return None
    try:
        with PILImage.open(io.BytesIO(data)) as im:  # type: ignore[name-defined]
            return im.format
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="Fetch a Jitbit attachment via API using Bearer token from .env")
    ap.add_argument("file_id", help="Attachment FileID (e.g., 26355)")
    ap.add_argument("--base-url", default=os.getenv("JITBIT_BASE_URL", "https://support.4plan.de"),
                    help="Base URL of your Jitbit (default from JITBIT_BASE_URL or https://support.4plan.de)")
    ap.add_argument("--out", default=None, help="Output filename (defaults to attachment_<id>.bin or guessed by content-type)")
    ap.add_argument("--verbose", action="store_true", help="Verbose output")
    args = ap.parse_args()

    token = os.getenv("JITBIT_API_TOKEN", "").strip()
    if not token:
        print("ERROR: JITBIT_API_TOKEN is not set in environment/.env", file=sys.stderr)
        sys.exit(1)

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "User-Agent": "jitbit-fetch-attachment/1.0",
        "Accept": "*/*",
    })

    if args.verbose:
        masked = (token[:4] + "..." + token[-4:]) if len(token) >= 8 else ("*" * len(token))
        print(f"[INFO] Using Bearer token: {masked}", file=sys.stderr)
        print(f"[INFO] Base URL: {args.base_url}", file=sys.stderr)

    urls = build_urls(args.base_url, args.file_id)
    last_resp = None
    data = None
    ctype = None
    used_url = None

    for url in urls:
        try:
            if args.verbose:
                print(f"[INFO] GET {url}", file=sys.stderr)
            r = session.get(url, timeout=30)
            last_resp = r
            if args.verbose:
                print(f"[INFO] -> HTTP {r.status_code} {r.headers.get('Content-Type','')}", file=sys.stderr)
            if r.status_code == 200:
                data = r.content
                ctype = (r.headers.get("Content-Type") or "").lower()
                used_url = url
                break
        except requests.exceptions.RequestException as e:
            last_resp = None
            print(f"[ERROR] Request error for {url}: {e}", file=sys.stderr)

    if data is None:
        if last_resp is not None:
            print(f"[FAIL] Could not fetch attachment id={args.file_id}. "
                  f"Last status: {last_resp.status_code}. Body snippet: {last_resp.text[:300]!r}", file=sys.stderr)
        else:
            print(f"[FAIL] Could not fetch attachment id={args.file_id}. No response.", file=sys.stderr)
        sys.exit(2)

    # Determine output filename
    out_path = args.out
    if not out_path:
        ext = ""
        if "image/png" in ctype:
            ext = ".png"
        elif "image/jpeg" in ctype:
            ext = ".jpg"
        elif "image/gif" in ctype:
            ext = ".gif"
        elif "application/pdf" in ctype:
            ext = ".pdf"
        out_path = f"attachment_{args.file_id}{ext or '.bin'}"

    try:
        with open(out_path, "wb") as f:
            f.write(data)
    except Exception as e:
        print(f"[ERROR] Failed to write output file {out_path}: {e}", file=sys.stderr)
        sys.exit(3)

    print(f"[OK] Downloaded attachment id={args.file_id} from {used_url}")
    print(f"[OK] Content-Type: {ctype or '(unknown)'}")
    print(f"[OK] Saved to: {out_path}")

    # Optional image validation
    if ctype and ctype.startswith("image/") and PILImage:
        try:
            import io  # local import for optional validation
            fmt = None
            with PILImage.open(io.BytesIO(data)) as im:
                fmt = im.format
            print(f"[OK] Image validated by PIL. Format={fmt}")
        except Exception as e:
            print(f"[WARN] PIL failed to open image: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
