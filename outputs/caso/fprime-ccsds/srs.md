# Esboço de SRS: fprime-ccsds

> Gerado pelo ReqKG-LLM a partir dos registros da corrida, sem edição manual. Para regenerar: `PYTHONPATH=code .venv/bin/python -m deliverables pilot-caso-01 --condition REQKG-grounded --run-index 0 --name fprime-ccsds --ingestion data/raw/caso/caso_piloto.toml`.
>
> - Corrida: `pilot-caso-01`, condição `REQKG-grounded`, repetição 0 (a corrida tem 1).
> - Corrida piloto: sim. Não entra no relatório como resultado.
> - Modelo: `qwen3:14b`. Respostas gravadas (replay): não.
> - Comando da corrida: `PYTHONPATH=code .venv/bin/python -m experiments.runner pilot-caso-01 --real --pilot --runs 1 --ingestion data/raw/caso/caso_piloto.toml`.
> - Casos: `src-10c1106f4b63ce65` (`data/raw/caso/sdd/SpacePacketDeframer.md`), `src-19633f6a72a3da31` (`data/raw/caso/issues/issue_3492.md`), `src-3dd53f82b418508a` (`data/raw/caso/issues/issue_3491.md`), `src-70d9f10aa1b8a6c3` (`data/raw/caso/sdd/TcDeframer.md`), `src-7945671485477302` (`data/raw/caso/issues/issue_5485.md`), `src-974e951c733c8e7a` (`data/raw/caso/discussions/discussion_4030.md`), `src-9cfd29d516561c4e` (`data/raw/caso/issues/issue_5114.md`), `src-c9b8a83013558e6f` (`data/raw/caso/sdd/ApidManager.md`), `src-cf097721f7a993df` (`data/raw/caso/sdd/TmFramer.md`), `src-d1507de263dc69b8` (`data/raw/caso/sdd/SpacePacketFramer.md`), `src-e4ac13f99401393a` (`data/raw/caso/discussions/discussion_5027.md`), `src-e8a2e7c2f903f103` (`data/raw/caso/sdd/AesGcmDecryptor.md`).
> - Configuração: `code/experiments/config/experiment.toml` (SHA-256 `43a48015ae13d15e742d4c1fa56694dd0a89b507ee5d26fd477d5839e48d806c`).
> - Ingestão: `data/raw/caso/caso_piloto.toml` (SHA-256 `45ce02412f1aab1ad26541aa3094e3e36e78ce54d01ef6a328eb7247a13bb89d`).

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
| D1 | `data/raw/caso/discussions/discussion_4030.md` | `meeting_record` | F Prime Discussion #4030: Make APID use in CCSDS telemetry/DPs match up more closely with ground systems. | `cad916295971eb5f25febe3389f08dcba3134fa693d2b494bf5536cfa945ee59` | `src-974e951c733c8e7a` |
| D2 | `data/raw/caso/discussions/discussion_5027.md` | `meeting_record` | F Prime Discussion #5027: Improvemtents to CCSDS In F Prime | `d504471a0eb9b2f643d1538723d7963b73170b685f754ce5797c0b4b3e2e407d` | `src-e4ac13f99401393a` |
| D3 | `data/raw/caso/issues/issue_3491.md` | `meeting_record` | F Prime Issue #3491: Add CCSDS Uplink (TC-SpacePacket) protocols | `6f6dda9c1cac1ac07a782bbc49e7be4996e94cb96bf2bd492889e5404889c9c4` | `src-3dd53f82b418508a` |
| D4 | `data/raw/caso/issues/issue_3492.md` | `meeting_record` | F Prime Issue #3492: Add CCSDS Downlink (TM-SpacePacket) protocols | `7c0f4c24b2098693a7b89d4cc6b26894c83e8da67883cb41b772b86d538dbb57` | `src-19633f6a72a3da31` |
| D5 | `data/raw/caso/issues/issue_5114.md` | `meeting_record` | F Prime Issue #5114: Add support for CCSDS security protocol (encryption/authentication) | `0619cbd2e35298523b7cdd8dcedad70e21b7d5b7b96983f9362879c399467636` | `src-9cfd29d516561c4e` |
| D6 | `data/raw/caso/issues/issue_5485.md` | `meeting_record` | F Prime Issue #5485: Multiplex Space Packets across TM/AOS for downlink efficiency | `5197559a7da12c8b4e16c5f93551349ed155b07c50a5846aae4f84aaf5db7428` | `src-7945671485477302` |
| D7 | `data/raw/caso/sdd/AesGcmDecryptor.md` | `existing_system_description` | F Prime Svc::Ccsds::AesGcmDecryptor SDD | `14a5f3ae50314764eb82a65f214381c4a7fb8eef3364d2bf665b8d59c3f65d2e` | `src-e8a2e7c2f903f103` |
| D8 | `data/raw/caso/sdd/ApidManager.md` | `existing_system_description` | F Prime Svc::Ccsds::ApidManager SDD | `c10498f9a645b95de3bae1d21d4840ec327e4d01ed5157d3513f88cd9f5349e3` | `src-c9b8a83013558e6f` |
| D9 | `data/raw/caso/sdd/SpacePacketDeframer.md` | `existing_system_description` | F Prime Svc::Ccsds::SpacePacketDeframer SDD | `32a6a76480eb35f773f8081754f11f337d949fce053ae69821f2871ddce3e32d` | `src-10c1106f4b63ce65` |
| D10 | `data/raw/caso/sdd/SpacePacketFramer.md` | `existing_system_description` | F Prime Svc::Ccsds::SpacePacketFramer SDD | `918c48437e90486ef1e559f32b517e19f26048c7233cbcf8d62f331ea47e14e5` | `src-d1507de263dc69b8` |
| D11 | `data/raw/caso/sdd/TcDeframer.md` | `existing_system_description` | F Prime Svc::Ccsds::TcDeframer SDD | `9557ee00d33e76094dcb01eb3a59a3d587a8e280ac17379cff0d9e0271d0b621` | `src-70d9f10aa1b8a6c3` |
| D12 | `data/raw/caso/sdd/TmFramer.md` | `existing_system_description` | F Prime Svc::Ccsds::TmFramer SDD | `6ad2f00437422bc878b25a8849152c3fb427d1dc4a6a9b355a870b6d346a9935` | `src-cf097721f7a993df` |

## 3. Stakeholders e atores

| Ator | Tipo | actor_id | Fonte | Citação | Requisitos ligados |
| --- | --- | --- | --- | --- | --- |
| ground software | papel de usuário | `act-0450fc644daecc16` | D2 `data/raw/caso/discussions/discussion_5027.md`, chunk `chk-ce17ae8cbb5eeb73` (índice 18) | “ground software can identify meaningful information about the packet by only parsing the CCSDS headers” (aparece no chunk) | REQ-011 |
| stakeholder-02 | stakeholder | `act-b1dec0745389d3ba` | D4 `data/raw/caso/issues/issue_3492.md`, chunk `chk-23506d61a70c4242` (índice 1); D2 `data/raw/caso/discussions/discussion_5027.md`, chunk `chk-314cbbe1f779c08e` (índice 8); D3 `data/raw/caso/issues/issue_3491.md`, chunk `chk-f4de815c733f8d00` (índice 1) | “Autor (pseudonimizado): stakeholder-02” (aparece no chunk); “stakeholder-02” (aparece no chunk); “Autor (pseudonimizado): stakeholder-02” (aparece no chunk) | REQ-012, REQ-013, REQ-014, REQ-015 |
| stakeholder-05 | stakeholder | `act-0001eb1211f82e3d` | D2 `data/raw/caso/discussions/discussion_5027.md`, chunk `chk-6d40b0efd6f58ddb` (índice 1) | “Autor (pseudonimizado): stakeholder-05” (aparece no chunk) | REQ-001, REQ-002, REQ-003 |
| stakeholder-08 | stakeholder | `act-59ff287a86f562ff` | D1 `data/raw/caso/discussions/discussion_4030.md`, chunk `chk-8c27925676e0d3dd` (índice 1); D6 `data/raw/caso/issues/issue_5485.md`, chunk `chk-98ca142c9b50795e` (índice 1) | “Autor (pseudonimizado): stakeholder-08” (aparece no chunk); “Autor (pseudonimizado): stakeholder-08” (aparece no chunk) | REQ-016, REQ-017 |
| stakeholder-17 | stakeholder | `act-104481a57ea2d76e` | D2 `data/raw/caso/discussions/discussion_5027.md`, chunk `chk-e4a96b87749b4543` (índice 12) | “stakeholder-17” (aparece no chunk) | nenhum |
| stakeholder-18 | stakeholder | `act-90c4fc8985d010a3` | D2 `data/raw/caso/discussions/discussion_5027.md`, chunk `chk-daae040143ecabd2` (índice 16) | “stakeholder-18” (aparece no chunk) | nenhum |

## 4. Requisitos específicos

| Grupo | Requisitos | Em revisão humana |
| --- | --- | --- |
| Funcionais | 16 | 0 |
| Não funcionais | 0 | 0 |
| Restrições | 1 | 0 |
| Tipo pendente | 0 | 0 |
| Total | 17 | 0 |

### 4.1 Requisitos funcionais

#### REQ-001 · `req-41ddf541e3825dc8`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve melhorar a representação de dados em pacotes CCSDS para alinhar-se com padrões da indústria e atender melhor às necessidades dos usuários. |
| Tipo | funcional |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | 0.7 |
| Origem | fato extraído |
| Refinamento | recusado |
| Fonte | D2 `data/raw/caso/discussions/discussion_5027.md`, chunk `chk-5771881ddc30d122` (índice 2) |
| Citação | “we would like to do better in how we represent data in CCSDS packets to fall in-line with more industry standards and better meet user needs” (aparece no chunk) |
| Registro | caso `src-e4ac13f99401393a`, chave `c0-R1` |

#### REQ-002 · `req-aa8af9b746c7c40c`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve permitir a representação de tempo em um cabeçalho secundário, possivelmente com formato U16/U32. |
| Declaração antes do refinamento | O sistema deve permitir a representação de tempo em um cabeçalho secundário, possivelmente com formato U16/U32. |
| Tipo | funcional |
| Prioridade | Should |
| Método de verificação | análise |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | não informada |
| Origem | fato extraído |
| Refinamento | aceito, revisão 1 |
| Fonte | D2 `data/raw/caso/discussions/discussion_5027.md`, chunk `chk-fae01834d331e52c` (índice 4) |
| Citação | “CCSDS recommends representing time in a secondary header. Possibly with a U16/U32 format. We suggest making this configurable so that project that do not need the full Fw.Time representation don't have to use this.” (aparece no chunk) |
| Registro | caso `src-e4ac13f99401393a`, chave `c0-R2` |

#### REQ-003 · `req-9f32ba94621e8bb2`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve permitir que projetos configurem a representação de tempo para não exigir a representação completa de Fw.Time quando não for necessária. |
| Tipo | funcional |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | 0.7 |
| Origem | fato extraído |
| Refinamento | recusado |
| Fonte | D2 `data/raw/caso/discussions/discussion_5027.md`, chunk `chk-fae01834d331e52c` (índice 4) |
| Citação | “We suggest making this configurable so that project that do not need the full Fw.Time representation don't have to use this.” (aparece no chunk) |
| Registro | caso `src-e4ac13f99401393a`, chave `c0-R3` |

#### REQ-004 · `req-b1da379cea72d155`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve permitir que o Packet ID do tlm packetizer seja mapeado para o APID. |
| Declaração antes do refinamento | O sistema deve permitir que o Packet ID do tlm packetizer seja mapeado para o APID. |
| Tipo | funcional |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | não informada |
| Origem | fato extraído |
| Refinamento | aceito, revisão 1 |
| Fonte | D2 `data/raw/caso/discussions/discussion_5027.md`, chunk `chk-365391d5cd373236` (índice 6) |
| Citação | “We propose having a configuration where the packet ID of the tlm packetizer maps to the APID.” (aparece no chunk) |
| Registro | caso `src-e4ac13f99401393a`, chave `c1-R1` |

#### REQ-005 · `req-aa07a72c8e17ab21`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve otimizar o uso do APID para reduzir a sobrecarga de enviar um Packet ID redundante. |
| Tipo | funcional |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | 0.7 |
| Origem | fato extraído |
| Refinamento | recusado |
| Fonte | D2 `data/raw/caso/discussions/discussion_5027.md`, chunk `chk-365391d5cd373236` (índice 6) |
| Citação | “This would save overhead on sending a redundant packet ID when the APID 11bits are under-utilized.” (aparece no chunk) |
| Registro | caso `src-e4ac13f99401393a`, chave `c1-R2` |

#### REQ-006 · `req-85f9ccb427ee5ad9`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve expandir o suporte aos diversos padrões CCSDS. |
| Declaração antes do refinamento | O sistema deve expandir o suporte aos diversos padrões CCSDS. |
| Tipo | funcional |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | 0.7 |
| Origem | fato extraído |
| Refinamento | aceito, revisão 1 |
| Fonte | D2 `data/raw/caso/discussions/discussion_5027.md`, chunk `chk-02673deeacf3aad1` (índice 9) |
| Citação | “I am highly in favor expanding our support of the various CCSDS standards!” (aparece no chunk) |
| Registro | caso `src-e4ac13f99401393a`, chave `c1-R3` |

#### REQ-007 · `req-9ce686f22719cd5c`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve incluir um carimbo de data/hora no cabeçalho secundário do pacote espacial. |
| Declaração antes do refinamento | O sistema deve incluir um carimbo de data/hora no cabeçalho secundário do pacote espacial. |
| Tipo | funcional |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | 0.7 |
| Origem | fato extraído |
| Refinamento | aceito, revisão 1 |
| Fonte | D2 `data/raw/caso/discussions/discussion_5027.md`, chunk `chk-eb8869963bdf1acd` (índice 10) |
| Citação | “For the timestamp in the secondary header of Space Packet, big upvote from me.” (aparece no chunk) |
| Registro | caso `src-e4ac13f99401393a`, chave `c1-R4` |

#### REQ-009 · `req-9e7154aa58441efb`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve permitir que APID seja atribuído a aplicações específicas, como transferência de arquivos, housekeeping e instrumentos/subsistemas. |
| Declaração antes do refinamento | O sistema deve permitir que APID seja atribuído a aplicações específicas, como transferência de arquivos, housekeeping e instrumentos/subsistemas. |
| Tipo | funcional |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | não informada |
| Origem | fato extraído |
| Refinamento | aceito, revisão 1 |
| Fonte | D2 `data/raw/caso/discussions/discussion_5027.md`, chunk `chk-e449e51c02cec32d` (índice 15) |
| Citação | “Anyway, my general preference is to consider APID's to represent *Applications*. That means I want things like file transfer to have an APID, general housekeeping to have an APID, a specific instrument or subsystem to be allocated its own APID.” (aparece no chunk) |
| Registro | caso `src-e4ac13f99401393a`, chave `c2-R1` |

#### REQ-010 · `req-ecebc47befd7a848`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve permitir que projetos incluam tempo no cabeçalho secundário com comprimento e formato configuráveis. |
| Declaração antes do refinamento | O sistema deve permitir que projetos incluam tempo no cabeçalho secundário com comprimento e formato configuráveis. |
| Tipo | funcional |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | não informada |
| Origem | fato extraído |
| Refinamento | aceito, revisão 1 |
| Fonte | D2 `data/raw/caso/discussions/discussion_5027.md`, chunk `chk-ccc54904009238f4` (índice 17) |
| Citação | “adding the time in a secondary header with a deployment configurable length/format” (aparece no chunk) |
| Registro | caso `src-e4ac13f99401393a`, chave `c2-R3` |

#### REQ-011 · `req-37def9fa32862d5f`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve permitir que o APID identifique a aplicação (fonte) e a criticidade dos dados. |
| Declaração antes do refinamento | O sistema deve permitir que o APID identifique a aplicação (fonte) e a criticidade dos dados. |
| Tipo | funcional |
| Prioridade | Must |
| Método de verificação | inspeção |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | não informada |
| Origem | fato extraído |
| Refinamento | aceito, revisão 1 |
| Fonte 1 | D2 `data/raw/caso/discussions/discussion_5027.md`, chunk `chk-ce17ae8cbb5eeb73` (índice 18) |
| Citação 1 | “considering an APID to identify application (source) + data criticality” (aparece no chunk) |
| Fonte 2 | D2 `data/raw/caso/discussions/discussion_5027.md`, chunk `chk-ce17ae8cbb5eeb73` (índice 18) |
| Citação 2 | “so that ground software can identify meaningful information about the packet by only parsing the CCSDS headers” (aparece no chunk) |
| Registro | caso `src-e4ac13f99401393a`, chave `c3-R1` |

#### REQ-012 · `req-460245cc876df49a`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve adicionar CCSDS Deframers para TC e SpacePacket ao Svc. |
| Declaração antes do refinamento | O sistema deve adicionar CCSDS Deframers para TC e SpacePacket ao Svc. |
| Tipo | funcional |
| Prioridade | Must |
| Método de verificação | inspeção |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | não informada |
| Origem | fato extraído |
| Refinamento | aceito, revisão 1 |
| Fonte 1 | D3 `data/raw/caso/issues/issue_3491.md`, chunk `chk-b4415af56c34b54b` (índice 3) |
| Citação 1 | “- [ ] Add CCSDS Deframers for TC and SpacePacket to Svc” (aparece no chunk) |
| Fonte 2 | D3 `data/raw/caso/issues/issue_3491.md`, chunk `chk-78e7f2871b67a938` (índice 5) |
| Citação 2 | “CCSDS are a set of robust and standardized protocols that we need to switch to; Community has been asking for a long time.” (aparece no chunk) |
| Registro | caso `src-3dd53f82b418508a`, chave `c0-R1` |

#### REQ-013 · `req-a5b5653c6158af34`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve adicionar framers no lado do GDS e permitir a seleção entre o protocolo F Prime e CCSDS. |
| Tipo | funcional |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | 0.7 |
| Origem | fato extraído |
| Refinamento | recusado |
| Fonte | D3 `data/raw/caso/issues/issue_3491.md`, chunk `chk-b4415af56c34b54b` (índice 3) |
| Citação | “Add framers on the GDS side, and allow for selection between F Prime protocol / CCSDS” (aparece no chunk) |
| Registro | caso `src-3dd53f82b418508a`, chave `c0-R2` |

#### REQ-014 · `req-4a378fdf9a95a0bf`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve adicionar CCSDS Framers para TM e SpacePacket ao Svc. |
| Declaração antes do refinamento | O sistema deve adicionar CCSDS Framers para TM e SpacePacket ao Svc. |
| Tipo | funcional |
| Prioridade | Could |
| Método de verificação | teste |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | não informada |
| Origem | fato extraído |
| Refinamento | aceito, revisão 1 |
| Fonte | D4 `data/raw/caso/issues/issue_3492.md`, chunk `chk-a2d670d4846d2aaf` (índice 3) |
| Citação | “- [ ] Add CCSDS Framers for TM and SpacePacket to Svc” (aparece no chunk) |
| Registro | caso `src-19633f6a72a3da31`, chave `c0-R1` |

#### REQ-015 · `req-db7239fef4629a54`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve adicionar deframers no lado do GDS e permitir a seleção entre o protocolo F Prime e CCSDS. |
| Tipo | funcional |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | 0.7 |
| Origem | fato extraído |
| Refinamento | recusado |
| Fonte | D4 `data/raw/caso/issues/issue_3492.md`, chunk `chk-a2d670d4846d2aaf` (índice 3) |
| Citação | “Add deframers on the GDS side, and allow for selection between F Prime protocol / CCSDS” (aparece no chunk) |
| Registro | caso `src-19633f6a72a3da31`, chave `c0-R2` |

#### REQ-016 · `req-0c7e31ff42ede510`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve preencher completamente os quadros TM com pacotes de espaço, mesmo que os pacotes precisem ser multiplexados. |
| Declaração antes do refinamento | O sistema deve preencher completamente os quadros TM com pacotes de espaço, mesmo que os pacotes precisem ser multiplexados. |
| Tipo | funcional |
| Prioridade | Should |
| Método de verificação | inspeção |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | não informada |
| Origem | fato extraído |
| Refinamento | aceito, revisão 1 |
| Fonte 1 | D6 `data/raw/caso/issues/issue_5485.md`, chunk `chk-54078ace60c30afc` (índice 3) |
| Citação 1 | “Have the TM framer completely fill TM frames with space packets, even if packets have to be multiplexed.” (aparece no chunk) |
| Fonte 2 | D6 `data/raw/caso/issues/issue_5485.md`, chunk `chk-30c6a6260df9b4f9` (índice 5) |
| Citação 2 | “Internal JPL projects assert that not completely filling TMs is a non-starter given link budgets.” (aparece no chunk) |
| Registro | caso `src-7945671485477302`, chave `c0-R1` |

#### REQ-017 · `req-2f554f60e3191e85`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve preencher cada pacote de espaço com um marcador de sincronização padrão CCSDS 0xEB90. |
| Tipo | funcional |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | 0.8 |
| Origem | fato extraído |
| Refinamento | recusado |
| Fonte | D6 `data/raw/caso/issues/issue_5485.md`, chunk `chk-54078ace60c30afc` (índice 3) |
| Citação | “Pre-pend each space packet with a standard CCSDS sync marker 0xEB90.” (aparece no chunk) |
| Registro | caso `src-7945671485477302`, chave `c0-R2` |

### 4.2 Requisitos não funcionais

Cada requisito aparece uma vez, no primeiro dos seus atributos na ordem abaixo. O campo Atributos de qualidade lista todos.

#### 4.2.1 Desempenho (`performance`)

Nenhum requisito.

#### 4.2.2 Segurança (`security`)

Nenhum requisito.

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

#### REQ-008 · `req-39be74680256dfc2`

| Campo | Valor |
| --- | --- |
| Declaração | O sistema deve evitar a atribuição forçada de APID ao TlmPacketizer Packet IDs. |
| Declaração antes do refinamento | O sistema deve evitar a atribuição forçada de APID ao TlmPacketizer Packet IDs. |
| Tipo | restrição |
| Prioridade | pendente |
| Método de verificação | pendente |
| Status | rascunho (`draft`) |
| Marcas de revisão | nenhuma |
| Confiança declarada | 0.7 |
| Origem | fato extraído |
| Refinamento | aceito, revisão 1 |
| Fonte | D2 `data/raw/caso/discussions/discussion_5027.md`, chunk `chk-39cab25d468e696c` (índice 13) |
| Citação | “APID should not be forcibly tied to the TlmPacketizer Packet IDs” (aparece no chunk) |
| Registro | caso `src-e4ac13f99401393a`, chave `c2-R2` |

### 4.4 Tipo pendente (C3)

Nenhum requisito.

## 5. Verificação

| Método de verificação | Requisitos |
| --- | --- |
| inspeção | 3 |
| análise | 1 |
| teste | 1 |
| pendente | 12 |

Plano de verificação: _A preencher pelo autor._

## Apêndice A. Rastreabilidade

A matriz de proveniência está em `matriz_proveniencia.md` e `matriz_proveniencia.csv`. As lacunas estão em `relatorio_lacunas.md`, e a instância do ReqKG em `instancia_reqkg.json`.
