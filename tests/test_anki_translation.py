import asyncio

import pytest

from app.api import anki
from app.api.anki import (
    AnkiTranslateRequest,
    AnkiTranslationAnalysisRequest,
    _automatic_translation_field,
    _is_numeric_only_translation_field,
    _parse_translation_response,
    _translation_items,
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
