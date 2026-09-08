# Deploy num servidor

Rodar isto num servidor muda duas coisas em relação ao seu laptop, e as duas
importam mais que o resto do procedimento.

**A porta 6080 é uma sessão do seu LinkedIn.** É uma ponte noVNC para o Chromium
que a automação dirige, e `docker/supervisord.conf` roda `x11vnc` com `-nopw`.
Isso é seguro enquanto a porta VNC crua não sai do contêiner. Deixa de ser no
instante em que a ponte fica alcançável pela internet: quem achar a porta recebe
uma sessão interativa já autenticada — sem senha, sem TLS, sem registro. Por
isso `docker-compose.prod.yml` só publica em `127.0.0.1` e o acesso é pelo
tailnet. O guard G8 (`python tools/guards.py`) falha o build se alguém afrouxar
isso.

**IP de datacenter é detectado mais rápido.** Automatizar o LinkedIn viola os
Termos de Uso dele — ver [safety.md](safety.md) — e as faixas de nuvem são
conhecidas. Restrição ou banimento da conta é desfecho realista, e um deploy
rodando sem ninguém olhando aumenta a chance, não diminui. As salvaguardas de
ritmo reduzem risco; não o eliminam.

---

## 1. Servidor

Chromium é a parte pesada; a API e as chamadas de IA não são. Com um provider
hospedado (Groq, Gemini) nenhum modelo roda aqui.

- 2 vCPU, 4 GB RAM, 20 GB disco. Menos que isso e o renderizador do Chromium
  morre sem erro útil.
- Debian 12 ou Ubuntu 22.04+, com Docker e o plugin Compose.
- Se quiser `AI_PROVIDER=ollama`, precisa de bem mais: `qwen2.5:7b` pede ~6 GB
  só para o modelo. Num servidor pequeno, use um provider hospedado.

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER" && newgrp docker
```

## 2. Tailscale

É o que substitui proxy reverso, senha e certificado. `tailscale serve` publica
os dois serviços só para o seu tailnet, com TLS, e nada para rotacionar.

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale status                  # anote o nome desta máquina
```

Guarde o nome completo — algo como `sja.tailnet-1234.ts.net`. Ele vai no `.env`
como `TAILNET_HOST`, porque o navegador só consegue falar com a API se aquela
origem estiver liberada no CORS.

## 3. Configuração

```bash
git clone https://github.com/joaovictorgcu/smart-job-apply.git
cd smart-job-apply
cp .env.example .env
```

O mínimo no `.env`:

```dotenv
# Provider de IA. Chave grátis em https://console.groq.com/keys
AI_PROVIDER=groq
AI_API_KEY=gsk_...

# O nome desta máquina no tailnet, do passo anterior.
TAILNET_HOST=sja.tailnet-1234.ts.net

# Gere dois valores DISTINTOS:
#   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
# Trocar ENCRYPTION_KEY depois torna a sessão salva do LinkedIn ilegível.
SECRET_KEY=
ENCRYPTION_KEY=
```

Seu currículo e suas respostas de triagem trafegam para o provider escolhido.
São dados pessoais; leia os termos dele, inclusive sobre uso em treinamento. Se
isso não servir, `AI_PROVIDER=ollama` mantém tudo na máquina ao custo de RAM.

### Ritmo — o que mais reduz risco de banimento

Os atrasos são aleatórios por construção (`app/automation/throttle.py`): cada
pausa é um `random.uniform` na faixa, nunca um valor fixo, porque intervalo
constante é ele mesmo uma assinatura. Há três camadas:

| Variável | Padrão | O que espaça |
|---|---|---|
| `DEFAULT_ACTION_DELAY_RANGE` | `2.5,7.0` | duas interações na mesma página |
| `DEFAULT_APPLY_DELAY_RANGE` | `45.0,120.0` | duas candidaturas — preparo e envio |
| `DEFAULT_WORKING_HOURS` | `8,20` | janela do dia em que uma execução roda |
| `DEFAULT_DAILY_CAP` | `15` | teto de envios por dia |

Além disso, `human_pause` move o mouse e rola a página em intervalos
aleatórios entre ações significativas.

Duas armadilhas reais:

1. **Os `DEFAULT_*` só semeiam contas novas.** Uma conta que já existe guarda os
   próprios valores em `UserSettings`. Se você reaproveitar um banco de demo, os
   atrasos dela estão em zero — `scripts/demo_server.py` e `scripts/seed_mock.py`
   zeram de propósito, porque contra o portal falso não há ninguém para poupar.
   O `Throttle` aplica um piso quando `DEMO_PORTAL=false`, então zero nunca
   alcança o site real; mesmo assim, confira os valores da conta em
   Configurações. O piso é uma rede de proteção, não a recomendação — os padrões
   acima são vários múltiplos dele.
2. **Aumentar é mais seguro que diminuir.** Se você não tem pressa, `5,15` e
   `120,400` reduzem bem mais o perfil de tráfego.

## 4. Subir

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f
```

Use **só** esse arquivo. Não combine com `docker-compose.yml`: o Compose
*mescla* listas de `ports` em vez de substituir, então as ligações públicas do
arquivo base sobreviveriam ao lado das de loopback e o isolamento iria embora
sem aviso.

Depois publique os dois serviços no tailnet:

```bash
sudo tailscale serve --bg --https 443 http://127.0.0.1:8000
sudo tailscale serve --bg --https 6080 http://127.0.0.1:6080
tailscale serve status
```

Confira que nada escapou:

```bash
sudo ss -ltnp | grep -E '8000|6080'     # esperado: só 127.0.0.1
```

## 5. Conta e login no LinkedIn

```bash
docker compose -f docker-compose.prod.yml exec app \
    python scripts/create_user.py --email voce@exemplo.com --name "Seu Nome"
```

De qualquer dispositivo no seu tailnet:

1. Abra `https://<TAILNET_HOST>` e entre na conta que acabou de criar.
2. Em **Configurações**, confirme que **modo de teste está ligado** e reveja os
   atrasos, o teto diário e a janela de horário.
3. No painel, **Iniciar a sessão do navegador**.
4. Abra `https://<TAILNET_HOST>:6080`. Você está vendo o Chromium real. Faça o
   login no LinkedIn **ali, à mão**, inclusive 2FA. O app nunca pede nem guarda
   sua senha do LinkedIn — só os cookies de sessão, criptografados com
   `ENCRYPTION_KEY`.
5. Deixe essa aba disponível: se o LinkedIn pedir verificação durante uma
   execução, é ali que você resolve. A automação para e espera; ela nunca tenta
   contornar um desafio.

## 6. Primeira execução

Com o modo de teste ligado, rode uma busca e prepare uma candidatura. Você vê o
fluxo inteiro — busca, pontuação, formulário — sem que nada seja enviado.
Quando estiver convencido, desligue o modo de teste em Configurações e aprove
**uma** candidatura, olhando a janela do navegador enquanto acontece.

`require_manual_approval` fica ligado. Nada é enviado sem uma segunda
confirmação explícita sua, e `ASSISTED_MODE_ONLY=true` é a garantia rígida
disso — ver [safety.md](safety.md).

## 7. Operação

**Backup.** Todo o estado está num volume: banco, sessão criptografada do
LinkedIn, currículos, capturas.

```bash
docker run --rm -v smart-job-apply-data:/data -v "$PWD":/backup alpine \
    tar czf /backup/sja-$(date +%F).tar.gz -C /data .
```

**Atualizar.**

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

**O que acompanhar.** Uma execução com `status=blocked` e `blocked_reason`
significa que o LinkedIn mostrou uma verificação — resolva no noVNC antes de
rodar de novo. Repetição disso é o sinal de que a conta está sob atenção; a
resposta certa é parar, não insistir. O botão **Parar** no topo é o kill switch
e faz o engine se retirar no próximo passo.

**Sair.**

```bash
docker compose -f docker-compose.prod.yml down          # mantém o volume
sudo tailscale serve reset
```
