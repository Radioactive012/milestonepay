"""The one place the app talks to an AI model: OpenRouter, with the model set by AI_MODEL in .env.

Every answer comes back as JSON that must match a Pydantic model, so code can check it before
anything is saved. The AI never gets tools and never touches money.
"""
from datetime import date
from functools import lru_cache
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from sqlmodel import Session

from app.config import Settings, get_settings
from app.db import engine
from app.models import AppState

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# keywords the strict schema format doesn't accept; Pydantic still enforces them afterwards
_UNSUPPORTED_KEYWORDS = {"default", "title", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"}

Output = TypeVar("Output", bound=BaseModel)


class AIError(Exception):
    pass


def strict_schema(model: type[BaseModel]) -> dict:
    """The model's JSON schema in strict form: every object closed and every field required."""

    def clean(node):
        if isinstance(node, list):
            return [clean(item) for item in node]
        if not isinstance(node, dict):
            return node
        result = {}
        for key, value in node.items():
            if key in ("properties", "$defs"):
                # field names like "title" are kept; only schema keywords are removed
                result[key] = {name: clean(sub) for name, sub in value.items()}
            elif key not in _UNSUPPORTED_KEYWORDS:
                result[key] = clean(value)
        if result.get("type") == "object" and "properties" in result:
            result["additionalProperties"] = False
            result["required"] = list(result["properties"])
        return result

    return clean(model.model_json_schema())


class DailyAILimit:
    """Counts real AI calls per calendar day in the database and refuses once the cap is reached.

    Uses the real date, so moving the demo clock can't reset it.
    """

    def __init__(self, db_engine, limit: int):
        self._engine = db_engine
        self.limit = limit

    def used_today(self, today: date | None = None) -> int:
        with Session(self._engine) as session:
            state = session.get(AppState, 1)
            if state is None or state.ai_calls_date != (today or date.today()):
                return 0
            return state.ai_calls_count

    def take_one(self, today: date | None = None) -> None:
        today = today or date.today()
        with Session(self._engine) as session:
            state = session.get(AppState, 1) or AppState(id=1)
            if state.ai_calls_date != today:
                state.ai_calls_date = today
                state.ai_calls_count = 0
            if state.ai_calls_count >= self.limit:
                raise AIError(
                    f"Today's AI limit ({self.limit} requests) is used up. It protects the team's AI credit. "
                    "Try again tomorrow, or raise AI_DAILY_LIMIT in .env."
                )
            state.ai_calls_count += 1
            session.add(state)
            session.commit()


class OpenRouterLLM:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
        limit: DailyAILimit | None = None,
    ):
        self._key = settings.openrouter_api_key
        self._model = settings.ai_model
        self._http = httpx.Client(timeout=120, transport=transport)
        self._limit = limit

    def _post(self, body: dict) -> dict:
        try:
            response = self._http.post(
                OPENROUTER_URL,
                json=body,
                headers={"Authorization": f"Bearer {self._key}", "X-Title": "MilestonePay"},
            )
        except httpx.HTTPError:
            raise AIError("Couldn't reach the AI service. Check the internet connection.")
        if response.status_code == 401:
            raise AIError("The OpenRouter API key isn't valid. Check OPENROUTER_API_KEY in .env.")
        if response.status_code == 402:
            raise AIError("The OpenRouter account is out of credit. Add credit or raise the key's limit.")
        if response.status_code == 429:
            raise AIError("The AI is busy right now. Try again in a minute.")
        if response.status_code >= 400:
            raise AIError(f"The AI request failed ({response.status_code}). Try again.")
        data = response.json()
        if "error" in data:
            raise AIError(f"The AI request failed: {str(data['error'].get('message', ''))[:200]}")
        return data

    def ask_json(self, *, system: str, content: str | list[dict], output: type[Output], max_tokens: int = 8000) -> Output:
        """Ask the model and return its answer as a validated `output`. Tries once more if the shape is wrong."""
        if not self._key:
            raise AIError("Add your OpenRouter API key to OPENROUTER_API_KEY in .env, then restart the app.")
        body = {
            "model": self._model,
            "max_tokens": max_tokens,
            # 0 = the most consistent answers: the same document reads the same way every time
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": output.__name__, "strict": True, "schema": strict_schema(output)},
            },
            # only use providers that support the strict JSON format
            "provider": {"require_parameters": True},
        }
        for _ in range(2):
            if self._limit:
                self._limit.take_one()
            choice = self._post(body)["choices"][0]
            if choice.get("finish_reason") == "length":
                raise AIError("The AI couldn't finish its answer. Try a shorter document.")
            if choice.get("finish_reason") == "content_filter":
                raise AIError("The AI declined to read this document.")
            answer = choice["message"].get("content") or ""
            try:
                return output.model_validate_json(answer)
            except ValidationError as error:
                # at temperature 0 the same question gets the same answer, so the retry says what was wrong
                body = body | {
                    "messages": body["messages"] + [
                        {"role": "assistant", "content": answer[:4000]},
                        {"role": "user", "content": "That answer didn't match the required format: "
                         f"{str(error)[:500]}\nReply again with only the corrected JSON."},
                    ]
                }
        raise AIError("The AI's answer wasn't in the expected format. Try again.")


@lru_cache
def get_ai_limit() -> DailyAILimit:
    return DailyAILimit(engine, get_settings().ai_daily_limit)


@lru_cache
def get_llm() -> OpenRouterLLM:
    return OpenRouterLLM(get_settings(), limit=get_ai_limit())
