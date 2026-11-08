# Extração, refinamento e classificação

Passos 5 e 7 de `PLAN.md`, do lado do modelo. O pacote importa o contrato de `code/domain/` e não o altera. A gravação no Neo4j e a recuperação local são de `code/graph/` e `code/retrieval/`.

## Peças

| Arquivo | Conteúdo |
| --- | --- |
| `prompts/*_vN.md` | Prompts de extração, refinamento, classificação do PROMISE e refinamento da classificação. O texto antes de `[system]` é nota e não vai ao modelo. |
| `prompts/REGISTRY.json` | Versão e SHA-256 de cada prompt e do schema de saída, e em `superseded` as versões retiradas. Gerado por `prompts.py`. |
| `schema.py` | Schema de saída enviado ao modelo: o do domínio, sem `$defs` nem `$ref`, passado por `anthropic.transform_schema`. O mesmo schema vai ao Ollama e à Anthropic. |
| `client.py` | Protocolo `LLMClient`, `OllamaClient` (o do experimento), `AnthropicClient`, `real_client` (escolhe pelo `model.provider`), `ReplayClient`, `CallLog` e `invoke`, que grava cada chamada em `<run_dir>/calls.jsonl` no formato `experiments.records.CallRecord`. |
| `pipeline.py` | `extract_case`, `refine_candidate`, `classify_item`, `refine_classification`, `SinglePassGuard` e auxiliares. |
| `fixtures/` | Textos sintéticos, respostas escritas à mão (`responses/`, todas com `"synthetic": true`), cenários e o índice de respostas por SHA-256 do prompt. |

## Regras que o código garante

- Toda chamada vira um `CaseResult`. Resposta que não valida no contrato vira `invalid_output` com o erro do Pydantic. Falha da API vira `api_error`. Na extração, uma chamada inválida invalida o caso inteiro.
- Extração e primeira classificação são compartilhadas pelas duas condições: o `CaseResult` delas tem `condition` e `target_key` nulos. Refinamento recusado fica com status `ok`, a resposta proposta e as violações G em `CaseResult.violations`. O `CaseResult` de refinamento guarda em `target_key` a chave do alvo (o `promise_id` na classificação), também quando a chamada falhou.
- Os chunks de um caso são agrupados por `extraction.chunks_per_call` da configuração, na ordem `(source_id, index)`. Cada grupo é uma chamada com prefixo `c0`, `c1`, ..., e as respostas são unidas com `merge_outputs`.
- O refinamento chama o modelo uma vez por alvo (caso, condição, corrida, chave). `SinglePassGuard` levanta `SecondRefinementError` antes de uma segunda chamada, inclusive quando a primeira falhou, e reconstrói a contagem a partir do `calls.jsonl` da corrida.
- Com violação G de `check_against`, o refinamento é recusado e o candidato original fica. `refine_candidate` recebe `corpus`, o `CorpusIndex` dos chunks do documento do caso, que G6 usa para conferir a evidência nova e a prioridade ou o método preenchidos. `refine_classification` passa o texto do item, que G5 compara com o texto de cada item de contexto.
- Falha do refinamento da classificação (resposta inválida ou erro de API) devolve a primeira classificação, e o `CaseResult` guarda o estado; o executor o copia para `ClassificationRecord.refinement_status`.
- O prompt de refinamento é o mesmo nas duas condições. Só os itens de contexto mudam. No PROMISE, as duas condições recebem os outros itens da chamada de extração, e B recebe também a expansão pelo grafo; a nota de `classification_refinement_v1.md` foi revista em 11 de outubro, sem mudar o texto enviado. `query` e `strategy` do `RetrievedContext` não são mostrados ao modelo, porque revelariam a condição.
- O registro de chamadas guarda o SHA-256 do prompt, a versão, o modelo, os parâmetros, o uso de tokens, a resposta bruta, o carimbo de tempo, o estado da temperatura e, no Ollama, a semente, o digest dos pesos e os tempos do servidor (`timing`). A chave de API nunca entra. Cada linha é validada por `experiments.records.CallRecord` ao gravar e ao ler. A extração exige `meta.chunk_ids`, e o refinamento os itens e a estratégia do contexto; `invoke` confere isso antes de fazer a chamada.
- Prioridade e método de verificação seguem a seção de anotação de `instructions/PROTOCOLO_ANOTACAO.md`: só com sinal explícito no texto, citado numa evidência. O verbo da necessidade ("deve", "tem de") sozinho não sustenta prioridade. Por isso extração e refinamento estão na versão 2. As versões 1 saíram do disco antes de qualquer chamada real e ficam no registro só com versão, hash e motivo.

## Comandos

A partir da raiz do repositório:

```sh
.venv/bin/python -m pytest code/extraction
.venv/bin/python code/extraction/prompts.py --check
.venv/bin/python code/extraction/fixtures/build_replays.py --check
```

Depois de mudar um prompt, rode os dois scripts sem `--check`. Uma resposta gravada que não corresponde mais ao prompt aparece como `MissingReplayError`.

## Ligar a chamada real (Ollama)

Decisão do autor em 13 de outubro de 2026: o experimento usa o Qwen3 14B local pelo Ollama, sem custo. `[model]` de `code/experiments/config/experiment.toml` traz `provider = "ollama"`, `base_url`, `model_id`, `model_digest`, `temperature`, `seed`, `num_ctx` e `max_tokens`.

1. `ollama serve` no ar (ou o app do Ollama aberto) e `ollama pull qwen3:14b`.
2. Rodar `REQKG_REAL_CALL=1 .venv/bin/python -m pytest code/extraction/test_extraction_real_call.py -s -rs`. Sem a variável, o teste pula, para que `make test` não carregue o modelo. Com ela, pula dizendo o que falta se o servidor não responder, se o modelo não estiver instalado ou se o digest for outro.

`OllamaClient` usa a API nativa `POST /api/chat`, não a compatível com OpenAI. O corpo leva `stream: false`, `think: false` (o modo de pensamento do Qwen3 desligado; com ele ligado, a documentação da API diz que o raciocínio vem em `message.thinking`), `format` com o schema de `schema.py` e `options` com `temperature`, `seed`, `num_ctx` e `num_predict` (o `max_tokens` da configuração). O Ollama converte o schema numa gramática, então a resposta segue o schema sem o schema ir no prompt. As restrições que `transform_schema` move para a descrição (`pattern`, `minLength`, `minimum`) não entram na gramática e continuam conferidas pela validação do domínio.

Ao montar, o cliente lê `/api/tags` e `/api/version`. Recusa (`ClientConfigError`, o executor sai com 1) se o servidor não responder ("rode `ollama serve`"), se o modelo não estiver instalado ("rode `ollama pull`") ou se o digest instalado diferir de `model_digest`. Numa chamada:

- erro de conexão vira `api_error` com "rode `ollama serve`"; HTTP 404 sugere `ollama pull`; HTTP 400 citando `temperature`, `seed` ou opção marca `temperature.accepted = false`;
- resposta com `message.thinking` vira `api_error`: o pensamento não foi desligado;
- resposta em que `prompt_eval_count + eval_count` chega a `num_ctx` vira `api_error`, porque o Ollama corta o prompt que não cabe na janela sem dar erro. O `prompt_eval_count` conta o prompt inteiro mesmo quando o prefixo vem do cache (conferido em 14 de outubro), então a soma é a ocupação real da janela;
- o registro traz `usage.input_tokens` (`prompt_eval_count`), `usage.output_tokens` (`eval_count`), `timing` (`total_s`, `load_s`, `prompt_eval_s`, `eval_s`, de `total_duration`, `load_duration`, `prompt_eval_duration` e `eval_duration`), `stop_reason` (`done_reason`: `stop` ou `length`), e `temperature` com `value`, `seed`, `transport = "options"`, `sent` e `accepted`. `client` traz o digest, a versão do servidor, `num_ctx` e `think`.

`accepted = true` quer dizer que o servidor respondeu sem erro com as opções no corpo; o Ollama não devolve os valores aplicados. A aplicação foi conferida pela fumaça de 14 de outubro, com o Ollama 0.32.4 e o `qwen3:14b` do digest registrado: com temperatura 0, duas chamadas iguais deram o mesmo texto, também com sementes diferentes; com temperatura 1, a mesma semente repetiu o texto e sementes diferentes o mudaram. Os prompts do experimento são previsíveis demais para mostrar isso (a extração saiu igual nos primeiros 160 tokens com temperatura 1 e sementes 11 e 12), por isso a fumaça usa uma sonda de texto livre. O `format` foi respeitado em todas as respostas, e nenhuma trouxe `thinking`; não foi preciso contorno com o schema no prompt.

## Chamada real pela Anthropic (fora do experimento)

`provider = "anthropic"` continua aceito, sem `model_digest`, `seed` nem `num_ctx` (a configuração recusa esses campos nesse provider). A chave vem de `ANTHROPIC_API_KEY` no ambiente ou numa linha do `.env` da raiz (fora do pacote de entrega). `extraction.client.find_api_key` lê o ambiente e, se a variável estiver vazia ou ausente, o `.env`, com o mesmo leitor de `graph.connection` (R79). O valor nunca entra em mensagem, registro nem `describe()`. O teste de fumaça atual é do Ollama.

O SDK `anthropic==1.13.0` não tem parâmetro `temperature` em `messages.create`. A temperatura da configuração vai por `extra_body`, e cada linha do registro traz `temperature` com `sent` e `accepted`. `accepted` é `true` quando a API respondeu sem erro com o campo no corpo, `false` quando recusou com erro 400 citando `temperature`, e `null` quando falhou por outro motivo ou o cliente é de replay. Resposta sem erro não prova que o valor foi aplicado, porque o SDK não devolve essa confirmação. Se a API recusar o campo, a decisão sobre a temperatura fica com o autor.

Uma corrida real pode ser reproduzida sem custo com `ReplayClient.from_calls_log(<run_dir>/calls.jsonl)`, que o executor usa no `--replay`. Ele indexa pelo SHA-256 do prompt e pelo alvo (caso, condição, corrida, etapa, chave), então cada repetição recebe a própria resposta. Chamada que falhou na API falha de novo com o mesmo erro, e o uso de tokens gravado volta junto. `ReplayClient.from_fixtures` indexa só pelo prompt e serve às respostas escritas à mão; quando falta uma resposta, a mensagem aponta a pasta `responses/` e o `build_replays.py` ao lado do `replay_index.json` usado (o da extração ou o do executor). A retomada de corrida do executor usa a mesma chave por alvo (`replay_key`), e `invoke` grava sem mudar a linha original quando a resposta traz `recorded`.
