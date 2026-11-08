"""Fumaça da chamada real ao modelo local. Só roda com REQKG_REAL_CALL=1, para que make test não carregue
o modelo, e pula, dizendo o que falta, se o Ollama não responder ou não tiver o modelo com o digest de
code/experiments/config/experiment.toml.

    REQKG_REAL_CALL=1 .venv/bin/python -m pytest code/extraction/test_extraction_real_call.py -s -rs

Pré-requisitos: `ollama serve` no ar e `ollama pull <model_id>`. Só texto sintético. Confere que a saída
respeita o schema com o pensamento desligado, que a temperatura e a semente vão em options e são
aceitas, que duas chamadas iguais com temperatura 0 dão o mesmo texto, e que, com temperatura 1, a
mesma semente repete a resposta e outra semente a muda (prova de que as duas opções são aplicadas).
"""

import json
import os

import pytest
from pydantic import BaseModel

from domain.enums import RunStatus
from domain.llm_io import ClassificationOutput
from extraction import prompts
from extraction.client import CallLog, CallTarget, ClientConfigError, LLMRequest, invoke, real_client
from extraction.prompts import RenderedPrompt
from extraction.fixtures import scenarios
from extraction.pipeline import classify_item, extract_case

MODEL = scenarios.config().model
CLIENT, MISSING = None, "defina REQKG_REAL_CALL=1 para chamar o modelo"
if os.environ.get("REQKG_REAL_CALL") == "1":
    try:
        CLIENT, MISSING = real_client(MODEL), ""
    except ClientConfigError as error:
        MISSING = str(error)

pytestmark = pytest.mark.skipif(CLIENT is None, reason=f"chamada real desligada: {MISSING}")


def test_real_classification_and_extraction(tmp_path):
    log = CallLog(tmp_path)
    item = scenarios.classification_items()["PROMISE-NFR-9002"]
    classified = classify_item(item=item, run_index=0, client=CLIENT, log=log)
    assert classified.status is RunStatus.OK, classified.error
    run = extract_case(case_id="fumaca", run_index=0, chunks=scenarios.entrevista_chunks(),
                       config=scenarios.config(), client=CLIENT, log=log)
    assert run.result.status is not RunStatus.API_ERROR, run.result.error
    entries = log.entries()
    assert all(e.usage.input_tokens and e.usage.output_tokens and e.timing for e in entries)
    assert all(e.client["think"] is False and e.client["model_digest"] == MODEL.model_digest for e in entries)
    assert all(e.temperature.model_dump(exclude_unset=True) == {"value": MODEL.temperature, "transport": "options",
                                                                 "seed": MODEL.seed, "sent": True, "accepted": True}
               for e in entries)
    for entry in entries:
        json.loads(entry.raw_response)
        print(f"{entry.target.stage}: {entry.usage.input_tokens} tokens de entrada, {entry.usage.output_tokens} de "
              f"saída, {entry.timing.total_s:.1f} s, parada {entry.stop_reason}")
    print(f"registro da fumaça: {log.path}; extração: {run.result.status.value} {run.result.error or ''}")


class Invented(BaseModel):
    nome: str
    frase: str


# Os prompts do experimento são previsíveis demais para mostrar o efeito da semente: a extração de
# entrevista_chunks sai igual nos primeiros 160 tokens com temperatura 1 e sementes 11 e 12.
PROBE = RenderedPrompt("sonda", 1, "0" * 64, "Responda só com o JSON pedido.",
                       "Invente um nome para um satélite e uma frase sobre ele.", Invented)


def _probe(temperature: float, seed: int) -> str:
    client = real_client(MODEL.model_copy(update={"temperature": temperature, "seed": seed, "max_tokens": 80}))
    response = client.complete(LLMRequest(PROBE, CallTarget("fumaca", None, 0, "classification", "sonda")))
    assert response.temperature == {"value": temperature, "transport": "options", "seed": seed, "sent": True,
                                    "accepted": True}
    Invented.model_validate_json(response.text)
    return response.text


def test_temperature_and_seed_are_applied():
    greedy = [_probe(0.0, MODEL.seed), _probe(0.0, MODEL.seed + 1)]
    assert greedy[0] == greedy[1], "temperatura 0 tem de dar o mesmo texto, com qualquer semente"
    hot = [_probe(1.0, 11), _probe(1.0, 11), _probe(1.0, 12), _probe(1.0, 13)]
    assert hot[0] == hot[1], "temperatura 1 com a mesma semente tem de repetir o texto"
    assert len(set(hot[1:])) == 3, "outras sementes com temperatura 1 têm de mudar o texto"
    print("sonda:", *greedy[:1], *hot, sep="\n  ")


def test_the_experiment_settings_repeat_the_same_answer(tmp_path):
    prompt = prompts.classification_prompt("PROMISE-NFR-9001", "The system shall refresh the display every 60 seconds.")
    request = LLMRequest(prompt, CallTarget("fumaca", None, 0, "classification", "PROMISE-NFR-9001"))
    first, second = (invoke(CLIENT, request, CallLog(tmp_path / str(i))).text for i in range(2))
    assert first == second
    assert ClassificationOutput.model_validate_json(first).promise_id == "PROMISE-NFR-9001"
