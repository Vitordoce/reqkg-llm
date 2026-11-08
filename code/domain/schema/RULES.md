# Regras do ReqKG

Arquivo gerado por `code/domain/export_schema.py`. Versão das regras: `3`.

| Regra | Família | O que conta |
| --- | --- | --- |
| C1 | completeness | Requisito sem prioridade MoSCoW. |
| C2 | completeness | Requisito sem método de verificação. |
| C3 | completeness | Requisito sem tipo (funcional, não funcional ou restrição). |
| C4 | completeness | Requisito não funcional sem atributo de qualidade ISO/IEC 25010. |
| P1 | provenance | Requisito sem nenhuma evidência (fonte e chunk). |
| P2 | provenance | Evidência cita fonte ou chunk que não existe no corpus, ou chunk de outra fonte. |
| P3 | provenance | Citação da evidência não aparece no texto do chunk citado. |
| P4 | provenance | Requisito ou relação marcado como fato extraído com evidência sem citação. |
| P5 | provenance | Relação sem evidência. |
| K1 | consistency | O mesmo par de requisitos aparece como conflicts_with e duplicates. |
| K2 | consistency | Relação de um elemento com ele mesmo. |
| K3 | consistency | Ciclo em depends_on. Uma violação por componente fortemente conexo. |
| K4 | consistency | Ciclo em refines. Uma violação por componente fortemente conexo. |
| K5 | consistency | Requisito Must depende de requisito Won't. |

## Escolha dos candidatos refinados

As duas condições refinam os mesmos candidatos: os que têm violação C1, C2, C3, C4, P1, P2, P3, P4, alguma marca de revisão, ou confiança abaixo de `review.confidence_threshold`. A escolha sai da extração compartilhada, antes de qualquer contexto.

## Refinamento recusado

Com qualquer violação G, o sistema recusa o refinamento e mantém o candidato original.

| Regra | O que conta |
| --- | --- |
| G1 | A resposta revisada aponta para outro item que não o alvo do refinamento. |
| G2 | used_context_ids cita item que não estava no contexto recuperado. |
| G3 | A evidência revisada cita chunk que não estava no contexto nem no candidato original. |
| G4 | Tipo, prioridade, método de verificação ou evidência existiam e foram perdidos. |
| G5 | O item do PROMISE avaliado aparece no próprio contexto de classificação, pelo promise_id ou por um texto idêntico depois de domain.rules.normalize_text. |
| G6 | Evidência nova (ausente do candidato original) não passa em CorpusIndex.supports no corpus do caso (chunk de outro documento ou citação que não aparece no chunk), ou prioridade ou método de verificação nulos no original foram preenchidos sem nenhuma evidência nova que passe. |

## Recusa na gravação do grafo

Recusas não mudam as métricas, que leem a resposta do modelo. Elas são reportadas à parte.

| Regra | O que conta |
| --- | --- |
| W1 | Item sem nenhuma evidência que resolve no corpus com citação presente no chunk. |
| W2 | Relação com uma ponta que não foi gravada. |
| W3 | Relação sem evidência que resolve no corpus. |
| W4 | Ator com o mesmo nome e tipo diferente de um ator já gravado. Vale o primeiro. |
| W5 | Relação que liga um nó a ele mesmo depois da resolução de identificadores. |
| W6 | Requisito com o mesmo identificador de outro já gravado. Vale o primeiro. |
