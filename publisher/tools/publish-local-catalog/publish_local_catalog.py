#!/usr/bin/env python3
"""Smoke-test CLI for publishing a local RDF catalogue to the central catalogue."""

from __future__ import annotations

import argparse
import mimetypes
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def detect_content_type(path: Path) -> str:
    if path.suffix.lower() in {".json", ".jsonld"}:
        return "application/ld+json"
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "text/turtle"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-file", required=True)
    parser.add_argument("--central-url", required=True)
    parser.add_argument("--webid", required=True)
    parser.add_argument("--token", default="")
    args = parser.parse_args()

    catalog_path = Path(args.catalog_file)
    payload = catalog_path.read_bytes()
    headers = {
        "Content-Type": detect_content_type(catalog_path),
        "X-Participant-WebID": args.webid,
        "X-Participant-Id": args.webid,
    }
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"

    request = Request(args.central_url, data=payload, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            print(f"HTTP {response.status}")
            print(body)
            return 0 if 200 <= response.status < 300 else 1
    except HTTPError as exc:
        print(f"HTTP {exc.code}")
        print(exc.read().decode("utf-8", errors="replace"))
        return 1
    except URLError as exc:
        print(f"Central catalogue could not be reached: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
