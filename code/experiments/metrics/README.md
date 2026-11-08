# Métricas de uma corrida

Lê os registros de `outputs/runs/<run_id>/` (formato em `code/experiments/records.py`), o arquivo de ingestão da corrida e, quando houver, a amostra de referência e os rótulos do PROMISE. Grava tabelas CSV e `summary.md` em `outputs/runs/<run_id>/metrics/`. O `summary.md` traz a fórmula de cada métrica, o SHA-256 de cada entrada e o comando que regenera todos os números.

Desenho: `code/experiments/config/DATA_SPLIT.md`, `instructions/PROTOCOLO_ANOTACAO.md` (seções 8 e 9) e capítulo 5 de `report/src/tg2_continuacao.tex`.

## Comandos

A partir da raiz do repositório. scikit-learn e bert-score vêm de `make venv-metrics`. A função de shell abaixo funciona em zsh e em bash; uma variável com o comando inteiro (`M="PYTHONPATH=code ..."; $M`) falha em zsh, que não divide a variável em palavras.

```sh
M() { PYTHONPATH=code .venv/bin/python -m experiments.metrics "$@"; }
M <run_id> sheet   --ingestion data/raw/amostra/amostra.toml --reference data/raw/amostra
# o autor preenche metrics/pairing/sheet_run<i>.toml, sem abrir metrics/pairing/key/
M <run_id> lock    --run-index 0 --ingestion data/raw/amostra/amostra.toml --reference data/raw/amostra   # imprime o SHA-256 para PROGRESS.md
M <run_id> compute --ingestion data/raw/amostra/amostra.toml --reference data/raw/amostra                 # PROMISE: rótulos de data/processed/promise/
```

- `--ingestion` aceita o arquivo de conjunto (`.toml`, o mesmo passado ao executor) ou a saída da ingestão (`.json`). O `.toml` é ingerido em memória com o `[chunking]` da configuração, sem gravar em `data/processed/`, e o SHA-256 dos bytes canônicos do conjunto ingerido tem de estar em `ingestion_sha256` do manifesto, que é o que o executor grava. O `.json` vale pelo SHA-256 do arquivo.
- `--config` aponta para a configuração congelada; o SHA-256 tem de bater com `config_sha256` do manifesto.
- `--reference`: cada artefato `aNN.txt` se liga ao documento ingerido de mesmo nome, e o SHA-256 do texto do artefato, normalizado como a ingestão normaliza (sem BOM, LF, NFC), tem de ser o `sha256` do documento. Textos diferentes com o mesmo nome são recusados em `sheet`, `lock` e `compute`, com os dois arquivos na mensagem (E2-6).
- `compute` recusa o BERTScore enquanto `evaluation.bertscore_model` estiver vazio. `--skip-bertscore` calcula o resto. Modelo fora da tabela do bert-score pede `--bertscore-num-layers`. A revisão (`--bertscore-revision`, padrão `main`) é resolvida para o hash do commit, que vai para o resumo.
- Corrida sem `lock` fica com o pareamento pendente; `compute` não abre a chave dela.

## O que é medido

As fórmulas completas vão impressas no `summary.md`. Escolhas que mudam números:

- Corpus do caso. `check_all`, `is_complete`, `corrected` e a cobertura de proveniência usam só os chunks do documento do caso (`Corpus.case`), como o executor e o capítulo 5. Evidência que cita chunk de outro documento não resolve e conta como P2. `foreign_evidence` conta essas citações por corrida e condição, na saída final inteira (requisitos, atores, componentes, entidades e relações).
- `corrected`: o alvo tem menos violações C e P na saída final do que na extração, e nenhuma violação P nova, comparando pares (regra, detalhe). Trocar P3 por P2, ou tirar C3 e C4 ganhando P4, não conta.
- Tamanho do contexto (`context_by_run.csv`): por alvo, itens e caracteres (soma de `len(item.text)`) do `ContextRecord`, com média, mediana e máximo por corrida e condição, nos estratos `all`, `written` (alvo gravado no grafo) e `rejected_w` (alvo recusado na gravação, com `RejectionRecord` de mesma chave). O contexto de B contém o de A; a diferença de tamanho é uma ameaça de construto (capítulo 5).
- Cobertura de proveniência: `covered / paired` e `covered / references`. O segundo denominador é o mesmo nas duas condições.
- Chamadas comuns às duas condições (`shared_by_run.csv` e a primeira tabela do resumo): extração da amostra (casos de `finals.jsonl`), extração dos projetos do PROMISE (os demais casos de extração, grafo por projeto de B) e primeira classificação do PROMISE, cada uma com chamadas e tokens. As colunas `extraction_*` são só da amostra.
- PROMISE: `refinement_status` diferente de ok (falha) mantém o rótulo inicial (o contrato exige `final == initial`) e entra em `promise_refinement_failures` por condição. Refinamento válido recusado por regra G (`refinement_status` ok e `refinement_accepted` falso) também mantém o rótulo inicial e entra, em separado, em `promise_refinement_refusals`, por regra. Primeira classificação inválida é predição inválida nas três classificações.
- PROMISE, diagnóstico (`promise_context_agreement.csv`): entre os itens de contexto com `item_id` `PROMISE-NFR-NNNN`, a fração com o mesmo rótulo de referência do item avaliado, ao lado da fração esperada se o contexto fosse sorteado entre os demais itens do projeto, e a fração de itens cuja maioria de rótulos no contexto, quando única, é a do item. Concordância muito acima da esperada indica que o contexto funciona como oráculo de rótulo.

## Pareamento cego

1. `sheet`: para cada requisito gerado, as candidatas são as referências do mesmo caso cuja citação aparece, pela comparação de P3, num chunk da chamada de extração que o produziu (prefixo `c0`, `c1`... da chave, chunks em `calls.jsonl`). Requisitos sem candidata não entram na planilha e contam como gerados sem par. Declarações iguais depois da normalização de P3, do mesmo caso e com as mesmas candidatas, viram uma linha só, venham de uma condição ou das duas. Códigos e ordem saem de `evaluation.seed` e do número da corrida. A planilha mostra caso, declaração e candidatas (id, declaração, citação). A chave fica em `key/`.
2. O autor preenche `decision` com o id de uma candidata ou `nenhum`.
3. `lock`: confere a planilha contra os registros, exige todas as decisões e grava o SHA-256 em `lock_run<i>.json`. Planilha alterada depois disso derruba `lock` e `compute`. Erro achado mais tarde vai para `corrections_run<i>.toml` (`code`, `decision`, `date`, `reason`), listado no resumo.
4. `compute`: decodifica pela chave e aplica a regra um a um por corrida, caso e condição. Duas chaves na mesma referência: fica a menor, a outra é duplicata.

## Fixtures

`fixtures/` tem dois artefatos sintéticos, a referência deles, o conjunto de ingestão, uma configuração de teste e duas corridas sintéticas geradas por `fixtures/build.py` (`--check` confere). `fixtures/decisions.py` preenche as planilhas como o autor faria. Os valores esperados, calculados à mão, estão em `test_metrics.py`. Alguns refinamentos aceitos nos fixtures citam chunk do outro documento ou criam P4; a regra G6 do executor recusaria parte deles, e eles existem para provar que as métricas medem certo um registro assim. `tools/test_report_tables.py` também lê valores calculados sobre estes fixtures.

```sh
.venv/bin/python code/experiments/metrics/fixtures/build.py --check
.venv/bin/python -m pytest code/experiments/metrics
```
