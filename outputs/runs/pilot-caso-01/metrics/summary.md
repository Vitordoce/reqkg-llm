# Métricas da corrida pilot-caso-01

Gerado por `experiments.metrics`. Não editar à mão. O comando abaixo, a partir da raiz do repositório, regenera cada número deste arquivo e das tabelas CSV da mesma pasta:

```sh
PYTHONPATH=code .venv/bin/python -m experiments.metrics pilot-caso-01 compute --ingestion data/raw/caso/caso_piloto.toml
```

## Entradas

- corrida: `outputs/runs/pilot-caso-01`, model_id `qwen3:14b`, replay False, runs 1
- corrida piloto: sim: dispensa o congelamento e não entra no relatório como resultado
- configuração: `code/experiments/config/experiment.toml`, SHA-256 `43a48015ae13d15e742d4c1fa56694dd0a89b507ee5d26fd477d5839e48d806c` (confere com o manifesto)
- registro de prompts: SHA-256 `339706257de53c8d6171dc8a464cb928498ce0d7228f70c6894ca337b21b8651`
- ingestão: `data/raw/caso/caso_piloto.toml`, ingerido em memória, SHA-256 dos bytes canônicos, SHA-256 `45ce02412f1aab1ad26541aa3094e3e36e78ce54d01ef6a328eb7247a13bb89d`

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
| 0 | 24 / 72967/24084 | 0 / 0/0 | 0 / 0/0 |

## Amostra de referência: métricas por regra

Regras de `code/domain/rules.py`, versão 3. Por corrida em `structural_by_run.csv`.

| corrida | condição | casos | inválidos | gerados | completude | C4 | sem proveniência | K por requisito | alvos | aceitos | recusados | com falha | corrigidos | evidências de outro documento | tokens refino (entrada/saída) | tokens por corrigido |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | LLM-only | 12 | 5 | 17 | 0.1765 | 0.0000 | 0.0000 | 0.0000 | 17 | 14 | 2 | 1 | 3 | 0 | 27725/7828 | 11851.0000 |
| 0 | REQKG-grounded | 12 | 5 | 17 | 0.2941 | 0.0000 | 0.0000 | 0.0000 | 17 | 11 | 6 | 0 | 5 | 0 | 37394/4312 | 8341.2000 |

Casos inválidos por estado: corrida 0, LLM-only: invalid_output 5; corrida 0, REQKG-grounded: invalid_output 5.

Recusas na gravação do grafo (regras W): não mudam as métricas e são reportadas à parte.

| corrida | recusas W | por regra |
| --- | --- | --- |
| 0 | 4 | W1 4 |

### Tamanho do contexto de refinamento

Por alvo, a partir de contexts.jsonl. written: alvo gravado no grafo; rejected_w: alvo recusado na gravação (regras W). Também em `context_by_run.csv`.

| corrida | condição | estrato | alvos | itens (média/mediana/máx.) | caracteres (média/mediana/máx.) |
| --- | --- | --- | --- | --- | --- |
| 0 | LLM-only | all | 17 | 5.7059 / 6.0000 / 6.0000 | 1025.1765 / 642.0000 / 1763.0000 |
| 0 | LLM-only | written | 17 | 5.7059 / 6.0000 / 6.0000 | 1025.1765 / 642.0000 / 1763.0000 |
| 0 | LLM-only | rejected_w | 0 | indefinido / indefinido / indefinido | indefinido / indefinido / indefinido |
| 0 | REQKG-grounded | all | 17 | 11.5882 / 10.0000 / 16.0000 | 1592.7059 / 1591.0000 / 2034.0000 |
| 0 | REQKG-grounded | written | 17 | 11.5882 / 10.0000 / 16.0000 | 1592.7059 / 1591.0000 / 2034.0000 |
| 0 | REQKG-grounded | rejected_w | 0 | indefinido / indefinido / indefinido | indefinido / indefinido / indefinido |

## Agregado entre corridas

Tabela completa em `summary.csv`.

| métrica | condição | n | média | desvio | valores por corrida |
| --- | --- | --- | --- | --- | --- |
| completeness_ratio | LLM-only | 1 | 0.1765 | indefinido | 0.1765 |
| c4_rate | LLM-only | 1 | 0.0000 | indefinido | 0.0000 |
| unsupported_claim_rate | LLM-only | 1 | 0.0000 | indefinido | 0.0000 |
| rule_violation_rate | LLM-only | 1 | 0.0000 | indefinido | 0.0000 |
| invalid_cases | LLM-only | 1 | 5.0000 | indefinido | 5.0000 |
| corrected | LLM-only | 1 | 3.0000 | indefinido | 3.0000 |
| foreign_evidence | LLM-only | 1 | 0.0000 | indefinido | 0.0000 |
| input_tokens_per_corrected | LLM-only | 1 | 9241.6667 | indefinido | 9241.6667 |
| output_tokens_per_corrected | LLM-only | 1 | 2609.3333 | indefinido | 2609.3333 |
| tokens_per_corrected | LLM-only | 1 | 11851.0000 | indefinido | 11851.0000 |
| completeness_ratio | REQKG-grounded | 1 | 0.2941 | indefinido | 0.2941 |
| c4_rate | REQKG-grounded | 1 | 0.0000 | indefinido | 0.0000 |
| unsupported_claim_rate | REQKG-grounded | 1 | 0.0000 | indefinido | 0.0000 |
| rule_violation_rate | REQKG-grounded | 1 | 0.0000 | indefinido | 0.0000 |
| invalid_cases | REQKG-grounded | 1 | 5.0000 | indefinido | 5.0000 |
| corrected | REQKG-grounded | 1 | 5.0000 | indefinido | 5.0000 |
| foreign_evidence | REQKG-grounded | 1 | 0.0000 | indefinido | 0.0000 |
| input_tokens_per_corrected | REQKG-grounded | 1 | 7478.8000 | indefinido | 7478.8000 |
| output_tokens_per_corrected | REQKG-grounded | 1 | 862.4000 | indefinido | 862.4000 |
| tokens_per_corrected | REQKG-grounded | 1 | 8341.2000 | indefinido | 8341.2000 |
| context_items_mean | LLM-only | 1 | 5.7059 | indefinido | 5.7059 |
| context_chars_mean | LLM-only | 1 | 1025.1765 | indefinido | 1025.1765 |
| context_items_mean | REQKG-grounded | 1 | 11.5882 | indefinido | 11.5882 |
| context_chars_mean | REQKG-grounded | 1 | 1592.7059 | indefinido | 1592.7059 |
