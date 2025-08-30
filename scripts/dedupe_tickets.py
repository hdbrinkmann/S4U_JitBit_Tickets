#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/dedupe_tickets.py

Detect quasi-duplicate support tickets using multilingual embeddings (bge-multilingual-gemma2 via Scaleway).
Outputs:
- tickets_dedup.json: canonical tickets with duplicates array and basic cluster info
- duplicate_groups.json: detailed cluster membership
- needs_review.csv: borderline similar pairs for manual review

Usage:
  python3 scripts/dedupe_tickets.py \
    --input Ticket_Data_TEST.JSON \
    --out tickets_dedup.json \
    --groups-out duplicate_groups.json \
    --review-out needs_review.csv \
    --threshold 0.84 \
    --threshold-low 0.78

Environment (.env read via process_tickets_with_llm.load_env):
- SCW_API_KEY or SCW_SECRET_KEY: Scaleway AI key (required)
- SCW_OPENAI_BASE_URL / OPENAI_BASE_URL / OPENAI_API_BASE: Base URL (OpenAI-compatible). We will resolve an /embeddings endpoint from this.
  Example: https://api.scaleway.ai/v1/chat/completions  (we will derive /embeddings)
- SCW_PROJECT_ID (optional): Project ID header if needed
- SCW_REGION (optional): e.g., fr-par, nl-ams (used to try region endpoints)
- SCW_EMBEDDING_MODEL or EMBEDDING_MODEL (optional): defaults to "bge-multilingual-gemma2"
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

# Reuse .env loader pattern from existing script for consistency
try:
    from process_tickets_with_llm import load_env  # type: ignore
except Exception:
    def load_env() -> None:
        # Minimal fallback
        env_path = Path(".env")
        if not env_path.exists():
            return
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'").strip('"')
                if k and k not in os.environ:
                    os.environ[k] = v
        except Exception:
            pass


def normalize_text(text: str) -> str:
    """
    Domain-aware normalization: remove URLs and transient IDs, keep meaningful technical tokens.
    """
    if not isinstance(text, str):
        text = str(text)
    t = text.lower()

    # Strip URLs
    t = re.sub(r"https?://[^\s]+", " ", t)

    # Jitbit file ids
    t = re.sub(r"\bfile/get/\d+\b", " ", t)

    # Remove transient person/temp codes
    t = re.sub(r"\bnn\d+\b", " ", t)             # NN1234
    t = re.sub(r"\bpers?nr?\s*[:#-]?\s*\d+\b", " ", t)  # PERSNR 12345
    t = re.sub(r"\bper\.\d+\b", " ", t)          # Per.493

    # Collapse whitespace
    t = re.sub(r"\s+", " ", t).strip()

    return t


def build_text_for_similarity(ticket: Dict[str, Any]) -> str:
    subject = ticket.get("subject", "") or ""
    problem = ticket.get("problem", "") or ""
    solution = ticket.get("solution", "") or ""
    return normalize_text(" . ".join([subject, problem, solution]))


def resolve_embeddings_model() -> str:
    return (
        os.environ.get("SCW_EMBEDDING_MODEL")
        or os.environ.get("EMBEDDING_MODEL")
        or "bge-multilingual-gemma2"
    )


class OpenAICompatibleEmbeddingsClient:
    """
    Minimal OpenAI-compatible embeddings client with Scaleway-friendly headers.
    Attempts several endpoint variants:
    - <base>/regions/<region>/embeddings
    - <base>/openai/v1/embeddings
    - <base>/v1/embeddings
    - <base>/providers/openai/embeddings
    - <base>/embeddings
    Also accepts if the provided base already ends with /embeddings.
    """

    def __init__(
        self,
        api_url_base: str,
        api_key: str,
        model: str,
        project_id: Optional[str] = None,
        region: Optional[str] = None,
        request_timeout: int = 60,
        max_retries: int = 5,
        backoff_base: float = 1.0,
        backoff_cap: float = 16.0,
    ) -> None:
        self.api_url_base = (api_url_base or "").strip().rstrip("/")
        self.api_key = api_key
        self.model = model
        self.project_id = project_id
        self.region = (region or "").strip()
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap

    def _headers(self) -> Dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Auth-Token": self.api_key,
            "Content-Type": "application/json",
        }
        if self.project_id:
            h["X-Project-Id"] = self.project_id
        # Org header optional
        org_id = os.environ.get("SCW_ORGANIZATION_ID") or os.environ.get("SCW_DEFAULT_ORGANIZATION_ID")
        if org_id:
            h["X-Organization-Id"] = org_id
        return h

    def _candidate_endpoints(self) -> List[str]:
        raw = self.api_url_base
        # Strip known chat endpoints to get base root
        base = raw
        for seg in [
            "/chat/completions",
            "/v1/chat/completions",
            "/openai/v1/chat/completions",
            "/providers/openai/chat/completions",
        ]:
            if base.endswith(seg):
                base = base[: -len(seg)].rstrip("/")
        # If user already provided /embeddings endpoint, keep it
        if base.endswith("/embeddings"):
            return [base]

        candidates: List[str] = []
        reg = self.region or os.environ.get("SCW_REGION") or ""
        reg_list = [reg] if reg else ["fr-par", "nl-ams", "pl-waw"]

        lower = base.lower()
        if "scaleway" in lower or "/ai/" in lower:
            for r in reg_list:
                candidates.append(f"{base}/regions/{r}/embeddings")
                # Some installations expose an openai-provider path
                candidates.append(f"{base}/regions/{r}/providers/openai/embeddings")

        candidates.extend([
            f"{base}/openai/v1/embeddings",
            f"{base}/v1/embeddings",
            f"{base}/providers/openai/embeddings",
            f"{base}/embeddings",
        ])

        # Deduplicate while preserving order
        seen = set()
        out = []
        for c in candidates:
            c = c.strip().rstrip("/")
            if c not in seen:
                seen.add(c)
                out.append(c)
        return out

    def _compute_backoff(self, attempt: int) -> float:
        base = min(self.backoff_cap, self.backoff_base * (2 ** (attempt - 1)))
        import random
        return base + random.uniform(0, 0.25 * base)

    def embed(self, inputs: List[str]) -> List[List[float]]:
        """
        Returns embeddings in the same order as inputs.
        """
        payload = {
            "model": self.model,
            "input": inputs,
        }

        headers = self._headers()
        last_err: Optional[str] = None

        for endpoint in self._candidate_endpoints():
            attempt = 0
            while attempt <= self.max_retries:
                attempt += 1
                try:
                    resp = requests.post(endpoint, headers=headers, data=json.dumps(payload), timeout=self.request_timeout)
                except requests.RequestException as e:
                    last_err = f"Network error: {e}"
                    time.sleep(self._compute_backoff(attempt))
                    continue

                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except Exception:
                        last_err = "Invalid JSON in embeddings response"
                        break
                    # Try OpenAI-compatible format
                    emb: List[List[float]] = []
                    if isinstance(data, dict) and isinstance(data.get("data"), list):
                        for item in data["data"]:
                            vec = item.get("embedding")
                            if isinstance(vec, list) and all(isinstance(x, (int, float)) for x in vec):
                                emb.append([float(x) for x in vec])
                        if len(emb) == len(inputs):
                            return emb
                        last_err = f"Embeddings count mismatch (got {len(emb)}, expected {len(inputs)})"
                        break
                    # Some providers may use "embeddings" key
                    if isinstance(data, dict) and isinstance(data.get("embeddings"), list):
                        for vec in data["embeddings"]:
                            if isinstance(vec, list) and all(isinstance(x, (int, float)) for x in vec):
                                emb.append([float(x) for x in vec])
                        if len(emb) == len(inputs):
                            return emb
                        last_err = f"Embeddings count mismatch (got {len(emb)}, expected {len(inputs)})"
                        break

                    last_err = "Unrecognized embeddings response format"
                    break

                if resp.status_code in (429, 500, 502, 503, 504):
                    last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    time.sleep(self._compute_backoff(attempt))
                    continue

                last_err = f"HTTP {resp.status_code}: {resp.text[:300]}"
                break

        raise RuntimeError(last_err or "Failed to obtain embeddings from any endpoint")


def unit_normalize(vecs: List[List[float]]) -> List[List[float]]:
    out: List[List[float]] = []
    for v in vecs:
        s = math.sqrt(sum((x * x) for x in v)) or 1.0
        out.append([x / s for x in v])
    return out


def cosine(u: List[float], v: List[float]) -> float:
    # assuming unit-normalized
    return float(sum((a * b) for a, b in zip(u, v)))


def connected_components(n: int, edges: Iterable[Tuple[int, int]]) -> List[List[int]]:
    parent = list(range(n))
    rank = [0] * n

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if rank[ra] < rank[rb]:
            parent[ra] = rb
        elif rank[ra] > rank[rb]:
            parent[rb] = ra
        else:
            parent[rb] = ra
            rank[ra] += 1

    for i, j in edges:
        union(i, j)

    groups: Dict[int, List[int]] = {}
    for i in range(n):
        r = find(i)
        groups.setdefault(r, []).append(i)

    return list(groups.values())


def pick_representative(indices: List[int], tickets: List[Dict[str, Any]]) -> int:
    # Most informative: longest solution text; fallback to longest problem; then subject length
    best = indices[0]
    best_len = len((tickets[best].get("solution") or ""))

    for idx in indices[1:]:
        s = tickets[idx].get("solution") or ""
        if len(s) > best_len:
            best = idx
            best_len = len(s)

    if best_len > 0:
        return best

    # fallback to problem length
    best2 = indices[0]
    best_len2 = len((tickets[best2].get("problem") or ""))
    for idx in indices[1:]:
        p = tickets[idx].get("problem") or ""
        if len(p) > best_len2:
            best2 = idx
            best_len2 = len(p)
    if best_len2 > 0:
        return best2

    # fallback subject length
    best3 = max(indices, key=lambda k: len((tickets[k].get("subject") or "")))
    return best3


def load_tickets(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and isinstance(data.get("tickets"), list):
        return data["tickets"]
    if isinstance(data, list):
        return data
    raise ValueError("Unsupported input JSON structure (expect top-level array or {'tickets': [...]})")


def main() -> None:
    load_env()

    parser = argparse.ArgumentParser(description="Deduplicate tickets with Scaleway embeddings (bge-multilingual-gemma2).")
    parser.add_argument("--input", "-i", default="Ticket_Data_TEST.JSON", help="Input JSON file (array of tickets with subject/problem/solution).")
    parser.add_argument("--out", "-o", default="tickets_dedup.json", help="Output JSON for canonical tickets.")
    parser.add_argument("--groups-out", default="duplicate_groups.json", help="Output JSON for all clusters.")
    parser.add_argument("--review-out", default="needs_review.csv", help="Output CSV for borderline pairs.")
    parser.add_argument("--threshold", type=float, default=0.84, help="Similarity threshold for auto-merge.")
    parser.add_argument("--threshold-low", type=float, default=0.78, help="Lower bound for needs-review zone.")
    parser.add_argument("--max-pairs", type=int, default=None, help="Optional cap for needs-review rows.")
    parser.add_argument("--batch-size", type=int, default=64, help="Embedding request batch size.")
    parser.add_argument("--dry-run", action="store_true", help="Compute and print summary without writing files.")
    args = parser.parse_args()

    api_key = (os.environ.get("SCW_API_KEY") or os.environ.get("SCW_SECRET_KEY") or "").strip()
    if not api_key:
        print("❌ Scaleway API key not set (SCW_API_KEY or SCW_SECRET_KEY)")
        sys.exit(1)

    api_base = (
        os.environ.get("SCW_OPENAI_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("OPENAI_API_BASE")
        or "https://api.scaleway.ai/v1"
    )
    project_id = os.environ.get("SCW_PROJECT_ID") or os.environ.get("SCW_DEFAULT_PROJECT_ID")
    region = os.environ.get("SCW_REGION")

    model = resolve_embeddings_model()

    in_path = Path(args.input)
    tickets = load_tickets(in_path)

    if not tickets:
        print("No tickets in input.")
        sys.exit(0)

    # Build normalized texts
    texts: List[str] = [build_text_for_similarity(t) for t in tickets]

    # Embed in batches
    client = OpenAICompatibleEmbeddingsClient(
        api_url_base=api_base,
        api_key=api_key,
        model=model,
        project_id=project_id,
        region=region,
    )

    all_vecs: List[List[float]] = []
    bsz = max(1, int(args.batch_size))
    for i in range(0, len(texts), bsz):
        batch = texts[i:i + bsz]
        vecs = client.embed(batch)
        all_vecs.extend(vecs)

    # Normalize and compute pairwise similarities
    vecs = unit_normalize(all_vecs)
    n = len(vecs)

    T = float(args.threshold)
    Tlow = float(args.threshold_low)
    edges: List[Tuple[int, int]] = []
    # Track borderline pairs for review; we'll keep top-1 neighbor in the range per node
    borderline_pairs: Dict[int, Tuple[int, float]] = {}

    for i in range(n):
        best_j = -1
        best_s = -1.0
        for j in range(i + 1, n):
            s = cosine(vecs[i], vecs[j])
            if s >= T:
                edges.append((i, j))
            elif Tlow <= s < T:
                # Track top neighbor in the gray zone for each side
                if s > best_s:
                    best_s = s
                    best_j = j
        if best_j != -1:
            borderline_pairs[i] = (best_j, best_s)

    # Build clusters via union-find
    comps = connected_components(n, edges)

    # Representative selection and outputs
    dedup: List[Dict[str, Any]] = []
    clusters_out: List[Dict[str, Any]] = []

    for cid, comp in enumerate(comps):
        rep_idx = pick_representative(comp, tickets)
        rep = dict(tickets[rep_idx])  # shallow copy
        duplicates = [tickets[k].get("ticket_id") for k in comp if k != rep_idx]
        # Keep canonical record with duplicates
        rep["duplicates"] = [str(x) for x in duplicates]
        rep["cluster_id"] = cid
        dedup.append(rep)

        clusters_out.append({
            "cluster_id": cid,
            "representative_index": rep_idx,
            "representative_ticket_id": str(tickets[rep_idx].get("ticket_id")),
            "member_indices": comp,
            "member_ticket_ids": [str(tickets[k].get("ticket_id")) for k in comp],
            "size": len(comp),
        })

    # Sort canonical tickets for stable output: by cluster size desc, then by date ascending if present
    size_map = {c["cluster_id"]: c["size"] for c in clusters_out}
    def _date_key(t: Dict[str, Any]) -> str:
        return str(t.get("date") or "")
    dedup.sort(key=lambda r: (-size_map.get(r.get("cluster_id"), 1), _date_key(r)))

    # Prepare needs review CSV rows
    review_rows: List[Tuple[str, str, float, str, str]] = []
    for i, (j, s) in borderline_pairs.items():
        ti = tickets[i]
        tj = tickets[j]
        review_rows.append((
            str(ti.get("ticket_id")),
            str(tj.get("ticket_id")),
            round(s, 4),
            (ti.get("subject") or "")[:120],
            (tj.get("subject") or "")[:120],
        ))

    # Optional cap
    if args.max_pairs is not None and args.max_pairs >= 0:
        review_rows = review_rows[: args.max_pairs]

    # I/O
    out_path = Path(args.out)
    groups_path = Path(args.groups_out)
    review_path = Path(args.review_out)

    summary = f"""Deduplication summary:
- Input tickets: {n}
- Threshold (auto-merge): {T}
- Threshold low (needs review): {Tlow}
- Clusters found: {len(comps)} (with size>1: {sum(1 for c in comps if len(c)>1)})
- Canonical tickets after dedup: {len(dedup)}
- Borderline review pairs: {len(review_rows)}
- Embedding model: {model}
- API base: {api_base}
"""

    if args.dry_run:
        print(summary)
        # Print top 5 largest clusters
        largest = sorted(comps, key=lambda c: -len(c))[:5]
        for idx, comp in enumerate(largest, 1):
            ids = [str(tickets[k].get("ticket_id")) for k in comp]
            print(f"Top#{idx} cluster size={len(comp)} members={ids}")
        return

    # Write outputs (UTF-8)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(dedup, f, ensure_ascii=False, indent=2)

    with groups_path.open("w", encoding="utf-8") as f:
        json.dump(clusters_out, f, ensure_ascii=False, indent=2)

    with review_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["ticket_id_A", "ticket_id_B", "similarity", "subject_A", "subject_B"])
        for a, b, s, sa, sb in review_rows:
            w.writerow([a, b, f"{s:.4f}", sa, sb])

    # Also write a short summary next to out file
    with Path(str(out_path) + ".summary.txt").open("w", encoding="utf-8") as f:
        f.write(summary)

    print(summary)
    print(f"Wrote canonical tickets: {out_path}")
    print(f"Wrote cluster breakdown: {groups_path}")
    print(f"Wrote needs-review pairs: {review_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted by user.")
        sys.exit(130)
