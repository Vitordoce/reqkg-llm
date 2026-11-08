# Instância parcial do ReqKG: fixture-sintetico

> Gerado pelo ReqKG-LLM a partir dos registros da corrida, sem edição manual. Para regenerar: `PYTHONPATH=code .venv/bin/python -m deliverables sintetico-entrevista --condition REQKG-grounded --run-index 0 --name fixture-sintetico --runs-dir code/deliverables/fixtures/runs --config code/deliverables/fixtures/experiment.toml`.
>
> - Corrida: `sintetico-entrevista`, condição `REQKG-grounded`, repetição 0 (a corrida tem 1).
> - Corrida piloto: não.
> - Modelo: `nenhum-fixture-sintetico`. Respostas gravadas (replay): sim.
> - Comando da corrida: `code/deliverables/fixtures/build.py (corrida sintética, sem chamada de modelo)`.
> - Casos: `src-339ed9b9a545ccbc` (`code/ingestion/fixtures/ata_sintetica.md`), `src-3f478d516d9d807d` (`code/domain/fixtures/corpus/entrevista_sintetica.txt`), `src-71d5fe87d6dfb68a` (`code/ingestion/fixtures/descricao_sintetica.txt`).
> - Configuração: `code/deliverables/fixtures/experiment.toml` (SHA-256 `55a6bc3ea88f82f06dba7bc42ab4f1d1f9144426fbf23e530d1dc8489954b5bc`).
> - Ingestão: `data/processed/ingestion/fixture.json` (SHA-256 `49756503282cf362a9f61a496f0fe29b6ea8e69dfa1ecf71f822b801cbe44a7f`).

A instância é o que uma carga limpa da saída final desta condição gravaria no Neo4j. Cada caso passa por `domain.persist.to_records` sobre a saída final, e os casos são unidos em ordem de `case_id` pela regra de união do grafo (`graph.properties.merge_provenance`). Documentos e chunks vêm do conjunto de ingestão. Requisito refinado e aceito entra como revisão 1, com a declaração anterior e o identificador calculado da declaração original.

SHA-256 do estado lógico: `877e01d8a9df2dcdcb09dd15367962a2c6d72e30e9363ee38d62202c9b3128c5`. É o mesmo valor que `graph.state.logical_state` calcula sobre o Neo4j depois de gravar estes registros num banco vazio.

Os registros completos estão em `instancia_reqkg.json`.

## Nós por classe

| Classe ReqKG | Rótulo no grafo | Nós |
| --- | --- | --- |
| Requisito | `Requirement` | 7 |
| Ator | `Actor` | 3 |
| Artefato-fonte | `SourceDocument` | 3 |
| Trecho de fonte | `SourceChunk` | 20 |
| Atributo de qualidade | `QualityAttribute` | 2 |
| Componente de software | `SoftwareComponent` | 1 |
| Entidade interna | `Entity` | 1 |

## Relações por tipo

| Relação | Tipo no grafo | De → para | Arestas |
| --- | --- | --- | --- |
| `allocated_to` | `ALLOCATED_TO` | Requirement → SoftwareComponent | 1 |
| `benefits_actor` | `BENEFITS_ACTOR` | Requirement → Actor | 1 |
| `conflicts_with` | `CONFLICTS_WITH` | Requirement → Requirement | 0 |
| `depends_on` | `DEPENDS_ON` | Requirement → Requirement | 2 |
| `derived_from` | `DERIVED_FROM` | Requirement → SourceDocument | 7 |
| `duplicates` | `DUPLICATES` | Requirement → Requirement | 0 |
| `measured_by` | `MEASURED_BY` | Requirement → QualityAttribute | 4 |
| `mentions` | `MENTIONS` | SourceChunk → Entity | 1 |
| `refines` | `REFINES` | Requirement → Requirement | 0 |
| `related_to` | `RELATED_TO` | Entity → Entity | 0 |
| `requested_by` | `REQUESTED_BY` | Requirement → Actor | 4 |
| estrutural | `CONTAINS` | SourceDocument → SourceChunk | 20 |
| estrutural | `SUPPORTS` | SourceChunk → Requirement | 7 |

## Origem dos registros com proveniência

Fato extraído tem citação em toda evidência. Fato sem citação é gravado como inferência do sistema.

| Registro | fato extraído | inferência do sistema | decisão do pesquisador |
| --- | --- | --- | --- |
| `Requirement` | 7 | 0 | 0 |
| `Actor` | 3 | 0 | 0 |
| `SoftwareComponent` | 1 | 0 | 0 |
| `Entity` | 1 | 0 | 0 |
| relações do contrato | 20 | 0 | 0 |

## Requisitos por status

| Status | Requisitos |
| --- | --- |
| rascunho (`draft`) | 6 |
| em revisão humana (`needs_review`) | 1 |
| aprovado (`approved`) | 0 |
| rejeitado (`rejected`) | 0 |

Requisitos na revisão 1 (refinamento aceito): 3.

## Fora da instância

6 recusa(s) na gravação (regras W) ficaram fora destes registros. A lista está em `relatorio_lacunas.md`.
