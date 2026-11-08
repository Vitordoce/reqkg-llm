# Roteiro do dia da corrida

Sequência do piloto real até o pacote de entrega. Reescrito depois do segundo ensaio geral, de 11 de outubro de 2026, que rodou a sequência inteira sobre o código corrigido em 11 de outubro, só com dados sintéticos e o cliente sintético, sem chave e sem modelo. Cada passo traz o comando, o que conferir, o que fazer se falhar e o que registrar.

Marcas:

- **[ensaiado]**: o comando rodou no ensaio, com a saída descrita.
- **[sintético]**: rodou só com o cliente sintético ou com dados de fixture. Com o modelo real, o comportamento pode mudar.
- **[não ensaiado]**: só a recusa ou o dry-run rodaram. A primeira execução de verdade é a do dia.
- **[corrigido: E2-n]**: defeito achado no segundo ensaio e corrigido em 11 de outubro, depois do ensaio, com teste e sabotagem (tabela do fim). O passo descreve o comportamento novo, que ainda não rodou numa sequência completa.

Todos os comandos rodam na raiz do repositório, em zsh. O zsh não divide variável em palavras, então `M="python -m ..."; $M` falha. Defina uma vez no shell:

```sh
M() { PYTHONPATH=code .venv/bin/python -m experiments.metrics "$@"; }
R() { PYTHONPATH=code .venv/bin/python -m experiments.runner "$@"; }
```

## Pré-requisitos

Antes do dia:

1. Amostra escrita, anotada e revista pelo orientador, em `data/raw/amostra/`: `aNN.txt`, `referencia.toml` e `notas/`. Na raiz da pasta, só `TEMPLATE/` e `notas/` como subpastas. Qualquer outra pasta entra no congelamento e no pacote sem aviso.
2. Conjunto `data/raw/amostra/amostra.toml`, com um `[[document]]` por artefato (formato em `code/ingestion/README.md`). Os arquivos listados são os da própria pasta da amostra. As métricas ligam artefato e documento pelo nome do arquivo e recusam o par quando o SHA-256 do texto difere **[corrigido: E2-6]**.
3. Em `code/experiments/config/experiment.toml`, já preenchidos em 14 de outubro: `[model]` com `provider = "ollama"`, `model_id = "qwen3:14b"`, `model_digest` (o de `/api/tags`), `temperature = 0`, `seed` e `num_ctx = 16384`; `[evaluation]` com `bertscore_model = "FacebookAI/xlm-roberta-large"`, `bertscore_revision` (hash do commit no Hugging Face) e `bertscore_num_layers = 17`. O executor recusa o modo real, piloto inclusive, se faltar algum deles.
4. Nada a fazer antes do congelamento quanto à publicação: as corridas publicadas ficam em `PUBLICACAO.toml`, na raiz, fora do congelamento, e são escolhidas no passo 11, depois que as corridas existem **[corrigido: E2-4]**. Até lá, `runs = []` e `run_metrics = []`.
5. `make secret-scan` passando **[corrigido: E2-1]**. `make test` também roda a varredura sobre a lista real do pacote, então uma chave falsa nova num teste aparece já no passo 0. Uma exceção nova em `ALLOWED` mexe em `tools/` e precisa chegar antes do congelamento.
6. Linhas `data/raw/amostra/*` retiradas do `.cursorignore`, se tiverem entrado.
7. `make venv-metrics` rodado. O primeiro `compute` com BERTScore baixa o modelo (cerca de 4,5 GB) e precisa de rede; depois, o cache local basta.
8. Ollama no ar, com o modelo da configuração baixado e o mesmo digest. Não há chave de API.

   ```sh
   ollama serve &                        # ou abra o app do Ollama
   ollama pull qwen3:14b
   curl -s http://localhost:11434/api/tags | python3 -c "import json,sys; print([(m['name'], m['digest']) for m in json.load(sys.stdin)['models']])"
   ```

   O digest impresso tem de ser o `model.model_digest` da configuração; o executor confere e recusa com saída 1 se for outro, se o modelo faltar ou se o servidor não responder. O modelo ocupa 11 GB com `num_ctx = 16384`: feche outros modelos e aplicativos pesados. A máquina não pode dormir durante a corrida: rode o executor sob `caffeinate -dims`.
9. Neo4j no ar (`make neo4j-up` e `make neo4j-wait`) e nenhum outro processo usando o banco. O executor segura `code/graph/.neo4j-test.lock` a corrida inteira; um `pytest` que esperar mais de 120 s falha. Peça aos agentes que não rodem testes nem editem `code/` ou `tools/` do passo 5 ao fim do passo 10: qualquer edição derruba o `freeze-check`.
10. Estudo de caso escolhido com o orientador, com o corpus em `data/raw/caso/` e o conjunto `data/raw/caso/caso.toml`.
11. Tempo, não preço: o modelo local não custa nada por token, mas a corrida completa leva horas. O arquivo de calibração `outputs/calibracao/qwen3-14b.json` ainda não existe: ele sai do piloto completo do passo 3, com `python -m experiments.runner.calibrate`, e faz o dry-run imprimir o tempo estimado. Medição parcial de 14 de outubro, 25 chamadas: extração cerca de 68 s por chamada, refinamento 12 s (A) e 17 s (B), saída de 18 a 24 tokens por segundo. Antes de uma corrida longa, feche outros containers do Docker e aplicativos pesados: com 24 GB, a máquina ficou com 12% de memória livre. Reserve a máquina pelo tempo do passo 6 mais uma margem.

## Registro em `PROGRESS.md`

Crie uma seção `## Registro da corrida` logo depois de "Decisões registradas", com esta tabela, e preencha uma linha a cada passo marcado com **Registrar**:

```markdown
| Data e hora | Passo | Item | Valor |
| --- | --- | --- | --- |
```

Hashes que o protocolo exige: SHA-256 do manifesto de congelamento e `tree_sha256` (seção 11), e SHA-256 de cada planilha de pareamento travada, antes de abrir a chave (seção 9, item 5).

## Passo 0. Estado de partida [ensaiado]

```sh
make test
make secret-scan
ls data/raw/amostra data/processed/ingestion outputs/runs report/src outputs/pacote
```

Conferir: testes e varredura passam. `data/raw/amostra` só tem artefatos, `referencia.toml`, `amostra.toml`, `notas/` e `TEMPLATE/`. `data/processed/ingestion/` não tem `.json` de teste. `outputs/runs/` não tem `freeze-<hoje>.json`, nem pasta `.partial-*`, nem corrida com o `run_id` que você vai usar (`ls -a`). `report/src/` não tem `.tex` solto além de `tg2_continuacao.tex`.

Se falhar: não siga. Teste ou varredura vermelhos antes do congelamento são defeito a corrigir agora, porque depois do passo 5 o código não muda. Sobra de ensaio é apagada agora.

No ensaio: 83 testes em `tools/`, 396 em `code/` (1 pulado, a chamada real). `make secret-scan` falhou (E2-1). Depois das correções de 11 de outubro: 87 em `tools/`, 406 em `code/` (1 pulado), varredura sem achados em 285 arquivos.

## Passo 1. Validar a amostra [sintético]

```sh
PYTHONPATH=code .venv/bin/python -m experiments.annotation data/raw/amostra | tee outputs/runs/validacao-amostra.txt
```

Conferir: "Resultado: amostra válida, 0 erro(s)". Cada alerta tem justificativa (seção 10 do protocolo). Números de artefatos e requisitos batem com o planejamento.

Se falhar: corrija o arquivo apontado e rode de novo. Saída 2 é pasta errada.

No ensaio, 3 artefatos e 7 requisitos sintéticos passaram com 11 alertas de faixa, esperados.

## Passo 2. Teste de fumaça da chamada real [ensaiado em 14 de outubro]

```sh
REQKG_REAL_CALL=1 .venv/bin/python -m pytest code/extraction/test_extraction_real_call.py -s -rs
```

Só texto sintético, cerca de 2 a 3 minutos. Conferir: `3 passed`, não `skipped`. Os três testes conferem que a saída valida no schema com `think = false`, sem `message.thinking`; que `temperature` e `seed` foram enviadas em `options` e aceitas; que duas chamadas iguais com a configuração do experimento dão o mesmo texto; e que, com temperatura 1, a mesma semente repete o texto e outra semente o muda (R48).

Se falhar: `skipped` diz o que falta: `REQKG_REAL_CALL=1`, o servidor ("rode `ollama serve`"), o modelo ("rode `ollama pull`") ou o digest ("os pesos mudaram"). Falha na comparação de textos quer dizer que temperatura ou semente não estão sendo aplicadas: registre em R48 e decida com o orientador antes do piloto. `api_error` com "janela de contexto cheia" pede `num_ctx` maior.

Em 14 de outubro, com o Ollama 0.32.4: 3 passed. A classificação levou 634 tokens de entrada e 25 de saída; a extração da entrevista sintética, 2.889 de entrada e 2.409 de saída, em 113 s, com status `ok`.

**Registrar**: `model_id`, digest, versão do Ollama e resultado da fumaça.

## Passo 3. Piloto real barato [não ensaiado]

Exercita extração, refinamento, pareamento, BERTScore e o PROMISE, sobre o fixture de métricas (desenvolvimento, com referência). A amostra não passa pelo pipeline antes do congelamento.

Use o projeto 2 do PROMISE **[corrigido: E2-7]**. Com a semente da configuração, `--promise-projects 1 --promise-limit 5` sorteia 5 itens funcionais (o projeto 1 tem 20 de 28 F), e o piloto não exercita a tarefa de categoria. O projeto 2 sorteia LF, A, SC, F e SE. O README do executor traz o mesmo piloto, e um teste confere que os pilotos dos dois documentos sorteiam itens não funcionais.

```sh
R --dry-run --pilot --runs 1 --ingestion code/experiments/metrics/fixtures/conjunto.toml --promise --promise-projects 2 --promise-limit 5
R pilot-01 --real --pilot --runs 1 --ingestion code/experiments/metrics/fixtures/conjunto.toml --promise --promise-projects 2 --promise-limit 5
```

O dry-run do ensaio deu 42 chamadas, cerca de 110 mil tokens de entrada e no máximo 172 mil de saída.

Métricas do piloto, com o conjunto `.toml` e a referência do fixture:

```sh
I=(--ingestion code/experiments/metrics/fixtures/conjunto.toml --reference code/experiments/metrics/fixtures/amostra)
M pilot-01 sheet $I
# preencher outputs/runs/pilot-01/metrics/pairing/sheet_run0.toml
M pilot-01 lock --run-index 0 $I
M pilot-01 compute $I
```

Conferir:

- saída 0 e a lista de arquivos da corrida;
- `outputs/runs/pilot-01/manifest.json`: `pilot` verdadeiro, `replay` falso, o `model_id` escolhido;
- estado das chamadas: `python3 -c "import json,collections; print(collections.Counter(json.loads(l)['status'] for l in open('outputs/runs/pilot-01/calls.jsonl')))"`;
- `summary.md`: tokens reais contra o dry-run (razão real/estimado, para o passo 6) e BERTScore com revisão resolvida para hash;
- as saídas finais em `finals.jsonl`. Ajuste de prompt só com dado de desenvolvimento.

Se falhar: recusa antes de gravar sai com 1 e nomeia o campo. Piloto interrompido (saída 2) retoma como no passo 7. Prompt ajustado exige `REGISTRY.json` atualizado e novo piloto, `pilot-02`.

Custo da corrida completa, com o PROMISE inteiro, cerca de 93% das chamadas:

```sh
R --dry-run --promise
```

No ensaio: 1.986 chamadas, cerca de 3,81 milhões de tokens de entrada e teto de 8,13 milhões de saída. Multiplique pela razão do piloto e pelo preço.

**Registrar**: custo real do piloto, razão real/estimado e custo previsto. Troca de modelo ou de parâmetro acontece agora, antes do congelamento.

## Passo 4. Ingerir a amostra [ensaiado]

```sh
PYTHONPATH=code .venv/bin/python -m ingestion data/raw/amostra/amostra.toml
PYTHONPATH=code .venv/bin/python -m ingestion data/raw/amostra/amostra.toml --check
```

Executor e métricas aceitam o `.toml` direto. Este passo grava `data/processed/ingestion/amostra.json`, que vai no pacote, e confere o corte. Conferir: tantos documentos quantos artefatos; a segunda linha diz "saída em dia".

Se falhar: "veio de outro arquivo de conjunto" quer dizer que `amostra.json` já existe e saiu de outro `.toml`. Nada foi gravado. Se o antigo é sobra, apague e rode de novo; se não, use `--output data/processed/ingestion/<nome>.json`.

## Passo 5. Congelar [ensaiado, só com `--allow-missing`]

```sh
make freeze
make freeze-check MANIFEST=outputs/runs/freeze-AAAA-MM-DD.json
python3 -c "import json; m=json.load(open('outputs/runs/freeze-AAAA-MM-DD.json')); print(m['missing']); print('\n'.join(k for k in m['files'] if k.startswith('data/raw/amostra')))"
```

O manifesto cobre `code/` inteiro (testes e fixtures inclusive), `tools/`, `requirements*.lock`, `pyproject.toml`, `Makefile`, `docker-compose.yml`, a configuração, os prompts, `data/raw/amostra/` e `data/raw/promise/`. Ficam fora `__pycache__`, `.pyc`, `.DS_Store` e entradas ocultas (`code/graph/.neo4j-test.lock`, `.partial-<run_id>/`). No ensaio, 261 arquivos, com os 233 de `code/` todos presentes.

Conferir: `missing` vazio. A lista da amostra traz cada `aNN.txt`, `referencia.toml`, `amostra.toml`, as notas e `TEMPLATE/`, e nada mais. No ensaio, a subpasta de teste entrou inteira, sem aviso.

Se falhar:

- "caminhos ausentes: data/raw/amostra/referencia.toml": a amostra não está na pasta. Não congele. `make freeze FREEZE_FLAGS=--allow-missing` grava um congelamento de teste, com o ausente em `missing`, que não vale como oficial;
- "já existe com outro conteúdo": já houve congelamento hoje. Rode o `make freeze-check` que a mensagem traz para ver o que mudou; se o novo for o certo, use o `make freeze FREEZE_FLAGS="--output …-b.json"` da mensagem e registre o motivo.

**Registrar**: data, número de artefatos e de requisitos, SHA-256 do manifesto e `tree_sha256`, os dois impressos por `make freeze`.

Daqui em diante, nada muda nos caminhos congelados.

## Passo 6. Dry-run da corrida [ensaiado]

```sh
R --dry-run --ingestion data/raw/amostra/amostra.toml --promise
```

Conferir: as extrações da amostra são três vezes as de uma corrida (`repetitions.structural_sample = 3`). Total dentro do orçamento do passo 3.

Se falhar: orçamento estourado depois do congelamento exige mudar a configuração, congelar de novo com `-b.json` e registrar. Não rode acima do orçamento.

## Passo 7. Corrida do experimento [sintético]

```sh
make freeze-check MANIFEST=outputs/runs/freeze-AAAA-MM-DD.json
R exp-01 --real --ingestion data/raw/amostra/amostra.toml --promise --freeze outputs/runs/freeze-AAAA-MM-DD.json
make freeze-check MANIFEST=outputs/runs/freeze-AAAA-MM-DD.json
```

O segundo `freeze-check` prova que o código da corrida é o congelado. Diferença nele é defeito a registrar antes das métricas.

Não passe `--config`. Com `--freeze`, a configuração tem de estar em `code/experiments/config/`, congelada e inalterada; uma cópia fora da árvore e o TOML de um fixture, mesmo congelado, são recusados com saída 1 **[corrigido: E2-3]**.

Conferir:

- saída 0 e a lista de arquivos (`calls`, `case_results`, `classifications`, `contexts`, `finals`, `manifest`, `rejections`);
- `manifest.json`: `model_id` escolhido, `replay` e `pilot` falsos, `runs` 3, `freeze_manifest_sha256` igual ao do passo 5, `config_sha256` igual a `shasum -a 256 code/experiments/config/experiment.toml`, e sem `resumptions` se não houve retomada;
- estado das chamadas em `calls.jsonl`, como no passo 3. Falha de API não para a corrida: vira chamada `failed` e caso inválido, contado nas métricas.

Se a corrida for interrompida (saída 2, queda de rede, Ctrl-C, máquina desligada), `outputs/runs/.partial-exp-01/` fica no disco. Não apague. Retome com o comando original, copiado do manifesto parcial, mais `--resume`:

```sh
python3 -c "import json; print(json.load(open('outputs/runs/.partial-exp-01/manifest.json'))['command'])"
# cole a linha impressa e acrescente --resume
```

Copie o comando em vez de redigitá-lo: a retomada confere configuração, entradas, prompts, congelamento, versões e a seleção efetiva, `selection_sha256` do manifesto (casos da amostra, filtros `--promise-projects`, `--promise-items` e `--promise-limit`, e os itens do PROMISE escolhidos). Um filtro diferente do original é recusado com saída 1, com "selection_sha256" na mensagem, sem tocar na parcial **[corrigido: E2-2]**. Parcial gravada antes dessa correção não tem o campo e não retoma. As chamadas já gravadas vêm do registro, sem custo; só o resto vai à API. O manifesto ganha `resumptions`, com o comando e o número de chamadas já gravadas.

No ensaio, uma corrida morta com SIGKILL aos 40 de 96 registros e retomada gerou os cinco registros byte a byte iguais aos da corrida sem interrupção, e o `calls.jsonl` só diferiu nos carimbos de tempo. Ctrl-C sai com 2, diz "interrompida pelo usuário (Ctrl-C)" e lembra o `--resume`. Falta de resposta gravada (replay) também sai com 2, mas diz que `--resume` não resolve **[corrigido: E2-9]**. Repetir sem `--resume` é recusado; retomar corrida completa, inexistente ou com outra configuração também.

Outras saídas:

- saída 1: recusa antes de gravar; a mensagem diz o motivo (configuração, congelamento, `--config`, `run_id` repetido, retomada incompatível);
- saída 2 depois de `--resume` com "sobrou chamada do registro": a retomada divergiu do início. Não apague a parcial; registre e decida com o orientador;
- muitas chamadas `failed` (limite de taxa, por exemplo): registre e decida com o orientador se vale ou se roda `exp-02`.

Defeito achado no código depois da corrida: corrija, registre e refaça os registros sem custo pelo replay. No ensaio, o replay reproduziu os cinco registros byte a byte; o `calls.jsonl` do replay muda só `client`, `model` e carimbo de tempo.

```sh
R exp-01-replay --replay outputs/runs/exp-01/calls.jsonl --ingestion data/raw/amostra/amostra.toml --promise --freeze outputs/runs/freeze-AAAA-MM-DD.json
```

**Registrar**: `run_id`, data, SHA-256 de `outputs/runs/exp-01/manifest.json`, número de chamadas `failed`, retomadas, custo real.

## Passo 8. Pareamento cego e métricas [sintético]

```sh
I=(--ingestion data/raw/amostra/amostra.toml --reference data/raw/amostra)
M exp-01 sheet $I
```

Preencha `outputs/runs/exp-01/metrics/pairing/sheet_run0.toml`, `sheet_run1.toml` e `sheet_run2.toml` com o id de uma candidata ou `nenhum` em cada `decision`, pela seção 8 do protocolo. Não abra `metrics/pairing/key/`. Requisito sem candidata não aparece e conta como gerado sem par.

```sh
M exp-01 lock --run-index 0 $I
M exp-01 lock --run-index 1 $I
M exp-01 lock --run-index 2 $I
```

**Registrar**, antes do `compute`: o SHA-256 que cada `lock` imprime.

```sh
M exp-01 compute $I
```

O `compute` lê os rótulos do PROMISE de `data/processed/promise/promise_nfr.jsonl` sozinho e confere o `.toml` pelo SHA-256 do conjunto ingerido em memória contra o manifesto.

Conferir em `outputs/runs/exp-01/metrics/summary.md`:

- configuração "confere com o manifesto", SHA-256 de cada planilha igual ao registrado, nenhuma linha "pareamento pendente", BERTScore com modelo e revisão em hash, 625 itens do PROMISE com registro;
- "Comum às duas condições": três colunas, extração da amostra, extração dos projetos do PROMISE e classificação. A extração dos projetos só aparece na corrida 0;
- PROMISE: falhas do refinamento (resposta inválida ou API) e recusas por regra G em linhas separadas;
- tamanho do contexto por estrato (`all`, `written`, `rejected_w`). B maior que A é esperado, porque B contém A;
- rótulo do PROMISE no contexto: concordância perto da esperada no projeto. Muito acima, o contexto virou oráculo de rótulo: registre e leve ao orientador;
- `foreign_evidence` por condição.

Se falhar:

- `lock` com "decision vazio": falta decisão;
- planilha alterada depois do `lock`: `compute` recusa com os dois SHA-256. Decisão travada não muda; erro objetivo vai para `corrections_run<i>.toml` (`code`, `decision`, `date`, `reason`);
- "não está nos rótulos de referência": `--promise-labels` aponta para outro arquivo;
- BERTScore vazio na configuração: o `compute` recusa. Só use `--skip-bertscore` com o motivo registrado; a tabela sai com n/d.

## Passo 9. Tabelas e relatório [sintético]

```sh
python3 tools/report_tables.py exp-01
```

Grava `report/src/gerado/exp-01/metricas_por_condicao.tex`, `promise_macro.tex` e `promise_por_rotulo.tex`. Acrescente no capítulo 6 de `report/src/tg2_continuacao.tex`:

```latex
\input{gerado/exp-01/metricas_por_condicao.tex}
\input{gerado/exp-01/promise_macro.tex}
\input{gerado/exp-01/promise_por_rotulo.tex}
```

```sh
make report
```

Conferir: a legenda diz `exp-01` e 3 corridas, BERTScore não está n/d, nenhuma legenda termina em "Corrida piloto" ou "Corrida sintética", e `tab:exp-01-condicoes`, `tab:exp-01-promise-macro` e `tab:exp-01-promise-rotulos` resolvem. Leia o PDF e `report/text/tg2_continuacao.md`.

Se falhar:

- corrida piloto é recusada sem `--allow-pilot`; piloto não entra como resultado;
- "tem model_id `synthetic`": corrida do cliente sintético ou replay dela, recusada sem `--allow-synthetic` (que marca a legenda). Replay de corrida real guarda o `model_id` real e passa;
- "falta a linha '- corrida: ..., model_id'": `summary.md` antigo. Rode o `compute` de novo.

No ensaio, a recusa e as legendas marcadas funcionaram, e as três tabelas compilaram sem aviso num `.tex` de teste com as margens do relatório.

**Registrar**: SHA-256 do PDF que `make report` imprime.

## Passo 10. Estudo de caso [sintético]

```sh
PYTHONPATH=code .venv/bin/python -m ingestion data/raw/caso/caso.toml
R --dry-run --ingestion data/raw/caso/caso.toml
make freeze-check MANIFEST=outputs/runs/freeze-AAAA-MM-DD.json
R caso-01 --real --ingestion data/raw/caso/caso.toml --freeze outputs/runs/freeze-AAAA-MM-DD.json
M caso-01 compute --ingestion data/raw/caso/caso.toml
python3 tools/report_tables.py caso-01
PYTHONPATH=code .venv/bin/python -m deliverables caso-01 --condition REQKG-grounded --run-index 0 --name <nome> --ingestion data/raw/caso/caso.toml
PYTHONPATH=code .venv/bin/python -m deliverables caso-01 --condition REQKG-grounded --run-index 0 --name <nome> --ingestion data/raw/caso/caso.toml --check
```

Os artefatos aceitam o `.toml` em `--ingestion`, como as métricas: o conjunto é ingerido em memória e o SHA-256 dos bytes canônicos tem de estar no manifesto **[corrigido: E2-5]**. Sem `--ingestion`, eles acham sozinhos `data/processed/ingestion/caso.json` pelo SHA-256, por isso a primeira linha continua: ela grava o `.json` que vai no pacote. A corrida do caso roda três repetições (`--runs` só vale com `--pilot`). Sem referência, não há pareamento nem BERTScore. Interrupção retoma como no passo 7.

Conferir: `outputs/caso/<nome>/` com `srs.md`, `instancia_reqkg.json`, `instancia_resumo.md`, `matriz_proveniencia.csv` e `.md`, `relatorio_lacunas.md` e `origem.json`. O cabeçalho mostra o `model_id` real e "Respostas gravadas (replay): não". O `--check` sai com 0. Preencha à mão só "A preencher pelo autor" e "Limitações observadas".

Se falhar: saída 2 com "não está em ingestion_sha256" quer dizer que o `.toml` passado não é o da corrida (ou o `[chunking]` da configuração mudou), ou, sem `--ingestion`, que `caso.json` falta ou está desatualizado. Confira o `.toml` contra o `command` do manifesto da corrida.

**Registrar**: `run_id`, SHA-256 do manifesto da corrida e o SHA-256 de cada artefato, em `origem.json`.

## Passo 11. Pacote de entrega [ensaiado em parte]

Antes, apague o que não é entrega e que o pacote pegaria: subpasta extra em `data/raw/amostra/`, `.json` de ingestão de teste em `data/processed/ingestion/`, `report/src/gerado/<run_id>` de piloto ou teste, `.tex` solto em `report/src/`, `outputs/runs/freeze-*.json` de teste. `python3 tools/package.py --list` avisa, sem bloquear, das tabelas de corrida não publicada e dos congelamentos que nenhuma corrida publicada cita. `data/raw/amostra/`, `data/processed/` e `.tex` soltos não têm aviso: confira à mão.

Preencha agora `PUBLICACAO.toml`, na raiz. Ele fica fora do congelamento, então editá-lo não derruba o `freeze-check` **[corrigido: E2-4]**:

- `runs`: a pasta inteira, com `calls.jsonl`, que guarda o texto dos documentos e permite o replay;
- `run_metrics`: só `manifest.json` e `metrics/`. As planilhas em `metrics/pairing/` trazem declarações geradas e citações curtas; leia-as antes de publicar uma corrida do caso assim (`PACKAGE.md`, "Registros de chamada").

```sh
make freeze-check MANIFEST=outputs/runs/freeze-AAAA-MM-DD.json
python3 tools/package.py --list > /dev/null
python3 tools/secret_scan.py outputs/runs/exp-01 outputs/caso/<nome>
make package
make package-check
```

`make package-check` sem `ZIP` confere o zip do dia (a primeira linha diz qual) e recusa se ele não existir, listando os que existem, em vez de conferir o de outro dia depois de um `make package` recusado **[corrigido: E2-8]**. Pacote com outra data: `make package-check PACKAGE_DATE=AAAA-MM-DD` ou `ZIP=<caminho>`.

Conferir: o `freeze-check` ainda passa, "secret scan sem achados", avisos "não está em runs nem em run_metrics de PUBLICACAO.toml" só para corridas que você decidiu não publicar, nenhum aviso de "corrida não publicada" sem explicação. `outputs/caso/` fica fora até haver registro de que o corpus é publicável.

Se falhar: achado da varredura mostra arquivo, linha, tipo e impressão digital. Valor real sai da fonte; falso positivo ganha entrada comentada em `ALLOWED` de `tools/secret_scan.py`, o que exige congelar de novo. Corrida nas duas listas, em `run_metrics` sem `metrics/`, ou `PUBLICACAO.toml` ausente ou com chave desconhecida interrompe o pacote. "make package de AAAA-MM-DD não rodou ou foi recusado" no `package-check`: o zip do dia não existe; rode `make package` e leia o motivo da recusa.

Depois das correções de 11 de outubro, com as listas vazias, `make secret-scan`, `make package` e `make package-check` passaram sobre 285 arquivos. No ensaio, `make package` foi recusado pela varredura (E2-1). Com a permissão e a lista de publicação só das métricas trocadas em memória, o pacote levou da corrida apenas `manifest.json` e `metrics/`, o aviso de sobra sumiu para a tabela e o congelamento citados por ela, e a conferência passou.

**Registrar**: SHA-256 do zip e `tree_sha256`, impressos por `make package`.

## Defeitos do segundo ensaio

Achados ao rodar a sequência sobre o código de 11 de outubro. Nenhum foi corrigido pelo ensaio; todos foram corrigidos depois, no mesmo dia. Cada correção tem um teste, e uma sabotagem que desfaz a correção no lugar (com `PYTHONDONTWRITEBYTECODE=1`) derruba esse teste, que volta a passar com o arquivo restaurado. A sequência completa ainda não rodou de novo sobre o código corrigido.

| # | Defeito | Situação em 11 de outubro |
| --- | --- | --- |
| E2-1 | `make secret-scan` e `make package` falham: a segunda chave sintética de `code/extraction/test_extraction_client.py`, linha 75 (teste da chave pelo `.env`), não está em `ALLOWED`. `make test` passa mesmo assim | Corrigido: exceção comentada `ed8fd788ab4718da` em `ALLOWED`. `test_real_package_tree_has_no_blocking_finding` (`tools/test_secret_scan.py`) varre a lista real de `make package` e exige zero achados. Sabotagem: sem a exceção, o teste falha |
| E2-2 | `--resume` não confere os filtros do PROMISE. Retomar com `--promise-items` novo saiu com 0, a corrida ficou com 2 itens em vez de 9, e o `command` do manifesto continuou o original | Corrigido: `selection_sha256` no manifesto (casos, filtros e itens do PROMISE), conferido na retomada. Testes: `test_resume_refuses_another_promise_selection` e a retomada com `--promise-items` diferentes na integração contra o Neo4j. Sabotagem: sem o campo em `RESUME_FIELDS`, o teste falha |
| E2-3 | A guarda do `--config` aceita qualquer TOML congelado com o mesmo hash, como `code/experiments/metrics/fixtures/experiment.toml`, porque o congelamento cobre `code/` inteiro | Corrigido: com `--freeze`, `--config` tem de estar em `code/experiments/config/`. Teste: `test_frozen_config_outside_the_config_folder_is_refused`. Sabotagem: sem a guarda da pasta, o TOML do fixture passa e o teste falha |
| E2-4 | As listas de publicação ficam em `tools/package.py`, que está no congelamento. Editá-las depois derruba o `freeze-check` e o pacote leva um arquivo diferente do congelado | Corrigido: listas `runs` e `run_metrics` em `PUBLICACAO.toml`, na raiz, fora de `DEFAULT_PATHS`, lidas e validadas por `tools/package.py`. Testes: `test_publication_lists_live_outside_the_freeze` e `test_publication_file_is_required_and_validated`. Sabotagem: com o arquivo em `DEFAULT_PATHS`, o teste falha |
| E2-5 | `python -m deliverables --ingestion <conjunto>.toml` é recusado ("não está em ingestion_sha256"); executor e métricas aceitam o `.toml` | Corrigido: o `.toml` é ingerido em memória e conferido pelo SHA-256 dos bytes canônicos, como nas métricas. Teste: `test_set_file_is_ingested_in_memory_and_checked_against_the_manifest`. Sabotagem: sem o ramo do `.toml`, o teste falha |
| E2-6 | As métricas pareiam artefato da referência e documento ingerido só pelo nome do arquivo, sem conferir o SHA-256 do texto | Corrigido: `sheet`, `lock` e `compute` recusam artefato e documento de mesmo nome com SHA-256 do texto normalizado diferente, com os dois arquivos na mensagem. Teste: `test_reference_artifact_must_have_the_text_of_the_ingested_document`. Sabotagem: sem a conferência, o teste falha |
| E2-7 | O piloto de `PROGRESS.md` e do README do executor (`--promise-projects 1 --promise-limit 5`) sorteia 5 itens funcionais | Corrigido no README do executor: `--promise-projects 2 --promise-limit 5`, 22 chamadas no dry-run sem amostra. `PROGRESS.md` (item 4 da próxima ação) ainda traz o projeto 1 e fica para quem edita esse arquivo. Teste: `test_documented_pilot_draws_non_functional_items` sorteia os pilotos do README e deste roteiro. Sabotagem: com o projeto 1 no README, o teste falha |
| E2-8 | `make package-check` sem argumento confere o zip mais novo pelo nome, mesmo de outro dia | Corrigido: sem `ZIP`, confere o zip do dia (ou de `PACKAGE_DATE`), diz qual na primeira linha, e recusa se ele não existir. Teste: `test_check_without_zip_never_falls_back_to_an_older_package`. Sabotagem: com a busca do mais novo de volta, o teste falha |
| E2-9 | Mensagens: Ctrl-C imprime "ficou em …: ." com o motivo vazio; falta de resposta gravada sugere `--resume`, que não resolve | Corrigido: Ctrl-C diz "interrompida pelo usuário (Ctrl-C)"; falta de resposta gravada diz que `--resume` não resolve e o que conferir. O README das métricas usa a função `M() { ...; }`. Testes: `test_ctrl_c_message_names_the_reason_and_the_resume`, `test_missing_recorded_response_does_not_suggest_resume` e `test_readme_commands_run_in_zsh`. Três sabotagens, uma por teste, cada uma derruba o seu |

Corrigidos depois do primeiro ensaio e confirmados neste: chave pelo ambiente ou pelo `.env` (R79), `--config` fora da árvore recusado (R77), métricas com `.toml` (R82), retomada byte a byte (R83), custo comum separado (R86), congelamento do código e recusa sem a amostra (R76, R78), ingestão que não sobrescreve outro conjunto (R84), tabelas que recusam corrida sintética (R85), publicação só das métricas e aviso de sobras (R81), sorteio espalhado do piloto (R74), alternância das condições (R71), A com os itens da chamada e B contendo A no PROMISE (R63, R65).

Sem mudança: trava do Neo4j com espera de 120 s entre corrida e testes (ninguém roda testes durante a corrida).
