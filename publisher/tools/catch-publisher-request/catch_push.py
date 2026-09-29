#!/usr/bin/env python3
"""Capture one or more publisher POST requests for Solid auth diagnosis.

This diagnostic server is intentionally tiny and dependency-free. It does not
verify JWT signatures. It only decodes visible JWT header/payload fields so the
operator can confirm whether the browser push carries Authorization and DPoP
headers that the central catalogue can verify later.
"""

from __future__ import annotations

import argparse
import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


ALLOWED_HEADERS = (
    "Authorization, DPoP, Content-Type, X-Participant-WebID, "
    "X-Participant-Id"
)


def decode_base64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def decode_jwt(jwt_value: str) -> tuple[dict[str, Any], dict[str, Any]]:
    parts = jwt_value.split(".")
    if len(parts) < 2:
        raise ValueError("expected at least two JWT segments")
    header = json.loads(decode_base64url(parts[0]).decode("utf-8"))
    payload = json.loads(decode_base64url(parts[1]).decode("utf-8"))
    return header, payload


def print_json(label: str, value: Any) -> None:
    print(f"{label}:")
    print(json.dumps(value, indent=2, sort_keys=True))


def inspect_authorization(value: str | None) -> None:
    if not value:
        print("Authorization: missing")
        return

    scheme, _, token = value.partition(" ")
    print(f"Authorization scheme: {scheme or '(none)'}")
    if not token:
        print("Authorization token: missing after scheme")
        return

    try:
        header, payload = decode_jwt(token)
    except Exception as exc:  # noqa: BLE001 - diagnostic output should not crash.
        print(f"Authorization token: not decoded as JWT ({exc})")
        return

    print_json("Authorization JWT header", header)
    print_json("Authorization JWT payload", payload)
    cnf = payload.get("cnf")
    jkt = cnf.get("jkt") if isinstance(cnf, dict) else None
    print(f"Authorization cnf.jkt present: {'yes' if jkt else 'no'}")


def inspect_dpop(value: str | None) -> None:
    if not value:
        print("DPoP: missing")
        return

    try:
        header, payload = decode_jwt(value)
    except Exception as exc:  # noqa: BLE001 - diagnostic output should not crash.
        print(f"DPoP proof: not decoded as JWT ({exc})")
        return

    print_json("DPoP JWT header", header)
    print_json("DPoP JWT payload", payload)
    print(f"DPoP header jwk present: {'yes' if header.get('jwk') else 'no'}")
    print(f"DPoP htu: {payload.get('htu')}")
    print(f"DPoP htm: {payload.get('htm')}")
    print(f"DPoP jti: {payload.get('jti')}")
    print(f"DPoP iat: {payload.get('iat')}")


class CaptureHandler(BaseHTTPRequestHandler):
    server_version = "PublisherRequestCatcher/1.0"

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", ALLOWED_HEADERS)
        super().end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API.
        self.send_response(204)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API.
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)

        print("\n=== Captured publisher POST ===")
        print(f"Path: {self.path}")
        print(f"Content-Type: {self.headers.get('Content-Type')}")
        print(f"Body bytes: {len(body)}")
        print("Headers:")
        for key, value in self.headers.items():
            print(f"  {key}: {value}")
        inspect_authorization(self.headers.get("Authorization"))
        inspect_dpop(self.headers.get("DPoP"))
        print("=== End capture ===\n")

        response = json.dumps({"ok": True, "captured": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), CaptureHandler)
    print(f"Listening on http://{args.host}:{args.port}")
    print("Point the publisher central catalogue URL at this server and publish.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping request catcher.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
