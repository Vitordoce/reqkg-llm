# Recuperação local

Passo 6 de `PLAN.md`, só o nível local do plano do LightRAG. Uma interface, `retrieve_context`, devolve o `domain.llm_io.RetrievedContext` do refinamento nas duas condições. O contrato confere o limite, a ordem `(rank, item_id)` e o `source_id` e `chunk_id` de cada item.

```python
from retrieval import CandidateTarget, PromiseTarget, retrieve_context

retrieve_context(target: CandidateTarget | PromiseTarget, condition: Condition,
                 config: ExperimentConfig, graph: Graph | None = None) -> RetrievedContext
```

| Arquivo | Conteúdo |
| --- | --- |
| `context.py` | `retrieve_context`, `CandidateTarget`, `PromiseTarget`, `source_chunks_context`, `extraction_call`. |
| `local.py` | `local_context`: semente (requisito e chunks da chamada), expansão por saltos com o atributo de qualidade como folha, vista, itens e seleção sob o limite sem cortar a semente. |
| `promise.py` | Construtor do PROMISE como conjunto de ingestão, extração por projeto e gravação no grafo. |
| `fixtures/` | Projeto PROMISE sintético (faixa 9001 em diante) e um cliente que faz o papel do Claude na extração. |

## Alvos

- `CandidateTarget(key, case_chunks, requirement_id=None, sources=None)`. `key` é a chave unida por `merge_outputs` (`c0-R4`). `case_chunks` são os chunks enviados a `extract_case`. `requirement_id` vem de `PersistBatch.key_to_id` e fica `None` quando a gravação recusou o candidato. `sources` restringe a recuperação a essas fontes.
- `PromiseTarget(promise_id, project)`. `project` vem de `promise.build_project` ou `promise.load_projects`, as duas com a semente de `evaluation.seed`.

## LLM-only (`source_chunks`)

O contexto são os chunks da chamada de extração em que o candidato nasceu. O agrupamento é `extraction.pipeline.group_chunks` com `extraction.chunks_per_call`, e o índice da chamada sai do prefixo da chave. `rank` é a posição do chunk na chamada. A saída é igual à de `extraction.pipeline.source_chunks_context`, e um teste confere isso. Esta condição nunca lê o grafo.

No PROMISE (decisão do autor de 11 de outubro), o contexto são os outros itens da chamada de extração do item, sem o item e sem item de texto igual ao dele (`PromiseProject.same_text_chunks`, com `domain.rules.normalize_text`). Cada item tem `kind = requirement`, `rank = 0`, `item_id` igual ao `promise_id` e o texto do chunk, exatamente como a semente de B vira item. Assim B menos A é só a expansão pelo grafo.

## REQKG-grounded (`graph_local`)

1. Semente, rank 0 (decisão do autor de 11 de outubro). O nó do requisito, se existe na vista, com os chunks que o sustentam (`SUPPORTS`), e sempre os chunks da chamada de extração. O nó do alvo não vira item, porque o candidato já está no prompt. Chunk da chamada fora do grafo é erro: os documentos do caso têm de estar gravados. Os itens de rank 0 contêm o contexto de A e nunca são cortados pelo limite: se passarem de `retrieval.max_items`, a recuperação levanta `RetrievalError` em vez de cortar.
2. Expansão sem direção até `retrieval.max_hops` saltos, pelas arestas `DEPENDS_ON`, `CONFLICTS_WITH`, `REFINES`, `DUPLICATES`, `REQUESTED_BY`, `BENEFITS_ACTOR`, `MEASURED_BY`, `ALLOCATED_TO`, `SUPPORTS`, `MENTIONS` e `RELATED_TO`. `CONTAINS` e `DERIVED_FROM` ficam de fora, porque passam pelo documento e trariam todos os chunks dele. O atributo de qualidade é folha: aparece como item, mas a expansão não continua a partir dele, então ele não traz os outros requisitos da mesma categoria. Ator continua expandindo. `rank` é a distância mínima em saltos.
3. Itens: cada nó alcançado e cada relação do contrato entre dois nós alcançados, menos `MENTIONS`. O `rank` da relação é o da ponta mais distante.
4. Proveniência: chunk aponta para ele mesmo. Requisito, ator, componente e entidade apontam para a evidência primária (menor `chunk_id`) dentro da vista. Relação aponta para a evidência primária dela. Atributo de qualidade não tem evidência própria e aponta para a evidência primária das arestas `MEASURED_BY` que chegam a ele dentro do subgrafo.
5. Texto: declaração do requisito, texto do chunk, `nome (tipo)` do ator e da entidade, nome e descrição do componente, categoria do atributo, e `ponta --tipo--> ponta` na relação, com cada ponta cortada em 160 caracteres. Nenhum texto cita a condição nem a estratégia. `query` registra a semente usada e não vai ao modelo (`extraction.prompts.render_context`).
6. Limite: os `retrieval.max_items` primeiros por `(rank, prioridade do tipo, item_id)`, com a prioridade requisito, chunk, relação, ator, componente, atributo e entidade. Todos os itens de rank 0 entram (passo 1). A saída volta à ordem `(rank, item_id)`.

Com `max_hops = 2`: rank 1 traz requisitos vizinhos, atores, atributos, componentes, entidades dos chunks da semente e outros requisitos sustentados pelos mesmos chunks. Rank 2 traz os chunks dos vizinhos, os outros chunks que mencionam as mesmas entidades, e os requisitos que dividem ator. Requisito que só divide o atributo de qualidade não entra.

Com `chunks_per_call = 6`, um documento de até seis parágrafos inteiro vira semente. A semente pode passar o limite só se `chunks_per_call` mais os chunks que sustentam o requisito passarem de `max_items` (hoje 6 contra 30).

### Vista

A vista esconde chunks (`excluded_chunks`) e fontes fora de `sources`. Ela segue a invalidação de `graph.writer.invalidate_chunks`: evidência fora da vista não conta, nó sem evidência restante sai, e requisito cuja evidência primária ficou fora sai, porque o identificador vem dela. `tainted_chunks` tira inteiro o ator, componente ou entidade com qualquer evidência nesses chunks, e `quality_attributes = False` tira os atributos de qualidade e, com eles, as arestas `MEASURED_BY`. As duas só são usadas no PROMISE.

O atributo de qualidade é um nó por categoria para o banco inteiro. Como ele é folha, não liga mais documentos de conjuntos diferentes; uma entidade com o mesmo nome ainda liga (há teste). Se o banco tiver mais de um conjunto, o experimento passa as fontes do conjunto em `sources`.

## PROMISE

`promise.build_project(..., seed)` monta um `IngestedSet` por projeto: um documento `business_document` com os textos do projeto na ordem de `sha256(f"{seed}:{promise_id}")` (`promise_order_key`, `seed = evaluation.seed`), separados por linha em branco, e um chunk por requisito (o construtor confere). O arquivo publicado vem ordenado por rótulo dentro do projeto: na ordem de `promise_id`, dois itens da mesma chamada de extração têm o mesmo rótulo em 64% dos pares, contra 26% ao acaso; com a ordem embaralhada, 27% (há teste que lê só os rótulos do arquivo real). O caminho lógico é o do JSONL com `#project-NN`, e `set_sha256` é o SHA-256 do JSONL. O rótulo nunca é lido (`load_promise_items` lê só `promise_id`, `project_id` e `text`). O tipo `business_document` é decisão do agente principal, reversível.

`promise.extract_project` faz uma extração por projeto com `extract_case`, e `promise.write_project_graph` grava documento, chunks e um lote por chamada de extração.

Na recuperação para classificar o item X, a vista é o grafo do projeto sem X: o chunk de X e os de texto igual ao dele ficam em `excluded_chunks` e em `tainted_chunks`, `sources` é o documento do projeto, e `quality_attributes = False`. Na vista, X não tem nó, então a semente são os outros chunks da chamada de extração de X. Todo chunk do projeto e todo requisito cuja evidência primária está nele viram um único item de tipo `requirement`, com `item_id` igual ao `promise_id` e o texto original (R49). Assim X nunca aparece, nenhum item cita o chunk de X, nenhum ator, componente ou entidade extraído do texto de X entra, os atributos de qualidade (categorias ISO inferidas pelo modelo, parecidas com os rótulos; resolve R54) ficam de fora, e a regra G5 dispara se alguém injetar X ou uma cópia dele no contexto (há teste dos dois lados).

## Testes

```sh
.venv/bin/python -m pytest code/retrieval -q -rs
.venv/bin/python -m pytest code/retrieval/test_retrieval_integration.py -q -s   # mostra os contextos
```

A integração carrega o fixture do domínio (`graph.fixture.write_fixture`) e o projeto PROMISE sintético 98 no Neo4j do projeto, segurando `exclusive_database`. Ela pula com motivo se o Neo4j não estiver acessível.

## Lacunas de contrato

1. `domain.persist.to_records` guarda só a evidência da primeira ocorrência de um ator, componente ou entidade com o mesmo nome na mesma resposta. Depois de `merge_outputs`, a entidade citada em duas chamadas fica só com os chunks da primeira, e as arestas `MENTIONS` das outras chamadas não chegam ao grafo. A expansão "outros chunks que mencionam a mesma entidade" perde esses caminhos. `promise.write_project_graph` contorna gravando um lote por chamada (`split_by_call`), e a regra de união entre lotes junta a evidência. A gravação da amostra anotada (`extraction.pipeline.persistable`) tem o mesmo problema.
2. `QualityAttribute` não tem proveniência própria. O item usa a evidência das arestas `MEASURED_BY` do subgrafo.
3. `RetrievedContext` não tem campo para a semente usada nem para o nó do alvo. A semente vai em `query`, que o prompt não mostra.
4. `ContextItem.kind` não distingue requisito do PROMISE de requisito extraído. O PROMISE usa `requirement` com `item_id` no formato `PROMISE-NFR-NNNN`.
5. Na amostra, o contexto de A mostra os chunks na ordem da chamada (`rank` = posição); em B, os mesmos chunks têm `rank` 0 e saem na ordem do `item_id`. O conteúdo de A está todo em B, mas a ordem de apresentação difere. No PROMISE as duas condições usam rank 0 e a mesma ordem.
