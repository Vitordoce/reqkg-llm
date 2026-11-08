# Ingestão sem modelo

Passo 3 de `PLAN.md`. Lê um conjunto de documentos, normaliza o texto, calcula hashes e corta em chunks com identificadores estáveis. Não chama LLM. A saída é a entrada comum das duas condições do experimento.

## Uso

A partir da raiz do repositório:

```sh
PYTHONPATH=code .venv/bin/python -m ingestion code/ingestion/fixtures/fixture.toml
PYTHONPATH=code .venv/bin/python -m ingestion code/ingestion/fixtures/fixture.toml --check
```

A primeira grava `data/processed/ingestion/fixture.json` e, se o arquivo já existia, mostra por documento quantos chunks entraram, saíram e ficaram. Bytes iguais não são regravados. `--check` não grava e sai com 1 se a saída estiver desatualizada. `--config` aponta para o TOML com a tabela `[chunking]`. O padrão é `code/experiments/config/experiment.toml`. `--output` troca o destino.

A saída padrão leva o nome do arquivo de conjunto, então `data/raw/amostra/conjunto.toml` e `outro/conjunto.toml` iriam para o mesmo `conjunto.json`. Se a saída existente veio de outro arquivo de conjunto (campo `set_path`), a ingestão sai com 1 sem gravar, com ou sem `--check`, e diz o que fazer: `--output data/processed/ingestion/<nome>.json`, renomear o conjunto, ou, se o conjunto mudou de lugar de propósito, apagar a saída antiga e rodar de novo.

## Arquivo de conjunto

```toml
[[document]]
path = "code/ingestion/fixtures/ata_sintetica.md"   # relativo à raiz do repositório
kind = "meeting_record"                              # um valor de domain.enums.SourceKind
title = "Ata sintética"                              # opcional
```

Aceita `.txt` e `.md` em UTF-8. O arquivo de conjunto fica dentro do repositório. O mesmo arquivo listado duas vezes, mesmo com grafias diferentes, é recusado. Todo erro nomeia o arquivo de conjunto e o campo, por exemplo `fontes.toml: document.1.path: arquivo 'docs/x.txt' não existe`.

## Saída

`IngestedSet`, em `corpus.py`, gravado com `domain.serialization.canonical_json`:

| Campo | Conteúdo |
| --- | --- |
| `ingestion_version` | Versão do algoritmo de ingestão. Muda se o corte mudar com a mesma configuração. |
| `set_path`, `set_sha256` | Caminho do arquivo de conjunto e SHA-256 dos bytes dele. |
| `chunking` | O `ChunkingConfig` usado. |
| `documents` | `SourceDocument`, em ordem de caminho. |
| `chunks` | `SourceChunk`, agrupados por documento, em ordem de índice. |

Não há data nem caminho absoluto na saída. A mesma entrada gera os mesmos bytes em qualquer processo, com qualquer `PYTHONHASHSEED`.

## Normalização

1. Decodifica UTF-8 estrito e remove o BOM.
2. Converte CRLF e CR em LF.
3. Normaliza para NFC.

O `sha256` do documento e as posições `char_start` e `char_end` se referem ao texto normalizado. Trocar só o fim de linha não muda o documento. O caminho passa por `ids.canonical_path`. Se o arquivo não for achado com o nome em NFC, a ingestão tenta o nome em NFD, porque alguns sistemas de arquivos gravam assim.

## Fronteiras da estratégia paragraph

Cada parágrafo é um chunk. Parágrafo é uma sequência de linhas não brancas. Linha só com espaços conta como branca. O texto do chunk vai do início da primeira linha ao fim da última, sem o LF final.

Por que o invariante vale: a fronteira de um chunk depende só do próprio parágrafo, e `ids.chunk_id` depende só da fonte, do texto e da ocorrência, nunca da posição. Editar, inserir ou apagar um parágrafo muda apenas os chunks desse parágrafo. Os outros mantêm o `chunk_id`, mesmo quando `index` e `char_start` mudam. O teste `test_editing_one_paragraph_keeps_every_other_chunk_id` confere isso em cerca de 1150 edições sobre documentos gerados, com semente fixa e `size_chars` de 60, 200 e 1500.

Agrupar parágrafos em sequência até `size_chars` quebra o invariante. Uma edição que muda o tamanho de um parágrafo desloca todas as fronteiras seguintes, até o fim do documento ou até a próxima fronteira forçada. Fechar o grupo depois de um parágrafo cujo hash satisfaz uma condição não resolve sozinho, porque o teto de tamanho obriga a contar caracteres desde o início do grupo, e essa contagem volta a deslocar as fronteiras seguintes.

Exceção, que vem do contrato: textos repetidos no mesmo documento são numerados pela `ocorrência`, em ordem. Uma edição que cria ou desfaz uma repetição renumera as cópias seguintes daquele mesmo texto. No máximo um identificador some ou aparece, e os restantes passam a apontar para cópias de texto idêntico. A citação continua batendo com o chunk. A posição muda. O teste de propriedade aceita essa exceção só para chunks posteriores ao parágrafo editado e com o mesmo texto de um pedaço dele.

Parágrafo maior que `size_chars` vira vários chunks de até `size_chars`, cortados da esquerda para a direita. O corte prefere a última quebra de linha, depois o último fim de frase (`.`, `!`, `?`, `;`, `…` seguido de espaço), depois o último espaço. Sem nenhum deles, corta seco sem separar letra de acento combinante. Espaços na emenda ficam fora dos dois pedaços. Os pedaços pertencem ao parágrafo, então o invariante continua valendo. Um pedaço só depende do texto entre o próprio início e `size_chars` caracteres adiante, então uma edição mais à frente no parágrafo não o altera.

## Estratégia window

Janelas de `size_chars` com sobreposição de `overlap_chars`, sem olhar parágrafo. Uma inserção no início troca todos os chunks. Serve só para comparação. Janela só de espaço em branco é descartada.

## Atualização incremental

`ingestion.diff.diff(anterior, novo) -> IngestionDiff` é pura. Para cada documento, em ordem de caminho, traz `status` (`added`, `removed`, `modified` ou `unchanged`, pelo SHA-256 do texto normalizado), os dois hashes, `metadata_changed` (tipo ou título) e as listas `added`, `removed` e `kept` de `chunk_id`. `IngestionDiff.removed_chunks` é o que o grafo invalida. `chunking_changed` avisa que a configuração mudou e que os chunks foram recalculados. Um chunk mantido pode ter mudado de posição. A posição nova vem da ingestão nova.

## Fixtures

`fixtures/` tem só texto sintético de desenvolvimento, marcado na primeira linha. `fixture.toml` também lê `code/domain/fixtures/corpus/entrevista_sintetica.txt`, e o teste confere que a ingestão gera para ela os mesmos `SourceDocument` e `SourceChunk` dos fixtures do contrato. PROMISE, amostra anotada e corpus do estudo de caso não entram aqui.
