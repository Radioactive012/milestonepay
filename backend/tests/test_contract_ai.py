import json
from io import BytesIO

import httpx
import pytest
from pydantic import BaseModel
from pypdf import PdfWriter

from app.ai.contract import ContractReader, pdf_text
from app.ai.llm import OPENROUTER_URL, AIError, OpenRouterLLM, strict_schema
from app.ai.schemas import ContractAnalysis
from app.config import Settings
from tests.conftest import sample_analysis


def make_pdf(text: str) -> bytes:
    """A real one-page PDF with the text on it, built by hand so tests need no extra packages."""
    stream = f"BT /F1 12 Tf 72 712 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def settings(**overrides) -> Settings:
    values = {"openrouter_api_key": "test-key", "ai_model": "deepseek/deepseek-v4.1-flash-1017"}
    values.update(overrides)
    return Settings(_env_file=None, **values)


def reply(content: str, finish_reason: str = "stop") -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}]}
    )


def llm_with(*responses, captured=None, **setting_overrides) -> OpenRouterLLM:
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(request)
        return queue.pop(0)

    return OpenRouterLLM(settings(**setting_overrides), transport=httpx.MockTransport(handler))


class Small(BaseModel):
    title: str
    count: int | None = None


VALID = sample_analysis().model_dump_json()


def test_strict_schema_closes_objects_and_keeps_field_names():
    schema = strict_schema(Small)
    assert set(schema["properties"]) == {"title", "count"}
    assert schema["required"] == ["title", "count"]
    assert schema["additionalProperties"] is False
    assert "default" not in json.dumps(schema)

    nested = strict_schema(ContractAnalysis)
    milestone = nested["$defs"]["MilestoneDraft"]
    assert "title" in milestone["properties"]
    assert milestone["additionalProperties"] is False


def test_request_uses_the_model_and_strict_json(monkeypatch):
    captured = []
    result = llm_with(reply(VALID), captured=captured).ask_json(system="s", content="c", output=ContractAnalysis)
    assert result.deposit_pct == 30
    request = captured[0]
    assert str(request.url) == OPENROUTER_URL
    assert request.headers["authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert body["model"] == "deepseek/deepseek-v4.1-flash-1017"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["provider"] == {"require_parameters": True}
    assert body["max_tokens"] <= 8000
    assert body["temperature"] == 0


def test_bad_shape_is_retried_once_then_fails():
    assert llm_with(reply("not json"), reply(VALID)).ask_json(system="s", content="c", output=ContractAnalysis)
    with pytest.raises(AIError) as error:
        llm_with(reply("{}"), reply("still wrong")).ask_json(system="s", content="c", output=ContractAnalysis)
    assert "expected format" in str(error.value)


@pytest.mark.parametrize(
    "response,message",
    [
        (httpx.Response(401, json={}), "isn't valid"),
        (httpx.Response(402, json={}), "out of credit"),
        (httpx.Response(429, json={}), "busy"),
        (httpx.Response(500, json={}), "failed (500)"),
        (httpx.Response(200, json={"error": {"message": "upstream broke"}}), "upstream broke"),
        (reply(VALID, finish_reason="length"), "couldn't finish"),
    ],
)
def test_errors_become_clear_messages(response, message):
    with pytest.raises(AIError) as error:
        llm_with(response).ask_json(system="s", content="c", output=ContractAnalysis)
    assert message in str(error.value)


def test_missing_key_fails_without_calling_the_ai():
    with pytest.raises(AIError) as error:
        llm_with(openrouter_api_key="").ask_json(system="s", content="c", output=ContractAnalysis)
    assert "OPENROUTER_API_KEY" in str(error.value)


def test_network_failure_is_a_clear_message():
    def handler(request):
        raise httpx.ConnectError("offline")

    llm = OpenRouterLLM(settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(AIError) as error:
        llm.ask_json(system="s", content="c", output=ContractAnalysis)
    assert "internet" in str(error.value)


def test_pdf_text_is_read_locally():
    assert "Logo design fee USD 500" in pdf_text(make_pdf("Logo design fee USD 500"))
    with pytest.raises(AIError) as error:
        pdf_text(blank_pdf())
    assert "photo" in str(error.value)
    with pytest.raises(AIError):
        pdf_text(b"not a pdf at all")


def test_reader_sends_pdf_as_text_and_keeps_it_for_quote_checks():
    captured = []
    reader = ContractReader(llm_with(reply(VALID), captured=captured))
    analysis = reader.analyse(text=None, file_bytes=make_pdf("Logo design fee USD 500"), media_type="application/pdf")
    parts = json.loads(captured[0].content)["messages"][1]["content"]
    assert [p["type"] for p in parts] == ["text"]
    assert "Logo design fee USD 500" in parts[0]["text"]
    assert "Logo design fee USD 500" in analysis.transcription


def test_reader_sends_images_to_the_model():
    captured = []
    reader = ContractReader(llm_with(reply(VALID), captured=captured))
    reader.analyse(text=None, file_bytes=b"\x89PNG fake", media_type="image/png")
    parts = json.loads(captured[0].content)["messages"][1]["content"]
    assert parts[0]["type"] == "image_url"
    assert parts[0]["image_url"]["url"].startswith("data:image/png;base64,")


def test_reader_refuses_other_file_types_without_calling_the_ai():
    reader = ContractReader(llm_with())
    with pytest.raises(AIError) as error:
        reader.analyse(text=None, file_bytes=b"abc", media_type="application/zip")
    assert "PDF" in str(error.value)


def test_daily_ai_limit_counts_calls_and_refuses_past_the_cap(engine):
    from datetime import date

    from app.ai.llm import DailyAILimit

    limit = DailyAILimit(engine, 2)
    day = date(2026, 11, 10)
    limit.take_one(day)
    limit.take_one(day)
    assert limit.used_today(day) == 2
    with pytest.raises(AIError) as error:
        limit.take_one(day)
    assert "AI_DAILY_LIMIT" in str(error.value)
    limit.take_one(date(2026, 11, 11))
    assert limit.used_today(date(2026, 11, 11)) == 1


def test_limit_is_checked_before_every_ai_call_including_the_retry(engine):
    from app.ai.llm import DailyAILimit

    limit = DailyAILimit(engine, 1)
    queue = [reply("not json"), reply(VALID)]
    llm = OpenRouterLLM(settings(), transport=httpx.MockTransport(lambda r: queue.pop(0)), limit=limit)
    with pytest.raises(AIError) as error:
        llm.ask_json(system="s", content="c", output=ContractAnalysis)
    assert "limit" in str(error.value)
    assert limit.used_today() == 1


def test_zero_limit_turns_the_ai_off(engine):
    from app.ai.llm import DailyAILimit

    llm = OpenRouterLLM(settings(), transport=httpx.MockTransport(lambda r: reply(VALID)), limit=DailyAILimit(engine, 0))
    with pytest.raises(AIError):
        llm.ask_json(system="s", content="c", output=ContractAnalysis)


def test_retry_tells_the_ai_what_was_wrong():
    captured = []
    result = llm_with(reply('{"not": "valid"}'), reply(VALID), captured=captured).ask_json(
        system="s", content="c", output=ContractAnalysis
    )
    assert result.client_name
    first, second = (json.loads(r.content) for r in captured)
    assert len(first["messages"]) == 2
    assert second["messages"][2] == {"role": "assistant", "content": '{"not": "valid"}'}
    assert "didn't match the required format" in second["messages"][3]["content"]
    assert second["temperature"] == 0
