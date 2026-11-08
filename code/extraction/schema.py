"""Formato de saída enviado à API, gerado dos modelos do domínio.

O schema do Pydantic usa $defs e $ref. O schema enviado não tem referências: cada $ref é
substituído pela definição. Depois, anthropic.transform_schema move para a descrição as
restrições que a saída estruturada não aplica (pattern, minLength, minimum). Essas restrições
continuam valendo na validação do domínio, que recusa a resposta que as violar.
"""

import copy
import hashlib
import json
from typing import Any

from anthropic import transform_schema
from pydantic import BaseModel


def inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    defs = schema.get("$defs", {})

    def resolve(node: Any, trail: tuple[str, ...]) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if ref is not None:
                name = ref.removeprefix("#/$defs/")
                if name in trail:
                    raise ValueError(f"schema recursivo em {name}: não dá para eliminar a referência")
                merged = {**copy.deepcopy(defs[name]), **{k: v for k, v in node.items() if k != "$ref"}}
                return resolve(merged, trail + (name,))
            return {k: resolve(v, trail) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [resolve(item, trail) for item in node]
        return node

    return resolve(schema, ())


def output_schema(model: type[BaseModel]) -> dict[str, Any]:
    return transform_schema(inline_refs(model.model_json_schema()))


def schema_sha256(model: type[BaseModel]) -> str:
    text = json.dumps(output_schema(model), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
