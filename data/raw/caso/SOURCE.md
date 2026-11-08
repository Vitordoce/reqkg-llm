# Origem e Preparo do Corpus do Estudo de Caso: F´ (`Svc/Ccsds`)

Este diretório guarda o corpus preparado e congelado do estudo de caso do TG: o subsistema de comunicação espacial CCSDS (`Svc/Ccsds`) do framework de software de voo **F´ (F Prime)** da NASA/JPL.

## Identificação da Fonte

| Campo | Valor |
| --- | --- |
| Projeto | F´ (F Prime Flight Software Framework) — NASA/JPL |
| Repositório | <https://github.com/nasa/fprime> |
| Documentação pública | <https://fprime.jpl.nasa.gov> |
| Commit congelado | `fd0ef09c177dc4fd8070d2c3576da1a4a426873a` (branch `devel`, 8 out. 2026) |
| Licença do repositório | Apache License 2.0 (`Apache-2.0`) |
| Data de escolha | 21 de outubro de 2026 (autor com o orientador) |

## Estrutura do Diretório

- `caso.toml`: arquivo de conjunto de ingestão (`34` documentos: `16` SDDs + `14` *issues* + `4` discussões).
- `sdd/*.md`: os `16` *Software Design Documents* (`docs/sdd.md`) dos componentes de `Svc/Ccsds`, **com a seção `## Requirements` removida** antes da ingestão para evitar vazamento do gabarito na entrada do pipeline (`kind = "existing_system_description"`).
- `issues/issue_*.md`: `14` *issues* técnicas do repositório `nasa/fprime` sobre elicitação, requisitos, protocolos CCSDS (TC, TM, AOS, Space Packet, SDLS/AES-GCM) e CFDP (`kind = "meeting_record"`, decisão R10).
- `discussions/discussion_*.md`: `4` discussões arquiteturais da comunidade e equipe de engenharia do F´ sobre conformidade CCSDS, empacotamento, APID e validação de arquivos (`kind = "meeting_record"`, decisão R10).
- `referencia/requisitos_oficiais_fprime_ccsds.csv` e `.md`: os **126 requisitos oficiais** extraídos das tabelas `## Requirements` dos 14 componentes que as possuem (incluindo identificador, descrição, *rationale* quando presente e método de verificação). Esta pasta **não entra em `caso.toml`** e serve exclusivamente para comparação a posteriori com a SRS gerada pelo ReqKG-LLM.

## Tratamento Aplicado no Preparo

1. **Remoção do gabarito da entrada**: Em cada `Svc/Ccsds/<Componente>/docs/sdd.md`, a seção `## Requirements` (e sua tabela de requisitos) foi extraída para `referencia/requisitos_oficiais_fprime_ccsds.csv` e removida do `.md` salvo em `sdd/`. Os componentes `AosDeframer` e `AosFramer` não possuem seção `## Requirements` no commit congelado e foram mantidos na íntegra.
2. **Pseudonimização de dados pessoais (LGPD / ética em pesquisa)**: Todos os nomes de usuário do GitHub (`login` de autores de *issues*, discussões, comentários, respostas e menções `@usuario` no corpo do texto) foram substituídos deterministicamente por identificadores neutros `stakeholder-01` a `stakeholder-18`. Anotações de código/Doxygen (como `@param`, `@return`, `@brief`) foram preservadas.
3. **Mapeamento de tipo de fonte (Decisão R10)**: Para preservar o contrato congelado em `code/domain/enums.py` (`SourceKind`), os SDDs são ingeridos como `existing_system_description` e as *issues* e discussões técnicas como `meeting_record`.

## Componentes `Svc/Ccsds` Incluídos (16 SDDs)

| Componente | Caminho original no repositório | Requisitos oficiais na tabela `## Requirements` |
| --- | --- | ---: |
| `AesGcmDecryptor` | `Svc/Ccsds/AesGcmDecryptor/docs/sdd.md` | 7 |
| `AesGcmEncryptor` | `Svc/Ccsds/AesGcmEncryptor/docs/sdd.md` | 11 |
| `AosDeframer` | `Svc/Ccsds/AosDeframer/docs/sdd.md` | 0 |
| `AosFramer` | `Svc/Ccsds/AosFramer/docs/sdd.md` | 0 |
| `ApidManager` | `Svc/Ccsds/ApidManager/docs/sdd.md` | 6 |
| `CcsdsSdlsDeframer` | `Svc/Ccsds/CcsdsSdlsDeframer/docs/sdd.md` | 8 |
| `CcsdsSdlsFramer` | `Svc/Ccsds/CcsdsSdlsFramer/docs/sdd.md` | 9 |
| `CfdpManager` | `Svc/Ccsds/CfdpManager/docs/sdd.md` | 13 |
| `ClearTextDecryptor` | `Svc/Ccsds/ClearTextDecryptor/docs/sdd.md` | 5 |
| `ClearTextEncryptor` | `Svc/Ccsds/ClearTextEncryptor/docs/sdd.md` | 5 |
| `SdlsFileKeyManager` | `Svc/Ccsds/SdlsFileKeyManager/docs/sdd.md` | 4 |
| `SdlsSaRouter` | `Svc/Ccsds/SdlsSaRouter/docs/sdd.md` | 9 |
| `SpacePacketDeframer` | `Svc/Ccsds/SpacePacketDeframer/docs/sdd.md` | 11 |
| `SpacePacketFramer` | `Svc/Ccsds/SpacePacketFramer/docs/sdd.md` | 11 |
| `TcDeframer` | `Svc/Ccsds/TcDeframer/docs/sdd.md` | 11 |
| `TmFramer` | `Svc/Ccsds/TmFramer/docs/sdd.md` | 16 |
| **Total** | **16 componentes** | **126** |
