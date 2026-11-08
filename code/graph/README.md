# ReqKG no Neo4j

Passo 4 de `PLAN.md` e as consultas do passo 6. Lê os registros de `domain.persist.to_records` e as listas de `SourceDocument` e `SourceChunk`. Não depende do formato de arquivo da ingestão.

| Arquivo | Conteúdo |
| --- | --- |
| `connection.py` | `Neo4jSettings.from_env` (ambiente vale sobre `.env`) e `Graph`, por onde passa toda leitura e escrita. Recusa a porta 7687, inclusive a padrão de uma URI sem porta. |
| `schema.py` | Rótulos e chaves, `ensure_schema`, `present_schema`, `drop_schema`, `extension_procedures`. |
| `properties.py` | Conversão entre modelos do contrato e propriedades, e `merge_provenance`. |
| `writer.py` | `write_documents`, `write_batch`, `invalidate_chunks`, `remove_document`, `clear_graph`. |
| `queries.py` | `gap_report` (C1 a C3, C4 à parte, P1, P2, P5, K1 a K5) e `recorded_output`, o lado Python do teste gêmeo. |
| `state.py` | `logical_state`: contagem por rótulo e tipo e SHA-256 canônico das propriedades. |
| `fixture.py` | Fixture do domínio e `exclusive_database`, a trava de arquivo de quem apaga o grafo. |

## Esquema

Uma constraint de unicidade por rótulo, no identificador do contrato: `SourceDocument.source_id`, `SourceChunk.chunk_id`, `Requirement.requirement_id`, `Actor.actor_id`, `SoftwareComponent.component_id`, `Entity.entity_id`, `QualityAttribute.quality_attribute_id` (`qa-performance`). Uma constraint de unicidade em `relation_id` para cada um dos 11 tipos de `RelationType`. Um índice em `SourceChunk.source_id`. A imagem `neo4j:5.26.31-community` aceita as constraints de relação e não traz APOC nem GDS, o que um teste confere.

## Propriedades

- Nó com proveniência (requisito, ator, componente, entidade) e aresta do contrato guardam `origin`, `validation`, `note`, `evidence_json` (lista de evidências em JSON canônico, ordenada por `chunk_id`) e `evidence_chunk_ids`.
- Requisito guarda também `statement`, `revision`, `previous_statement`, `type`, `priority`, `verification_method`, `status`, `quality_attributes`, `quantitative_value` e `review_flags`.
- Campo nulo não vira propriedade. `properties.model_from_props` reconstrói o modelo do contrato.
- Arestas estruturais: `CONTAINS` (documento para chunk) e `SUPPORTS` (chunk para requisito, uma por chunk da evidência). Não têm `relation_id`.
- `CONFLICTS_WITH` e `DUPLICATES` vão sempre do menor para o maior identificador.

## Idempotência

- Todo nó e toda aresta entram por `MERGE` no identificador, e `SET n = props` substitui todas as propriedades. Gravar o mesmo lote duas vezes chega ao mesmo estado.
- O mesmo nó ou relação vindo de lotes diferentes segue a regra de união abaixo.
- Cada chamada é uma transação. Chunk citado que não está no grafo, chunk de outra fonte ou ponta que falta derruba a transação inteira.
- `write_batch` revalida o lote inteiro, então um `model_construct` sem evidência não chega ao Cypher. `relation_props` recusa relação sem `source_id` e `chunk_id` de novo, logo antes da escrita.
- `write_documents` recusa gravar um documento enquanto houver chunk antigo dele no grafo. O chunk antigo sai antes, por `invalidate_chunks`, com o que derivou dele.

## Regra de união entre lotes

Quando dois lotes gravam o mesmo identificador (nó ou relação):

1. A evidência é a união das duas, sem repetição, ordenada por `chunk_id`.
2. A origem só continua `extracted_fact` se os dois lados forem `extracted_fact`. Senão vira `system_inference`. Uma `researcher_decision` não é sobrescrita por extração e mantém a própria validação e nota.
3. Os demais campos (declaração, tipo, prioridade, método, status, validação, nota) ficam com o valor do lote mais novo.

Gravar o mesmo lote de novo não muda nada, porque a união com ela mesma é a mesma evidência. Implementado em `properties.merge_provenance`.

## Invalidação

`invalidate_chunks(graph, source_id, removed_chunk_ids)` recebe os chunks removidos do `diff` da ingestão:

1. Nó ou relação com evidência só nos chunks removidos sai.
2. Com evidência parcial, perde só a evidência daqueles chunks.
3. Requisito cujo chunk da evidência primária (`primary_evidence`, menor `chunk_id`) saiu é apagado com suas relações, mesmo com evidência em outro chunk. O identificador vem desse chunk, e a nova extração do parágrafo alterado grava o requisito de novo com o identificador certo. O relatório lista esses requisitos em `deleted_by_primary`.
4. `DERIVED_FROM` leva só a evidência do próprio documento e sai pela poda do item 1.
5. Os chunks saem, e com eles `CONTAINS`, `SUPPORTS` e `MENTIONS`.
6. Atributo de qualidade sem `MEASURED_BY` sai.

Repetir a chamada não muda nada. Depois da invalidação e da nova carga, o estado lógico é o mesmo de uma carga limpa da versão nova, inclusive quando o requisito tinha evidência em dois chunks.

## Teste gêmeo

`gap_report(graph)` tem de ser igual a `rules.check_all(recorded_output(batch), corpus)`, com o identificador do grafo como assunto. Os dois lados divergem por desenho em quatro pontos:

1. O grafo só tem o que passou por `to_records`. Candidato recusado (W1 a W6) não existe nele, e a violação dele some: C1, C2, C4 e P3 de um requisito sem evidência válida, P1, P5 e K2 de relação recusada.
2. Relação com ponta recusada não é gravada (W2). Ciclo K3 ou K4 e K5 que passavam por essa ponta somem.
3. `to_records` filtra a evidência que não resolve e rebaixa para inferência o fato sem citação. P2, P3 e P4 ficam em zero no grafo.
4. O grafo identifica por identificador estável, as regras por chave. Duas chaves que resolvem no mesmo identificador (W6, ator repetido) unem nós, e o grafo pode ver um ciclo que as regras não veem (`fixture.aliased_output`).

O grafo também acumula lotes de casos diferentes. As regras olham uma resposta por vez. Por isso as métricas leem o `ExtractionOutput` e não o grafo (`DATA_SPLIT.md`).

## Segurança

- `Graph` recusa a porta 7687, pela URI e pela porta que o servidor reporta. Nesta máquina ela é do container `jota-context-neo4j`.
- `clear_graph` recusa apagar um banco com nó de rótulo que não é do ReqKG.
- Testes de integração e `python -m graph fixture` seguram `exclusive_database`, uma trava de arquivo em `code/graph/.neo4j-test.lock`, porque outros processos de pytest rodam a mesma suíte contra o mesmo banco.

## Lacunas de contrato

Resolvidas em 10 de outubro de 2026: requisito sem a evidência primária sai do grafo (item 3 da invalidação), e `to_records` dá a cada `DERIVED_FROM` só a evidência do próprio documento.

Abertas:

1. O plano do LightRAG pede versão e data de ingestão em `SourceDocument`. O contrato não tem os campos. O grafo não grava data, porque ela quebraria a igualdade de estado lógico. O `sha256` marca a versão.
2. A regra de união entre lotes acima ainda precisa entrar em `PLAN.md`.

## Comandos

```sh
make neo4j-up && make neo4j-wait
.venv/bin/python -m pytest code/graph -q -rs
PYTHONPATH=code .venv/bin/python -m graph fixture
```

Os testes de integração pulam, com o motivo, se o Neo4j não estiver acessível ou se `NEO4J_URI` apontar para a porta 7687.
