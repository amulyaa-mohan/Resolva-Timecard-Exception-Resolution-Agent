"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.ai.providers import ProviderError, build_provider
from app.core.config import Settings
from app.core.contracts import CONTRACT_VERSION
from app.core.errors import install_error_handlers
from app.core.tracing import TRACE_HEADER, new_trace_id, set_trace_id


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Timecard exception resolution: AI drafts, rules verify, the manager decides.",
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
        allow_methods=["GET"],
        allow_headers=["*"],
        expose_headers=[TRACE_HEADER],
    )
    install_error_handlers(app)

    @app.middleware("http")
    async def trace_middleware(request: Request, call_next) -> Response:
        incoming = request.headers.get(TRACE_HEADER, "")
        trace_id = incoming if incoming.isalnum() and len(incoming) <= 64 else new_trace_id()
        set_trace_id(trace_id)
        response = await call_next(request)
        response.headers[TRACE_HEADER] = trace_id
        return response

    @app.get("/health", tags=["operations"])
    def health() -> dict[str, str | bool]:
        """Liveness plus model-provider reachability. Detection never depends on the LLM."""
        llm_status = "disabled"
        if settings.ai_enabled:
            try:
                # Build once per app: each provider owns an HTTP connection pool.
                if getattr(app.state, "provider", None) is None:
                    app.state.provider = build_provider(settings)
                reachable = app.state.provider.is_reachable()
                llm_status = "reachable" if reachable else "unreachable"
            except ProviderError:
                llm_status = "unavailable"
        return {
            "status": "ok",
            "service": "resolva-api",
            "stage": "scaffold",
            "contract_version": CONTRACT_VERSION,
            "ai_enabled": settings.ai_enabled,
            "llm_provider": settings.llm_provider,
            "llm_status": llm_status,
            "mode": "ai_assisted" if llm_status == "reachable" else "rules_only",
        }

    return app


app = create_app()
