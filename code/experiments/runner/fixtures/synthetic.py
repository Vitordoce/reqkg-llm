"""Cliente sintético que faz o papel do Claude nos testes do executor. Nada aqui veio de modelo.

- Extração da amostra: resposta gravada em responses/, achada pelo SHA-256 do prompt (replay_index.json).
- Extração do PROMISE sintético: retrieval.fixtures.extraction_response, escrita à mão por projeto.
- Refinamento: lê o candidato e os itens de contexto do próprio prompt e aplica uma política fixa
  (REFINEMENT_POLICY). O padrão completa a evidência com o primeiro trecho do contexto.
- Classificação: rótulos fixos em FIRST_LABELS e REFINED_LABELS, alguns errados de propósito, e um
  refinamento quebrado (BROKEN_CLASSIFICATION).

O uso de tokens é uma estimativa (caracteres / 4), marcada em describe(), só para exercitar a
contagem por condição.
"""

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from domain import ids
from domain.enums import Condition
from extraction.client import LLMRequest, LLMResponse, MissingReplayError, ReplayClient
from experiments.runner.fixtures import ATA, ENTREVISTA, REPLAY_INDEX
from retrieval.fixtures import extraction_response
from retrieval.promise import PromiseProject, case_id

LLM_ONLY, REQKG = Condition.LLM_ONLY, Condition.REQKG_GROUNDED

# (documento, chave, condição) -> ação. Sem entrada, a ação é "complete".
REFINEMENT_POLICY = {
    (ENTREVISTA, "c0-R2", REQKG): "lose_type",        # G4: recusado em B, aceito em A
    (ATA, "c1-R3", LLM_ONLY): "out_of_context",       # G3: recusado em A, aceito em B
    (ATA, "c0-R1", LLM_ONLY): "invalid_json",         # refinamento inválido: o candidato original fica
}
FIRST_LABELS = {
    "PROMISE-NFR-9001": "F", "PROMISE-NFR-9002": "F", "PROMISE-NFR-9003": "PE", "PROMISE-NFR-9004": "F",
    "PROMISE-NFR-9005": "SE", "PROMISE-NFR-9006": "SE", "PROMISE-NFR-9007": "US", "PROMISE-NFR-9008": "F",
    "PROMISE-NFR-9101": "F",
}
REFINED_LABELS = {
    ("PROMISE-NFR-9004", REQKG): "SE",
    ("PROMISE-NFR-9007", REQKG): "LF",
    ("PROMISE-NFR-9005", LLM_ONLY): "L",
}
# Em B, o refinamento de 9006 cita o próprio item, que não está no contexto: violação G2.
CITES_ITSELF = {("PROMISE-NFR-9006", REQKG)}
# Em A, o refinamento de 9002 volta como JSON quebrado: o rótulo inicial fica e a falha é registrada.
BROKEN_CLASSIFICATION = {("PROMISE-NFR-9002", LLM_ONLY)}

ITEM = re.compile(r'<item item_id="([^"]*)" kind="([^"]*)" source_id="([^"]*)" chunk_id="([^"]*)">\n(.*?)\n</item>',
                  re.DOTALL)
QUOTE_CHARS = 48


def _squash(text: str) -> str:
    return " ".join(text.split()).casefold()


def context_items(user_prompt: str) -> list[dict[str, str]]:
    return [dict(zip(("item_id", "kind", "source_id", "chunk_id", "text"), match))
            for match in ITEM.findall(user_prompt)]


def candidate_of(user_prompt: str) -> dict:
    start = user_prompt.index("Candidato:\n") + len("Candidato:\n")
    end = user_prompt.index("\n\nMotivos da seleção:")
    return json.loads(user_prompt[start:end])


def _quote(text: str) -> str:
    """Começo literal do texto, cortado num espaço, para servir de citação contínua."""
    if len(text) <= QUOTE_CHARS:
        return text
    cut = text.rfind(" ", 0, QUOTE_CHARS)
    return text[:cut if cut > 0 else QUOTE_CHARS]


def refinement_response(candidate: dict, items: list[dict[str, str]], action: str) -> str:
    if action == "invalid_json":
        return "{\"target_key\": "
    revised = dict(candidate)
    chunks = [i for i in items if i["kind"] == "source_chunk"]
    texts = {i["chunk_id"]: i["text"] for i in chunks}
    kept = [e for e in candidate["evidence"]
            if not (e["chunk_id"] in texts and e.get("quote") and _squash(e["quote"]) not in _squash(texts[e["chunk_id"]]))]
    used: list[str] = []
    if not kept and chunks:
        first = chunks[0]
        kept = [{"source_id": first["source_id"], "chunk_id": first["chunk_id"], "quote": _quote(first["text"])}]
        used = [first["item_id"]]
    revised["evidence"] = kept
    if action == "lose_type":
        revised["type"] = None
    elif action == "out_of_context":
        revised["evidence"] = kept + [{"source_id": "src-0000000000000000", "chunk_id": "chk-ffffffffffffffff",
                                       "quote": None}]
    return json.dumps({"target_key": candidate["key"], "revised": revised, "used_context_ids": used},
                      ensure_ascii=False, sort_keys=True)


def classification_response(promise_id: str, label: str, used: list[str]) -> str:
    return json.dumps({"promise_id": promise_id, "label": label, "rationale": None, "used_context_ids": used},
                      sort_keys=True)


@dataclass
class SyntheticClient:
    projects: Mapping[str, PromiseProject] = field(default_factory=dict)
    extraction: ReplayClient = field(default_factory=lambda: ReplayClient.from_fixtures(REPLAY_INDEX))
    calls: list[LLMRequest] = field(default_factory=list)

    @classmethod
    def for_projects(cls, projects: list[PromiseProject]) -> "SyntheticClient":
        return cls(projects={case_id(p): p for p in projects})

    def describe(self) -> dict[str, object]:
        return {"provider": "synthetic", "model_id": "synthetic", "usage": "estimativa sintética, caracteres / 4"}

    def _text(self, request: LLMRequest) -> str:
        target, prompt = request.target, request.prompt
        if target.stage == "extraction":
            if target.case_id in self.projects:
                chunk_ids = list(request.meta["chunk_ids"])
                return json.dumps(extraction_response(self.projects[target.case_id], chunk_ids), ensure_ascii=False)
            return self.extraction.complete(request).text
        if target.stage == "refinement":
            document = {ids.source_id(path): path for path in (ENTREVISTA, ATA)}.get(target.case_id)
            action = REFINEMENT_POLICY.get((document, target.key, target.condition), "complete")
            return refinement_response(candidate_of(prompt.user), context_items(prompt.user), action)
        if target.stage == "classification":
            if target.key not in FIRST_LABELS:
                raise MissingReplayError(f"sem rótulo sintético para {target.key}")
            return classification_response(target.key, FIRST_LABELS[target.key], [])
        if target.stage == "classification_refinement":
            if (target.key, target.condition) in BROKEN_CLASSIFICATION:
                return "{\"promise_id\": "
            label = REFINED_LABELS.get((target.key, target.condition), FIRST_LABELS[target.key])
            items = context_items(prompt.user)
            used = [items[0]["item_id"]] if target.condition is REQKG and items else []
            if (target.key, target.condition) in CITES_ITSELF:
                used = [target.key]
            return classification_response(target.key, label, used)
        raise MissingReplayError(f"etapa sem resposta sintética: {target.stage}")

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        text = self._text(request)
        prompt_chars = len(request.prompt.system) + len(request.prompt.user)
        usage = {"input_tokens": math.ceil(prompt_chars / 4), "output_tokens": math.ceil(len(text) / 4)}
        return LLMResponse(text=text, model="synthetic", stop_reason="end_turn", usage=usage)
