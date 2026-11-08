"""BERTScore F1 entre o requisito gerado e a referência com que ele formou par.

O modelo vem de evaluation.bertscore_model, e a revisão do Hugging Face usada fica registrada no
resultado (o hash do commit, não o nome do ramo). bert_score, torch e huggingface_hub vêm do lock de
métricas (make venv-metrics) e só são importados aqui.
"""

import importlib.metadata
from dataclasses import dataclass
from pathlib import Path

from domain.config import ContractError

MODEL_FILES = ["config.json", "*.safetensors", "pytorch_model.bin", "tokenizer.json", "tokenizer_config.json",
               "special_tokens_map.json", "vocab.txt", "vocab.json", "merges.txt", "sentencepiece.bpe.model",
               "spiece.model"]


class BertScoreUnavailable(ContractError):
    """O modelo não pode ser usado: campo vazio, biblioteca ausente ou download impossível."""


@dataclass(frozen=True)
class BertScoreModel:
    name: str
    requested_revision: str
    revision: str
    num_layers: int
    path: str

    def describe(self) -> dict[str, object]:
        versions = {}
        for package in ("bert-score", "transformers", "torch", "huggingface-hub"):
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                versions[package] = "ausente"
        return {
            "model": self.name,
            "revision": self.revision,
            "requested_revision": self.requested_revision,
            "num_layers": self.num_layers,
            "idf": False,
            "rescale_with_baseline": False,
            **{f"version {k}": v for k, v in versions.items()},
        }


def resolve(name: str, revision: str = "main", num_layers: int | None = None) -> BertScoreModel:
    if not name.strip():
        raise BertScoreUnavailable(
            "evaluation.bertscore_model está vazio na configuração da corrida. O BERTScore não é calculado sem o "
            "modelo escolhido e registrado antes da primeira corrida; preencha o campo ou rode compute com "
            "--skip-bertscore"
        )
    try:
        from bert_score.utils import model2layers
        from huggingface_hub import snapshot_download
    except ImportError as error:
        raise BertScoreUnavailable(f"dependência de métrica ausente ({error.name}); rode make venv-metrics") from None
    if num_layers is None:
        num_layers = model2layers.get(name)
        if num_layers is None:
            raise BertScoreUnavailable(
                f"o bert-score não conhece a camada padrão de {name!r}; informe --bertscore-num-layers"
            )
    try:
        path = snapshot_download(name, revision=revision, allow_patterns=MODEL_FILES)
    except Exception as online:  # noqa: BLE001 - qualquer falha do Hub cai no cache local
        try:
            path = snapshot_download(name, revision=revision, allow_patterns=MODEL_FILES, local_files_only=True)
        except Exception as cached:  # noqa: BLE001
            raise BertScoreUnavailable(
                f"não foi possível obter {name}@{revision} do Hugging Face ({online}) nem do cache local ({cached})"
            ) from None
    return BertScoreModel(name, revision, Path(path).name, num_layers, path)


def score(pairs: list[tuple[str, str]], model: BertScoreModel, batch_size: int = 64) -> list[float]:
    """F1 de cada par (candidato, referência), na ordem recebida."""
    if not pairs:
        return []
    import bert_score

    unique = sorted(set(pairs))
    _, _, f1 = bert_score.score(
        [c for c, _ in unique], [r for _, r in unique], model_type=model.path, num_layers=model.num_layers,
        batch_size=batch_size, idf=False, rescale_with_baseline=False, verbose=False,
    )
    by_pair = dict(zip(unique, f1.tolist()))
    return [by_pair[p] for p in pairs]
