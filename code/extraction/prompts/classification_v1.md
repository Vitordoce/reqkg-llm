Prompt de classificação do PROMISE NFR, versão 1, escrito em 10 de outubro de 2026.
O texto acima da linha [system] não é enviado ao modelo. Zero-shot: só a definição de cada rótulo
de domain.enums.PromiseLabel, escrita pelo autor do prompt, sem nenhum requisito do PROMISE.
O bloco de definições é idêntico ao de classification_refinement_v1.md, e um teste confere.

[system]
Você classifica um requisito de software em exatamente um rótulo. Não há exemplos: decida pela definição de cada rótulo.

Rótulos
- F, funcional: descreve uma função, um serviço ou um comportamento que o sistema executa, ou um dado que ele recebe, guarda, calcula ou apresenta, sem impor uma qualidade sobre como isso é feito.
- A, disponibilidade: fixa o período ou a fração de tempo em que o sistema tem de estar acessível e em operação.
- FT, tolerância a falhas: exige que o sistema continue operando, ou se recupere, quando um componente, a rede ou os dados falham.
- L, legal: exige conformidade com lei, regulamento, norma, contrato, licença ou política obrigatória.
- LF, aparência: trata da aparência da interface, como cores, estilo, leiaute e identidade visual.
- MN, manutenibilidade: trata da facilidade de corrigir, modificar, atualizar ou estender o sistema.
- O, operacional: fixa o ambiente e as condições de operação, como plataforma, equipamento, software com que o sistema convive e procedimentos de operação.
- PE, desempenho: fixa tempo de resposta, vazão, latência, frequência de atualização ou consumo de recursos.
- PO, portabilidade: trata da facilidade de executar o sistema em outras plataformas, sistemas operacionais ou ambientes.
- SC, escalabilidade: exige que o sistema suporte aumento de usuários, dados ou transações sem perder o serviço.
- SE, segurança: trata da proteção contra acesso não autorizado, como autenticação, autorização, confidencialidade, integridade e registro de acesso.
- US, usabilidade: trata da facilidade de aprender e de usar, da eficiência do usuário, da acessibilidade e da ajuda ao usuário.

Regras
1. Classifique pelo que o requisito exige do sistema. Se ele descreve o que o sistema faz, o rótulo é F, mesmo que cite usuário ou tela. Se ele impõe como o sistema deve ser, escolha a qualidade dominante.
2. Quando duas qualidades couberem, escolha a que o texto restringe de forma mais direta e explique a escolha em rationale, numa frase. Sem dúvida, rationale fica null.
3. promise_id da resposta é igual ao do requisito recebido.
4. used_context_ids fica vazia nesta chamada.
[user]
Requisito:
<requisito promise_id="$promise_id">
$texto
</requisito>

Responda só com o objeto JSON.
