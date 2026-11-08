# Estatísticas do PROMISE NFR processado

Arquivo gerado por `code/benchmarks/promise.py`. Não editar à mão.

Para regenerar, a partir da raiz do repositório:

```
python3 code/benchmarks/promise.py
```

Entrada: `data/raw/promise/nfr.tar`, membro `nfr/nfr.arff`.
SHA-256 da entrada: `28f9328ce72f1c54f09b8dd45573eb811b7a78959b5bf290561cbad1d5adb0b5`.
Saída: `data/processed/promise/promise_nfr.jsonl`.

## Totais

| Medida | Valor |
| --- | ---: |
| Requisitos | 625 |
| Funcionais (F) | 255 |
| Não funcionais | 370 |
| Projetos | 15 |
| Textos repetidos (além da primeira ocorrência) | 2 |

## Distribuição por rótulo

| Rótulo | Nome | Quantidade | Percentual |
| --- | --- | ---: | ---: |
| F | Functional | 255 | 40.80% |
| US | Usability | 67 | 10.72% |
| SE | Security | 66 | 10.56% |
| O | Operational | 62 | 9.92% |
| PE | Performance | 54 | 8.64% |
| LF | Look and feel | 38 | 6.08% |
| A | Availability | 21 | 3.36% |
| SC | Scalability | 21 | 3.36% |
| MN | Maintainability | 17 | 2.72% |
| L | Legal | 13 | 2.08% |
| FT | Fault tolerance | 10 | 1.60% |
| PO | Portability | 1 | 0.16% |

## Contagem por projeto

| ProjectID | Quantidade |
| ---: | ---: |
| 1 | 28 |
| 2 | 40 |
| 3 | 80 |
| 4 | 55 |
| 5 | 73 |
| 6 | 74 |
| 7 | 23 |
| 8 | 93 |
| 9 | 24 |
| 10 | 53 |
| 11 | 13 |
| 12 | 22 |
| 13 | 19 |
| 14 | 16 |
| 15 | 12 |

## Textos repetidos

Cada linha lista registros com o mesmo `text`, no formato `promise_id:rótulo`.

- PROMISE-NFR-0107:F, PROMISE-NFR-0108:F
- PROMISE-NFR-0426:SE, PROMISE-NFR-0460:F

## Notas

- O `text` é o conteúdo entre aspas no ARFF, decodificado de cp1252, sem outra normalização.
  Espaços iniciais e espaços duplos do original foram mantidos.
- `promise_id` segue a ordem das linhas em `@DATA`.
- O PROMISE serve só para avaliar classificação. Não é oráculo de proveniência.
