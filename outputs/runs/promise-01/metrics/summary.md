# Métricas da corrida promise-01

Gerado por `experiments.metrics`. Não editar à mão. O comando abaixo, a partir da raiz do repositório, regenera cada número deste arquivo e das tabelas CSV da mesma pasta:

```sh
PYTHONPATH=code .venv/bin/python -m experiments.metrics promise-01 compute
```

## Entradas

- corrida: `outputs/runs/promise-01`, model_id `qwen3:14b`, replay False, runs 1
- corrida piloto: não
- configuração: `code/experiments/config/experiment.toml`, SHA-256 `43a48015ae13d15e742d4c1fa56694dd0a89b507ee5d26fd477d5839e48d806c` (confere com o manifesto)
- registro de prompts: SHA-256 `339706257de53c8d6171dc8a464cb928498ce0d7228f70c6894ca337b21b8651`
- manifesto de congelamento: SHA-256 `3b33c728292f4c1ac3ab02523f48c27a88aadbc01ba63fc66f62650c025ae0a2`
- rótulos do PROMISE: `data/processed/promise/promise_nfr.jsonl`, SHA-256 `1a01f43a7f9b303dfea9dc6267dcc47bc5f2a820e9397b6530e90f0f37e03479`

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
| 0 | 0 / 0/0 | 84 / 245757/169321 | 625 / 399732/17104 |

## PROMISE NFR

Itens na referência: 625. Itens com registro na corrida: 625. Por rótulo em `promise_by_label.csv`; médias em `promise_macro.csv`.
Itens sem registro de uma condição, contados como predição inválida: nenhum.
Refinamentos com falha (refinement_status diferente de ok: resposta inválida ou erro de API), que mantêm o rótulo inicial: corrida 0, LLM-only: 0; corrida 0, REQKG-grounded: 0.
Refinamentos recusados por regra G (refinement_status ok e refinement_accepted falso), que mantêm o rótulo inicial: corrida 0, LLM-only: 0; corrida 0, REQKG-grounded: 0.
PO fora da média macro: um único item no PROMISE publicado; um acerto ou um erro levaria o F1 do rótulo a 1 ou a 0.
O par PROMISE-NFR-0426 (SE) e PROMISE-NFR-0460 (F) tem o mesmo texto e rótulos diferentes; um dos dois sempre conta como erro.

| corrida | classificação | tarefa | itens | inválidas | rótulos na média | precisão macro | revocação macro | F1 macro |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | initial | binary | 625 | 0 | F NF | 0.8467 | 0.8576 | 0.8394 |
| 0 | initial | category | 370 | 0 | A FT L LF MN O PE SC SE US | 0.8497 | 0.6689 | 0.7329 |
| 0 | LLM-only | binary | 625 | 0 | F NF | 0.8723 | 0.8848 | 0.8737 |
| 0 | LLM-only | category | 370 | 0 | A FT L LF MN O PE SC SE US | 0.8031 | 0.6938 | 0.7284 |
| 0 | REQKG-grounded | binary | 625 | 0 | F NF | 0.8709 | 0.8835 | 0.8721 |
| 0 | REQKG-grounded | category | 370 | 0 | A FT L LF MN O PE SC SE US | 0.8051 | 0.6938 | 0.7290 |

Por rótulo:

| corrida | classificação | tarefa | rótulo | suporte | preditos | precisão | revocação | F1 | na média |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | initial | binary | F | 255 | 331 | 0.7341 | 0.9529 | 0.8294 | sim |
| 0 | initial | binary | NF | 370 | 294 | 0.9592 | 0.7622 | 0.8494 | sim |
| 0 | initial | category | A | 21 | 23 | 0.8261 | 0.9048 | 0.8636 | sim |
| 0 | initial | category | FT | 10 | 9 | 0.8889 | 0.8000 | 0.8421 | sim |
| 0 | initial | category | L | 13 | 18 | 0.6111 | 0.8462 | 0.7097 | sim |
| 0 | initial | category | LF | 38 | 31 | 0.8710 | 0.7105 | 0.7826 | sim |
| 0 | initial | category | MN | 17 | 8 | 0.8750 | 0.4118 | 0.5600 | sim |
| 0 | initial | category | O | 62 | 42 | 0.8571 | 0.5806 | 0.6923 | sim |
| 0 | initial | category | PE | 54 | 43 | 0.8605 | 0.6852 | 0.7629 | sim |
| 0 | initial | category | PO | 1 | 5 | 0.0000 | 0.0000 | 0.0000 | não |
| 0 | initial | category | SC | 21 | 11 | 0.7273 | 0.3810 | 0.5000 | sim |
| 0 | initial | category | SE | 66 | 50 | 0.9800 | 0.7424 | 0.8448 | sim |
| 0 | initial | category | US | 67 | 42 | 1.0000 | 0.6269 | 0.7706 | sim |
| 0 | LLM-only | binary | F | 255 | 301 | 0.7940 | 0.9373 | 0.8597 | sim |
| 0 | LLM-only | binary | NF | 370 | 324 | 0.9506 | 0.8324 | 0.8876 | sim |
| 0 | LLM-only | category | A | 21 | 25 | 0.8400 | 1.0000 | 0.9130 | sim |
| 0 | LLM-only | category | FT | 10 | 12 | 0.6667 | 0.8000 | 0.7273 | sim |
| 0 | LLM-only | category | L | 13 | 18 | 0.6111 | 0.8462 | 0.7097 | sim |
| 0 | LLM-only | category | LF | 38 | 32 | 0.8125 | 0.6842 | 0.7429 | sim |
| 0 | LLM-only | category | MN | 17 | 8 | 0.8750 | 0.4118 | 0.5600 | sim |
| 0 | LLM-only | category | O | 62 | 44 | 0.8409 | 0.5968 | 0.6981 | sim |
| 0 | LLM-only | category | PE | 54 | 43 | 0.8372 | 0.6667 | 0.7423 | sim |
| 0 | LLM-only | category | PO | 1 | 5 | 0.0000 | 0.0000 | 0.0000 | não |
| 0 | LLM-only | category | SC | 21 | 13 | 0.6923 | 0.4286 | 0.5294 | sim |
| 0 | LLM-only | category | SE | 66 | 52 | 0.9808 | 0.7727 | 0.8644 | sim |
| 0 | LLM-only | category | US | 67 | 56 | 0.8750 | 0.7313 | 0.7967 | sim |
| 0 | REQKG-grounded | binary | F | 255 | 302 | 0.7914 | 0.9373 | 0.8582 | sim |
| 0 | REQKG-grounded | binary | NF | 370 | 323 | 0.9505 | 0.8297 | 0.8860 | sim |
| 0 | REQKG-grounded | category | A | 21 | 25 | 0.8400 | 1.0000 | 0.9130 | sim |
| 0 | REQKG-grounded | category | FT | 10 | 12 | 0.6667 | 0.8000 | 0.7273 | sim |
| 0 | REQKG-grounded | category | L | 13 | 18 | 0.6111 | 0.8462 | 0.7097 | sim |
| 0 | REQKG-grounded | category | LF | 38 | 32 | 0.8125 | 0.6842 | 0.7429 | sim |
| 0 | REQKG-grounded | category | MN | 17 | 8 | 0.8750 | 0.4118 | 0.5600 | sim |
| 0 | REQKG-grounded | category | O | 62 | 43 | 0.8605 | 0.5968 | 0.7048 | sim |
| 0 | REQKG-grounded | category | PE | 54 | 43 | 0.8372 | 0.6667 | 0.7423 | sim |
| 0 | REQKG-grounded | category | PO | 1 | 5 | 0.0000 | 0.0000 | 0.0000 | não |
| 0 | REQKG-grounded | category | SC | 21 | 13 | 0.6923 | 0.4286 | 0.5294 | sim |
| 0 | REQKG-grounded | category | SE | 66 | 52 | 0.9808 | 0.7727 | 0.8644 | sim |
| 0 | REQKG-grounded | category | US | 67 | 56 | 0.8750 | 0.7313 | 0.7967 | sim |

### Rótulo dos requisitos do PROMISE no contexto

Diagnóstico: se a concordância passa muito da esperada, o contexto funciona como oráculo de rótulo. Também em `promise_context_agreement.csv`.

| corrida | condição | itens com requisito do PROMISE no contexto | itens de contexto | mesmo rótulo | concordância | esperada no projeto | maioria igual ao rótulo |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | LLM-only | 621 | 3038 | 832 | 0.2739 | 0.2728 | 176 (0.2834) |
| 0 | REQKG-grounded | 621 | 3058 | 846 | 0.2767 | 0.2739 | 178 (0.2866) |

## Agregado entre corridas

Tabela completa em `summary.csv`.

| métrica | condição | n | média | desvio | valores por corrida |
| --- | --- | --- | --- | --- | --- |
| promise_binary_macro_precision | initial | 1 | 0.8467 | indefinido | 0.8467 |
| promise_binary_macro_recall | initial | 1 | 0.8576 | indefinido | 0.8576 |
| promise_binary_macro_f1 | initial | 1 | 0.8394 | indefinido | 0.8394 |
| promise_category_macro_precision | initial | 1 | 0.8497 | indefinido | 0.8497 |
| promise_category_macro_recall | initial | 1 | 0.6689 | indefinido | 0.6689 |
| promise_category_macro_f1 | initial | 1 | 0.7329 | indefinido | 0.7329 |
| promise_binary_macro_precision | LLM-only | 1 | 0.8723 | indefinido | 0.8723 |
| promise_binary_macro_recall | LLM-only | 1 | 0.8848 | indefinido | 0.8848 |
| promise_binary_macro_f1 | LLM-only | 1 | 0.8737 | indefinido | 0.8737 |
| promise_category_macro_precision | LLM-only | 1 | 0.8031 | indefinido | 0.8031 |
| promise_category_macro_recall | LLM-only | 1 | 0.6938 | indefinido | 0.6938 |
| promise_category_macro_f1 | LLM-only | 1 | 0.7284 | indefinido | 0.7284 |
| promise_binary_macro_precision | REQKG-grounded | 1 | 0.8709 | indefinido | 0.8709 |
| promise_binary_macro_recall | REQKG-grounded | 1 | 0.8835 | indefinido | 0.8835 |
| promise_binary_macro_f1 | REQKG-grounded | 1 | 0.8721 | indefinido | 0.8721 |
| promise_category_macro_precision | REQKG-grounded | 1 | 0.8051 | indefinido | 0.8051 |
| promise_category_macro_recall | REQKG-grounded | 1 | 0.6938 | indefinido | 0.6938 |
| promise_category_macro_f1 | REQKG-grounded | 1 | 0.7290 | indefinido | 0.7290 |
| promise_refinement_failures | LLM-only | 1 | 0.0000 | indefinido | 0.0000 |
| promise_refinement_failures | REQKG-grounded | 1 | 0.0000 | indefinido | 0.0000 |
| promise_refinement_refusals | LLM-only | 1 | 0.0000 | indefinido | 0.0000 |
| promise_refinement_refusals | REQKG-grounded | 1 | 0.0000 | indefinido | 0.0000 |
| promise_context_label_agreement | LLM-only | 1 | 0.2739 | indefinido | 0.2739 |
| promise_context_label_agreement_expected | LLM-only | 1 | 0.2728 | indefinido | 0.2728 |
| promise_context_label_agreement | REQKG-grounded | 1 | 0.2767 | indefinido | 0.2767 |
| promise_context_label_agreement_expected | REQKG-grounded | 1 | 0.2739 | indefinido | 0.2739 |
