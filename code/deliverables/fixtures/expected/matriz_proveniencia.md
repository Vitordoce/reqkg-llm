# Matriz de proveniência: fixture-sintetico

> Gerado pelo ReqKG-LLM a partir dos registros da corrida, sem edição manual. Para regenerar: `PYTHONPATH=code .venv/bin/python -m deliverables sintetico-entrevista --condition REQKG-grounded --run-index 0 --name fixture-sintetico --runs-dir code/deliverables/fixtures/runs --config code/deliverables/fixtures/experiment.toml`.
>
> - Corrida: `sintetico-entrevista`, condição `REQKG-grounded`, repetição 0 (a corrida tem 1).
> - Corrida piloto: não.
> - Modelo: `nenhum-fixture-sintetico`. Respostas gravadas (replay): sim.
> - Comando da corrida: `code/deliverables/fixtures/build.py (corrida sintética, sem chamada de modelo)`.
> - Casos: `src-339ed9b9a545ccbc` (`code/ingestion/fixtures/ata_sintetica.md`), `src-3f478d516d9d807d` (`code/domain/fixtures/corpus/entrevista_sintetica.txt`), `src-71d5fe87d6dfb68a` (`code/ingestion/fixtures/descricao_sintetica.txt`).
> - Configuração: `code/deliverables/fixtures/experiment.toml` (SHA-256 `55a6bc3ea88f82f06dba7bc42ab4f1d1f9144426fbf23e530d1dc8489954b5bc`).
> - Ingestão: `data/processed/ingestion/fixture.json` (SHA-256 `49756503282cf362a9f61a496f0fe29b6ea8e69dfa1ecf71f822b801cbe44a7f`).

Uma linha por evidência citada pelo requisito na saída final. A coluna "Citação no chunk" confere a citação contra o texto do chunk com a normalização da regra P3 (NFC, espaços colapsados, sem diferença de maiúsculas). Valores: "sim", "não" (P3), "sem citação", "chunk fora do corpus do caso" (P2) e "sem evidência" (P1). A mesma tabela está em `matriz_proveniencia.csv`.

## Documentos

| Documento | Caminho | Tipo |
| --- | --- | --- |
| D1 | `code/domain/fixtures/corpus/entrevista_sintetica.txt` | `interview` |
| D2 | `code/ingestion/fixtures/ata_sintetica.md` | `meeting_record` |
| D3 | `code/ingestion/fixtures/descricao_sintetica.txt` | `existing_system_description` |

## Requisito por documento

Número de evidências do requisito em cada documento. "—" quando não há nenhuma.

| Requisito | D1 | D2 | D3 | Fora do corpus | Sem evidência |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | 1 | — | — | — | — |
| REQ-002 | 1 | — | — | — | — |
| REQ-003 | 1 | — | — | — | — |
| REQ-004 | 1 | — | — | — | — |
| REQ-005 | 1 | — | — | — | — |
| REQ-006 | 1 | — | — | — | — |
| REQ-007 | — | 1 | — | — | — |
| REQ-008 | — | 1 | — | — | — |
| REQ-009 | — | — | — | 1 | — |
| REQ-010 | — | — | — | — | sim |

## Detalhe por evidência

| Requisito | requirement_id | Documento | Chunk | Índice | Citação | Citação no chunk |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | `req-3b1ddc6aee370cc7` | D1 | `chk-9e31855f3c8b8ca8` | 1 | “Os técnicos precisam reservar um equipamento por horário” | sim |
| REQ-002 | `req-9355e7e726822797` | D1 | `chk-9e31855f3c8b8ca8` | 1 | “o sistema tem de impedir duas reservas no mesmo horário” | sim |
| REQ-003 | `req-72bbb881bec43307` | D1 | `chk-f7faa2ea1130ac73` | 2 | “O sistema deve enviar um aviso ao responsável em até cinco minutos depois que a calibração vence” | sim |
| REQ-004 | `req-d6f0dc9db697e655` | D1 | `chk-f7faa2ea1130ac73` | 2 | “A consulta da agenda precisa ser rápida” | sim |
| REQ-005 | `req-c8625b22e934be3a` | D1 | `chk-202c7f98847e276d` | 3 | “só a coordenação pode cancelar reserva de outra pessoa” | sim |
| REQ-006 | pendente | D1 | `chk-202c7f98847e276d` | 3 | “Os dados de uso ficam armazenados por dois anos” | não |
| REQ-007 | `req-de8ecb7a42bffc2b` | D2 | `chk-c5b123cf9e21984a` | 6 | “Ela pediu que o sistema novo recuse a segunda reserva e mostre quem já reservou” | sim |
| REQ-008 | `req-9dc3db710289946e` | D2 | `chk-e317d2f30be53bb4` | 7 | “Ele quer o aviso no próprio sistema, no mesmo dia do vencimento” | sim |
| REQ-009 | pendente | — | `chk-3ebce0a3871c0412` | — | “A coordenação vai listar os equipamentos que exigem calibração” | chunk fora do corpus do caso |
| REQ-010 | pendente | — | — | — | — | sem evidência |
