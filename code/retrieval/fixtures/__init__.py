"""Fixture sintético da recuperação no PROMISE. Nenhum texto vem do PROMISE NFR.

promise_sintetico.jsonl imita o formato de data/processed/promise/promise_nfr.jsonl, com
promise_id na faixa 9001 em diante, que não existe no PROMISE (625 itens). O rótulo está lá só
para provar que o construtor não o lê.

SyntheticExtractionClient faz o papel do Claude na extração por projeto: para cada chamada, monta
a resposta a partir das anotações abaixo, escritas à mão, restritas aos chunks daquela chamada.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from extraction.client import LLMRequest, LLMResponse
from retrieval.promise import PromiseProject

PROMISE_JSONL = Path(__file__).with_name("promise_sintetico.jsonl")

# promise_id: (declaração, citação, tipo, atributos de qualidade, atores, entidades)
# ator: (nome, tipo, citação); entidade: (nome, tipo, citação)
TECHNICIAN = ("technician", "user_role", "technician")
COORDINATOR = ("laboratory coordinator", "stakeholder", "laboratory coordinator")
BOOKING = ("booking", "concept", "book")
AUDIT_LOG = ("audit log", "artifact", "audit log")
INSTRUMENT = ("instrument", "equipment", "instrument")
CALIBRATION = ("calibração", "evento", "calibration")

ANNOTATIONS = {
    "PROMISE-NFR-9001": ("The system shall let a technician book an instrument for a time slot.",
                         "allow a technician to book an instrument", "functional", [], [TECHNICIAN],
                         [BOOKING, INSTRUMENT]),
    "PROMISE-NFR-9002": ("The system shall e-mail the technician one day before each booking.",
                         "send a reminder e-mail to the technician", "functional", [], [TECHNICIAN], [BOOKING]),
    "PROMISE-NFR-9003": ("The booking calendar shall load in under two seconds.",
                         "load in under two seconds", "non_functional", ["performance"], [], [BOOKING]),
    "PROMISE-NFR-9004": ("Only the laboratory coordinator shall cancel bookings of other technicians.",
                         "Only the laboratory coordinator shall cancel a booking", "functional", ["security"],
                         [COORDINATOR], [BOOKING]),
    "PROMISE-NFR-9005": ("The system shall log every cancellation for two years.",
                         "record every cancellation in an audit log", "constraint", [], [], [AUDIT_LOG]),
    "PROMISE-NFR-9006": ("Only the laboratory coordinator shall read the audit log.",
                         "readable only by the laboratory coordinator", "non_functional", ["security"],
                         [COORDINATOR], [AUDIT_LOG]),
    "PROMISE-NFR-9007": ("The instrument list shall follow the institute visual identity guide.",
                         "follow the visual identity guide", "non_functional", ["usability"], [], [INSTRUMENT]),
    "PROMISE-NFR-9008": ("The system shall warn the person in charge when a calibration expires.",
                         "warn the person in charge", "functional", [], [], [INSTRUMENT, CALIBRATION]),
    "PROMISE-NFR-9101": ("The system shall export the monthly usage report as a spreadsheet.",
                         "export the monthly usage report", "functional", [], [], []),
}
# (tipo, origem, destino): só entra na resposta se as duas pontas estiverem na mesma chamada.
RELATIONS = [("depends_on", "PROMISE-NFR-9005", "PROMISE-NFR-9004")]


def _key(prefix: str, name: str) -> str:
    return prefix + "".join(part.capitalize() for part in name.replace("ç", "c").replace("ã", "a").split())


def extraction_response(project: PromiseProject, chunk_ids: list[str]) -> dict:
    promise_of = project.promise_of_chunk()
    chunk = {c.chunk_id: c for c in project.chunks}
    requirements, relations = [], []
    others: dict[tuple[str, str], dict] = {}

    def evidence(chunk_id: str, quote: str) -> dict:
        assert quote.casefold() in chunk[chunk_id].text.casefold(), (quote, chunk_id)
        return {"source_id": project.document.source_id, "chunk_id": chunk_id, "quote": quote}

    for chunk_id in chunk_ids:
        promise_id = promise_of[chunk_id]
        statement, quote, kind, qualities, actors, entities = ANNOTATIONS[promise_id]
        requirements.append({"key": "R" + promise_id[-4:], "statement": statement, "type": kind,
                             "quality_attributes": qualities, "evidence": [evidence(chunk_id, quote)]})
        for name, actor_kind, actor_quote in actors:
            actor = others.setdefault(("actors", name), {"key": _key("A", name), "name": name, "kind": actor_kind,
                                                         "evidence": []})
            actor["evidence"].append(evidence(chunk_id, actor_quote))
            relations.append({"type": "requested_by", "source_key": "R" + promise_id[-4:], "target_key": actor["key"],
                              "evidence": [evidence(chunk_id, quote)]})
        for name, entity_type, entity_quote in entities:
            entity = others.setdefault(("entities", name), {"key": _key("E", name), "name": name,
                                                            "entity_type": entity_type, "evidence": []})
            entity["evidence"].append(evidence(chunk_id, entity_quote))
    present = {promise_of[c]: c for c in chunk_ids}
    for kind, source, target in RELATIONS:
        if source in present and target in present:
            relations.append({"type": kind, "source_key": "R" + source[-4:], "target_key": "R" + target[-4:],
                              "evidence": [evidence(present[source], ANNOTATIONS[source][1])]})
    return {
        "requirements": requirements,
        "actors": [v for (group, _), v in sorted(others.items()) if group == "actors"],
        "components": [],
        "entities": [v for (group, _), v in sorted(others.items()) if group == "entities"],
        "relations": relations,
    }


@dataclass
class SyntheticExtractionClient:
    project: PromiseProject
    calls: list[LLMRequest] = field(default_factory=list)

    def describe(self) -> dict[str, object]:
        return {"provider": "synthetic", "model_id": "synthetic"}

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        response = extraction_response(self.project, list(request.meta["chunk_ids"]))
        return LLMResponse(text=json.dumps(response, ensure_ascii=False), model="synthetic", stop_reason="end_turn")
