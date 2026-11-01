"""FastAPI application factory."""

from fastapi import FastAPI

from insmart_api import __version__
from insmart_api.api import router
from insmart_api.db import build_engine, build_session_factory, default_database_url
from insmart_api.models import Base


def create_app(database_url: str | None = None) -> FastAPI:
    """Build the FastAPI application bound to a database (default: local SQLite)."""
    engine = build_engine(database_url or default_database_url())
    Base.metadata.create_all(engine)

    app = FastAPI(title="Insmart AI API", version=__version__)
    app.state.session_factory = build_session_factory(engine)
    app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok"}

    return app


app = create_app()
