# Artefatos do estudo de caso

Passo 10 de `PLAN.md`, item 2. Lê os registros de uma corrida (`code/experiments/records.py`), a configuração e o conjunto de ingestão, e gera os quatro artefatos que a proposta exige para o estudo de caso. Não chama modelo, não lê o Neo4j e não altera nenhum outro pacote.

O estudo de caso ainda não foi escolhido. Até lá, este pacote só roda sobre a corrida sintética de `fixtures/`, que não é estudo de caso.

## Uso

A partir da raiz do repositório:

```sh
PYTHONPATH=code .venv/bin/python -m deliverables <run_id> --condition REQKG-grounded --run-index 0 --name <nome>
PYTHONPATH=code .venv/bin/python -m deliverables <run_id> --condition REQKG-grounded --run-index 0 --name <nome> --check
# com o arquivo de conjunto da corrida, sem depender de data/processed/ingestion/
PYTHONPATH=code .venv/bin/python -m deliverables <run_id> --run-index 0 --name <nome> --ingestion data/raw/caso/caso.toml
```

Grava em `outputs/caso/<nome>/`. Bytes iguais não são regravados. `--check` não grava e sai com 1 se algum artefato estiver desatualizado. Erro de entrada sai com 2 e uma mensagem que nomeia o arquivo.

| Opção | Padrão | Uso |
| --- | --- | --- |
| `--condition` | `REQKG-grounded` | Condição cuja saída final vira artefato. |
| `--run-index` | obrigatório | Repetição da corrida, a partir de 0. |
| `--case` | todos | Restringe aos casos dados. Repetível. |
| `--runs-dir` | `outputs/runs` | Onde fica `<run_id>/`. |
| `--config` | `code/experiments/config/experiment.toml` | O SHA-256 dos bytes tem de ser o `config_sha256` da corrida. |
| `--ingestion` | os arquivos de `data/processed/ingestion/` cujo SHA-256 está em `ingestion_sha256` | Repetível. Aceita o arquivo de conjunto (`.toml`, o mesmo passado ao executor), ingerido em memória com o `[chunking]` da configuração e sem gravar em `data/processed/`, ou a saída da ingestão (`.json`). O SHA-256 dos bytes canônicos do conjunto ingerido, ou do `.json`, tem de estar no manifesto, como nas métricas. |

Entradas fora do repositório são recusadas, para que nenhum artefato guarde caminho absoluto.

## Artefatos

| Arquivo | Conteúdo |
| --- | --- |
| `srs.md` | Esboço de SRS na estrutura da ISO/IEC/IEEE 29148:2018. Introdução com propósito, escopo e visão geral a preencher pelo autor. Documentos-fonte. Stakeholders e atores com fonte e citação, e os atores recusados. Requisitos por tipo: funcionais, não funcionais por atributo da ISO/IEC 25010, restrições e tipo pendente. Cada requisito com `REQ-NNN`, `requirement_id`, declaração, declaração anterior (revisão 1), prioridade, método de verificação, status, marcas, origem, refinamento, fonte e citação. Requisito em revisão humana vem destacado. Verificação por método. |
| `instancia_reqkg.json` | Nós e arestas da instância, com as propriedades que o grafo grava (`graph.properties.node_props` e `relation_props`), ordenados por rótulo e identificador. Traz a origem (corrida, condição, entradas com SHA-256) e o estado lógico (contagens e SHA-256). |
| `instancia_resumo.md` | Contagem por classe e por relação, inclusive as zeradas, origem dos registros (fato extraído, inferência, decisão do pesquisador), requisitos por status e número de recusas W. |
| `matriz_proveniencia.csv` e `.md` | Uma linha por evidência: requisito, documento, chunk, índice, citação e se a citação aparece no chunk (`sim`, `não`, `sem citação`, `chunk fora do corpus`, `sem evidência`). O Markdown traz também a matriz requisito por documento. |
| `relatorio_lacunas.md` | Violações C, P e K com a explicação de cada regra, recusas W da instância e as do executor, refinamentos recusados com a regra G, chamadas de refinamento que falharam, requisitos em revisão humana, atributos sem valor quantitativo, casos sem saída e a seção "Limitações observadas", vazia para o autor. |
| `origem.json` | Comando de reprodução, entradas com SHA-256 e SHA-256 de cada artefato. |

Nenhum artefato tem data. A mesma entrada gera os mesmos bytes com qualquer `PYTHONHASHSEED`. O gerador não preenche campo: o que falta aparece como "pendente".

## Decisões

1. Cada caso é um documento, com `case_id` igual ao `source_id`, como no executor (`code/experiments/runner/README.md`). A evidência de um requisito é conferida só contra o documento do caso, o único que o modelo viu: regras, `to_records`, ordem de leitura e matriz usam esse corpus. Um chunk de outro documento do conjunto conta como P2 e aparece como "chunk fora do corpus do caso". Caso cujo `case_id` não é `source_id` de nenhum documento da ingestão é recusado.
2. A instância sai de `domain.persist.to_records` sobre a saída final de cada caso, não da leitura do Neo4j. O grafo da corrida guarda a extração compartilhada antes do refinamento e acumula casos, corridas e as duas condições. A saída final de uma condição nunca é gravada lá. Ler o grafo daria um artefato que não bate com o SRS nem com as métricas, que leem a saída final (`DATA_SPLIT.md`). Os casos são unidos em ordem de `case_id` pela regra de `graph.writer.write_batch` (`merge_provenance`). O teste de integração grava os mesmos lotes num Neo4j vazio e confere que `graph.state.logical_state` dá o mesmo SHA-256 do artefato.
3. `REQ-NNN` segue a ordem de leitura da primeira evidência que resolve no corpus, na extração compartilhada: documento por caminho, índice do chunk, caso e chave. O mesmo candidato tem o mesmo número nas duas condições, e o refinamento não renumera.
4. Requisito com refinamento aceito entra na instância como revisão 1, com `previous_statement` da extração compartilhada e o identificador calculado da evidência primária revisada e da declaração original. A regra é a de `domain.persist.to_records`, que recebe em `revisions` a declaração original de cada chave de `FinalRecord.accepted`. Um candidato recusado com W1 na extração compartilhada pode ganhar evidência no refinamento e entrar só na revisão 1. O identificador então depende do chunk que cada condição citou e pode diferir entre as condições.
5. As violações C, P e K são recalculadas por `rules.check_all` sobre a saída final. `FinalRecord.violations` não é lido. As violações G vêm do `CaseResult` de refinamento da condição.
6. "Em revisão humana" é o candidato com `low_confidence` (inclusive pelo limiar da configuração) ou `ambiguous_type`, as marcas que põem o requisito em `needs_review` em `to_records`.
7. "Atributo sem valor quantitativo" é o requisito com atributo de qualidade e sem `quantitative_value`.

## Lacunas de contrato

1. `RunManifest` guarda `config_sha256` e `ingestion_sha256`, mas não a configuração nem o caminho da ingestão. `records.py` não diz sobre o que o hash é calculado. O executor (`experiments/runner/rundir.py`) usa o SHA-256 dos bytes do arquivo, e este pacote confere do mesmo jeito. O operador tem de apontar a configuração usada com `--config`. Seria mais simples o executor copiar a configuração para o diretório da corrida. Numa corrida com PROMISE, `ingestion_sha256` traz também o hash da entrada do PROMISE, que não fica em `data/processed/ingestion/`. O cabeçalho dos artefatos lista esse hash como entrada sem arquivo lido.
2. `FinalRecord.violations` não tem semântica escrita em `records.py`.
3. A citação que sustenta a prioridade não tem campo próprio (R50 em `PROGRESS.md`). O SRS mostra a prioridade sem apontar qual citação a sustenta.

## Fixture e testes

`fixtures/build.py` escreve a corrida sintética `fixtures/runs/sintetico-entrevista/` (três casos, um por documento do conjunto, o da descrição inválido, nas duas condições) sobre `data/processed/ingestion/fixture.json`, com `fixtures/experiment.toml` como configuração, e grava em `fixtures/expected/` os artefatos esperados. A corrida tem requisito sem prioridade, citação que não aparece no chunk, citação de um chunk de outro documento, requisito sem evidência, requisitos em revisão humana, recusas W1 a W4, ciclo K3, relação sem evidência, refinamento aceito, recusado (G3, e G2 na outra condição) e chamadas que falharam.

```sh
.venv/bin/python code/deliverables/fixtures/build.py --check
.venv/bin/python -m pytest code/deliverables -q
```

Depois de mudar o gerador, a ingestão do fixture ou `records.py`, rode `build.py` sem `--check` e leia o diff de `fixtures/expected/`.

Em 10 de outubro, o gerador também leu uma corrida do executor real em modo sintético (`python -m experiments.runner <id> --synthetic --ingestion code/ingestion/fixtures/fixture.toml`), nas duas condições e nas repetições 0 e 2, e `--check` confirmou os mesmos bytes. Essa corrida não fica no repositório. `test_deliverables_graph.py` pula com motivo se o Neo4j não estiver no ar, e segura `exclusive_database` porque apaga o grafo.
