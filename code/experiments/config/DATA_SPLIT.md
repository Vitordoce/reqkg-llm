# Dados, condições e métricas

Registrado no dia 1 do plano e revisto em 10 de outubro de 2026, antes de qualquer prompt existir. Revisto de novo em 11 de outubro, depois de uma revisão adversarial do experimento implementado e antes de qualquer corrida com o Claude. Mudar este arquivo depois de ver uma saída do modelo invalida a comparação entre as condições. As decisões de 10 e 11 de outubro estão em `PROGRESS.md`, com autor e motivo.

## Desenvolvimento

Serve para escrever e ajustar prompts, regras e código.

- Os fixtures sintéticos em `code/domain/fixtures/`. O texto em `corpus/entrevista_sintetica.txt` foi escrito para testar o contrato e não descreve sistema real.
- Outros textos sintéticos de desenvolvimento em `code/*/fixtures/` (por exemplo `code/ingestion/fixtures/` e `code/extraction/fixtures/`), sempre marcados como sintéticos na primeira linha. Itens sintéticos de classificação usam `promise_id` da faixa `PROMISE-NFR-9001` em diante, que não existe no PROMISE.

Exemplo dentro de um prompt só pode sair daqui.

## Avaliação

Nenhum texto destes conjuntos entra em prompt, exemplo, regra ou ajuste.

- PROMISE NFR, inteiro. O prompt de classificação é zero-shot, com a definição de cada rótulo.
- Amostra de referência: 6 a 8 artefatos sintéticos e cerca de 60 requisitos de referência. A anotação é humana, feita pelo autor e revista pelo orientador. Nenhum modelo anota. O hash dos arquivos é registrado no congelamento, antes da primeira corrida.
- Corpus do estudo de caso. Roda uma vez, depois do congelamento, sem ajuste de prompt a partir do resultado.

Quem ajusta prompt não abre a amostra nem o corpus do caso. Depois do congelamento, prompt, schema, regras e `experiment.toml` só mudam com registro em `PROGRESS.md` e nova corrida das duas condições.

## As duas condições

As duas condições compartilham tudo, menos a origem do contexto do refinamento.

1. Ingestão. O mesmo arquivo de ingestão serve às duas condições, com os mesmos `source_id` e `chunk_id`. O hash desse arquivo vai para o registro da corrida.
2. Extração. Uma única extração por caso e por corrida, com o mesmo agrupamento de chunks por chamada. O prompt mostra o `source_id` e o `chunk_id` de cada trecho. As respostas das chamadas de um caso são unidas com `domain.llm_io.merge_outputs`, que prefixa as chaves pela chamada. Relação entre chaves de chamadas diferentes não existe no MVP.
3. Escolha dos candidatos a refinar. `domain.rules.refinement_targets` aplica as regras C1 a C4 e P1 a P4, as marcas de revisão e o limiar de confiança à extração compartilhada. A lista é a mesma nas duas condições.
4. Refinamento. Uma passagem por candidato escolhido, nas duas condições. A condição que refina primeiro troca de um caso para o seguinte, para que uma mudança da API no meio da corrida não recaia sempre sobre a mesma condição.
   - `LLM-only`: o contexto são os chunks da chamada de extração em que o candidato nasceu (`ContextStrategy.SOURCE_CHUNKS`).
   - `REQKG-grounded`: o contexto é o subgrafo local recuperado do Neo4j (`ContextStrategy.GRAPH_LOCAL`), limitado por `retrieval.max_items`. A semente é o nó do requisito, quando a gravação o aceitou, mais os chunks da chamada de extração. Os chunks da semente entram no nível zero, então o contexto de B sempre contém o de A. Atributo de qualidade é folha na expansão: a busca chega a ele e não segue, porque um nó por categoria ligaria requisitos de outros documentos só pela categoria. Ator continua expandindo.
   - Um refinamento com violação G (ver `code/domain/schema/RULES.md`) é recusado, e o candidato original fica. Campo que a fonte não sustenta fica nulo e recebe marca de revisão. O modelo não inventa prioridade nem método de verificação.
   - G6 recusa o refinamento que acrescenta evidência que não se sustenta no corpus do caso, ou que preenche prioridade ou método de verificação que o candidato não tinha sem acrescentar evidência. O contexto de B pode ter chunks de outros documentos, e G3 aceita qualquer chunk do contexto; sem G6, B poderia trocar a evidência por um chunk que o modelo não viu na extração do caso.
5. Saída final. A resposta da extração com os refinamentos aceitos no lugar dos candidatos. É sobre ela que toda métrica é calculada.

O grafo serve para recuperar contexto na condição B. Ele não é ponto de medida. As recusas na gravação (regras W) não mudam as métricas e são reportadas à parte.

Esta definição muda a condição A do TG-1, que não tinha refinamento. Com uma passagem nas duas condições e o contexto de B contendo o de A, a diferença entre elas é o que a expansão pelo grafo acrescenta.

## PROMISE NFR

A classificação é uma tarefa própria, com o contrato `ClassificationOutput`. Cada item recebe uma classificação e uma passagem de refinamento.

Ordem. Antes de agrupar os chunks em chamadas de extração, os itens de cada projeto são ordenados por `sha256(semente:promise_id)`, com a semente da configuração. O arquivo publicado vem ordenado por rótulo dentro de cada projeto. Sem embaralhar, os itens de uma chamada tendem a ter o mesmo rótulo, e os vizinhos no contexto do refinamento viram pista de rótulo nas duas condições, sem relação com o grafo. O pacote de métricas reporta, como diagnóstico, a concordância de rótulo entre vizinhos da mesma chamada e o valor esperado com rótulos ao acaso.

- `LLM-only`: o refinamento vê os outros itens da mesma chamada, como texto, do mesmo jeito que na amostra. O próprio item já está no prompt e não entra no contexto.
- `REQKG-grounded`: o refinamento vê o subgrafo local de um grafo montado com os requisitos do mesmo projeto, sem rótulo. A semente são os outros chunks da chamada, então o contexto de B contém o de A, e a diferença é a expansão pelo grafo. O contexto não traz atributos de qualidade (são categorias ISO inferidas pelo modelo e se parecem com os rótulos, como PE e performance) nem nó com evidência no chunk do item avaliado.
- A regra G5 compara identificador e texto de cada item do contexto com os do item avaliado e recusa o refinamento se o item aparecer.
- Classificação inicial inválida ou com falha da API erra o item nas duas condições. Refinamento que falha mantém o rótulo inicial; o estado fica em `ClassificationRecord.refinement_status`, e as falhas são contadas por condição.

Rótulos: os do próprio PROMISE (`domain.enums.PromiseLabel`), sem correspondência com a ISO/IEC 25010. Duas tarefas: binária (F contra os demais) e de categoria (A, FT, L, LF, MN, O, PE, PO, SC, SE, US). PO tem um único exemplo e fica fora da média macro, com o motivo escrito no relatório.

Duplicatas: `PROMISE-NFR-0107` e `PROMISE-NFR-0108` têm o mesmo texto e o mesmo rótulo. `PROMISE-NFR-0426` (SE) e `PROMISE-NFR-0460` (F) têm o mesmo texto e rótulos diferentes. Os quatro ficam no conjunto. O relatório cita o par contraditório como limite do rótulo de referência.

## Repetições e casos inválidos

- Três corridas completas na amostra anotada e uma no PROMISE (`repetitions` em `experiment.toml`). Temperatura 0 não garante a mesma resposta. A variação entre corridas é reportada.
- Toda chamada vira um `CaseResult`, inclusive quando a resposta é inválida ou a API falha. Um caso inválido conta como zero requisito gerado para aquele caso: as referências dele entram como não encontradas. O número de casos inválidos por condição é reportado.

## Pareamento com a amostra anotada

Fixado antes da anotação, sem BERTScore, para que a métrica não seja circular. Duas etapas:

1. Um requisito gerado só pode parear com um requisito de referência cuja citação esperada esteja em um dos chunks enviados na chamada de extração que produziu o requisito gerado. A evidência que o modelo citou não entra nesta etapa. Se entrasse, a cobertura de proveniência sobre os pares ficaria perto de 100% por construção, e um requisito gerado sem evidência nunca formaria par.
2. Entre os pares possíveis, o anotador decide se os dois dizem a mesma necessidade, sem saber a condição.

O relatório traz três contagens: pareados, gerados sem par e referências sem par.

## Métricas

O ponto de partida é a saída final de cada condição, por caso e por corrida. A evidência é conferida contra o corpus do caso, os chunks do documento que o modelo viu na extração. Chunk de outro documento da corrida conta como P2, mesmo que esteja no grafo.

- `precision`, `recall`, `f1`: classificação no PROMISE, por rótulo e média macro, com scikit-learn.
- `bertscore_f1`: BERTScore entre cada requisito gerado e o requisito pareado. O modelo do BERTScore fica em `evaluation.bertscore_model`, escolhido antes da primeira corrida.
- `completeness_ratio`: fração de requisitos para os quais `domain.rules.is_complete` é verdadeiro: tipo, prioridade, método de verificação e ao menos uma evidência que resolve no corpus do caso. Esses campos são opcionais no contrato para que a ausência possa ser contada. Status não entra.
- `provenance_coverage`: fração dos requisitos de referência pareados cuja evidência gerada cita um chunk que contém a citação esperada pelo anotador. É uma medida por requisito e por chunk. A mesma contagem também sai dividida pelo total de requisitos de referência, para que uma condição que forma menos pares não ganhe cobertura por perder os requisitos difíceis. Substitui a "taxa de campos sem fonte" do TG-1, que o contrato não calcula, porque a evidência é registrada por requisito e não por campo.
- `unsupported_claim_rate`: fração de requisitos gerados com violação P1, P2 ou P3.
- `rule_violation_rate`: violações K1 a K5 por requisito gerado. O refinamento não propõe relações, então a diferença esperada entre as condições nesta métrica é pequena.

Medidas complementares para as contra-hipóteses:

- Propagação de erro para o grafo: precisão dos registros aceitos no grafo contra a anotação.
- Custo: tokens de entrada e saída por requisito corrigido, por condição. Corrigido é o alvo com menos violações C e P depois do refinamento do que antes e sem nenhuma violação P nova.

Diagnósticos, fora das métricas de resultado:

- Tamanho do contexto do refinamento, por alvo e por condição. A análise separa os alvos gravados no grafo dos recusados na gravação, porque nos recusados a recuperação de B parte só dos chunks da chamada.
- PROMISE: concordância de rótulo entre vizinhos da mesma chamada, contra o valor esperado ao acaso, e número de refinamentos que falharam por condição.

As regras vivem em `code/domain/rules.py`, versão `RULES_VERSION`. A lista legível é gerada em `code/domain/schema/RULES.md`.
