# Esboço de SRS: fixture-sintetico

> Gerado pelo ReqKG-LLM a partir dos registros da corrida, sem edição manual. Para regenerar: `PYTHONPATH=code .venv/bin/python -m deliverables sintetico-entrevista --condition REQKG-grounded --run-index 0 --name fixture-sintetico --runs-dir code/deliverables/fixtures/runs --config code/deliverables/fixtures/experiment.toml`.
>
> - Corrida: `sintetico-entrevista`, condição `REQKG-grounded`, repetição 0 (a corrida tem 1).
> - Corrida piloto: não.
> - Modelo: `nenhum-fixture-sintetico`. Respostas gravadas (replay): sim.
> - Comando da corrida: `code/deliverables/fixtures/build.py (corrida sintética, sem chamada de modelo)`.
> - Casos: `src-339ed9b9a545ccbc` (`code/ingestion/fixtures/ata_sintetica.md`), `src-3f478d516d9d807d` (`code/domain/fixtures/corpus/entrevista_sintetica.txt`), `src-71d5fe87d6dfb68a` (`code/ingestion/fixtures/descricao_sintetica.txt`).
> - Configuração: `code/deliverables/fixtures/experiment.toml` (SHA-256 `55a6bc3ea88f82f06dba7bc42ab4f1d1f9144426fbf23e530d1dc8489954b5bc`).
> - Ingestão: `data/processed/ingestion/fixture.json` (SHA-256 `49756503282cf362a9f61a496f0fe29b6ea8e69dfa1ecf71f822b801cbe44a7f`).

Esboço na estrutura de SRS da ISO/IEC/IEEE 29148:2018. O gerador não preenche nenhum campo: o que falta nos registros aparece como "pendente". Propósito, escopo e visão geral ficam com o autor. Requisito marcado **Em revisão humana** tem baixa confiança ou tipo ambíguo e ainda não foi aceito.

## 1. Introdução

### 1.1 Propósito

_A preencher pelo autor._

### 1.2 Escopo

_A preencher pelo autor._

### 1.3 Visão geral do produto

_A preencher pelo autor._

### 1.4 Convenções deste esboço

- `REQ-NNN` numera os requisitos pela ordem de leitura da primeira evidência que resolve no corpus, na extração compartilhada pelas duas condições. O mesmo candidato tem o mesmo número nas duas condições. Ao lado vem o `requirement_id` do ReqKG. Candidato que não entrou no grafo diz o motivo no campo Status.
- Prioridade em MoSCoW. Método de verificação: inspeção, análise, demonstração ou teste. Atributos de qualidade da ISO/IEC 25010.
- "pendente" marca campo ausente nos registros. O modelo só preenche prioridade e método com sinal explícito no texto, citado.
- A citação é o trecho que o modelo deu como evidência, conferido contra o texto do chunk com a normalização da regra P3.

## 2. Referências

### 2.1 Documentos-fonte

| Documento | Caminho | Tipo | Título | SHA-256 | source_id |
| --- | --- | --- | --- | --- | --- |
| D1 | `code/domain/fixtures/corpus/entrevista_sintetica.txt` | `interview` | Entrevista sintética de desenvolvimento | `ec33b403b91299165cc86651d8c0751927a1225a27d04adbd912b792ba3676ac` | `src-3f478d516d9d807d` |
| D2 | `code/ingestion/fixtures/ata_sintetica.md` | `meeting_record` | Ata sintética da reunião de acompanhamento | `3b9c5d000e99031d05ca6980ca083e7801ac4be805d435ca8a4ded55496bb7c8` | `src-339ed9b9a545ccbc` |
| D3 | `code/ingestion/fixtures/descricao_sintetica.txt` | `existing_system_description` | Descrição sintética do processo atual | `957e15615e3f88e5efa775b23a978a9cfa7761a3087ffc007908c6c0a342b19b` | `src-71d5fe87d6dfb68a` |

## 3. Stakeholders e atores

| Ator | Tipo | actor_id | Fonte | Citação | Requisitos ligados |
| --- | --- | --- | --- | --- | --- |
| Coordenadora do laboratório | stakeholder | `act-a8ce03319323904b` | D1 `code/domain/fixtures/corpus/entrevista_sintetica.txt`, chunk `chk-9e31855f3c8b8ca8` (índice 1); D2 `code/ingestion/fixtures/ata_sintetica.md`, chunk `chk-c5b123cf9e21984a` (índice 6) | “Coordenadora do laboratório” (aparece no chunk); “A coordenadora relatou” (aparece no chunk) | REQ-005, REQ-007 |
| Responsável pela calibração | stakeholder | `act-8b59336233f82449` | D2 `code/ingestion/fixtures/ata_sintetica.md`, chunk `chk-e317d2f30be53bb4` (índice 7) | “O responsável pela calibração” (aparece no chunk) | REQ-008 |
| Técnico | papel de usuário | `act-f800de8bd6992ad6` | D1 `code/domain/fixtures/corpus/entrevista_sintetica.txt`, chunk `chk-f7faa2ea1130ac73` (índice 2) | “Técnico” (aparece no chunk) | REQ-001, REQ-003 |

Atores propostos pelo modelo e não gravados no grafo:

| Ator | Tipo | Registro | Fonte | Motivo |
| --- | --- | --- | --- | --- |
| técnico | stakeholder | caso `src-3f478d516d9d807d`, chave `c0-A3` | pendente | W4: Ator com o mesmo nome e tipo diferente de um ator já gravado. Vale o primeiro. |

## 4. Requisitos específicos

| Grupo | Requisitos | Em revisão humana |
| --- | --- | --- |
| Funcionais | 4 | 0 |
| Não funcionais | 4 | 1 |
| Restrições | 1 | 0 |
| Tipo pendente | 1 | 1 |
| Total | 10 | 2 |

### 4.1 Requisitos funcionais

#### REQ-001 · `req-3b1ddc6aee370cc7`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve permitir que o técnico reserve um equipamento por horário. |
| Tipo | funcional |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | 0.9 |
| Origem | fato extraído |
| Refinamento | chamada falhou |
| Fonte | D1 `code/domain/fixtures/corpus/entrevista_sintetica.txt`, chunk `chk-9e31855f3c8b8ca8` (índice 1) |
| Citação | “Os técnicos precisam reservar um equipamento por horário” (aparece no chunk) |
| Registro | caso `src-3f478d516d9d807d`, chave `c0-R1` |

#### REQ-002 · `req-9355e7e726822797`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve impedir duas reservas do mesmo equipamento no mesmo horário. |
| Tipo | funcional |
| Prioridade | Must |
| Método de verificação | teste |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | 0.95 |
| Origem | fato extraído |
| Refinamento | não selecionado |
| Fonte | D1 `code/domain/fixtures/corpus/entrevista_sintetica.txt`, chunk `chk-9e31855f3c8b8ca8` (índice 1) |
| Citação | “o sistema tem de impedir duas reservas no mesmo horário” (aparece no chunk) |
| Registro | caso `src-3f478d516d9d807d`, chave `c0-R2` |

#### REQ-007 · `req-de8ecb7a42bffc2b`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve recusar a segunda reserva do mesmo equipamento no mesmo horário e mostrar quem já reservou. |
| Declaração antes do refinamento | O sistema deve recusar a segunda reserva do mesmo equipamento no mesmo horário e mostrar quem já reservou. |
| Tipo | funcional |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | 0.9 |
| Origem | fato extraído |
| Refinamento | aceito, revisão 1 |
| Fonte | D2 `code/ingestion/fixtures/ata_sintetica.md`, chunk `chk-c5b123cf9e21984a` (índice 6) |
| Citação | “Ela pediu que o sistema novo recuse a segunda reserva e mostre quem já reservou” (aparece no chunk) |
| Registro | caso `src-339ed9b9a545ccbc`, chave `c1-R1` |

#### REQ-009 · sem requirement_id

| Campo | Valor |
| --- | --- |
| Declaração | A coordenação deve listar os equipamentos que exigem calibração. |
| Tipo | funcional |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | pendente: não gravado no grafo (W1: Item sem nenhuma evidência que resolve no corpus com citação presente no chunk.) |
| Marcas de revisão | nenhuma |
| Confiança declarada | 0.7 |
| Origem | fato extraído (declarada pelo modelo, não gravada) |
| Refinamento | aceito |
| Fonte | `src-339ed9b9a545ccbc` / `chk-3ebce0a3871c0412`: fora do corpus do caso (P2) |
| Citação | “A coordenação vai listar os equipamentos que exigem calibração” (não conferida: chunk fora do corpus do caso) |
| Registro | caso `src-3f478d516d9d807d`, chave `c0-R7` |

### 4.2 Requisitos não funcionais

Cada requisito aparece uma vez, no primeiro dos seus atributos na ordem abaixo. O campo Atributos de qualidade lista todos.

#### 4.2.1 Desempenho (`performance`)

##### REQ-003 · `req-72bbb881bec43307`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve enviar um aviso ao responsável em até cinco minutos depois que a calibração vence. |
| Declaração antes do refinamento | O sistema deve avisar o responsável quando a calibração vencer. |
| Tipo | não funcional |
| Atributos de qualidade | desempenho (`performance`) |
| Valor quantitativo | até cinco minutos |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | 0.8 |
| Origem | fato extraído |
| Refinamento | aceito, revisão 1 |
| Fonte | D1 `code/domain/fixtures/corpus/entrevista_sintetica.txt`, chunk `chk-f7faa2ea1130ac73` (índice 2) |
| Citação | “O sistema deve enviar um aviso ao responsável em até cinco minutos depois que a calibração vence” (aparece no chunk) |
| Registro | caso `src-3f478d516d9d807d`, chave `c0-R3` |

##### REQ-004 · `req-d6f0dc9db697e655`

| Campo | Valor |
| --- | --- |
| Declaração | A consulta da agenda deve ser rápida. |
| Tipo | não funcional |
| Atributos de qualidade | desempenho (`performance`) |
| Valor quantitativo | pendente |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | rascunho (`draft`) |
| Marcas de revisão | valor quantitativo pendente |
| Confiança declarada | 0.85 |
| Origem | fato extraído |
| Refinamento | chamada falhou |
| Fonte | D1 `code/domain/fixtures/corpus/entrevista_sintetica.txt`, chunk `chk-f7faa2ea1130ac73` (índice 2) |
| Citação | “A consulta da agenda precisa ser rápida” (aparece no chunk) |
| Registro | caso `src-3f478d516d9d807d`, chave `c0-R4` |

##### REQ-008 · `req-9dc3db710289946e`

| Campo | Valor |
| --- | --- |
| Declaração | O aviso de vencimento da calibração deve aparecer no próprio sistema no mesmo dia do vencimento. |
| Declaração antes do refinamento | O aviso de vencimento da calibração deve aparecer no próprio sistema no mesmo dia do vencimento. |
| Tipo | não funcional |
| Atributos de qualidade | desempenho (`performance`) |
| Valor quantitativo | no mesmo dia do vencimento |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | 0.85 |
| Origem | fato extraído |
| Refinamento | aceito, revisão 1 |
| Fonte | D2 `code/ingestion/fixtures/ata_sintetica.md`, chunk `chk-e317d2f30be53bb4` (índice 7) |
| Citação | “Ele quer o aviso no próprio sistema, no mesmo dia do vencimento” (aparece no chunk) |
| Registro | caso `src-339ed9b9a545ccbc`, chave `c1-R2` |

#### 4.2.2 Segurança (`security`)

##### REQ-005 · `req-c8625b22e934be3a`

> **Em revisão humana**: baixa confiança (0.4 abaixo do limiar 0.6).

| Campo | Valor |
| --- | --- |
| Declaração | Somente a coordenação pode cancelar a reserva de outra pessoa. |
| Tipo | não funcional |
| Atributos de qualidade | segurança (`security`) |
| Valor quantitativo | pendente |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | em revisão humana (`needs_review`) |
| Marcas de revisão | baixa confiança |
| Confiança declarada | 0.4 |
| Origem | fato extraído |
| Refinamento | recusado |
| Fonte | D1 `code/domain/fixtures/corpus/entrevista_sintetica.txt`, chunk `chk-202c7f98847e276d` (índice 3) |
| Citação | “só a coordenação pode cancelar reserva de outra pessoa” (aparece no chunk) |
| Registro | caso `src-3f478d516d9d807d`, chave `c0-R5` |

#### 4.2.3 Usabilidade (`usability`)

Nenhum requisito.

#### 4.2.4 Confiabilidade (`reliability`)

Nenhum requisito.

#### 4.2.5 Manutenibilidade (`maintainability`)

Nenhum requisito.

#### 4.2.6 Portabilidade (`portability`)

Nenhum requisito.

#### 4.2.7 Sem atributo de qualidade (C4)

Nenhum requisito.

### 4.3 Restrições

#### REQ-006 · sem requirement_id

| Campo | Valor |
| --- | --- |
| Declaração | Os dados de uso devem ser guardados por dois anos para auditoria. |
| Tipo | restrição |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | pendente: não gravado no grafo (W1: Item sem nenhuma evidência que resolve no corpus com citação presente no chunk.) |
| Marcas de revisão | nenhuma |
| Confiança declarada | 0.9 |
| Origem | fato extraído (declarada pelo modelo, não gravada) |
| Refinamento | aceito |
| Fonte | D1 `code/domain/fixtures/corpus/entrevista_sintetica.txt`, chunk `chk-202c7f98847e276d` (índice 3) |
| Citação | “Os dados de uso ficam armazenados por dois anos” (**não aparece no chunk citado, P3**) |
| Registro | caso `src-3f478d516d9d807d`, chave `c0-R6` |

### 4.4 Tipo pendente (C3)

#### REQ-010 · sem requirement_id

> **Em revisão humana**: tipo ambíguo; baixa confiança (0.5 abaixo do limiar 0.6).

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve funcionar no celular. |
| Tipo | pendente |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | pendente: não gravado no grafo (W1: Item sem nenhuma evidência que resolve no corpus com citação presente no chunk.) |
| Marcas de revisão | tipo ambíguo, baixa confiança |
| Confiança declarada | 0.5 |
| Origem | fato extraído (declarada pelo modelo, não gravada) |
| Refinamento | aceito |
| Fonte | pendente (sem evidência, P1) |
| Citação | pendente |
| Registro | caso `src-3f478d516d9d807d`, chave `c0-R8` |

## 5. Verificação

| Método de verificação | Requisitos |
| --- | --- |
| teste | 1 |
| pendente | 9 |

Plano de verificação: _A preencher pelo autor._

## Apêndice A. Rastreabilidade

A matriz de proveniência está em `matriz_proveniencia.md` e `matriz_proveniencia.csv`. As lacunas estão em `relatorio_lacunas.md`, e a instância do ReqKG em `instancia_reqkg.json`.
