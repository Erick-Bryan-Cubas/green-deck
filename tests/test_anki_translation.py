import asyncio
import json

import pytest

from app.api import anki
from app.api.anki import (
    AnkiTranslateRequest,
    AnkiTranslationAnalysisRequest,
    _automatic_translation_field,
    _is_numeric_only_translation_field,
    _parse_translation_response,
    _translation_items,
    TranslateProviderError,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2", True),
        ("0 0 1 0 0", True),
        ("<b>1</b> 0 1", True),
        ("[sound:answer.mp3] 1", True),
        ("Question 2", False),
        ("", False),
    ],
)
def test_numeric_only_field_detection(value, expected):
    assert _is_numeric_only_translation_field(value) is expected


def test_automatic_fields_skip_allinone_control_values():
    assert _automatic_translation_field("What is the capital?") is True
    assert _automatic_translation_field("Paris") is True
    assert _automatic_translation_field("2") is False
    assert _automatic_translation_field("0 0 1 0") is False
    assert _automatic_translation_field("<img src=\"map.png\">") is False


def test_translation_response_is_mapped_by_opaque_id_not_response_order():
    source = {
        "Question": "What is the capital?",
        "Q_1": "Paris",
        "Q_2": "London",
    }
    items, field_map = _translation_items(source)
    assert [item["field_id"] for item in items] == ["field_0", "field_1", "field_2"]

    parsed = {
        "translations": [
            {"field_id": "field_2", "translated_text": "Londres"},
            {"field_id": "field_0", "translated_text": "Qual é a capital?"},
            {"field_id": "field_1", "translated_text": "Paris"},
        ]
    }

    assert _parse_translation_response(parsed, field_map) == {
        "Question": "Qual é a capital?",
        "Q_1": "Paris",
        "Q_2": "Londres",
    }


@pytest.mark.parametrize(
    "translations",
    [
        [{"field_id": "field_0", "translated_text": "Pergunta"}],
        [
            {"field_id": "field_0", "translated_text": "Pergunta"},
            {"field_id": "field_0", "translated_text": "Resposta"},
        ],
        [
            {"field_id": "field_0", "translated_text": "Pergunta"},
            {"field_id": "field_9", "translated_text": "Resposta"},
        ],
    ],
)
def test_translation_response_rejects_missing_duplicate_or_unknown_ids(translations):
    _, field_map = _translation_items({"Question": "Question", "Q_1": "Answer"})
    with pytest.raises(ValueError):
        _parse_translation_response({"translations": translations}, field_map)


def test_analysis_recommends_text_and_skips_allinone_numeric_fields(monkeypatch):
    async def fake_ankiconnect(_client, action, params=None):
        if action == "cardsInfo":
            return [
                {
                    "cardId": 10,
                    "noteId": 20,
                    "modelName": "AllInOne (kprim, mc, sc)",
                }
            ]
        if action == "notesInfo":
            return [
                {
                    "noteId": 20,
                    "modelName": "AllInOne (kprim, mc, sc)",
                    "fields": {
                        "Question": {"value": "Which option is correct?", "order": 0},
                        "QType (0=kprim,1=mc,2=sc)": {"value": "2", "order": 1},
                        "Q_1": {"value": "First option", "order": 2},
                        "Answers": {"value": "1 0 0", "order": 3},
                    },
                }
            ]
        raise AssertionError(f"Unexpected AnkiConnect action: {action} {params}")

    monkeypatch.setattr(anki, "ankiconnect", fake_ankiconnect)
    response = asyncio.run(
        anki.analyze_translation_fields(
            AnkiTranslationAnalysisRequest(cardIds=[10])
        )
    )

    fields = {
        field["name"]: field
        for field in response["noteTypes"][0]["fields"]
    }
    assert fields["Question"]["recommended"] is True
    assert fields["Q_1"]["recommended"] is True
    assert fields["QType (0=kprim,1=mc,2=sc)"]["numericOnly"] is True
    assert fields["QType (0=kprim,1=mc,2=sc)"]["recommended"] is False
    assert fields["Answers"]["numericOnly"] is True
    assert fields["Answers"]["recommended"] is False


def test_translate_endpoint_updates_only_selected_original_fields(monkeypatch):
    updates = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    async def fake_ankiconnect(_client, action, params=None):
        if action == "cardsInfo":
            return [
                {
                    "cardId": 10,
                    "noteId": 20,
                    "modelName": "AllInOne (kprim, mc, sc)",
                }
            ]
        if action == "notesInfo":
            return [
                {
                    "noteId": 20,
                    "modelName": "AllInOne (kprim, mc, sc)",
                    "fields": {
                        "Question": {"value": "Which option is correct?", "order": 0},
                        "QType (0=kprim,1=mc,2=sc)": {"value": "2", "order": 1},
                        "Q_1": {"value": "The heart", "order": 2},
                        "Answers": {"value": "1 0 0", "order": 3},
                    },
                }
            ]
        if action == "updateNoteFields":
            updates.append(params)
            return None
        raise AssertionError(f"Unexpected AnkiConnect action: {action} {params}")

    async def fake_translate_provider(**_kwargs):
        # Deliberadamente fora da ordem para provar que a posição da resposta
        # não interfere no direcionamento dos campos.
        return (
            '{"translations": ['
            '{"field_id": "field_1", "translated_text": "O coração"},'
            '{"field_id": "field_0", "translated_text": "Qual opção está correta?"}'
            ']}',
            "test.toon",
        )

    monkeypatch.setattr(anki.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(anki, "ankiconnect", fake_ankiconnect)
    monkeypatch.setattr(anki, "_translate_with_provider", fake_translate_provider)

    async def run_request():
        response = await anki.translate_cards(
            AnkiTranslateRequest(
                cardIds=[10],
                noteType="AllInOne (kprim, mc, sc)",
                fieldNames=["Question", "Q_1"],
            )
        )
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        return "".join(chunks)

    stream = asyncio.run(run_request())

    assert '"translated": 1' in stream
    assert len(updates) == 1
    assert updates[0]["note"]["fields"] == {
        "Question": "Qual opção está correta?",
        "QType (0=kprim,1=mc,2=sc)": "2",
        "Q_1": "O coração",
        "Answers": "1 0 0",
    }


class TranslationFakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def _parse_sse(stream):
    events = []
    for block in stream.split("\n\n"):
        if not block.strip():
            continue
        event = "message"
        data = ""
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data += line.split(":", 1)[1].strip()
        events.append((event, json.loads(data)))
    return events


async def _consume_translation(request):
    response = await anki.translate_cards(request)
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    return _parse_sse("".join(chunks))


def _install_parallel_anki(monkeypatch, note_count, update_hook=None):
    cards = [
        {"cardId": index + 100, "noteId": index + 1, "modelName": "Basic"}
        for index in range(note_count)
    ]
    notes = [
        {
            "noteId": index + 1,
            "modelName": "Basic",
            "fields": {"Front": {"value": f"Question {index + 1}", "order": 0}},
        }
        for index in range(note_count)
    ]

    async def fake_ankiconnect(_client, action, params=None):
        if action == "cardsInfo":
            return cards
        if action == "notesInfo":
            return notes
        if action == "updateNoteFields":
            if update_hook:
                await update_hook(params)
            return None
        raise AssertionError(f"Unexpected AnkiConnect action: {action}")

    monkeypatch.setattr(anki.httpx, "AsyncClient", TranslationFakeAsyncClient)
    monkeypatch.setattr(anki, "ankiconnect", fake_ankiconnect)
    return cards


def test_parallel_translation_respects_limit_serializes_anki_and_orders_results(monkeypatch):
    active_calls = 0
    max_active_calls = 0
    active_updates = 0
    max_active_updates = 0

    async def update_hook(_params):
        nonlocal active_updates, max_active_updates
        active_updates += 1
        max_active_updates = max(max_active_updates, active_updates)
        await asyncio.sleep(0.002)
        active_updates -= 1

    _install_parallel_anki(monkeypatch, 8, update_hook)

    async def fake_translate(**kwargs):
        nonlocal active_calls, max_active_calls
        active_calls += 1
        max_active_calls = max(max_active_calls, active_calls)
        # Inverte a ordem natural de conclusão.
        await asyncio.sleep((9 - kwargs["source_note_id"]) * 0.002)
        active_calls -= 1
        return '{"translations":[{"field_id":"field_0","translated_text":"Traduzido"}]}', "test.toon"

    monkeypatch.setattr(anki, "_translate_with_provider", fake_translate)
    events = asyncio.run(_consume_translation(AnkiTranslateRequest(
        cardIds=list(range(100, 108)), model="gpt-4o-mini", openaiApiKey="test",
        maxConcurrency=5,
    )))
    start = next(data for event, data in events if event == "start")
    result = next(data for event, data in events if event == "result")

    assert start["effectiveConcurrency"] == 5
    assert 2 <= max_active_calls <= 5
    assert max_active_updates == 1
    assert [item["noteId"] for item in result["results"]] == list(range(1, 9))
    assert result["translated"] == 8


def test_ollama_concurrency_is_capped_at_two(monkeypatch):
    active = 0
    max_active = 0
    _install_parallel_anki(monkeypatch, 5)

    async def fake_translate(**_kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.005)
        active -= 1
        return '{"translations":[{"field_id":"field_0","translated_text":"OK"}]}', "test.toon"

    monkeypatch.setattr(anki, "_translate_with_provider", fake_translate)
    events = asyncio.run(_consume_translation(AnkiTranslateRequest(
        cardIds=list(range(100, 105)), model="qwen-flashcard", maxConcurrency=10,
    )))
    start = next(data for event, data in events if event == "start")
    assert start["requestedConcurrency"] == 10
    assert start["effectiveConcurrency"] == 2
    assert max_active == 2


def test_retry_after_rate_limit_and_permanent_error(monkeypatch):
    attempts = {1: 0, 2: 0}
    _install_parallel_anki(monkeypatch, 2)

    async def fake_translate(**kwargs):
        note_id = kwargs["source_note_id"]
        attempts[note_id] += 1
        if note_id == 1 and attempts[note_id] < 3:
            raise TranslateProviderError("rate limited", status_code=429, retry_after=0)
        if note_id == 2:
            raise TranslateProviderError(
                "quota exhausted", status_code=429, error_code="insufficient_quota", retry_after=0,
            )
        return '{"translations":[{"field_id":"field_0","translated_text":"OK"}]}', "test.toon"

    monkeypatch.setattr(anki, "_translate_with_provider", fake_translate)
    events = asyncio.run(_consume_translation(AnkiTranslateRequest(
        cardIds=[100, 101], model="gpt-4o-mini", openaiApiKey="test", maxConcurrency=5,
    )))
    result = next(data for event, data in events if event == "result")

    assert attempts == {1: 3, 2: 1}
    assert result["retryCount"] == 2
    assert result["rateLimitCount"] == 3
    assert result["translated"] == 1
    assert result["failed"] == 1
    assert result["success"] is True


def test_timeout_is_retried_and_then_succeeds(monkeypatch):
    attempts = 0
    _install_parallel_anki(monkeypatch, 1)

    async def no_wait(_delay):
        return None

    async def fake_translate(**_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise anki.httpx.ReadTimeout("provider timeout")
        return '{"translations":[{"field_id":"field_0","translated_text":"OK"}]}', "test.toon"

    monkeypatch.setattr(anki.asyncio, "sleep", no_wait)
    monkeypatch.setattr(anki, "_translate_with_provider", fake_translate)
    events = asyncio.run(_consume_translation(AnkiTranslateRequest(
        cardIds=[100], model="gpt-4o-mini", openaiApiKey="test",
    )))
    result = next(data for event, data in events if event == "result")
    assert attempts == 2
    assert result["retryCount"] == 1
    assert result["translated"] == 1


def test_translation_context_is_sent_to_provider_prompt(monkeypatch):
    captured = {}
    _install_parallel_anki(monkeypatch, 1)

    async def fake_translate(**kwargs):
        captured["system"] = kwargs["system_prompt"]
        captured["user"] = json.loads(kwargs["user_prompt"])
        return '{"translations":[{"field_id":"field_0","translated_text":"Miocárdio"}]}', "test.toon"

    monkeypatch.setattr(anki, "_translate_with_provider", fake_translate)
    events = asyncio.run(_consume_translation(AnkiTranslateRequest(
        cardIds=[100], model="gpt-4o-mini", openaiApiKey="test",
        translationContext=(
            "Cartões de cardiologia para estudantes de medicina; "
            "use terminologia clínica brasileira."
        ),
    )))
    result = next(data for event, data in events if event == "result")

    assert captured["user"]["translation_context"].startswith("Cartões de cardiologia")
    assert "não o traduza" in captured["system"]
    assert result["translated"] == 1


@pytest.mark.parametrize(
    ("status_code", "code", "retryable"),
    [(408, None, True), (429, None, True), (500, None, True), (400, None, False), (429, "insufficient_quota", False)],
)
def test_provider_error_retry_classification(status_code, code, retryable):
    error = TranslateProviderError("failure", status_code=status_code, error_code=code)
    assert error.retryable is retryable


def test_cancellation_stops_workers_without_late_anki_writes(monkeypatch):
    workers_started = asyncio.Event()
    updates = []
    _install_parallel_anki(monkeypatch, 4, lambda params: updates.append(params))

    async def slow_translate(**_kwargs):
        workers_started.set()
        await asyncio.sleep(30)
        return '{"translations":[{"field_id":"field_0","translated_text":"Late"}]}', "test.toon"

    monkeypatch.setattr(anki, "_translate_with_provider", slow_translate)

    async def run_cancel():
        response = await anki.translate_cards(AnkiTranslateRequest(
            cardIds=[100, 101, 102, 103], model="gpt-4o-mini",
            openaiApiKey="test", maxConcurrency=3,
        ))
        iterator = response.body_iterator
        first = await iterator.__anext__()
        assert "event: start" in first
        pending_read = asyncio.create_task(iterator.__anext__())
        await asyncio.wait_for(workers_started.wait(), timeout=1)
        pending_read.cancel()
        await asyncio.gather(pending_read, return_exceptions=True)
        await asyncio.sleep(0)

    asyncio.run(run_cancel())
    assert updates == []
