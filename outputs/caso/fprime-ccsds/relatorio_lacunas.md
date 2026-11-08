# Relatório de lacunas: fprime-ccsds

> Gerado pelo ReqKG-LLM a partir dos registros da corrida, sem edição manual. Para regenerar: `PYTHONPATH=code .venv/bin/python -m deliverables pilot-caso-01 --condition REQKG-grounded --run-index 0 --name fprime-ccsds --ingestion data/raw/caso/caso_piloto.toml`.
>
> - Corrida: `pilot-caso-01`, condição `REQKG-grounded`, repetição 0 (a corrida tem 1).
> - Corrida piloto: sim. Não entra no relatório como resultado.
> - Modelo: `qwen3:14b`. Respostas gravadas (replay): não.
> - Comando da corrida: `PYTHONPATH=code .venv/bin/python -m experiments.runner pilot-caso-01 --real --pilot --runs 1 --ingestion data/raw/caso/caso_piloto.toml`.
> - Casos: `src-10c1106f4b63ce65` (`data/raw/caso/sdd/SpacePacketDeframer.md`), `src-19633f6a72a3da31` (`data/raw/caso/issues/issue_3492.md`), `src-3dd53f82b418508a` (`data/raw/caso/issues/issue_3491.md`), `src-70d9f10aa1b8a6c3` (`data/raw/caso/sdd/TcDeframer.md`), `src-7945671485477302` (`data/raw/caso/issues/issue_5485.md`), `src-974e951c733c8e7a` (`data/raw/caso/discussions/discussion_4030.md`), `src-9cfd29d516561c4e` (`data/raw/caso/issues/issue_5114.md`), `src-c9b8a83013558e6f` (`data/raw/caso/sdd/ApidManager.md`), `src-cf097721f7a993df` (`data/raw/caso/sdd/TmFramer.md`), `src-d1507de263dc69b8` (`data/raw/caso/sdd/SpacePacketFramer.md`), `src-e4ac13f99401393a` (`data/raw/caso/discussions/discussion_5027.md`), `src-e8a2e7c2f903f103` (`data/raw/caso/sdd/AesGcmDecryptor.md`).
> - Configuração: `code/experiments/config/experiment.toml` (SHA-256 `43a48015ae13d15e742d4c1fa56694dd0a89b507ee5d26fd477d5839e48d806c`).
> - Ingestão: `data/raw/caso/caso_piloto.toml` (SHA-256 `45ce02412f1aab1ad26541aa3094e3e36e78ce54d01ef6a328eb7247a13bb89d`).

As violações C, P e K são as de `domain.rules.check_all` sobre a saída final de cada caso, o mesmo ponto de medida das métricas. As recusas W são as de `domain.persist.to_records` ao montar a instância. As explicações das regras são as de `code/domain/schema/RULES.md`.

## Resumo

| Família | Regra | O que conta | Ocorrências |
| --- | --- | --- | --- |
| completude | C1 | Requisito sem prioridade MoSCoW. | 12 |
| completude | C2 | Requisito sem método de verificação. | 12 |
| completude | C3 | Requisito sem tipo (funcional, não funcional ou restrição). | 0 |
| completude | C4 | Requisito não funcional sem atributo de qualidade ISO/IEC 25010. | 0 |
| proveniência | P1 | Requisito sem nenhuma evidência (fonte e chunk). | 0 |
| proveniência | P2 | Evidência cita fonte ou chunk que não existe no corpus, ou chunk de outra fonte. | 0 |
| proveniência | P3 | Citação da evidência não aparece no texto do chunk citado. | 4 |
| proveniência | P4 | Requisito ou relação marcado como fato extraído com evidência sem citação. | 0 |
| proveniência | P5 | Relação sem evidência. | 0 |
| consistência | K1 | O mesmo par de requisitos aparece como conflicts_with e duplicates. | 0 |
| consistência | K2 | Relação de um elemento com ele mesmo. | 0 |
| consistência | K3 | Ciclo em depends_on. Uma violação por componente fortemente conexo. | 0 |
| consistência | K4 | Ciclo em refines. Uma violação por componente fortemente conexo. | 0 |
| consistência | K5 | Requisito Must depende de requisito Won't. | 0 |
| recusa na gravação | W1 | Item sem nenhuma evidência que resolve no corpus com citação presente no chunk. | 4 |
| recusa na gravação | W2 | Relação com uma ponta que não foi gravada. | 0 |
| recusa na gravação | W3 | Relação sem evidência que resolve no corpus. | 0 |
| recusa na gravação | W4 | Ator com o mesmo nome e tipo diferente de um ator já gravado. Vale o primeiro. | 0 |
| recusa na gravação | W5 | Relação que liga um nó a ele mesmo depois da resolução de identificadores. | 0 |
| recusa na gravação | W6 | Requisito com o mesmo identificador de outro já gravado. Vale o primeiro. | 0 |

| Outras lacunas | Ocorrências |
| --- | --- |
| Requisitos em revisão humana | 0 |
| Atributos de qualidade sem valor quantitativo | 0 |
| Refinamentos recusados (regras G) | 6 |
| Casos sem saída nesta condição | 5 |

## Completude (C1 a C4)

### C1. Requisito sem prioridade MoSCoW.

- REQ-001: priority ausente (caso `src-e4ac13f99401393a`)
- REQ-003: priority ausente (caso `src-e4ac13f99401393a`)
- REQ-004: priority ausente (caso `src-e4ac13f99401393a`)
- REQ-005: priority ausente (caso `src-e4ac13f99401393a`)
- REQ-006: priority ausente (caso `src-e4ac13f99401393a`)
- REQ-007: priority ausente (caso `src-e4ac13f99401393a`)
- REQ-008: priority ausente (caso `src-e4ac13f99401393a`)
- REQ-009: priority ausente (caso `src-e4ac13f99401393a`)
- REQ-010: priority ausente (caso `src-e4ac13f99401393a`)
- REQ-013: priority ausente (caso `src-3dd53f82b418508a`)
- REQ-015: priority ausente (caso `src-19633f6a72a3da31`)
- REQ-017: priority ausente (caso `src-7945671485477302`)

### C2. Requisito sem método de verificação.

- REQ-001: verification_method ausente (caso `src-e4ac13f99401393a`)
- REQ-003: verification_method ausente (caso `src-e4ac13f99401393a`)
- REQ-004: verification_method ausente (caso `src-e4ac13f99401393a`)
- REQ-005: verification_method ausente (caso `src-e4ac13f99401393a`)
- REQ-006: verification_method ausente (caso `src-e4ac13f99401393a`)
- REQ-007: verification_method ausente (caso `src-e4ac13f99401393a`)
- REQ-008: verification_method ausente (caso `src-e4ac13f99401393a`)
- REQ-009: verification_method ausente (caso `src-e4ac13f99401393a`)
- REQ-010: verification_method ausente (caso `src-e4ac13f99401393a`)
- REQ-013: verification_method ausente (caso `src-3dd53f82b418508a`)
- REQ-015: verification_method ausente (caso `src-19633f6a72a3da31`)
- REQ-017: verification_method ausente (caso `src-7945671485477302`)

### C3. Requisito sem tipo (funcional, não funcional ou restrição).

Nenhuma ocorrência.

### C4. Requisito não funcional sem atributo de qualidade ISO/IEC 25010.

Nenhuma ocorrência.

## Proveniência (P1 a P5)

### P1. Requisito sem nenhuma evidência (fonte e chunk).

Nenhuma ocorrência.

### P2. Evidência cita fonte ou chunk que não existe no corpus, ou chunk de outra fonte.

Nenhuma ocorrência.

### P3. Citação da evidência não aparece no texto do chunk citado.

- componente 'TM/AOS framer': citação não aparece em chk-fc6c32a5a509b7aa (caso `src-7945671485477302`)
- entidade 'CCSDS TC Space Data Link Protocol': citação não aparece em chk-c6a8f78eb2d82112 (caso `src-70d9f10aa1b8a6c3`)
- entidade 'CCSDS TC specification (CCSDS 232.0-B-4)': citação não aparece em chk-971e889a11b4e078 (caso `src-70d9f10aa1b8a6c3`)
- entidade 'Expedited Service mode': citação não aparece em chk-bb305a12b912c89b (caso `src-70d9f10aa1b8a6c3`)

### P4. Requisito ou relação marcado como fato extraído com evidência sem citação.

Nenhuma ocorrência.

### P5. Relação sem evidência.

Nenhuma ocorrência.

## Consistência (K1 a K5)

### K1. O mesmo par de requisitos aparece como conflicts_with e duplicates.

Nenhuma ocorrência.

### K2. Relação de um elemento com ele mesmo.

Nenhuma ocorrência.

### K3. Ciclo em depends_on. Uma violação por componente fortemente conexo.

Nenhuma ocorrência.

### K4. Ciclo em refines. Uma violação por componente fortemente conexo.

Nenhuma ocorrência.

### K5. Requisito Must depende de requisito Won't.

Nenhuma ocorrência.

## Recusas na gravação (W1 a W6)

### Nesta instância

Recusas de `to_records` sobre a saída final desta condição. O item recusado não está na instância.

#### W1. Item sem nenhuma evidência que resolve no corpus com citação presente no chunk.

- entidade 'Expedited Service mode': entidade sem evidência que resolve (caso `src-70d9f10aa1b8a6c3`)
- entidade 'CCSDS TC Space Data Link Protocol': entidade sem evidência que resolve (caso `src-70d9f10aa1b8a6c3`)
- entidade 'CCSDS TC specification (CCSDS 232.0-B-4)': entidade sem evidência que resolve (caso `src-70d9f10aa1b8a6c3`)
- componente 'TM/AOS framer': componente sem evidência que resolve (caso `src-7945671485477302`)

#### W2. Relação com uma ponta que não foi gravada.

Nenhuma ocorrência.

#### W3. Relação sem evidência que resolve no corpus.

Nenhuma ocorrência.

#### W4. Ator com o mesmo nome e tipo diferente de um ator já gravado. Vale o primeiro.

Nenhuma ocorrência.

#### W5. Relação que liga um nó a ele mesmo depois da resolução de identificadores.

Nenhuma ocorrência.

#### W6. Requisito com o mesmo identificador de outro já gravado. Vale o primeiro.

Nenhuma ocorrência.

### Registradas pelo executor

Recusas de `outputs/runs/pilot-caso-01/rejections.jsonl` nesta repetição, da gravação da extração compartilhada no grafo. Podem diferir das recusas acima, que partem da saída final depois do refinamento. Os assuntos são chaves da extração compartilhada.

- W1: entidade 'Expedited Service mode': entidade sem evidência que resolve (caso `src-70d9f10aa1b8a6c3`)
- W1: entidade 'CCSDS TC Space Data Link Protocol': entidade sem evidência que resolve (caso `src-70d9f10aa1b8a6c3`)
- W1: entidade 'CCSDS TC specification (CCSDS 232.0-B-4)': entidade sem evidência que resolve (caso `src-70d9f10aa1b8a6c3`)
- W1: componente 'TM/AOS framer': componente sem evidência que resolve (caso `src-7945671485477302`)

## Refinamento de uma passagem

| Caso | Alvos | Aceitos | Recusados | Chamada falhou | Sem resultado registrado |
| --- | --- | --- | --- | --- | --- |
| `src-10c1106f4b63ce65` | 0 | 0 | 0 | 0 | 0 |
| `src-19633f6a72a3da31` | 2 | 1 | 1 | 0 | 0 |
| `src-3dd53f82b418508a` | 2 | 1 | 1 | 0 | 0 |
| `src-70d9f10aa1b8a6c3` | 0 | 0 | 0 | 0 | 0 |
| `src-7945671485477302` | 2 | 1 | 1 | 0 | 0 |
| `src-974e951c733c8e7a` | 0 | 0 | 0 | 0 | 0 |
| `src-9cfd29d516561c4e` | 0 | 0 | 0 | 0 | 0 |
| `src-c9b8a83013558e6f` | 0 | 0 | 0 | 0 | 0 |
| `src-cf097721f7a993df` | 0 | 0 | 0 | 0 | 0 |
| `src-d1507de263dc69b8` | 0 | 0 | 0 | 0 | 0 |
| `src-e4ac13f99401393a` | 11 | 8 | 3 | 0 | 0 |
| `src-e8a2e7c2f903f103` | 0 | 0 | 0 | 0 | 0 |

### Refinamentos recusados

Com qualquer violação G, o sistema recusa o refinamento e mantém o candidato original.

- REQ-015 (caso `src-19633f6a72a3da31`): G6 (Evidência nova (ausente do candidato original) não passa em CorpusIndex.supports no corpus do caso (chunk de outro documento ou citação que não aparece no chunk), ou prioridade ou método de verificação nulos no original foram preenchidos sem nenhuma evidência nova que passe.): priority preenchido sem evidência nova válida; G6 (Evidência nova (ausente do candidato original) não passa em CorpusIndex.supports no corpus do caso (chunk de outro documento ou citação que não aparece no chunk), ou prioridade ou método de verificação nulos no original foram preenchidos sem nenhuma evidência nova que passe.): verification_method preenchido sem evidência nova válida
- REQ-013 (caso `src-3dd53f82b418508a`): G6 (Evidência nova (ausente do candidato original) não passa em CorpusIndex.supports no corpus do caso (chunk de outro documento ou citação que não aparece no chunk), ou prioridade ou método de verificação nulos no original foram preenchidos sem nenhuma evidência nova que passe.): priority preenchido sem evidência nova válida; G6 (Evidência nova (ausente do candidato original) não passa em CorpusIndex.supports no corpus do caso (chunk de outro documento ou citação que não aparece no chunk), ou prioridade ou método de verificação nulos no original foram preenchidos sem nenhuma evidência nova que passe.): verification_method preenchido sem evidência nova válida
- REQ-017 (caso `src-7945671485477302`): G6 (Evidência nova (ausente do candidato original) não passa em CorpusIndex.supports no corpus do caso (chunk de outro documento ou citação que não aparece no chunk), ou prioridade ou método de verificação nulos no original foram preenchidos sem nenhuma evidência nova que passe.): priority preenchido sem evidência nova válida; G6 (Evidência nova (ausente do candidato original) não passa em CorpusIndex.supports no corpus do caso (chunk de outro documento ou citação que não aparece no chunk), ou prioridade ou método de verificação nulos no original foram preenchidos sem nenhuma evidência nova que passe.): verification_method preenchido sem evidência nova válida
- REQ-001 (caso `src-e4ac13f99401393a`): G6 (Evidência nova (ausente do candidato original) não passa em CorpusIndex.supports no corpus do caso (chunk de outro documento ou citação que não aparece no chunk), ou prioridade ou método de verificação nulos no original foram preenchidos sem nenhuma evidência nova que passe.): priority preenchido sem evidência nova válida; G6 (Evidência nova (ausente do candidato original) não passa em CorpusIndex.supports no corpus do caso (chunk de outro documento ou citação que não aparece no chunk), ou prioridade ou método de verificação nulos no original foram preenchidos sem nenhuma evidência nova que passe.): verification_method preenchido sem evidência nova válida
- REQ-003 (caso `src-e4ac13f99401393a`): G6 (Evidência nova (ausente do candidato original) não passa em CorpusIndex.supports no corpus do caso (chunk de outro documento ou citação que não aparece no chunk), ou prioridade ou método de verificação nulos no original foram preenchidos sem nenhuma evidência nova que passe.): priority preenchido sem evidência nova válida; G6 (Evidência nova (ausente do candidato original) não passa em CorpusIndex.supports no corpus do caso (chunk de outro documento ou citação que não aparece no chunk), ou prioridade ou método de verificação nulos no original foram preenchidos sem nenhuma evidência nova que passe.): verification_method preenchido sem evidência nova válida
- REQ-005 (caso `src-e4ac13f99401393a`): G6 (Evidência nova (ausente do candidato original) não passa em CorpusIndex.supports no corpus do caso (chunk de outro documento ou citação que não aparece no chunk), ou prioridade ou método de verificação nulos no original foram preenchidos sem nenhuma evidência nova que passe.): priority preenchido sem evidência nova válida; G6 (Evidência nova (ausente do candidato original) não passa em CorpusIndex.supports no corpus do caso (chunk de outro documento ou citação que não aparece no chunk), ou prioridade ou método de verificação nulos no original foram preenchidos sem nenhuma evidência nova que passe.): verification_method preenchido sem evidência nova válida

### Chamadas de refinamento que falharam

O candidato original fica. Alvos de `FinalRecord.failed`, com o erro do `CaseResult` do mesmo alvo:

Nenhuma ocorrência.

## Requisitos em revisão humana

Candidato com baixa confiança (abaixo de `review.confidence_threshold`, 0.6) ou tipo ambíguo. Fica em `needs_review` e não é descartado.

Nenhuma ocorrência.

## Atributos de qualidade sem valor quantitativo

Requisito com atributo de qualidade e sem `quantitative_value`. A expressão vaga foi normalizada para a categoria, e o valor fica para refinamento.

Nenhuma ocorrência.

## Casos sem saída nesta condição

Caso inválido conta como zero requisito gerado. Nenhum artefato acima tem requisito dele.

- `src-9cfd29d516561c4e`: `invalid_output`
- `src-c9b8a83013558e6f`: `invalid_output`
- `src-cf097721f7a993df`: `invalid_output`
- `src-d1507de263dc69b8`: `invalid_output`
- `src-e8a2e7c2f903f103`: `invalid_output`

## Limitações observadas

Espaço do autor. O gerador não escreve nesta seção.

- O que o grafo não conseguiu representar: _A preencher pelo autor._
- Requisitos que a fonte não sustenta: _A preencher pelo autor._
- Outras observações: _A preencher pelo autor._
