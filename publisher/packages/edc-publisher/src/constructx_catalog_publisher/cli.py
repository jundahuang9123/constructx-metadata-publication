"""Prepare, inspect, publish and retry a source's DCAT metadata snapshot."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .converter import PROFILE_IRI, MappingError, convert_assets
from .inventory import InventoryClient, InventoryError, InventorySnapshot
from .publication import PublicationClient, PublicationError
from .validation import profile_hash, validate_graph


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def encode(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode()


def read_json(path: Path):
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Input JSON exceeds the supported size.")
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, content: bytes | str):
    path.write_bytes(content.encode() if isinstance(content, str) else content)


def token(env_name: str) -> str:
    value = os.environ.get(env_name, "")
    if not value:
        raise ValueError(f"Set the credential environment variable {env_name}.")
    return value


def publication_client(config: dict) -> PublicationClient:
    settings = config.get("publication", {})
    return PublicationClient(
        settings["catalogUrl"], token(settings.get("tokenEnv", "CATALOG_PUBLISHER_TOKEN"))
    )


def inventory(config: dict, assets_file: Path | None) -> InventorySnapshot:
    if assets_file:
        started = now()
        assets = read_json(assets_file)
        if not isinstance(assets, list) or any(not isinstance(v, dict) for v in assets):
            raise ValueError("Offline asset input must be a JSON array of asset objects.")
        return InventorySnapshot(
            assets,
            started,
            now(),
            hashlib.sha256(encode(assets)).hexdigest(),
            0,
            "offline-input-not-live-verified",
        )
    settings = config.get("management", {})
    return InventoryClient(
        settings["baseUrl"],
        token(settings.get("apiKeyEnv", "MANAGEMENT_API_KEY")),
        query_path=settings.get("queryPath", "/v3/assets/request"),
        page_size=settings.get("pageSize", 100),
        max_pages=settings.get("maxPages", 1000),
        sort_field=settings.get("sortField", "id"),
        timeout=settings.get("timeout", 30),
    ).harvest()


def report_html(audit: dict, validation: dict, verification: str) -> str:
    esc = html.escape
    rows = "".join(
        "<tr><td>"
        + "</td><td>".join(esc(str(row.get(k, ""))) for k in ("assetId", "from", "to"))
        + "</td></tr>"
        for row in audit["mappings"]
    )
    errors = "".join(
        "<li>" + esc(str(e.get("focusNode", ""))) + " — " + esc(str(e.get("message", ""))) + "</li>"
        for e in validation["errors"]
    )
    warnings = "".join(
        "<li>" + esc(str(e["assetId"])) + " — " + esc(e["message"]) + "</li>"
        for e in audit["warnings"]
    )
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
+<title>Construct-X publication preview</title><style>
+body{{font:16px/1.6 system-ui,sans-serif;margin:3rem auto;padding:0 1.5rem;max-width:960px;color:#19332f;background:#f5f7f3}}
+h1{{font-size:2rem;line-height:1.2}}.status{{padding:1rem;background:#e1eae3;border-radius:8px}}
+table{{width:100%;border-collapse:collapse;background:white}}th,td{{text-align:left;padding:.65rem;border-bottom:1px solid #ddd;overflow-wrap:anywhere}}
+.table{{overflow-x:auto}}small{{color:#52645f}}a{{color:#165e4a}}code{{overflow-wrap:anywhere}}
+</style><h1>Metadata publication preview</h1><p>Source: <strong>{esc(audit["sourceId"])}</strong></p>
+<p class="status">{"Ready for publication" if validation["conforms"] else "Needs correction"} · {validation["datasetCount"]} datasets · {audit["tripleCount"]} triples</p>
+<p>{audit["selectedAssetCount"]} selected from {audit["inputAssetCount"]} assets. {audit["omittedAssetCount"]} omitted. Retrieval: <code>{esc(verification)}</code>.</p>
+<p><a href="catalog.ttl">DCAT graph</a> · <a href="manifest.json">Mapping and validation report</a></p>
+<p><small>Provisional publication profile. This is not a complete ConstructDCAT or DCAT-AP conformance claim. Connector access remains governed by its own policies.</small></p>
+<h2>Validation</h2><ul>{errors or "<li>Local topology and SHACL checks passed.</li>"}</ul>
+<h2>Metadata mapping</h2><div class="table"><table><thead><tr><th>Asset</th><th>Source</th><th>Result</th></tr></thead><tbody>{rows}</tbody></table></div>
+<h2>Profile notes</h2><ul>{warnings or "<li>No additional profile notes.</li>"}</ul></html>""".replace(
        "\n+", "\n"
    )


def prepare(config: dict, output: Path, assets_file: Path | None, client: PublicationClient | None):
    # Capture the publication baseline BEFORE reading the connector.
    baseline = client.baseline(config["sourceId"], config["catalogIri"]) if client else None
    snapshot = inventory(config, assets_file)
    converted = convert_assets(snapshot.assets, config)
    validation = validate_graph(converted.graph, config["catalogIri"])
    rdf = converted.graph.serialize(format="turtle")
    verification = {
        "method": snapshot.verification,
        "pages": snapshot.pages,
        "atomicSnapshot": False,
        "live": assets_file is None,
    }
    envelope = {
        "catalogIri": config["catalogIri"],
        "profileIri": PROFILE_IRI,
        "profileShapeHash": profile_hash(),
        "audience": "public",
        "harvest": {
            "complete": True,
            "sourceRevision": snapshot.digest,
            "startedAt": snapshot.started_at,
            "finishedAt": snapshot.finished_at,
            "datasetCount": validation["datasetCount"],
            "allowEmpty": config.get("allowEmpty") is True,
            "verification": verification,
        },
        "rdf": {"mediaType": "text/turtle", "content": rdf},
    }
    if validation["datasetCount"] == 0 and not envelope["harvest"]["allowEmpty"]:
        validation["conforms"] = False
        validation["errors"].append(
            {"message": "Empty snapshots require explicit allowEmpty=true."}
        )
    payload = encode(envelope)
    manifest = {
        "profileIri": PROFILE_IRI,
        "validation": validation,
        "audit": converted.audit,
        "harvest": envelope["harvest"],
        "baselineRevision": baseline,
        "catalogTurtleSha256": hashlib.sha256(rdf.encode()).hexdigest(),
    }
    write(output / "catalog.ttl", rdf)
    write(output / "manifest.json", encode(manifest))
    write(output / "preview.html", report_html(converted.audit, validation, snapshot.verification))
    if not validation["conforms"]:
        raise MappingError(
            "Metadata failed validation. Inspect preview.html and manifest.json; nothing was published."
        )
    write(output / "publication.json", payload)
    if client:
        request = {
            "sourceId": config["sourceId"],
            "catalogUrl": client.url,
            "method": "PUT",
            "baselineRevision": baseline,
            "idempotencyKey": str(uuid4()),
            "payloadSha256": hashlib.sha256(payload).hexdigest(),
        }
        write(output / "request.json", encode(request))
    return envelope


def submit(output: Path, token_env: str):
    saved = read_json(output / "request.json")
    method = saved["method"]
    if method not in {"PUT", "DELETE"}:
        raise ValueError("Saved request has an unsupported method.")
    body = (output / "publication.json").read_bytes() if method == "PUT" else None
    digest = hashlib.sha256(body or b"").hexdigest()
    if digest != saved["payloadSha256"]:
        raise ValueError(
            "Prepared payload changed; prepare a new bundle instead of reusing its retry key."
        )
    client = PublicationClient(saved["catalogUrl"], token(token_env))
    result = client.submit(
        saved["sourceId"], body, saved["baselineRevision"], saved["idempotencyKey"], method
    )
    write(output / "receipt.json", encode(result))
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare and publish Construct-X discovery metadata."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "publish", "withdraw"):
        cmd = sub.add_parser(command)
        cmd.add_argument("--config", type=Path, required=True)
        cmd.add_argument(
            "--output",
            type=Path,
            required=True,
            help="New bundle directory; existing directories are never overwritten.",
        )
        if command != "withdraw":
            cmd.add_argument(
                "--assets-file",
                type=Path,
                help="Offline captured/fixture inventory; recorded as not live verified.",
            )
        if command == "prepare":
            cmd.add_argument(
                "--with-baseline",
                action="store_true",
                help="Read catalog revision before harvest, enabling later submit.",
            )
    retry = sub.add_parser(
        "submit", help="Send or retry the exact prepared request without rebasing it."
    )
    retry.add_argument("--bundle", type=Path, required=True)
    retry.add_argument("--token-env", default="CATALOG_PUBLISHER_TOKEN")
    args = parser.parse_args(argv)
    try:
        if args.command == "submit":
            result = submit(args.bundle, args.token_env)
            print(f"Publication accepted at revision {result['revision']}; receipt saved.")
            return 0
        config = read_json(args.config)
        if not isinstance(config, dict):
            raise ValueError("Source configuration must be a JSON object.")
        args.output.mkdir(parents=True, exist_ok=False)
        client = (
            publication_client(config)
            if args.command in {"publish", "withdraw"} or args.with_baseline
            else None
        )
        if args.command == "withdraw":
            baseline = client.baseline(config["sourceId"], config["catalogIri"])
            if baseline == "none":
                raise ValueError("Source has no publication to withdraw.")
            write(
                args.output / "request.json",
                encode(
                    {
                        "sourceId": config["sourceId"],
                        "catalogUrl": client.url,
                        "method": "DELETE",
                        "baselineRevision": baseline,
                        "idempotencyKey": str(uuid4()),
                        "payloadSha256": hashlib.sha256(b"").hexdigest(),
                    }
                ),
            )
        else:
            prepare(config, args.output, args.assets_file, client)
        if args.command in {"publish", "withdraw"}:
            result = submit(
                args.output,
                config.get("publication", {}).get("tokenEnv", "CATALOG_PUBLISHER_TOKEN"),
            )
            print(f"Publication accepted at revision {result['revision']}; receipt saved.")
        else:
            print(f"Prepared metadata. Review {args.output / 'preview.html'}")
        return 0
    except (ValueError, KeyError, OSError, InventoryError, PublicationError) as exc:
        # Do not echo input values, response bodies, or credentials for parser/IO failures.
        if isinstance(exc, (MappingError, InventoryError, PublicationError)):
            message = str(exc)
        elif isinstance(exc, KeyError):
            message = "Configuration or saved bundle is missing a required field. See the example configuration."
        elif isinstance(exc, FileExistsError):
            message = "Output directory already exists. Choose a new directory or submit the existing bundle."
        elif isinstance(exc, OSError):
            message = "Could not read or write a local file; check paths and permissions."
        else:
            message = (
                str(exc) if type(exc) is ValueError else "Invalid JSON configuration or input."
            )
        print("Error: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
