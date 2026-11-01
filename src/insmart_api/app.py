"""FastAPI application factory.

Later tasks register routers (work-order ingestion, timelines, diagnoses)
here; the scaffold ships only the liveness surface.
"""

from fastapi import FastAPI

from insmart_api import __version__


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    app = FastAPI(title="Insmart AI API", version=__version__)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok"}

    return app


app = create_app()
