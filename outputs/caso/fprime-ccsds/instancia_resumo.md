# Instância parcial do ReqKG: fprime-ccsds

> Gerado pelo ReqKG-LLM a partir dos registros da corrida, sem edição manual. Para regenerar: `PYTHONPATH=code .venv/bin/python -m deliverables pilot-caso-01 --condition REQKG-grounded --run-index 0 --name fprime-ccsds --ingestion data/raw/caso/caso_piloto.toml`.
>
> - Corrida: `pilot-caso-01`, condição `REQKG-grounded`, repetição 0 (a corrida tem 1).
> - Corrida piloto: sim. Não entra no relatório como resultado.
> - Modelo: `qwen3:14b`. Respostas gravadas (replay): não.
> - Comando da corrida: `PYTHONPATH=code .venv/bin/python -m experiments.runner pilot-caso-01 --real --pilot --runs 1 --ingestion data/raw/caso/caso_piloto.toml`.
> - Casos: `src-10c1106f4b63ce65` (`data/raw/caso/sdd/SpacePacketDeframer.md`), `src-19633f6a72a3da31` (`data/raw/caso/issues/issue_3492.md`), `src-3dd53f82b418508a` (`data/raw/caso/issues/issue_3491.md`), `src-70d9f10aa1b8a6c3` (`data/raw/caso/sdd/TcDeframer.md`), `src-7945671485477302` (`data/raw/caso/issues/issue_5485.md`), `src-974e951c733c8e7a` (`data/raw/caso/discussions/discussion_4030.md`), `src-9cfd29d516561c4e` (`data/raw/caso/issues/issue_5114.md`), `src-c9b8a83013558e6f` (`data/raw/caso/sdd/ApidManager.md`), `src-cf097721f7a993df` (`data/raw/caso/sdd/TmFramer.md`), `src-d1507de263dc69b8` (`data/raw/caso/sdd/SpacePacketFramer.md`), `src-e4ac13f99401393a` (`data/raw/caso/discussions/discussion_5027.md`), `src-e8a2e7c2f903f103` (`data/raw/caso/sdd/AesGcmDecryptor.md`).
> - Configuração: `code/experiments/config/experiment.toml` (SHA-256 `43a48015ae13d15e742d4c1fa56694dd0a89b507ee5d26fd477d5839e48d806c`).
> - Ingestão: `data/raw/caso/caso_piloto.toml` (SHA-256 `45ce02412f1aab1ad26541aa3094e3e36e78ce54d01ef6a328eb7247a13bb89d`).

A instância é o que uma carga limpa da saída final desta condição gravaria no Neo4j. Cada caso passa por `domain.persist.to_records` sobre a saída final, e os casos são unidos em ordem de `case_id` pela regra de união do grafo (`graph.properties.merge_provenance`). Documentos e chunks vêm do conjunto de ingestão. Requisito refinado e aceito entra como revisão 1, com a declaração anterior e o identificador calculado da declaração original.

SHA-256 do estado lógico: `a7b981b3abbdd56fd4c031acd8cdeed33aa58e54d5f02cdc6b9794532681c1ea`. É o mesmo valor que `graph.state.logical_state` calcula sobre o Neo4j depois de gravar estes registros num banco vazio.

Os registros completos estão em `instancia_reqkg.json`.

## Nós por classe

| Classe ReqKG | Rótulo no grafo | Nós |
| --- | --- | --- |
| Requisito | `Requirement` | 17 |
| Ator | `Actor` | 6 |
| Artefato-fonte | `SourceDocument` | 12 |
| Trecho de fonte | `SourceChunk` | 149 |
| Atributo de qualidade | `QualityAttribute` | 0 |
| Componente de software | `SoftwareComponent` | 5 |
| Entidade interna | `Entity` | 26 |

## Relações por tipo

| Relação | Tipo no grafo | De → para | Arestas |
| --- | --- | --- | --- |
| `allocated_to` | `ALLOCATED_TO` | Requirement → SoftwareComponent | 0 |
| `benefits_actor` | `BENEFITS_ACTOR` | Requirement → Actor | 1 |
| `conflicts_with` | `CONFLICTS_WITH` | Requirement → Requirement | 0 |
| `depends_on` | `DEPENDS_ON` | Requirement → Requirement | 0 |
| `derived_from` | `DERIVED_FROM` | Requirement → SourceDocument | 17 |
| `duplicates` | `DUPLICATES` | Requirement → Requirement | 0 |
| `measured_by` | `MEASURED_BY` | Requirement → QualityAttribute | 0 |
| `mentions` | `MENTIONS` | SourceChunk → Entity | 28 |
| `refines` | `REFINES` | Requirement → Requirement | 0 |
| `related_to` | `RELATED_TO` | Entity → Entity | 1 |
| `requested_by` | `REQUESTED_BY` | Requirement → Actor | 9 |
| estrutural | `CONTAINS` | SourceDocument → SourceChunk | 149 |
| estrutural | `SUPPORTS` | SourceChunk → Requirement | 19 |

## Origem dos registros com proveniência

Fato extraído tem citação em toda evidência. Fato sem citação é gravado como inferência do sistema.

| Registro | fato extraído | inferência do sistema | decisão do pesquisador |
| --- | --- | --- | --- |
| `Requirement` | 17 | 0 | 0 |
| `Actor` | 6 | 0 | 0 |
| `SoftwareComponent` | 5 | 0 | 0 |
| `Entity` | 26 | 0 | 0 |
| relações do contrato | 48 | 8 | 0 |

## Requisitos por status

| Status | Requisitos |
| --- | --- |
| rascunho (`draft`) | 17 |
| em revisão humana (`needs_review`) | 0 |
| aprovado (`approved`) | 0 |
| rejeitado (`rejected`) | 0 |

Requisitos na revisão 1 (refinamento aceito): 11.

## Fora da instância

4 recusa(s) na gravação (regras W) ficaram fora destes registros. A lista está em `relatorio_lacunas.md`.
