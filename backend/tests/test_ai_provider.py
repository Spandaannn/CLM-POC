"""Groq adapter, provider factory, and playbook tests.

Groq is mocked with httpx.MockTransport: these tests never use the network
or any real API key.
"""

import json
from dataclasses import asdict

import httpx
import pytest

from app.ai.errors import (
    AIAuthenticationError,
    AIConfigurationError,
    AIModelUnavailableError,
    AIProviderError,
    AIRateLimitError,
    AIRequestTooLargeError,
    AIResponseFormatError,
    AIResponseTruncatedError,
    AITimeoutError,
)
from app.ai.factory import build_provider, get_ai_status
from app.ai.groq import GroqProvider
from app.ai.playbook import load_playbook
from app.core.config import Settings

FAKE_KEY = "gsk_test_FAKE_KEY_for_unit_tests_only"
PROVIDER_BODY_SECRET = "internal provider detail that must never leak"


def make_provider(handler) -> GroqProvider:
    return GroqProvider(
        api_key=FAKE_KEY,
        model="test-model",
        timeout=5,
        transport=httpx.MockTransport(handler),
    )


def ok_response(content: str) -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"content": content}}]}
    )


def call(provider: GroqProvider) -> str:
    return provider.complete_json(system_prompt="sys", user_prompt="user")


def test_successful_call_sends_key_only_in_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        seen["url"] = str(request.url)
        return ok_response('{"hello": "world"}')

    assert call(make_provider(handler)) == '{"hello": "world"}'
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["auth"] == f"Bearer {FAKE_KEY}"
    assert seen["body"]["model"] == "test-model"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert FAKE_KEY not in json.dumps(seen["body"])


@pytest.mark.parametrize(
    ("status_code", "body", "expected"),
    [
        (401, {"error": {"code": "invalid_api_key"}}, AIAuthenticationError),
        (403, {}, AIAuthenticationError),
        (429, {"error": {"code": "rate_limit_exceeded"}}, AIRateLimitError),
        (404, {"error": {"code": "model_not_found"}}, AIModelUnavailableError),
        (400, {"error": {"code": "model_decommissioned"}}, AIModelUnavailableError),
        (413, {}, AIRequestTooLargeError),
        (400, {"error": {"code": "json_validate_failed"}}, AIResponseFormatError),
        (400, {"error": {"code": "something_else"}}, AIProviderError),
        (500, {}, AIProviderError),
        (503, {}, AIProviderError),
    ],
)
def test_provider_errors_map_to_safe_exceptions(status_code, body, expected):
    body = {**body}
    body.setdefault("error", {})["message"] = PROVIDER_BODY_SECRET

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=body)

    with pytest.raises(expected) as excinfo:
        call(make_provider(handler))

    shown = f"{excinfo.value} {excinfo.value.message}"
    assert PROVIDER_BODY_SECRET not in shown
    assert FAKE_KEY not in shown


def test_timeout_maps_to_timeout_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(AITimeoutError):
        call(make_provider(handler))


def test_connection_failure_maps_to_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(AIProviderError):
        call(make_provider(handler))


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json at all"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"unexpected": True}),
        httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}),
        httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
    ],
)
def test_malformed_provider_payload_is_rejected(response):
    with pytest.raises(AIResponseFormatError):
        call(make_provider(lambda request: response))


def test_reasoning_effort_is_sent_only_when_configured():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return ok_response("{}")

    transport = httpx.MockTransport(handler)
    GroqProvider(
        api_key=FAKE_KEY, model="m", transport=transport, reasoning_effort="low"
    ).complete_json(system_prompt="s", user_prompt="u", max_output_tokens=1234)
    GroqProvider(api_key=FAKE_KEY, model="m", transport=transport).complete_json(
        system_prompt="s", user_prompt="u"
    )

    assert seen[0]["reasoning_effort"] == "low"
    assert seen[0]["max_completion_tokens"] == 1234
    assert "reasoning_effort" not in seen[1]


def test_reply_cut_off_at_the_output_limit_is_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": '{"summary": {"overview": "cut'},
                    }
                ]
            },
        )

    with pytest.raises(AIResponseTruncatedError):
        call(make_provider(handler))


def test_provider_repr_hides_the_key():
    assert FAKE_KEY not in repr(make_provider(lambda r: ok_response("{}")))


# ------------------------------- factory -----------------------------------


def settings(**values) -> Settings:
    base = {"database_url": "postgresql+psycopg://u:p@localhost/db"}
    return Settings(_env_file=None, **{**base, **values})


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"ai_provider": "groq"},
        {"ai_provider": "groq", "groq_api_key": "   "},
        {"ai_provider": "groq", "groq_api_key": FAKE_KEY, "groq_model": " "},
        {"ai_provider": "openai", "groq_api_key": FAKE_KEY},
    ],
)
def test_missing_or_invalid_configuration_is_reported(values):
    with pytest.raises(AIConfigurationError):
        build_provider(settings(**values))

    status = get_ai_status(settings(**values))
    assert status.configured is False
    assert status.message
    assert FAKE_KEY not in json.dumps(asdict(status))


def test_ai_tuning_defaults_and_validation():
    config = settings()
    assert config.ai_max_output_tokens == 4000
    assert config.groq_reasoning_effort == "low"
    assert settings(groq_reasoning_effort=" ").groq_reasoning_effort is None
    assert settings(groq_reasoning_effort="HIGH").groq_reasoning_effort == "high"
    with pytest.raises(ValueError):
        settings(groq_reasoning_effort="extreme")
    with pytest.raises(ValueError):
        settings(ai_max_output_tokens=10)


def test_valid_configuration_builds_groq_without_exposing_the_key():
    config = settings(
        ai_provider=" Groq ", groq_api_key=FAKE_KEY, groq_model="my-model"
    )

    provider = build_provider(config)
    status = get_ai_status(config)

    assert provider.name == "groq" and provider.model == "my-model"
    assert status.configured is True
    assert (status.provider, status.model) == ("groq", "my-model")
    assert FAKE_KEY not in json.dumps(asdict(status))
    assert FAKE_KEY not in repr(config)
    assert FAKE_KEY not in str(config.model_dump())


# ------------------------------- playbook ----------------------------------


def test_baseline_playbook_is_valid_and_labelled_not_policy():
    playbook = load_playbook()

    assert playbook.label == "baseline-poc@1"
    assert len(playbook.rules) >= 8
    assert "NOT an approved company legal policy" in playbook.disclaimer
    assert len({rule.id for rule in playbook.rules}) == len(playbook.rules)


def test_custom_playbook_is_used_and_invalid_one_is_rejected(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(
        json.dumps(
            {
                "id": "acme",
                "name": "Acme playbook",
                "version": "7",
                "rules": [
                    {
                        "id": "r1",
                        "category": "payment_terms",
                        "title": "T",
                        "requirement": "R",
                        "severity_if_not_met": "high",
                    }
                ],
            }
        )
    )
    bad = tmp_path / "bad.json"
    bad.write_text('{"id": "x"}')
    duplicate = tmp_path / "dup.json"
    duplicate.write_text(
        json.dumps(
            {
                "id": "d",
                "name": "d",
                "version": "1",
                "rules": [
                    {"id": "r", "category": "c", "title": "t", "requirement": "q"},
                    {"id": "r", "category": "c", "title": "t", "requirement": "q"},
                ],
            }
        )
    )

    assert load_playbook(good).label == "acme@7"
    for path in (bad, duplicate, tmp_path / "missing.json"):
        with pytest.raises(AIConfigurationError):
            load_playbook(path)
