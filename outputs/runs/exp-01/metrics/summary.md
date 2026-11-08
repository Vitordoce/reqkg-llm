# Métricas da corrida exp-01

Gerado por `experiments.metrics`. Não editar à mão. O comando abaixo, a partir da raiz do repositório, regenera cada número deste arquivo e das tabelas CSV da mesma pasta:

```sh
PYTHONPATH=code .venv/bin/python -m experiments.metrics exp-01 compute --ingestion data/raw/amostra/amostra.toml --reference data/raw/amostra
```

## Entradas

- corrida: `outputs/runs/exp-01`, model_id `qwen3:14b`, replay False, runs 3
- corrida piloto: não
- configuração: `code/experiments/config/experiment.toml`, SHA-256 `43a48015ae13d15e742d4c1fa56694dd0a89b507ee5d26fd477d5839e48d806c` (confere com o manifesto)
- registro de prompts: SHA-256 `339706257de53c8d6171dc8a464cb928498ce0d7228f70c6894ca337b21b8651`
- manifesto de congelamento: SHA-256 `df8ba8f609b0db7b0b8bc1cea885e1cce2cddf03cbb647ca529c38ca279e47d9`
- ingestão: `data/raw/amostra/amostra.toml`, ingerido em memória, SHA-256 dos bytes canônicos, SHA-256 `8837c8136f327a8ddc0312afbe82583507d6c218fe3d2649d16fe6a51baf47b0`
- referência: `data/raw/amostra`
-   a01.txt: SHA-256 `0f664f830220321f698a52f374b7fb690e2ffa84e6104c2bd65a69ef62f7769f`
-   a02.txt: SHA-256 `1ff440bb3ed39749640384aa52eb61972fd55c578bc0aa5029a38ad7c4262101`
-   a03.txt: SHA-256 `d03cbb7c5fe17953c9d6bea54346c5f726674974066cc80be12215c1fa4b3300`
-   a04.txt: SHA-256 `85ac804ca762ee2657867fc5b1019b635044416c87ae521734b3746af3bcfa3a`
-   a05.txt: SHA-256 `e3fcf27f25c675080773e52446b47fa37f282f8a86ce8d6e2c5ffb73124d1ac2`
-   a06.txt: SHA-256 `5b8efc410139520ec55a790f497c73e2b6a62cb35ffd2e9246cc16cbac15d8c4`
-   referencia.toml: SHA-256 `260a6d15787673ad3cf35d787262cec18f0e6669a32b9ce7cc5594bb3caa6992`

## Definições

- Denominador das razões da amostra: G, número de requisitos gerados na saída final (FinalRecord.output) da corrida e da condição. Caso inválido (FinalRecord.status diferente de ok) conta como zero requisito gerado.
- Corpus do caso: check_all, is_complete e a cobertura de proveniência usam só os chunks do documento do caso, como o executor. Evidência que cita chunk de outro documento não resolve e conta como P2.
- `completeness_ratio` = #{r em G : rules.is_complete(r, corpus do caso)} / |G|.
- `c4_rate` = #{r em G : C4 em check_all com subject = r.key} / |G| (C4 fica fora de is_complete).
- `unsupported_claim_rate` = #{r em G : P1, P2 ou P3 em check_all com subject = r.key} / |G|. Violações de ator, componente, entidade e relação não entram.
- `rule_violation_rate` = #{violações K1 a K5 de check_all na saída} / |G|.
- `foreign_evidence` = número de citações da saída final (requisitos, atores, componentes, entidades e relações) cujo chunk_id é de outro documento da ingestão. Contagem, não razão.
- `corrected` = #{k em FinalRecord.targets : CP_final(k) < CP_extração(k) e nenhuma violação P nova em k}, com CP = número de violações C1 a C4 e P1 a P5 de check_all com subject = k, e violação P nova = par (regra, detalhe) de P1 a P5 que aparece mais vezes na saída final do que na extração. A extração é o CaseResult de stage extraction da mesma corrida.
- `input_tokens_per_corrected` = soma de usage.input_tokens, cache_creation_input_tokens e cache_read_input_tokens das chamadas de refinamento da condição e da corrida em calls.jsonl / corrected; `output_tokens_per_corrected` idem com output_tokens; `tokens_per_corrected` com a soma dos dois. Chamada com falha da API conta zero. Indefinido com corrected = 0 ou com resposta sem usage. As colunas final_record_* somam FinalRecord.input_tokens e output_tokens, só para conferência.
- Chamadas comuns às duas condições (shared_by_run.csv), por corrida, com chamadas e tokens de entrada (com cache) e saída: extração da amostra = chamadas de stage extraction cujo case_id é um caso de finals.jsonl; extração dos projetos do PROMISE = as demais chamadas de stage extraction (grafo por projeto de B); classificação = chamadas de stage classification. Falha da API conta a chamada e zero token.
- Tamanho do contexto (context_by_run.csv): para cada alvo de FinalRecord.targets com ContextRecord de mesmo caso, corrida, condição e chave, itens = len(context.items) e caracteres = soma de len(item.text); média, mediana e máximo sobre os alvos. Estratos: all, written (alvo gravado no grafo) e rejected_w (alvo com RejectionRecord de subject igual à chave na mesma corrida). `context_items_mean` e `context_chars_mean` no agregado são as médias do estrato all.
- Pareamento: `paired` = pares depois da atribuição um a um; `generated_unpaired` = |G| - paired (sem candidata, decisão nenhum ou duplicata); `references_unpaired` = R - paired, com R = referências dos casos da corrida, inválidos inclusive.
- `provenance_coverage` = covered / paired, com covered = #{pares (g, r) : alguma evidência de g resolve no corpus do caso e cita um chunk que contém r.quote pela comparação de P3}. `provenance_coverage_of_references` = covered / R: o denominador não depende da condição.
- `bertscore_f1` = média do F1 do BERTScore (idf desligado, sem baseline) entre a declaração de g e a de r, sobre os pares da corrida e da condição.
- PROMISE: precisão, revocação e F1 de scikit-learn (precision_recall_fscore_support, zero_division = 0). Predição inválida (primeira classificação com status diferente de ok) erra o item e não conta para rótulo nenhum. Refinamento com refinement_status diferente de ok (falha) mantém o rótulo inicial e é contado em `promise_refinement_failures`. Refinamento com refinement_status ok e refinement_accepted falso (recusa por regra G) mantém o rótulo inicial em final e é contado em `promise_refinement_refusals`, por regra. Binária: F contra NF sobre todos os itens, média macro de F e NF. Categoria: onze rótulos não funcionais sobre os itens de referência não funcional; média macro sobre os rótulos com suporte, sem PO.
- PROMISE, diagnóstico do contexto (promise_context_agreement.csv): para cada item avaliado i, N_i = itens do contexto com item_id PROMISE-NFR-NNNN. `promise_context_label_agreement` = soma dos N_i com o rótulo de referência de i / soma dos N_i. `promise_context_label_agreement_expected` = soma de N_i * q_i / soma dos N_i, com q_i = fração dos demais itens do projeto de i com o mesmo rótulo de i: a concordância esperada se o contexto fosse sorteado no projeto. majority_rate = itens cujo rótulo mais frequente no contexto, quando único, é o de i / itens com N_i > 0.
- Agregado entre corridas: média aritmética e desvio padrão amostral (n - 1) dos valores definidos de cada corrida.

## Comum às duas condições: chamadas e tokens

Chamadas sem condição, feitas uma vez por corrida. Cada célula: chamadas / tokens de entrada (com cache)/saída. Também em `shared_by_run.csv`.

| corrida | extração da amostra | extração dos projetos do PROMISE | classificação do PROMISE |
| --- | --- | --- | --- |
| 0 | 12 / 38222/27164 | 0 / 0/0 | 0 / 0/0 |
| 1 | 12 / 38222/27164 | 0 / 0/0 | 0 / 0/0 |
| 2 | 12 / 38222/27164 | 0 / 0/0 | 0 / 0/0 |

## Amostra de referência: métricas por regra

Regras de `code/domain/rules.py`, versão 3. Por corrida em `structural_by_run.csv`.

| corrida | condição | casos | inválidos | gerados | completude | C4 | sem proveniência | K por requisito | alvos | aceitos | recusados | com falha | corrigidos | evidências de outro documento | tokens refino (entrada/saída) | tokens por corrigido |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | LLM-only | 6 | 0 | 43 | 0.4419 | 0.0000 | 0.0000 | 0.0000 | 32 | 24 | 7 | 1 | 10 | 0 | 58308/11979 | 7028.7000 |
| 0 | REQKG-grounded | 6 | 0 | 43 | 0.4884 | 0.0000 | 0.0233 | 0.0000 | 32 | 19 | 13 | 0 | 10 | 0 | 116161/8000 | 12416.1000 |
| 1 | LLM-only | 6 | 0 | 43 | 0.4419 | 0.0000 | 0.0000 | 0.0000 | 32 | 24 | 7 | 1 | 10 | 0 | 58308/11979 | 7028.7000 |
| 1 | REQKG-grounded | 6 | 0 | 43 | 0.4884 | 0.0000 | 0.0233 | 0.0000 | 32 | 19 | 13 | 0 | 10 | 0 | 116161/8000 | 12416.1000 |
| 2 | LLM-only | 6 | 0 | 43 | 0.4419 | 0.0000 | 0.0000 | 0.0000 | 32 | 24 | 7 | 1 | 10 | 0 | 58308/11979 | 7028.7000 |
| 2 | REQKG-grounded | 6 | 0 | 43 | 0.4884 | 0.0000 | 0.0233 | 0.0000 | 32 | 19 | 13 | 0 | 10 | 0 | 116161/8000 | 12416.1000 |

Casos inválidos por estado: nenhum.

Recusas na gravação do grafo (regras W): não mudam as métricas e são reportadas à parte.

| corrida | recusas W | por regra |
| --- | --- | --- |
| 0 | 5 | W1 2, W2 2, W4 1 |
| 1 | 5 | W1 2, W2 2, W4 1 |
| 2 | 5 | W1 2, W2 2, W4 1 |

### Tamanho do contexto de refinamento

Por alvo, a partir de contexts.jsonl. written: alvo gravado no grafo; rejected_w: alvo recusado na gravação (regras W). Também em `context_by_run.csv`.

| corrida | condição | estrato | alvos | itens (média/mediana/máx.) | caracteres (média/mediana/máx.) |
| --- | --- | --- | --- | --- | --- |
| 0 | LLM-only | all | 32 | 4.8125 / 6.0000 / 6.0000 | 1746.2812 / 1561.0000 / 2988.0000 |
| 0 | LLM-only | written | 31 | 4.9032 / 6.0000 / 6.0000 | 1782.7097 / 1561.0000 / 2988.0000 |
| 0 | LLM-only | rejected_w | 1 | 2.0000 / 2.0000 / 2.0000 | 617.0000 / 617.0000 / 617.0000 |
| 0 | REQKG-grounded | all | 32 | 22.8438 / 25.0000 / 30.0000 | 3968.0000 / 4308.5000 / 6704.0000 |
| 0 | REQKG-grounded | written | 31 | 23.4839 / 26.0000 / 30.0000 | 4072.7419 / 4414.0000 / 6704.0000 |
| 0 | REQKG-grounded | rejected_w | 1 | 3.0000 / 3.0000 / 3.0000 | 721.0000 / 721.0000 / 721.0000 |
| 1 | LLM-only | all | 32 | 4.8125 / 6.0000 / 6.0000 | 1746.2812 / 1561.0000 / 2988.0000 |
| 1 | LLM-only | written | 31 | 4.9032 / 6.0000 / 6.0000 | 1782.7097 / 1561.0000 / 2988.0000 |
| 1 | LLM-only | rejected_w | 1 | 2.0000 / 2.0000 / 2.0000 | 617.0000 / 617.0000 / 617.0000 |
| 1 | REQKG-grounded | all | 32 | 22.8438 / 25.0000 / 30.0000 | 3968.0000 / 4308.5000 / 6704.0000 |
| 1 | REQKG-grounded | written | 31 | 23.4839 / 26.0000 / 30.0000 | 4072.7419 / 4414.0000 / 6704.0000 |
| 1 | REQKG-grounded | rejected_w | 1 | 3.0000 / 3.0000 / 3.0000 | 721.0000 / 721.0000 / 721.0000 |
| 2 | LLM-only | all | 32 | 4.8125 / 6.0000 / 6.0000 | 1746.2812 / 1561.0000 / 2988.0000 |
| 2 | LLM-only | written | 31 | 4.9032 / 6.0000 / 6.0000 | 1782.7097 / 1561.0000 / 2988.0000 |
| 2 | LLM-only | rejected_w | 1 | 2.0000 / 2.0000 / 2.0000 | 617.0000 / 617.0000 / 617.0000 |
| 2 | REQKG-grounded | all | 32 | 22.8438 / 25.0000 / 30.0000 | 3968.0000 / 4308.5000 / 6704.0000 |
| 2 | REQKG-grounded | written | 31 | 23.4839 / 26.0000 / 30.0000 | 4072.7419 / 4414.0000 / 6704.0000 |
| 2 | REQKG-grounded | rejected_w | 1 | 3.0000 / 3.0000 / 3.0000 | 721.0000 / 721.0000 / 721.0000 |

## Pareamento com a amostra de referência

- Corrida 0: planilha com SHA-256 `b6105c9111bce1fc02c865d5a830710d3094df31c38cc057a33b9b0f1c27a9a1`, registrada em 2026-10-24T04:44:17+00:00.
- Corrida 1: planilha com SHA-256 `ae8cf623c15899592730fcc5ed5f4a864254b056fb8c4a20fb3613c2664af508`, registrada em 2026-10-24T04:44:17+00:00.
- Corrida 2: planilha com SHA-256 `5fd8941986a199fd1ed394d33a9c68beddc81fbeb5d335670c2ecc8a6e2a12d1`, registrada em 2026-10-24T04:44:18+00:00.
- BERTScore: model FacebookAI/xlm-roberta-large, revision c23d21b0620b635a76227c604d44e43a9f0ee389, requested_revision c23d21b0620b635a76227c604d44e43a9f0ee389, num_layers 17, idf False, rescale_with_baseline False, version bert-score 0.3.13, version transformers 5.19.0, version torch 2.14.1, version huggingface-hub 2.2.0.

Por corrida em `pairing_by_run.csv`; cada requisito gerado em `pairs.csv`.

| corrida | condição | gerados | referências | pareados | gerados sem par | sem candidata | decisão nenhum | duplicata | referências sem par | cobertos | cobertura (cobertos / pareados) | cobertura (cobertos / referências) | BERTScore F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | LLM-only | 43 | 54 | 42 | 1 | 0 | 0 | 1 | 12 | 42 | 1.0000 | 0.7778 | 0.9616 |
| 0 | REQKG-grounded | 43 | 54 | 42 | 1 | 0 | 0 | 1 | 12 | 42 | 1.0000 | 0.7778 | 0.9616 |
| 1 | LLM-only | 43 | 54 | 42 | 1 | 0 | 0 | 1 | 12 | 42 | 1.0000 | 0.7778 | 0.9616 |
| 1 | REQKG-grounded | 43 | 54 | 42 | 1 | 0 | 0 | 1 | 12 | 42 | 1.0000 | 0.7778 | 0.9616 |
| 2 | LLM-only | 43 | 54 | 42 | 1 | 0 | 0 | 1 | 12 | 42 | 1.0000 | 0.7778 | 0.9616 |
| 2 | REQKG-grounded | 43 | 54 | 42 | 1 | 0 | 0 | 1 | 12 | 42 | 1.0000 | 0.7778 | 0.9616 |

## Agregado entre corridas

Tabela completa em `summary.csv`.

| métrica | condição | n | média | desvio | valores por corrida |
| --- | --- | --- | --- | --- | --- |
| completeness_ratio | LLM-only | 3 | 0.4419 | 0.0000 | 0.4419; 0.4419; 0.4419 |
| c4_rate | LLM-only | 3 | 0.0000 | 0.0000 | 0.0000; 0.0000; 0.0000 |
| unsupported_claim_rate | LLM-only | 3 | 0.0000 | 0.0000 | 0.0000; 0.0000; 0.0000 |
| rule_violation_rate | LLM-only | 3 | 0.0000 | 0.0000 | 0.0000; 0.0000; 0.0000 |
| invalid_cases | LLM-only | 3 | 0.0000 | 0.0000 | 0.0000; 0.0000; 0.0000 |
| corrected | LLM-only | 3 | 10.0000 | 0.0000 | 10.0000; 10.0000; 10.0000 |
| foreign_evidence | LLM-only | 3 | 0.0000 | 0.0000 | 0.0000; 0.0000; 0.0000 |
| input_tokens_per_corrected | LLM-only | 3 | 5830.8000 | 0.0000 | 5830.8000; 5830.8000; 5830.8000 |
| output_tokens_per_corrected | LLM-only | 3 | 1197.9000 | 0.0000 | 1197.9000; 1197.9000; 1197.9000 |
| tokens_per_corrected | LLM-only | 3 | 7028.7000 | 0.0000 | 7028.7000; 7028.7000; 7028.7000 |
| completeness_ratio | REQKG-grounded | 3 | 0.4884 | 0.0000 | 0.4884; 0.4884; 0.4884 |
| c4_rate | REQKG-grounded | 3 | 0.0000 | 0.0000 | 0.0000; 0.0000; 0.0000 |
| unsupported_claim_rate | REQKG-grounded | 3 | 0.0233 | 0.0000 | 0.0233; 0.0233; 0.0233 |
| rule_violation_rate | REQKG-grounded | 3 | 0.0000 | 0.0000 | 0.0000; 0.0000; 0.0000 |
| invalid_cases | REQKG-grounded | 3 | 0.0000 | 0.0000 | 0.0000; 0.0000; 0.0000 |
| corrected | REQKG-grounded | 3 | 10.0000 | 0.0000 | 10.0000; 10.0000; 10.0000 |
| foreign_evidence | REQKG-grounded | 3 | 0.0000 | 0.0000 | 0.0000; 0.0000; 0.0000 |
| input_tokens_per_corrected | REQKG-grounded | 3 | 11616.1000 | 0.0000 | 11616.1000; 11616.1000; 11616.1000 |
| output_tokens_per_corrected | REQKG-grounded | 3 | 800.0000 | 0.0000 | 800.0000; 800.0000; 800.0000 |
| tokens_per_corrected | REQKG-grounded | 3 | 12416.1000 | 0.0000 | 12416.1000; 12416.1000; 12416.1000 |
| context_items_mean | LLM-only | 3 | 4.8125 | 0.0000 | 4.8125; 4.8125; 4.8125 |
| context_chars_mean | LLM-only | 3 | 1746.2812 | 0.0000 | 1746.2812; 1746.2812; 1746.2812 |
| context_items_mean | REQKG-grounded | 3 | 22.8438 | 0.0000 | 22.8438; 22.8438; 22.8438 |
| context_chars_mean | REQKG-grounded | 3 | 3968.0000 | 0.0000 | 3968.0000; 3968.0000; 3968.0000 |
| paired | LLM-only | 3 | 42.0000 | 0.0000 | 42.0000; 42.0000; 42.0000 |
| generated_unpaired | LLM-only | 3 | 1.0000 | 0.0000 | 1.0000; 1.0000; 1.0000 |
| references_unpaired | LLM-only | 3 | 12.0000 | 0.0000 | 12.0000; 12.0000; 12.0000 |
| provenance_coverage | LLM-only | 3 | 1.0000 | 0.0000 | 1.0000; 1.0000; 1.0000 |
| provenance_coverage_of_references | LLM-only | 3 | 0.7778 | 0.0000 | 0.7778; 0.7778; 0.7778 |
| bertscore_f1 | LLM-only | 3 | 0.9616 | 0.0000 | 0.9616; 0.9616; 0.9616 |
| paired | REQKG-grounded | 3 | 42.0000 | 0.0000 | 42.0000; 42.0000; 42.0000 |
| generated_unpaired | REQKG-grounded | 3 | 1.0000 | 0.0000 | 1.0000; 1.0000; 1.0000 |
| references_unpaired | REQKG-grounded | 3 | 12.0000 | 0.0000 | 12.0000; 12.0000; 12.0000 |
| provenance_coverage | REQKG-grounded | 3 | 1.0000 | 0.0000 | 1.0000; 1.0000; 1.0000 |
| provenance_coverage_of_references | REQKG-grounded | 3 | 0.7778 | 0.0000 | 0.7778; 0.7778; 0.7778 |
| bertscore_f1 | REQKG-grounded | 3 | 0.9616 | 0.0000 | 0.9616; 0.9616; 0.9616 |
