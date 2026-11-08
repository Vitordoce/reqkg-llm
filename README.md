# ReqKG-LLM

Protótipo do framework que integra um modelo de linguagem local e um grafo de conhecimento para extrair, classificar e refinar requisitos de software. Trabalho de graduação de Vitor de Jesus Caetano, Instituto Tecnológico de Aeronáutica, 2026. Orientador: Prof. Dr. Inaldo Capistrano Costa.

Este repositório traz o código e o material das corridas citadas no relatório. Não traz o relatório, a apresentação nem o conversor de LaTeX.

## Código

`code/` é o framework:

- `ingestion` lê documentos e produz chunks com identificador estável
- `extraction` chama o modelo e valida a saída com Pydantic
- `graph` grava e consulta o ReqKG no Neo4j
- `retrieval` monta o subgrafo usado no refinamento
- `experiments` executa as duas condições, `LLM-only` e `REQKG-grounded`, e calcula as métricas
- `domain` é o contrato: tipos, regras e schemas

O modelo das corridas foi o Qwen3 14B, via Ollama, tag `qwen3:14b`, digest `bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`. Temperatura 0 e semente `20261010`, em `code/experiments/config/experiment.toml`.

## Estudo de caso

`data/raw/caso/` é o corpus do subsistema `Svc/Ccsds` do F´ (NASA/JPL), commit `fd0ef09c177dc4fd8070d2c3576da1a4a426873a`, licença Apache-2.0. A origem, o recorte e a pseudonimização estão em `data/raw/caso/SOURCE.md`. Nomes de usuário do GitHub foram trocados por `stakeholder-01` a `stakeholder-18`.

A corrida executada é `pilot-caso-01`, sobre `data/raw/caso/caso_piloto.toml` (12 documentos). Os artefatos gerados estão em `outputs/caso/fprime-ccsds/`: esboço de SRS, instância do grafo, matriz de proveniência e relatório de lacunas.

## Corridas

Cada pasta em `outputs/runs/` guarda o manifesto, as métricas e o `calls.jsonl`, que é o registro de cada chamada: prompt e resposta. Dá para inspecionar a chamada sem rodar o modelo de novo.

| Pasta | O que é |
| --- | --- |
| `outputs/runs/promise-01/` | PROMISE NFR, 625 requisitos. Métricas de classificação |
| `outputs/runs/exp-01/` | Amostra anotada, 6 artefatos e 54 requisitos, 3 repetições. Métricas, BERTScore e pareamento cego em `metrics/pairing/` |
| `outputs/runs/pilot-caso-01/` | Estudo de caso F´ `Svc/Ccsds` |

O pareamento cego é o da amostra (`exp-01`). O estudo de caso não tem planilha de pareamento. As planilhas `sheet_run0.toml`, `sheet_run1.toml` e `sheet_run2.toml` estão travadas pelos `lock_run*.json`.

## Rodar

Python 3.14, o mesmo do `requirements.lock`. Os testes também leem `tools/freeze_manifest.py`, `data/processed/ingestion/fixture.json`, o JSONL derivado do PROMISE, o modelo vazio em `data/raw/amostra/TEMPLATE` e `instructions/ROTEIRO_CORRIDA.md`.

```sh
make venv
make test
cp .env.example .env   # troque NEO4J_PASSWORD; mínimo de 8 caracteres
make neo4j-up && make neo4j-wait && make graph-fixture
```

`make neo4j-up` recusa a senha de exemplo. As portas locais são 17474 e 17687. O código não usa a porta 7687.

O `calls.jsonl` guarda o prompt e a resposta de cada chamada. Dá para ler a corrida sem chamar o modelo. Refazer a corrida pelo executor pede também os mesmos argumentos de entrada da vez original. O modo de cada comando está em `code/experiments/runner/README.md`. Uma corrida nova com o modelo local pede o Ollama e a tag `qwen3:14b`.

## Licenças

O código deste repositório não tem licença de reúso. A leitura e a reprodução do experimento estão autorizadas. Outro uso depende de autorização do autor.

O corpus do F´ segue a Apache-2.0 do repositório [nasa/fprime](https://github.com/nasa/fprime). Os registros de `promise-01` contêm texto do PROMISE NFR (Cleland-Huang et al., 2007, Zenodo 10.5281/zenodo.268542), sob CC BY-SA 3.0.
