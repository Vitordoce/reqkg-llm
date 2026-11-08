"""Prompts versionados e o registro com o SHA-256 de cada arquivo.

Cada arquivo em prompts/ se chama <nome>_v<versão>.md. O texto antes de [system] é nota para
quem lê e não vai ao modelo. Os campos variáveis usam string.Template ($trechos, $contexto).

Uso, a partir da raiz do repositório:
    .venv/bin/python code/extraction/prompts.py          # reescreve prompts/REGISTRY.json
    .venv/bin/python code/extraction/prompts.py --check  # falha se o registro divergir
"""

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from string import Template

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel

from domain.llm_io import (
    ClassificationOutput,
    ExtractionOutput,
    RefinementOutput,
    RequirementCandidate,
    RetrievedContext,
)
from domain.models import SourceChunk
from extraction.schema import schema_sha256

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
REGISTRY_PATH = PROMPTS_DIR / "REGISTRY.json"
FILE_PATTERN = re.compile(r"^(?P<name>[a-z_]+)_v(?P<version>\d+)\.md$")

PROMPT_FILES = {
    "extraction": "extraction_v2.md",
    "refinement": "refinement_v2.md",
    "classification": "classification_v1.md",
    "classification_refinement": "classification_refinement_v1.md",
}
OUTPUT_MODELS: dict[str, type[BaseModel]] = {
    "extraction": ExtractionOutput,
    "refinement": RefinementOutput,
    "classification": ClassificationOutput,
    "classification_refinement": ClassificationOutput,
}
NO_CONTEXT = "(nenhum item de contexto)"

# Versões retiradas do disco antes de qualquer chamada real. Ficam aqui para que o registro
# mostre o hash do texto anterior. Nenhuma corrida nem saída cita estas versões.
SUPERSEDED: dict[str, list[dict[str, object]]] = {
    "extraction": [{
        "version": 1,
        "sha256": "0062847dd8ee88974ac6267c05f2aee859c0a49e46d42a1ba59694a9e739da88",
        "reason": "tirava a prioridade do verbo modal; contrariava instructions/PROTOCOLO_ANOTACAO.md",
    }],
    "refinement": [{
        "version": 1,
        "sha256": "fa1b661e7f657ebb8549d288a36eb8d6b5d453073a77c64616d17027f4b62147",
        "reason": "aceitava marcador de obrigação como prioridade; contrariava instructions/PROTOCOLO_ANOTACAO.md",
    }],
}


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: int
    file: str
    sha256: str
    system: str
    user: Template


@dataclass(frozen=True)
class RenderedPrompt:
    name: str
    version: int
    template_sha256: str
    system: str
    user: str
    output_model: type[BaseModel]

    @property
    def sha256(self) -> str:
        """Identidade do texto enviado. Indexa as respostas gravadas."""
        return hashlib.sha256(f"{self.system}\x1f{self.user}".encode("utf-8")).hexdigest()


def load(name: str) -> PromptTemplate:
    file = PROMPT_FILES[name]
    match = FILE_PATTERN.match(file)
    if match is None or match["name"] != name:
        raise ValueError(f"{file}: o nome do arquivo tem de ser {name}_v<versão>.md")
    raw = (PROMPTS_DIR / file).read_bytes()
    text = raw.decode("utf-8")
    parts = re.split(r"^\[(system|user)\]\n", text, flags=re.MULTILINE)
    if len(parts) != 5 or parts[1] != "system" or parts[3] != "user":
        raise ValueError(f"{file}: precisa de uma seção [system] seguida de uma seção [user]")
    return PromptTemplate(
        name=name,
        version=int(match["version"]),
        file=file,
        sha256=hashlib.sha256(raw).hexdigest(),
        system=parts[2].strip(),
        user=Template(parts[4].strip()),
    )


def render(name: str, **fields: str) -> RenderedPrompt:
    template = load(name)
    return RenderedPrompt(
        name=name,
        version=template.version,
        template_sha256=template.sha256,
        system=template.system,
        user=template.user.substitute(fields),
        output_model=OUTPUT_MODELS[name],
    )


def _json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def render_chunks(chunks: list[SourceChunk]) -> str:
    return "\n\n".join(
        f'<trecho source_id="{c.source_id}" chunk_id="{c.chunk_id}">\n{c.text}\n</trecho>' for c in chunks
    )


def render_context(context: RetrievedContext) -> str:
    """Só os itens. query e strategy ficam de fora, porque revelariam a condição."""
    if not context.items:
        return NO_CONTEXT
    return "\n\n".join(
        f'<item item_id="{i.item_id}" kind="{i.kind}" source_id="{i.source_id}" chunk_id="{i.chunk_id}">\n'
        f"{i.text}\n</item>"
        for i in context.items
    )


def extraction_prompt(chunks: list[SourceChunk]) -> RenderedPrompt:
    if not chunks:
        raise ValueError("a chamada de extração precisa de ao menos um chunk")
    return render("extraction", trechos=render_chunks(chunks))


def refinement_prompt(
    candidate: RequirementCandidate, context: RetrievedContext, reasons: list[str]
) -> RenderedPrompt:
    return render(
        "refinement",
        target_key=candidate.key,
        candidato=_json(candidate.model_dump(mode="json")),
        motivos="\n".join(f"- {reason}" for reason in reasons) or "- (nenhum)",
        contexto=render_context(context),
    )


def classification_prompt(promise_id: str, text: str) -> RenderedPrompt:
    return render("classification", promise_id=promise_id, texto=text)


def classification_refinement_prompt(
    promise_id: str, text: str, first: ClassificationOutput, context: RetrievedContext
) -> RenderedPrompt:
    shown = {"label": first.label.value, "rationale": first.rationale}
    return render(
        "classification_refinement",
        promise_id=promise_id,
        texto=text,
        classificacao=_json(shown),
        contexto=render_context(context),
    )


def registry() -> dict[str, dict[str, object]]:
    entries = {}
    for name in sorted(PROMPT_FILES):
        template = load(name)
        model = OUTPUT_MODELS[name]
        entries[name] = {
            "file": f"code/extraction/prompts/{template.file}",
            "version": template.version,
            "sha256": template.sha256,
            "output_model": model.__name__,
            "output_schema_sha256": schema_sha256(model),
            "superseded": SUPERSEDED.get(name, []),
        }
    return entries


def render_registry() -> str:
    return json.dumps(registry(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    content = render_registry()
    if "--check" in argv:
        if not REGISTRY_PATH.exists() or REGISTRY_PATH.read_text(encoding="utf-8") != content:
            print(f"{REGISTRY_PATH.name} desatualizado: rode .venv/bin/python code/extraction/prompts.py")
            return 1
        return 0
    REGISTRY_PATH.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
