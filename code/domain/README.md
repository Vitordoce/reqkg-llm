# Contrato do ReqKG-LLM

Revisto em 10 de outubro de 2026 depois da revisão dos dias 1 e 2 (achados em `PROGRESS.md`). Ingestão, grafo, extração, recuperação, refinamento e experimento importam daqui e não editam nada aqui. Mudança no contrato exige registro em `PROGRESS.md` e nova rodada dos testes.

`code/` não é pacote Python, porque `code` já é módulo da biblioteca padrão. O `pyproject.toml` põe `code/` no caminho de importação, então os pacotes de topo são `domain`, `benchmarks`, `ingestion`, `graph`, `extraction`, `retrieval`, `refinement` e `experiments`. Não use `datasets` como nome de pasta. Ele colide com o pacote do HuggingFace do qual o BERTScore depende.

O desenho do experimento que este contrato implementa está em `code/experiments/config/DATA_SPLIT.md`.

## Onde está cada coisa

| Arquivo | Conteúdo |
| --- | --- |
| `enums.py` | Vocabulário fechado: tipo, MoSCoW, método de verificação, categorias ISO/IEC 25010 e o nome de cada uma na edição de 2023, rótulos do PROMISE, origem, relações, pontas permitidas, condições e a origem do contexto de cada condição. |
| `ids.py` | Identificadores estáveis e o caminho canônico da fonte. Use estas funções. Não invente outro formato. |
| `models.py` | O que pode ser gravado no Neo4j. Todo requisito e toda relação exigem `source_id` e `chunk_id`. O requisito confere o próprio identificador e aceita uma única revisão. |
| `llm_io.py` | Resposta da extração (`ExtractionOutput`), união das chamadas de um caso (`merge_outputs`), contexto (`RetrievedContext`), refinamento (`RefinementOutput`), classificação do PROMISE (`ClassificationOutput`) e registro de cada chamada (`CaseResult`). |
| `rules.py` | Regras C1 a C4, P1 a P5 e K1 a K5, `is_complete`, `refinement_targets` e o índice do corpus. |
| `persist.py` | `to_records`: converte um `ExtractionOutput` em registros graváveis, deriva as relações de sistema e devolve as recusas (regras W). Com `revisions`, grava os refinados aceitos como revisão 1, com o identificador da declaração original. |
| `violations.py` | O tipo `Violation`, comum a regras e refinamento. |
| `config.py` | `ExperimentConfig`. `refinement.max_calls` só aceita 1, `conditions` só aceita o par `LLM-only` e `REQKG-grounded`, e `repetitions.structural_sample` exige pelo menos 3. |
| `serialization.py` | `load_json`, `load_toml`, `parse` com erro que nomeia arquivo e campo, e `canonical_json` para bytes determinísticos. |
| `schema/` | JSON Schema gerado, para mandar ao Claude como formato de saída, e `RULES.md` com todas as regras C, P, K, G (G1 a G6) e W. |
| `fixtures/` | Texto sintético de desenvolvimento, fixtures válidos e inválidos, todos gerados por `fixtures/build.py`. |

## Regras de identidade

- Fonte: `ids.source_id(caminho)`. O caminho é relativo à raiz do repositório e passa por `ids.canonical_path` (NFC, barras normais, sem `./`, sem `..`, nunca absoluto). O SHA-256 do conteúdo marca a versão.
- Chunk: `ids.chunk_id(source_id, texto, ocorrência)`. Com `chunking.strategy = "paragraph"`, um parágrafo alterado só invalida o próprio chunk. `ocorrência` conta repetições do mesmo texto no documento. A ingestão grava o texto em NFC.
- Requisito: `ids.requirement_id(source_id, chunk_id, declaração)`, calculado com a evidência primária (`models.primary_evidence`, a de menor `chunk_id`) e a declaração original. O refinamento mantém o identificador: a revisão 1 guarda a declaração anterior em `previous_statement`.
- Ator, componente e entidade: hash do nome normalizado. Dois atores com o mesmo nome e tipos diferentes: vale o primeiro, e o segundo vira recusa W4.
- Relação: `ids.relation_id(tipo, origem, destino)`. Em `conflicts_with` e `duplicates` a ordem das pontas não importa.

## O que o modelo não propõe

`derived_from` e `mentions` saem da evidência, e `measured_by` sai de `quality_attributes`. O modelo não pode propor essas três relações. `ExtractionOutput` recusa, e `persist.to_records` as deriva.

## Recusa do refinamento

`RefinementOutput.check_against(contexto, original, corpus)` recebe o `CorpusIndex` só com os chunks do documento do caso. Além de G1 a G4, a regra G6 (11 de outubro) recusa evidência nova que não passa em `corpus.supports` (chunk de outro documento, mesmo que esteja no contexto de B, ou citação que não aparece no chunk) e prioridade ou método de verificação que eram nulos e foram preenchidos sem nenhuma evidência nova válida. `ClassificationOutput.check_against(contexto, original, texto_do_item)` dispara G5 pelo `promise_id` e também por item de contexto com texto igual ao do item depois de `rules.normalize_text` (as duplicatas do PROMISE). `RULES_VERSION` não mudou: G5 e G6 são regras de recusa, não de medida.

## O que vai ao grafo

Só evidência que resolve no corpus e cuja citação, quando existe, aparece no chunk (`CorpusIndex.supports`). Fato extraído sem citação vira inferência do sistema. Candidato com confiança abaixo de `review.confidence_threshold` recebe `low_confidence` e fica em `needs_review`. As métricas não passam pelo grafo: leem o `ExtractionOutput` final de cada condição.

## Comandos

A partir da raiz do repositório:

```sh
.venv/bin/python -m pytest code
.venv/bin/python code/domain/fixtures/build.py --check
.venv/bin/python code/domain/export_schema.py --check
```

Depois de mudar um modelo ou uma regra, rode os dois scripts sem `--check` e confira o diff dos arquivos gerados.
