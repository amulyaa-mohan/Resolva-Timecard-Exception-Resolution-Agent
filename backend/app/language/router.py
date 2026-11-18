"""POST /assistant/query: multilingual manager request -> language-neutral intent (B-04).

Read-only. It returns the parsed intent, the filters Track A's exception list should apply,
and a localized confirmation. It never approves, edits or deletes anything.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field

from app.ai.providers import ProviderError, build_provider
from app.attendance.access import authenticated_manager, bearer
from app.language.assistant import ExceptionQuery, render, to_query, understand
from app.language.intents import Intent, Language

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=500)


class AssistantResponse(BaseModel):
    language: Language
    method: str = Field(description="rules (lexicon), llm (AI fallback) or none (not understood)")
    intent: Intent
    query: ExceptionQuery | None = Field(
        description="Filters for the exception list; null when the request is unsupported."
    )
    message: str = Field(description="Localized confirmation; ids and codes stay canonical.")
    model_id: str | None = None


def manager_when_configured(
    request: Request, auth: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
):
    """Require a manager token whenever the attendance store is enabled.

    Audit 2026-11-18: the endpoint was open and can trigger model calls (cost, denial of
    service). Without the attendance store (offline demo, tests) there is no identity to check.
    """
    if getattr(request.app.state, "attendance_repository", None) is None:
        return None
    return authenticated_manager(request, auth)


@router.post("/query", response_model=AssistantResponse)
def assistant_query(
    body: AssistantRequest,
    request: Request,
    _manager: Annotated[object, Depends(manager_when_configured)] = None,
) -> AssistantResponse:
    settings = request.app.state.settings
    provider = None
    if settings.ai_enabled:
        try:
            if getattr(request.app.state, "provider", None) is None:
                request.app.state.provider = build_provider(settings)
            provider = request.app.state.provider
        except ProviderError:
            provider = None  # rules-only: the lexicon parser still works
    result = understand(body.text, settings=settings, provider=provider)
    return AssistantResponse(
        language=result.language,
        method=result.method,
        intent=result.intent,
        query=to_query(result.intent),
        message=render(result),
        model_id=result.model_id,
    )
