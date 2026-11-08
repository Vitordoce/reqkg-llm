# Executor do experimento

Passo 9 de `PLAN.md`, com o desenho de `code/experiments/config/DATA_SPLIT.md`. Liga ingestão, extração, gravação no Neo4j, escolha dos alvos, recuperação por condição e refinamento, e grava os registros de `code/experiments/records.py` em `outputs/runs/<run_id>/`. Não calcula métricas: isso é de `code/experiments/metrics/`, que lê estes registros.

## Uso

A partir da raiz do repositório:

```sh
# quanto custa, sem chamar nada nem abrir o grafo
PYTHONPATH=code .venv/bin/python -m experiments.runner --dry-run --ingestion <conjunto>.toml --promise

# demonstração com o cliente sintético dos fixtures (sem modelo)
PYTHONPATH=code .venv/bin/python -m experiments.runner demo --synthetic \
    --ingestion code/ingestion/fixtures/fixture.toml \
    --promise --promise-file code/retrieval/fixtures/promise_sintetico.jsonl

# refazer uma corrida a partir do calls.jsonl dela, sem custo
PYTHONPATH=code .venv/bin/python -m experiments.runner demo-replay --replay outputs/runs/demo/calls.jsonl \
    --ingestion code/ingestion/fixtures/fixture.toml \
    --promise --promise-file code/retrieval/fixtures/promise_sintetico.jsonl

# piloto com o modelo local, sem congelamento: run_id começa por pilot-
PYTHONPATH=code .venv/bin/python -m experiments.runner pilot-01 --real --pilot --runs 1 \
    --promise --promise-projects 2 --promise-limit 5

# taxa medida no piloto, para o dry-run estimar o tempo
PYTHONPATH=code .venv/bin/python -m experiments.runner.calibrate pilot-01

# corrida do experimento
PYTHONPATH=code .venv/bin/python -m experiments.runner exp-01 --real \
    --ingestion data/raw/amostra/<conjunto>.toml --promise --freeze outputs/runs/freeze-<data>.json

# a mesma corrida, interrompida (saída 2): repetir com --resume
PYTHONPATH=code .venv/bin/python -m experiments.runner exp-01 --real \
    --ingestion data/raw/amostra/<conjunto>.toml --promise --freeze outputs/runs/freeze-<data>.json --resume
```

Um modo é obrigatório fora do dry-run: `--replay ARQ` (um `calls.jsonl` de corrida ou um `replay_index.json` de fixtures), `--synthetic` ou `--real`. `--ingestion` aceita arquivos de conjunto (`.toml`, ingeridos na hora) ou saídas da ingestão (`.json`, conferidas contra o `[chunking]` da configuração). `--promise-projects` e `--promise-items` filtram os itens classificados. `--promise-limit N` sorteia, com `evaluation.seed`, no máximo N itens no total entre os que passaram no filtro, espalhados pelos projetos (`inputs.sample_spread`: cada projeto entrega um item antes de algum entregar o segundo, e a ordem dos projetos e dos itens vem de `sha256(seed:...)`); antes de 11 de outubro ele pegava os primeiros itens de cada projeto por `promise_id`. Cada projeto com item sorteado custa uma extração do projeto inteiro: o piloto com `--promise-projects 2 --promise-limit 5` dá 22 chamadas (7 extrações do projeto e 5 classificações, mais 5 refinamentos por condição), e `--promise-limit 5` sem filtro de projeto vai a 52. O piloto usa o projeto 2 porque, com a semente da configuração, ele sorteia LF, A, SC, SE e F; o projeto 1 sorteia 5 itens funcionais, e a tarefa de categoria ficaria sem teste (`test_documented_pilot_draws_non_functional_items` confere os pilotos deste README e do roteiro). O grafo de B continua com o projeto inteiro. Saída 0 é corrida gravada, 1 é recusa antes de gravar e 2 é corrida interrompida no meio (retome com `--resume`). Na corrida real, `extraction.client.real_client` escolhe o cliente pelo `model.provider` da configuração: com `ollama`, o do experimento, o executor recusa com saída 1, antes de abrir o grafo, se o Ollama não responder, se o modelo não estiver instalado ou se o digest instalado diferir de `model.model_digest` (ver `code/extraction/README.md`). Com `anthropic`, a chave vem de `ANTHROPIC_API_KEY` no ambiente ou, se ausente, do `.env` da raiz.

## Caso e limpeza do grafo

Um caso é um documento de um conjunto de ingestão, com `case_id` igual ao `source_id`. Os chunks do caso são os do documento, agrupados por `extraction.chunks_per_call` dentro dele. O corpus que confere a evidência (regras, `refinement_targets`, `to_records`) é o do caso, porque o modelo só viu esses trechos. Um caso inválido zera os requisitos daquele documento, como `DATA_SPLIT.md` pede para as referências dele.

O grafo é limpo por corrida (`run_index`). Em cada corrida:

1. `clear_graph`, `ensure_schema` e gravação de todos os documentos e chunks dos conjuntos.
2. Extração compartilhada de cada caso, `to_records` com o corpus do caso, recusas W em `rejections.jsonl`, `write_batch`.
3. Só depois de todos os casos gravados, os alvos e os refinamentos. O grafo de B tem a corrida inteira, então um requisito de um documento pode receber contexto de outro (os artefatos da amostra descrevem um único sistema). `CandidateTarget.sources` recebe as fontes dos conjuntos da corrida.

O refinamento não é gravado no grafo. Todo contexto de B vê o mesmo estado, a extração da corrida, e a ordem dos alvos não altera nada. No fim, o banco fica com o estado da última coisa gravada (última corrida da amostra ou último projeto do PROMISE).

No PROMISE, o grafo é limpo por projeto e recebe só aquele projeto, pelo caminho de `retrieval.promise` (`extract_project` e `write_project_graph`). Os itens de cada projeto entram no documento na ordem de `sha256(seed:promise_id)`, e é essa ordem que forma as chamadas de extração (ver `code/retrieval/README.md`). A extração do projeto é compartilhada. Se ela for inválida, o grafo recebe só documento e chunks, e B recupera a partir deles. A recebe os outros itens da chamada de extração do item; B recebe esses mesmos itens e a expansão pelo grafo.

O refinamento da amostra recebe o corpus do caso (`Case.corpus`), que a regra G6 usa para recusar evidência nova fora do documento do caso.

## Ordem das condições

Em cada caso da amostra (o `source_id`) e em cada item do PROMISE (o `promise_id`), `execute.condition_order` roda primeiro `LLM-only` quando `sha256(seed:case_id)` é par e `REQKG-grounded` quando é ímpar, com `seed = evaluation.seed`. A ordem é a mesma nas três corridas de um caso. A posição fica em `condition_position` (0 rodou primeiro, 1 depois) de cada `FinalRecord` e `ClassificationRecord`, inclusive nos registros de caso inválido, e `finals.jsonl` e `classifications.jsonl` seguem a ordem de execução.

A corrida inteira segura `graph.fixture.exclusive_database`.

## Registros

Formato em `code/experiments/records.py`. Escolhas do executor:

- `finals.jsonl`: um `FinalRecord` por caso, corrida e condição. `accepted` são os refinamentos aceitos, `refused` os recusados por violação G (com as violações), `failed` os de resposta inválida ou erro de API, que mantiveram o candidato. O `CaseResult` de mesmo `target_key` dá o erro.
- Tokens em `FinalRecord` e `ClassificationRecord`: só as chamadas da própria condição, ou seja, os refinamentos. Entrada soma `input_tokens` e os dois campos de cache. A extração e a primeira classificação são compartilhadas e ficam em `calls.jsonl`, com `condition` nula.
- `contexts.jsonl`: também um `ContextRecord` por item do PROMISE e condição, com `case_id` e `target_key` iguais ao `promise_id`.
- `ClassificationRecord` com primeira classificação válida tem status `ok`. Refinamento que falha (resposta inválida ou erro de API) mantém o rótulo inicial em `final`, com `refinement_accepted = false`, sem violação, e o estado da falha em `refinement_status`; o modelo recusa um registro com falha e `final` diferente de `initial`.
- Tempo: só o `timestamp` de cada linha de `calls.jsonl`. Os outros arquivos não têm data, e o mesmo replay gera os mesmos bytes.

A corrida grava em `outputs/runs/.partial-<run_id>/` e vira `outputs/runs/<run_id>/` por rename no fim. Um `run_id` completo é sempre recusado. Um interrompido é recusado sem `--resume`, e a mensagem sugere a retomada.

## Retomada (`--resume`)

Repita o comando da corrida interrompida, com os mesmos argumentos, acrescentando `--resume` (R83). O executor:

1. confere que `.partial-<run_id>/manifest.json` existe e que `outputs/runs/<run_id>/` não existe;
2. monta o manifesto atual e recusa (saída 1, sem tocar na pasta) se mudou algum destes campos desde o início: `model_id`, `replay`, `pilot`, `runs`, `config_sha256`, `ingestion_sha256`, `promise_sha256`, `selection_sha256`, `prompts_registry_sha256`, `freeze_manifest_sha256` ou `packages`. `selection_sha256` é o SHA-256 da seleção efetiva: os `case_id` da amostra, os filtros do PROMISE normalizados (`--promise-projects`, `--promise-items`, `--promise-limit`) e os `promise_id` escolhidos por projeto. Sem ele, uma retomada com `--promise-items` diferente passava, porque o arquivo do PROMISE tem o mesmo hash (E2-2). Manifesto parcial anterior a esse campo não retoma. O pré-voo de sempre também roda (`REGISTRY.json`, regras, congelamento e `--config`);
3. junta as chamadas já gravadas (as do `calls.jsonl` parcial e as de retomadas anteriores, guardadas em `.calls-before-resume.jsonl`). Uma última linha cortada no meio da gravação é descartada, e essa chamada é refeita; linha inválida no meio do registro recusa a retomada;
4. apaga os outros registros e refaz a corrida do começo, com `clients.ResumeClient` na frente do cliente: chamada cujo prompt e alvo (caso, condição, corrida, etapa, chave) estão no registro é servida dele, e `invoke` grava a linha original sem mudar (carimbo de tempo, modelo, tokens e temperatura da chamada paga); chamada que tinha falhado na API falha de novo. Só o que falta vai à API;
5. no fim, se sobrou chamada do registro que a corrida não pediu, para com saída 2 (`ResumeDiverged`) e deixa a pasta parcial para conferência. Senão, apaga `.calls-before-resume.jsonl` e faz o rename.

O manifesto mantém o `command` original e ganha `resumptions`, uma entrada por retomada com o comando e o número de chamadas que o registro já tinha. Corrida nunca retomada não tem o campo no JSON, então os manifestos antigos continuam com os mesmos bytes. Uma retomada interrompida pode ser retomada de novo. A corrida sintética interrompida no meio e retomada gera os cinco arquivos de registro byte a byte iguais aos da corrida sem interrupção (há teste). `KeyboardInterrupt` ("interrompida pelo usuário (Ctrl-C)") e a trava do Neo4j presa saem com 2 e lembram o `--resume`. `MissingReplayError` também sai com 2, mas diz que `--resume` não resolve, porque a retomada pediria de novo a chamada sem resposta: confira se os argumentos são os da corrida gravada.

## Manifesto e recusas

`manifest.json` traz SHA-256 da configuração, de cada conjunto de ingestão (bytes canônicos do `IngestedSet`, iguais a `data/processed/ingestion/<conjunto>.json` atualizado), do JSONL do PROMISE e da seleção efetiva (`selection_sha256`, seção acima), de `REGISTRY.json` e do manifesto de congelamento, as versões de todas as distribuições do venv e do Python, e o comando. `runs` é o número de repetições da amostra, ou do PROMISE se só ele roda. `model_id` é o da configuração na corrida real, o da corrida original num replay de `calls.jsonl`, e `synthetic` no modo sintético. `replay` é verdadeiro fora da corrida real.

Antes de gravar qualquer coisa, a corrida é recusada se:

- `REGISTRY.json` não bate com os prompts em disco, ou `rules_version` difere de `RULES_VERSION`;
- em modo real, `config.ensure_runnable()` falha (com `ollama`: `model_id`, `model_digest`, `seed` ou `num_ctx` ausentes; nos dois providers, `bertscore_model` ou `bertscore_revision` vazios), ou o cliente não monta (servidor fora do ar, modelo ausente, digest diferente);
- em modo real sem `--pilot`, falta `--freeze`;
- com `--freeze`, a árvore difere do manifesto (`tools/freeze_manifest.py --check`), ou a `--config` usada não está em `code/experiments/config/` ou não está no manifesto com o mesmo SHA-256: arquivo fora do repositório, fora da pasta da configuração, fora da árvore congelada ou alterado (R77). O congelamento cobre `code/` inteiro, então o TOML de um fixture está congelado e inalterado; a exigência da pasta o recusa (E2-3);
- com `--resume`, não há `.partial-<run_id>/` ou o manifesto do início difere do atual (seção acima);
- `--pilot` sem `run_id` começando por `pilot-`, ou `pilot-` sem `--pilot`. o manifesto grava `pilot = true`, e o prefixo exigido torna a corrida piloto visível pelo nome;
- `--runs` sem `--pilot`.

## Replay

`load_replay` escolhe o `ReplayClient` do pacote de extração. Um `calls.jsonl` vai para `ReplayClient.from_calls_log`, com a chave formada pelo SHA-256 do prompt e pelo alvo (caso, condição, corrida, etapa, chave). Chamada que falhou na API falha de novo com o mesmo erro, e o uso de tokens volta junto. Assim, corrigir o executor depois de uma corrida real e refazer os registros não perde o custo. Um `replay_index.json` de fixtures vai para `ReplayClient.from_fixtures`, só pelo prompt.

## Dry-run

Conta exatamente as chamadas de extração e de classificação e renderiza esses prompts. Os refinamentos da amostra são estimados com `--targets-per-chunk` alvos por chunk (padrão 1), porque os alvos só existem depois da extração. O contexto de B na amostra é estimado com `min(retrieval.max_items, chunks)` itens do tamanho médio de um chunk. No PROMISE, o contexto de A é o exato (os outros itens da chamada), e o de B é o de A mais itens do tamanho médio de um chunk até `min(retrieval.max_items, chunks do projeto - 1)`.

PROMISE inteiro em 11 de outubro (`--dry-run --promise`): 1.986 chamadas (111 extrações, 625 classificações e 625 refinamentos por condição), cerca de 3,81 milhões de tokens de entrada (refinamento de A 0,87 milhão, de B 1,83 milhão) e teto de saída de 8,13 milhões. O número de chamadas não mudou com o contexto de A; a entrada de A subiu. A entrada inclui o schema de saída de cada chamada. Tokens são caracteres divididos por `--chars-per-token` (padrão 3,5). A saída é o teto `max_tokens` por chamada.

## Fixtures

`fixtures/` tem só material sintético. As respostas de extração de `responses/` são escritas à mão, com `"synthetic": true`, para os três documentos de `code/ingestion/fixtures/fixture.toml` com o `chunks_per_call` congelado (6). A descrição tem uma resposta inválida de propósito. `fixtures/synthetic.py` responde refinamentos e classificações por regra fixa, lendo o candidato e o contexto do próprio prompt, com uma recusa G4, uma G3 com G6 (chunk inventado), um refinamento inválido, uma recusa G2 no PROMISE e um refinamento de classificação quebrado (9002 em A). Depois de mudar prompt, texto ou agrupamento:

```sh
.venv/bin/python code/experiments/runner/fixtures/build_replays.py
```

## Testes

```sh
.venv/bin/python -m pytest code/experiments/runner -q -rs
```

A integração roda uma corrida sintética completa (três repetições e o PROMISE sintético) e dois replays dela contra o Neo4j do projeto, e pula com motivo se ele não estiver no ar.

## Lacunas

1. Resolvido: `RunManifest.pilot` marca a corrida piloto, e o prefixo `pilot-` continua exigido.
2. `PLAN.md` (passo 7, item 3) pede gravar no grafo a revisão 1 do requisito refinado. `domain.persist.to_records(..., revisions=...)` monta esses registros (identificador da declaração original, `revision = 1`, `previous_statement`), e o pacote de artefatos usa. O executor não grava o refinamento, o que mantém o grafo de B igual para todos os alvos. As métricas não leem o grafo, então nada muda nelas.
3. O uso de tokens do modo sintético é uma estimativa (caracteres / 4). Num replay de fixture por `replay_index.json`, não há uso gravado e os tokens ficam em zero.
