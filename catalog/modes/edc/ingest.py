# Mirrors modes/solid/ingest.py; wire when EDC substrate is ready.
"""EDC-mode push ingestion."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.interfaces.ingest import IngestSource


class EdcIngest(IngestSource):
    def routes(self) -> APIRouter:
        router = APIRouter()

        @router.post("/catalog")
        async def push_catalog() -> JSONResponse:
            return JSONResponse(
                status_code=501,
                content={
                    "error": "edc_not_wired",
                    "detail": "EDC mode not wired for testing yet",
                    "stage": "ingest",
                },
            )

        return router
