# Matriz de proveniência: fprime-ccsds

> Gerado pelo ReqKG-LLM a partir dos registros da corrida, sem edição manual. Para regenerar: `PYTHONPATH=code .venv/bin/python -m deliverables pilot-caso-01 --condition REQKG-grounded --run-index 0 --name fprime-ccsds --ingestion data/raw/caso/caso_piloto.toml`.
>
> - Corrida: `pilot-caso-01`, condição `REQKG-grounded`, repetição 0 (a corrida tem 1).
> - Corrida piloto: sim. Não entra no relatório como resultado.
> - Modelo: `qwen3:14b`. Respostas gravadas (replay): não.
> - Comando da corrida: `PYTHONPATH=code .venv/bin/python -m experiments.runner pilot-caso-01 --real --pilot --runs 1 --ingestion data/raw/caso/caso_piloto.toml`.
> - Casos: `src-10c1106f4b63ce65` (`data/raw/caso/sdd/SpacePacketDeframer.md`), `src-19633f6a72a3da31` (`data/raw/caso/issues/issue_3492.md`), `src-3dd53f82b418508a` (`data/raw/caso/issues/issue_3491.md`), `src-70d9f10aa1b8a6c3` (`data/raw/caso/sdd/TcDeframer.md`), `src-7945671485477302` (`data/raw/caso/issues/issue_5485.md`), `src-974e951c733c8e7a` (`data/raw/caso/discussions/discussion_4030.md`), `src-9cfd29d516561c4e` (`data/raw/caso/issues/issue_5114.md`), `src-c9b8a83013558e6f` (`data/raw/caso/sdd/ApidManager.md`), `src-cf097721f7a993df` (`data/raw/caso/sdd/TmFramer.md`), `src-d1507de263dc69b8` (`data/raw/caso/sdd/SpacePacketFramer.md`), `src-e4ac13f99401393a` (`data/raw/caso/discussions/discussion_5027.md`), `src-e8a2e7c2f903f103` (`data/raw/caso/sdd/AesGcmDecryptor.md`).
> - Configuração: `code/experiments/config/experiment.toml` (SHA-256 `43a48015ae13d15e742d4c1fa56694dd0a89b507ee5d26fd477d5839e48d806c`).
> - Ingestão: `data/raw/caso/caso_piloto.toml` (SHA-256 `45ce02412f1aab1ad26541aa3094e3e36e78ce54d01ef6a328eb7247a13bb89d`).

Uma linha por evidência citada pelo requisito na saída final. A coluna "Citação no chunk" confere a citação contra o texto do chunk com a normalização da regra P3 (NFC, espaços colapsados, sem diferença de maiúsculas). Valores: "sim", "não" (P3), "sem citação", "chunk fora do corpus do caso" (P2) e "sem evidência" (P1). A mesma tabela está em `matriz_proveniencia.csv`.

## Documentos

| Documento | Caminho | Tipo |
| --- | --- | --- |
| D1 | `data/raw/caso/discussions/discussion_4030.md` | `meeting_record` |
| D2 | `data/raw/caso/discussions/discussion_5027.md` | `meeting_record` |
| D3 | `data/raw/caso/issues/issue_3491.md` | `meeting_record` |
| D4 | `data/raw/caso/issues/issue_3492.md` | `meeting_record` |
| D5 | `data/raw/caso/issues/issue_5114.md` | `meeting_record` |
| D6 | `data/raw/caso/issues/issue_5485.md` | `meeting_record` |
| D7 | `data/raw/caso/sdd/AesGcmDecryptor.md` | `existing_system_description` |
| D8 | `data/raw/caso/sdd/ApidManager.md` | `existing_system_description` |
| D9 | `data/raw/caso/sdd/SpacePacketDeframer.md` | `existing_system_description` |
| D10 | `data/raw/caso/sdd/SpacePacketFramer.md` | `existing_system_description` |
| D11 | `data/raw/caso/sdd/TcDeframer.md` | `existing_system_description` |
| D12 | `data/raw/caso/sdd/TmFramer.md` | `existing_system_description` |

## Requisito por documento

Número de evidências do requisito em cada documento. "—" quando não há nenhuma.

| Requisito | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 | D11 | D12 | Fora do corpus | Sem evidência |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | — | 1 | — | — | — | — | — | — | — | — | — | — | — | — |
| REQ-002 | — | 1 | — | — | — | — | — | — | — | — | — | — | — | — |
| REQ-003 | — | 1 | — | — | — | — | — | — | — | — | — | — | — | — |
| REQ-004 | — | 1 | — | — | — | — | — | — | — | — | — | — | — | — |
| REQ-005 | — | 1 | — | — | — | — | — | — | — | — | — | — | — | — |
| REQ-006 | — | 1 | — | — | — | — | — | — | — | — | — | — | — | — |
| REQ-007 | — | 1 | — | — | — | — | — | — | — | — | — | — | — | — |
| REQ-008 | — | 1 | — | — | — | — | — | — | — | — | — | — | — | — |
| REQ-009 | — | 1 | — | — | — | — | — | — | — | — | — | — | — | — |
| REQ-010 | — | 1 | — | — | — | — | — | — | — | — | — | — | — | — |
| REQ-011 | — | 2 | — | — | — | — | — | — | — | — | — | — | — | — |
| REQ-012 | — | — | 2 | — | — | — | — | — | — | — | — | — | — | — |
| REQ-013 | — | — | 1 | — | — | — | — | — | — | — | — | — | — | — |
| REQ-014 | — | — | — | 1 | — | — | — | — | — | — | — | — | — | — |
| REQ-015 | — | — | — | 1 | — | — | — | — | — | — | — | — | — | — |
| REQ-016 | — | — | — | — | — | 2 | — | — | — | — | — | — | — | — |
| REQ-017 | — | — | — | — | — | 1 | — | — | — | — | — | — | — | — |

## Detalhe por evidência

| Requisito | requirement_id | Documento | Chunk | Índice | Citação | Citação no chunk |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | `req-41ddf541e3825dc8` | D2 | `chk-5771881ddc30d122` | 2 | “we would like to do better in how we represent data in CCSDS packets to fall in-line with more industry standards and better meet user needs” | sim |
| REQ-002 | `req-aa8af9b746c7c40c` | D2 | `chk-fae01834d331e52c` | 4 | “CCSDS recommends representing time in a secondary header. Possibly with a U16/U32 format. We suggest making this configurable so that project that do not need the full Fw.Time representation don't have to use this.” | sim |
| REQ-003 | `req-9f32ba94621e8bb2` | D2 | `chk-fae01834d331e52c` | 4 | “We suggest making this configurable so that project that do not need the full Fw.Time representation don't have to use this.” | sim |
| REQ-004 | `req-b1da379cea72d155` | D2 | `chk-365391d5cd373236` | 6 | “We propose having a configuration where the packet ID of the tlm packetizer maps to the APID.” | sim |
| REQ-005 | `req-aa07a72c8e17ab21` | D2 | `chk-365391d5cd373236` | 6 | “This would save overhead on sending a redundant packet ID when the APID 11bits are under-utilized.” | sim |
| REQ-006 | `req-85f9ccb427ee5ad9` | D2 | `chk-02673deeacf3aad1` | 9 | “I am highly in favor expanding our support of the various CCSDS standards!” | sim |
| REQ-007 | `req-9ce686f22719cd5c` | D2 | `chk-eb8869963bdf1acd` | 10 | “For the timestamp in the secondary header of Space Packet, big upvote from me.” | sim |
| REQ-008 | `req-39be74680256dfc2` | D2 | `chk-39cab25d468e696c` | 13 | “APID should not be forcibly tied to the TlmPacketizer Packet IDs” | sim |
| REQ-009 | `req-9e7154aa58441efb` | D2 | `chk-e449e51c02cec32d` | 15 | “Anyway, my general preference is to consider APID's to represent *Applications*. That means I want things like file transfer to have an APID, general housekeeping to have an APID, a specific instrument or subsystem to be allocated its own APID.” | sim |
| REQ-010 | `req-ecebc47befd7a848` | D2 | `chk-ccc54904009238f4` | 17 | “adding the time in a secondary header with a deployment configurable length/format” | sim |
| REQ-011 | `req-37def9fa32862d5f` | D2 | `chk-ce17ae8cbb5eeb73` | 18 | “considering an APID to identify application (source) + data criticality” | sim |
| REQ-011 | `req-37def9fa32862d5f` | D2 | `chk-ce17ae8cbb5eeb73` | 18 | “so that ground software can identify meaningful information about the packet by only parsing the CCSDS headers” | sim |
| REQ-012 | `req-460245cc876df49a` | D3 | `chk-b4415af56c34b54b` | 3 | “- [ ] Add CCSDS Deframers for TC and SpacePacket to Svc” | sim |
| REQ-012 | `req-460245cc876df49a` | D3 | `chk-78e7f2871b67a938` | 5 | “CCSDS are a set of robust and standardized protocols that we need to switch to; Community has been asking for a long time.” | sim |
| REQ-013 | `req-a5b5653c6158af34` | D3 | `chk-b4415af56c34b54b` | 3 | “Add framers on the GDS side, and allow for selection between F Prime protocol / CCSDS” | sim |
| REQ-014 | `req-4a378fdf9a95a0bf` | D4 | `chk-a2d670d4846d2aaf` | 3 | “- [ ] Add CCSDS Framers for TM and SpacePacket to Svc” | sim |
| REQ-015 | `req-db7239fef4629a54` | D4 | `chk-a2d670d4846d2aaf` | 3 | “Add deframers on the GDS side, and allow for selection between F Prime protocol / CCSDS” | sim |
| REQ-016 | `req-0c7e31ff42ede510` | D6 | `chk-54078ace60c30afc` | 3 | “Have the TM framer completely fill TM frames with space packets, even if packets have to be multiplexed.” | sim |
| REQ-016 | `req-0c7e31ff42ede510` | D6 | `chk-30c6a6260df9b4f9` | 5 | “Internal JPL projects assert that not completely filling TMs is a non-starter given link budgets.” | sim |
| REQ-017 | `req-2f554f60e3191e85` | D6 | `chk-54078ace60c30afc` | 3 | “Pre-pend each space packet with a standard CCSDS sync marker 0xEB90.” | sim |
