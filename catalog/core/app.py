import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, is_dataclass
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from core.config import load_active_mode
from core.publication.errors import PublicationError
from core.publication.routes import publication_api_from_env

logger = logging.getLogger(__name__)

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def _as_dict(value: object) -> dict[str, object]:
    return asdict(value) if is_dataclass(value) else dict(value)  # type: ignore[arg-type]


def _readiness_payload(mode_name: str, status_payload: dict[str, object]) -> tuple[bool, dict[str, object]]:
    dependencies = status_payload.get("dependencies") or {}
    fuseki_ready = bool(dependencies.get("fuseki")) if isinstance(dependencies, dict) else False
    registry_value = dependencies.get("registry") if isinstance(dependencies, dict) else None
    registry_ready = registry_value is not False
    ready = bool(status_payload.get("operational")) and fuseki_ready and registry_ready
    return ready, {"mode": mode_name, "ready": ready, "dependencies": dependencies}


def _env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        logger.warning("Invalid numeric environment value", extra={"name": name, "value": raw_value})
        return default


def _solid_fuseki_unavailable(mode_name: str, dependencies: object) -> bool:
    return (
        mode_name == "solid"
        and isinstance(dependencies, dict)
        and dependencies.get("fuseki") is False
    )


def _log_startup_status(mode_name: str, status_payload: dict[str, object]) -> tuple[bool, dict[str, object]]:
    ready, payload = _readiness_payload(mode_name, status_payload)
    dependencies = payload["dependencies"]
    logger.info("Catalog startup dependency status", extra={"mode": mode_name, **payload})
    if isinstance(dependencies, dict) and dependencies.get("registry") is False:
        logger.warning("Solid registry is not reachable at startup", extra={"mode": mode_name})
    return ready, payload


def _cors_origins() -> list[str]:
    raw_value = os.getenv("CATALOG_CORS_ORIGINS", DEFAULT_CORS_ORIGINS).strip()
    if not raw_value:
        return []
    if raw_value in {"*", "all"}:
        return ["*"]
    return [origin.strip() for origin in raw_value.split(",") if origin.strip()]


def _configure_cors(app: FastAPI) -> None:
    origins = _cors_origins()
    if not origins:
        return

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=origins != ["*"],
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["*"],
    )


def _startup_checks(mode) -> None:
    if os.getenv("CATALOG_STARTUP_CHECKS", "true").lower() in {"0", "false", "no"}:
        logger.warning("Catalog startup dependency checks are disabled")
        return

    wait_seconds = _env_float("CATALOG_STARTUP_WAIT_SECONDS", 60.0)
    retry_seconds = _env_float("CATALOG_STARTUP_RETRY_SECONDS", 1.0)
    deadline = time.monotonic() + wait_seconds

    while True:
        status_payload = _as_dict(mode.discovery.get_status())
        ready, payload = _log_startup_status(mode.name, status_payload)
        dependencies = payload["dependencies"]

        if not _solid_fuseki_unavailable(mode.name, dependencies):
            break

        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            raise RuntimeError(f"Fuseki is not reachable: {status_payload.get('detail')}")

        sleep_seconds = min(retry_seconds, remaining_seconds)
        logger.info(
            "Waiting for Fuseki before catalog startup",
            extra={"mode": mode.name, "retry_in_seconds": sleep_seconds},
        )
        time.sleep(sleep_seconds)

    if not ready:
        logger.warning("Catalog started but is not ready", extra={"mode": mode.name, **payload})


def create_app() -> FastAPI:
    publication_api = publication_api_from_env()
    mode = load_active_mode() if os.getenv("CATALOG_MODE") or not publication_api else None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if mode is not None:
            _startup_checks(mode)
        yield

    app = FastAPI(title="Dual-Substrate Federated Catalog", lifespan=lifespan)
    _configure_cors(app)
    if mode is not None:
        app.include_router(mode.ingest.routes())
    if publication_api is not None:
        app.include_router(publication_api.routes())
        app.state.publication_api = publication_api

    @app.get("/status")
    def status() -> dict[str, object]:
        if mode is None:
            return publication_api.status()
        status_result = mode.discovery.get_status()
        return _as_dict(status_result)

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"status": "ok", "mode": mode.name if mode else "shared"}

    @app.get("/ready")
    def ready() -> JSONResponse:
        if mode is None:
            try:
                status_payload = publication_api.status()
                return JSONResponse(status_code=200, content={"mode": "shared", "ready": True, **status_payload})
            except (PublicationError, sqlite3.Error, OSError):
                return JSONResponse(status_code=503, content={"mode": "shared", "ready": False})
        status_payload = _as_dict(mode.discovery.get_status())
        is_ready, payload = _readiness_payload(mode.name, status_payload)
        payload["status"] = status_payload
        return JSONResponse(status_code=200 if is_ready else 503, content=payload)

    @app.get("/datasets")
    def datasets() -> list[dict[str, object]]:
        if mode is None:
            return []  # Shared publications use the source-aware /v1/datasets API.
        return [_as_dict(item) for item in mode.discovery.list_datasets()]

    @app.get("/datasets/detail", response_model=None)
    def dataset_detail(dataset_id: str = Query(...)):
        detail = mode.discovery.get_dataset(dataset_id) if mode else None
        if detail is None:
            return JSONResponse(
                status_code=404,
                content={
                    "error": "dataset_not_found",
                    "detail": f"Dataset not found: {dataset_id}",
                    "stage": "discovery",
                },
            )
        return _as_dict(detail)

    ui_dir = Path(__file__).resolve().parent.parent / "ui"
    if (ui_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(ui_dir), html=True), name="ui")

    return app


app = create_app()
