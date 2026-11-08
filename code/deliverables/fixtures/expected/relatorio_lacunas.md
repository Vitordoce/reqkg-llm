# Relatório de lacunas: fixture-sintetico

> Gerado pelo ReqKG-LLM a partir dos registros da corrida, sem edição manual. Para regenerar: `PYTHONPATH=code .venv/bin/python -m deliverables sintetico-entrevista --condition REQKG-grounded --run-index 0 --name fixture-sintetico --runs-dir code/deliverables/fixtures/runs --config code/deliverables/fixtures/experiment.toml`.
>
> - Corrida: `sintetico-entrevista`, condição `REQKG-grounded`, repetição 0 (a corrida tem 1).
> - Corrida piloto: não.
> - Modelo: `nenhum-fixture-sintetico`. Respostas gravadas (replay): sim.
> - Comando da corrida: `code/deliverables/fixtures/build.py (corrida sintética, sem chamada de modelo)`.
> - Casos: `src-339ed9b9a545ccbc` (`code/ingestion/fixtures/ata_sintetica.md`), `src-3f478d516d9d807d` (`code/domain/fixtures/corpus/entrevista_sintetica.txt`), `src-71d5fe87d6dfb68a` (`code/ingestion/fixtures/descricao_sintetica.txt`).
> - Configuração: `code/deliverables/fixtures/experiment.toml` (SHA-256 `55a6bc3ea88f82f06dba7bc42ab4f1d1f9144426fbf23e530d1dc8489954b5bc`).
> - Ingestão: `data/processed/ingestion/fixture.json` (SHA-256 `49756503282cf362a9f61a496f0fe29b6ea8e69dfa1ecf71f822b801cbe44a7f`).

As violações C, P e K são as de `domain.rules.check_all` sobre a saída final de cada caso, o mesmo ponto de medida das métricas. As recusas W são as de `domain.persist.to_records` ao montar a instância. As explicações das regras são as de `code/domain/schema/RULES.md`.

## Resumo

| Família | Regra | O que conta | Ocorrências |
| --- | --- | --- | --- |
| completude | C1 | Requisito sem prioridade MoSCoW. | 9 |
| completude | C2 | Requisito sem método de verificação. | 9 |
| completude | C3 | Requisito sem tipo (funcional, não funcional ou restrição). | 1 |
| completude | C4 | Requisito não funcional sem atributo de qualidade ISO/IEC 25010. | 0 |
| proveniência | P1 | Requisito sem nenhuma evidência (fonte e chunk). | 1 |
| proveniência | P2 | Evidência cita fonte ou chunk que não existe no corpus, ou chunk de outra fonte. | 1 |
| proveniência | P3 | Citação da evidência não aparece no texto do chunk citado. | 1 |
| proveniência | P4 | Requisito ou relação marcado como fato extraído com evidência sem citação. | 0 |
| proveniência | P5 | Relação sem evidência. | 1 |
| consistência | K1 | O mesmo par de requisitos aparece como conflicts_with e duplicates. | 0 |
| consistência | K2 | Relação de um elemento com ele mesmo. | 0 |
| consistência | K3 | Ciclo em depends_on. Uma violação por componente fortemente conexo. | 1 |
| consistência | K4 | Ciclo em refines. Uma violação por componente fortemente conexo. | 0 |
| consistência | K5 | Requisito Must depende de requisito Won't. | 0 |
| recusa na gravação | W1 | Item sem nenhuma evidência que resolve no corpus com citação presente no chunk. | 3 |
| recusa na gravação | W2 | Relação com uma ponta que não foi gravada. | 1 |
| recusa na gravação | W3 | Relação sem evidência que resolve no corpus. | 1 |
| recusa na gravação | W4 | Ator com o mesmo nome e tipo diferente de um ator já gravado. Vale o primeiro. | 1 |
| recusa na gravação | W5 | Relação que liga um nó a ele mesmo depois da resolução de identificadores. | 0 |
| recusa na gravação | W6 | Requisito com o mesmo identificador de outro já gravado. Vale o primeiro. | 0 |

| Outras lacunas | Ocorrências |
| --- | --- |
| Requisitos em revisão humana | 2 |
| Atributos de qualidade sem valor quantitativo | 2 |
| Refinamentos recusados (regras G) | 1 |
| Casos sem saída nesta condição | 1 |

## Completude (C1 a C4)

### C1. Requisito sem prioridade MoSCoW.

- REQ-001: priority ausente (caso `src-3f478d516d9d807d`)
- REQ-003: priority ausente (caso `src-3f478d516d9d807d`)
- REQ-004: priority ausente (caso `src-3f478d516d9d807d`)
- REQ-005: priority ausente (caso `src-3f478d516d9d807d`)
- REQ-006: priority ausente (caso `src-3f478d516d9d807d`)
- REQ-007: priority ausente (caso `src-339ed9b9a545ccbc`)
- REQ-008: priority ausente (caso `src-339ed9b9a545ccbc`)
- REQ-009: priority ausente (caso `src-3f478d516d9d807d`)
- REQ-010: priority ausente (caso `src-3f478d516d9d807d`)

### C2. Requisito sem método de verificação.

- REQ-001: verification_method ausente (caso `src-3f478d516d9d807d`)
- REQ-003: verification_method ausente (caso `src-3f478d516d9d807d`)
- REQ-004: verification_method ausente (caso `src-3f478d516d9d807d`)
- REQ-005: verification_method ausente (caso `src-3f478d516d9d807d`)
- REQ-006: verification_method ausente (caso `src-3f478d516d9d807d`)
- REQ-007: verification_method ausente (caso `src-339ed9b9a545ccbc`)
- REQ-008: verification_method ausente (caso `src-339ed9b9a545ccbc`)
- REQ-009: verification_method ausente (caso `src-3f478d516d9d807d`)
- REQ-010: verification_method ausente (caso `src-3f478d516d9d807d`)

### C3. Requisito sem tipo (funcional, não funcional ou restrição).

- REQ-010: type ausente (caso `src-3f478d516d9d807d`)

### C4. Requisito não funcional sem atributo de qualidade ISO/IEC 25010.

Nenhuma ocorrência.

## Proveniência (P1 a P5)

### P1. Requisito sem nenhuma evidência (fonte e chunk).

- REQ-010: sem evidência (caso `src-3f478d516d9d807d`)

### P2. Evidência cita fonte ou chunk que não existe no corpus, ou chunk de outra fonte.

- REQ-009: src-339ed9b9a545ccbc/chk-3ebce0a3871c0412 não existe no corpus (caso `src-3f478d516d9d807d`)

### P3. Citação da evidência não aparece no texto do chunk citado.

- REQ-006: citação não aparece em chk-202c7f98847e276d (caso `src-3f478d516d9d807d`)

### P4. Requisito ou relação marcado como fato extraído com evidência sem citação.

Nenhuma ocorrência.

### P5. Relação sem evidência.

- relação allocated_to de REQ-002 para componente 'Agenda de reservas': allocated_to sem evidência (caso `src-3f478d516d9d807d`)

## Consistência (K1 a K5)

### K1. O mesmo par de requisitos aparece como conflicts_with e duplicates.

Nenhuma ocorrência.

### K2. Relação de um elemento com ele mesmo.

Nenhuma ocorrência.

### K3. Ciclo em depends_on. Uma violação por componente fortemente conexo.

- REQ-001, REQ-002: ciclo em depends_on (caso `src-3f478d516d9d807d`)

### K4. Ciclo em refines. Uma violação por componente fortemente conexo.

Nenhuma ocorrência.

### K5. Requisito Must depende de requisito Won't.

Nenhuma ocorrência.

## Recusas na gravação (W1 a W6)

### Nesta instância

Recusas de `to_records` sobre a saída final desta condição. O item recusado não está na instância.

#### W1. Item sem nenhuma evidência que resolve no corpus com citação presente no chunk.

- REQ-006: requisito sem evidência que resolve (caso `src-3f478d516d9d807d`)
- REQ-009: requisito sem evidência que resolve (caso `src-3f478d516d9d807d`)
- REQ-010: requisito sem evidência que resolve (caso `src-3f478d516d9d807d`)

#### W2. Relação com uma ponta que não foi gravada.

- relação requested_by de REQ-006 para ator 'Coordenadora do laboratório': c0-R6 ou c0-A1 não foi gravado (caso `src-3f478d516d9d807d`)

#### W3. Relação sem evidência que resolve no corpus.

- relação allocated_to de REQ-002 para componente 'Agenda de reservas': allocated_to sem evidência que resolve (caso `src-3f478d516d9d807d`)

#### W4. Ator com o mesmo nome e tipo diferente de um ator já gravado. Vale o primeiro.

- ator 'técnico': 'técnico' já gravado como user_role (caso `src-3f478d516d9d807d`)

#### W5. Relação que liga um nó a ele mesmo depois da resolução de identificadores.

Nenhuma ocorrência.

#### W6. Requisito com o mesmo identificador de outro já gravado. Vale o primeiro.

Nenhuma ocorrência.

### Registradas pelo executor

Recusas de `code/deliverables/fixtures/runs/sintetico-entrevista/rejections.jsonl` nesta repetição, da gravação da extração compartilhada no grafo. Podem diferir das recusas acima, que partem da saída final depois do refinamento. Os assuntos são chaves da extração compartilhada.

- W1: REQ-006: requisito sem evidência que resolve (caso `src-3f478d516d9d807d`)
- W1: REQ-009: requisito sem evidência que resolve (caso `src-3f478d516d9d807d`)
- W1: REQ-010: requisito sem evidência que resolve (caso `src-3f478d516d9d807d`)
- W2: relação requested_by de REQ-006 para ator 'Coordenadora do laboratório': c0-R6 ou c0-A1 não foi gravado (caso `src-3f478d516d9d807d`)
- W3: relação allocated_to de REQ-002 para componente 'Agenda de reservas': allocated_to sem evidência que resolve (caso `src-3f478d516d9d807d`)
- W4: ator 'técnico': 'técnico' já gravado como user_role (caso `src-3f478d516d9d807d`)

## Refinamento de uma passagem

| Caso | Alvos | Aceitos | Recusados | Chamada falhou | Sem resultado registrado |
| --- | --- | --- | --- | --- | --- |
| `src-339ed9b9a545ccbc` | 2 | 2 | 0 | 0 | 0 |
| `src-3f478d516d9d807d` | 7 | 4 | 1 | 2 | 0 |
| `src-71d5fe87d6dfb68a` | 0 | 0 | 0 | 0 | 0 |

### Refinamentos recusados

Com qualquer violação G, o sistema recusa o refinamento e mantém o candidato original.

- REQ-005 (caso `src-3f478d516d9d807d`): G3 (A evidência revisada cita chunk que não estava no contexto nem no candidato original.): cita chk-c5b123cf9e21984a, fora do contexto e do original; G6 (Evidência nova (ausente do candidato original) não passa em CorpusIndex.supports no corpus do caso (chunk de outro documento ou citação que não aparece no chunk), ou prioridade ou método de verificação nulos no original foram preenchidos sem nenhuma evidência nova que passe.): evidência nova src-339ed9b9a545ccbc/chk-c5b123cf9e21984a não passa no corpus do caso

### Chamadas de refinamento que falharam

O candidato original fica. Alvos de `FinalRecord.failed`, com o erro do `CaseResult` do mesmo alvo:

- REQ-001 (caso `src-3f478d516d9d807d`): `api_error`: falha sintética da API
- REQ-004 (caso `src-3f478d516d9d807d`): `invalid_output`: resposta sintética fora do contrato

## Requisitos em revisão humana

Candidato com baixa confiança (abaixo de `review.confidence_threshold`, 0.6) ou tipo ambíguo. Fica em `needs_review` e não é descartado.

- REQ-005: “Somente a coordenação pode cancelar a reserva de outra pessoa.”. Motivo: baixa confiança (0.4 abaixo do limiar 0.6)
- REQ-010: “O sistema deve funcionar no celular.”. Motivo: tipo ambíguo; baixa confiança (0.5 abaixo do limiar 0.6)

## Atributos de qualidade sem valor quantitativo

Requisito com atributo de qualidade e sem `quantitative_value`. A expressão vaga foi normalizada para a categoria, e o valor fica para refinamento.

- REQ-004: desempenho. Valor quantitativo pendente. Marca de valor pendente: sim
- REQ-005: segurança. Valor quantitativo pendente. Marca de valor pendente: não

## Casos sem saída nesta condição

Caso inválido conta como zero requisito gerado. Nenhum artefato acima tem requisito dele.

- `src-71d5fe87d6dfb68a`: `invalid_output`

## Limitações observadas

Espaço do autor. O gerador não escreve nesta seção.

- O que o grafo não conseguiu representar: _A preencher pelo autor._
- Requisitos que a fonte não sustenta: _A preencher pelo autor._
- Outras observações: _A preencher pelo autor._
