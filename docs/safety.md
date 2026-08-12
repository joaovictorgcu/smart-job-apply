# Segurança, risco e ética

Leia isto antes de rodar a ferramenta, não depois. É a versão honesta.

## O conflito central

O Contrato de Usuário do LinkedIn proíbe acessar o serviço por meios automatizados — scrapers, bots e
automação de navegador estão todos citados. Este projeto automatiza a interface web do LinkedIn. Não existe leitura
do Contrato sob a qual isso seja permitido.

O LinkedIn não oferece uma API pública para buscar vagas ou enviar candidaturas. Não há caminho em conformidade
para o mesmo resultado. É *por isso* que este projeto dirige um navegador, e não é uma justificativa —
é o motivo de o risco existir e não poder ser eliminado por engenharia.

**O que isso significa para você concretamente:** o LinkedIn pode restringir a sua conta, exigir verificação
de identidade ou bani-la permanentemente, a critério dele, sem recurso a que você tenha direito. A sua rede
profissional, o seu histórico de mensagens, o seu histórico de candidaturas e o seu perfil estão todos nessa
conta. Pese isso contra o tempo que esta ferramenta economiza. Para algumas pessoas essa troca claramente não vale
a pena, e a resposta certa é fechar este repositório e se candidatar à mão.

## O que as salvaguardas fazem

| Salvaguarda | Contra o que ela realmente protege |
|---|---|
| Atrasos de ação aleatórios (2,5–7 s) | Cliques cronometrados por máquina disparando um atrás do outro, martelando o serviço sem espaço para você intervir |
| Atrasos de candidatura aleatórios (45–120 s) | Rajadas de candidaturas em poucos segundos |
| Limite diário (15, máximo rígido 50) | Volume que nenhuma busca humana de emprego produz |
| Janela de horário (08:00–20:00) | Atividade às 4 da manhã todo dia |
| Uma única sessão de navegador | Sessões paralelas de uma mesma conta |
| Limite de resultados por execução (`max_results`, ≤ 100) | Longas varreduras de coleta por dezenas de páginas de resultados |
| Navegador visível (não headless) | Falha silenciosa — você vê o que está acontecendo e assume o controle |
| Aprovação humana antes de cada envio | Enviar candidaturas que você não leu |

Juntas, elas mantêm a ferramenta operando de forma conservadora — volume modesto, ritmo sem pressa, uma sessão por
vez e um humano aprovando cada envio em vez de um script rodando sozinho. Isso é uma redução significativa
de risco, e é também simplesmente a forma responsável de dirigir o serviço de outra pessoa.

## O que as salvaguardas não fazem

Elas não tornam a automação aceitável para o LinkedIn, e não conseguem esconder que é automação — seria
desonesto sugerir o contrário.

- **O fingerprinting de navegador ainda se aplica.** O Chromium dirigido pelo Playwright é distinguível de um
  navegador dirigido à mão por flags de automação, características de renderização e temporização, e telemetria
  comportamental. Este projeto não faz nenhuma tentativa de derrotar o fingerprinting.
- **O comportamento no agregado ainda é incomum.** Mesmo num ritmo humano, uma sessão que visita páginas de vaga e
  abre modais de Candidatura Simplificada numa sequência consistente, dia após dia, tem um formato.
- **Sinais do lado do servidor são invisíveis para nós.** Os sistemas anti-automação do LinkedIn não são documentados e
  mudam sem aviso. Nada aqui pode ser ajustado contra eles.
- **O risco não é proporcional só ao volume.** Uma única sessão azarada pode disparar uma verificação. Uma configuração
  cautelosa reduz as chances; ela não cria um limiar seguro.
- **Nenhuma salvaguarda protege você de uma candidatura ruim.** Atrasos e limites governam ritmo e volume, não
  correção. Se a carta de apresentação é precisa e as respostas de triagem são verdadeiras depende inteiramente da
  etapa de revisão humana.

**Não afrouxe as salvaguardas para ir mais rápido.** Cada botão em
[configuration.md](configuration.md#guard-rails) diz o que você está trocando. Os padrões são conservadores
de propósito.

## O invariante da aprovação humana

Esta é a única propriedade que o projeto trata como inegociável: **nada envia uma candidatura do LinkedIn
sem uma ação explícita, separada e confirmada pelo usuário.**

Ela é imposta estruturalmente, e não por uma configuração, em quatro lugares independentes:

1. **O contrato do serviço.** `LinkedInService.fill_and_advance()` é especificado para avançar o formulário de
   Candidatura Simplificada e parar na etapa de revisão. Ele não tem caminho de código para o envio. `submit()` é um método separado.
2. **O formato da API.** Preparar candidaturas (`POST /api/automation/prepare`) e enviar uma
   (`POST /api/applications/{id}/submit`) são endpoints diferentes. Preparar exige `confirmed: true` e
   age sobre um lote; enviar exige `confirm: true` e age sobre exatamente uma candidatura, por id. Não há
   endpoint de envio em massa.
3. **A máquina de estados.** Uma candidatura preparada fica em `awaiting_review`. Nada a tira desse
   estado automaticamente.
4. **Os padrões.** `ASSISTED_MODE_ONLY=true`, `require_manual_approval=true`, `dry_run=true`.

Um modo totalmente automático não é um recurso inacabado. É uma recusa deliberada, e um pull request que
enfraqueça qualquer um dos quatro pontos acima não será aceito — veja [CONTRIBUTING.md](../CONTRIBUTING.md).

### Modo de teste (dry run)

`dry_run` tem padrão `true`. Nesse estado o engine faz tudo, exceto o clique final: ele busca,
pontua, abre o formulário, preenche os campos, anexa o currículo e para na revisão. Candidaturas criadas
durante um dry run são marcadas com `was_dry_run = true`, para que o seu histórico distinga ensaios de envios
reais.

Rode em modo de teste até ter acompanhado o fluxo inteiro pelo menos uma vez e lido algumas candidaturas
geradas de ponta a ponta. Depois desligue deliberadamente.

## Verificações de segurança

Se um CAPTCHA, uma tela de "verificação de segurança", um aviso de "atividade incomum" ou qualquer desafio
equivalente aparecer, a automação levanta `SecurityCheckpointError` e para.

O que acontece nesse caminho:

1. O status da execução vira `BLOCKED` e `blocked_reason` é registrado.
2. Um evento `automation.blocked` é publicado no painel.
3. Sem repetição. Sem seletor alternativo. Sem tentativa de ler, adivinhar ou contornar o desafio.

**Resolva você mesmo, na janela do navegador, como você mesmo.** Depois decida se continua. Se as verificações
aparecerem repetidamente, é o LinkedIn dizendo que a atividade parece automatizada — pare de usar a ferramenta nessa
conta em vez de ajustar atrasos até os avisos sumirem.

Não há opção de configuração para contornar uma verificação, e adicionar uma está fora de escopo para este projeto.

## Senhas e dados de sessão

**O projeto nunca pede, recebe ou armazena a sua senha do LinkedIn.** Não há campo para ela no
schema, nem parâmetro para ela na API, nem prompt para ela na UI.

O fluxo é: a automação abre uma janela visível do Chromium, você faz login à mão exatamente como faria
normalmente — incluindo a autenticação de dois fatores — e apenas o estado de sessão resultante é persistido.

Esse estado é criptografado em repouso com Fernet (AES-128-CBC + HMAC), usando uma chave derivada via HKDF-SHA256 de
`ENCRYPTION_KEY` (recorrendo a `SECRET_KEY`). `LinkedInAccountRead`, o único schema que expõe a
conta pela API, carrega um nome de exibição, uma flag de conectado e um timestamp — nenhum cookie jamais sai
por um endpoint.

Mudar `ENCRYPTION_KEY` torna as sessões armazenadas ilegíveis. Isso é recuperável: reconecte o LinkedIn e faça
login de novo.

## O que é armazenado, e onde

| Dado | Local | Sensibilidade |
|---|---|---|
| A senha da sua conta do app | `users.hashed_password` | hash bcrypt, não reversível |
| Cookies de sessão do LinkedIn | `linkedin_accounts.encrypted_storage_state` | **Credenciais vivas.** Criptografadas em repouso; quem tiver esta linha e a sua `ENCRYPTION_KEY` pode agir como você no LinkedIn |
| A própria chave de criptografia (Docker) | `backend/data/.secrets.env`, modo `600` | **A chave da linha acima.** Gerada no primeiro boot e mantida no volume de dados para que reinícios não invalidem a sua sessão — o que também significa que uma cópia desse volume contém tanto a fechadura quanto a chave |
| Diretório de perfil do navegador | `backend/data/browser_profiles/` | Pode conter mais artefatos de sessão escritos pelo Chromium |
| O seu currículo, como enviado | `backend/data/resumes/` | Dados pessoais — nome, endereço, telefone, histórico de trabalho |
| O seu currículo, como texto | `profiles.resume_text` | O mesmo, no banco de dados |
| Banco de respostas | `profiles.answer_bank` | Pretensões salariais, aviso prévio, autorização de trabalho |
| Descrições de vagas e notas | `jobs` | Baixa |
| Cartas e respostas geradas | `applications` | Pessoal, e enviado a empregadores uma vez aprovado |
| Registros de chamadas de IA | `ai_analyses` | Saída bruta do modelo, contagens de tokens, custo |
| Trilha de auditoria | `application_events` | O que foi enviado em seu nome, e quando |
| Capturas de tela | `backend/data/` | Podem conter os dados que você preencheu no formulário |

Tudo acima vive na sua própria máquina ou servidor. Nada é enviado a um serviço que o projeto opera —
não existe tal serviço.

Duas partes externas de fato recebem dados, e você deve saber exatamente o quê:

- **A Anthropic** recebe a descrição da vaga mais as partes do seu perfil necessárias para pontuá-la e redigir
  a carta, sempre que os recursos de IA são usados. Deixe `ANTHROPIC_API_KEY` sem definir e nenhum dado é enviado;
  você preenche os formulários você mesmo.
- **O LinkedIn** recebe as suas candidaturas — que é o objetivo.

### `backend/data/` está no gitignore por um motivo

Esse diretório guarda cookies de sessão vivos, o seu currículo e o seu banco de respostas. Ele está no
[`.gitignore`](../.gitignore) e deve continuar lá. Antes de enviar este repositório para qualquer lugar público, verifique:

```bash
git check-ignore -v backend/data/app.db   # deve imprimir a regra que o ignora
git ls-files backend/data                 # não deve imprimir nada
```

O mesmo vale para o `.env`, que guarda a sua chave de API e a sua chave de criptografia.

Quando você fizer backup do diretório — e você deve, já que é a única cópia do seu histórico de busca de emprego —
guarde-o em algum lugar onde você se sentiria confortável armazenando o seu currículo e um conjunto de credenciais vivas.

## Ética

O risco técnico é seu para aceitar. Estes pontos são sobre outras pessoas.

**Use apenas na sua própria conta.** Não na de um cliente, não na de um amigo, não numa compartilhada. A pessoa cuja
conta está em risco deve ser a pessoa que escolheu correr o risco.

**Não faça spam com empregadores.** Do outro lado de cada candidatura há um humano que a lê. O limite diário e
o limiar de nota existem tanto pelo bem deles quanto pelo seu: quinze candidaturas ponderadas a vagas que você
plausivelmente combina são uma busca de emprego, e duzentas atiradas ao acaso são um ataque de negação de serviço à
caixa de entrada de alguém. Aumentar o limite e baixar o limiar ao mesmo tempo é exatamente a direção errada.

**Revise cada candidatura antes de ela sair.** Este é o núcleo ético do modo assistido, não apenas um
recurso de segurança. A carta sai em seu nome e as respostas de triagem são declarações sobre
você. Uma resposta gerada por IA que está errada é a *sua* declaração falsa a um empregador uma vez que você a aprova. Leia
a carta. Confira cada resposta, e confira as de baixa confiança duas vezes —
[`ScreeningAnswer`](../backend/app/ai/schemas.py) as sinaliza com `needs_review` justamente para que a UI possa
colocá-las na sua frente.

**Nunca exagere a sua experiência.** Se a IA redigir "8 anos de Python" e você tem quatro, corrija antes de
aprovar. A ferramenta facilita enviar muitas candidaturas rapidamente; isso facilita enviar uma pequena
mentira muitas vezes.

**A IA às vezes vai recusar.** Recusas são registradas (`AIAnalysis.was_refusal`) e a candidatura
recorre ao preenchimento manual. Isso é o sistema funcionando: preencha o campo você mesmo.

## Se a sua conta for restringida

Nada neste projeto pode recorrer de uma restrição por você, e nem o autor pode. Siga o processo de
recuperação do próprio LinkedIn, como você mesmo. Depois reconsidere se vale continuar usando automação de navegador na conta —
uma segunda restrição na mesma conta é geralmente pior que a primeira.

## Resumo

- Automatizar o LinkedIn viola o Contrato de Usuário dele e pode custar a sua conta, permanentemente.
- Não há API oficial para se candidatar a vagas, e é por isso que isto existe e por que o risco não pode ser
  removido.
- As salvaguardas reduzem as chances. Elas não deixam você seguro, e afrouxá-las eleva as chances bruscamente.
- O envio sempre exige uma confirmação humana separada, por design e em quatro lugares independentes.
- Desafios de segurança param tudo. Resolva-os você mesmo; nunca os contorne.
- A sua senha do LinkedIn nunca é armazenada. Os cookies de sessão são, criptografados.
- `backend/data/` e `.env` guardam credenciais vivas e dados pessoais. Mantenha-os fora do git e faça backup deles
  com cuidado.
- Use na sua própria conta, num volume humano, e leia cada candidatura antes de aprovar.
