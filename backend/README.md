# ELLOTEC ERP API

Backend em **FastAPI** do ELLOTEC ERP — autenticação com JWT + sessão revogável,
controle de acesso por chave de permissão (`dominio.contexto.acao`) reforçado em
todo endpoint, identificação de dispositivo, e schema MySQL preparado para
sincronização distribuída futura.

> Para entender as decisões de arquitetura e como manter/estender este
> projeto, leia **[ARCHITECTURE.md](./ARCHITECTURE.md)** antes de mexer no
> código.

## Pré-requisitos

- Python 3.12+
- MySQL 8 rodando em `localhost:3306`

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# crie o banco e o usuário de aplicação no MySQL:
mysql -u root -e "
  CREATE DATABASE IF NOT EXISTS ELLOTEC_erp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
  CREATE USER IF NOT EXISTS 'ELLOTEC_erp'@'localhost' IDENTIFIED BY 'sua-senha-aqui';
  GRANT ALL PRIVILEGES ON ELLOTEC_erp.* TO 'ELLOTEC_erp'@'localhost';
"

cp .env.example .env
# edite .env com suas credenciais de banco e um JWT_SEGREDO forte

.venv/bin/alembic upgrade head      # cria todas as tabelas
.venv/bin/python -m scripts.seed    # cria usuário admin + dados de exemplo
```

## Rodando

```bash
.venv/bin/uvicorn app.main:app --reload --port 8000
```
- no windows:
```
uvicorn app.main:app --reload --port 8000
```
- API: http://localhost:8000
- Documentação interativa (Swagger): http://localhost:8000/docs
- Documentação alternativa (ReDoc): http://localhost:8000/redoc

## Sincronização periódica com o sistema de origem (Oracle do ERP)

Com a API já no ar, sobe em processo próprio (separado do `uvicorn`) o loop que
sincroniza funcionários, clientes, marcas, produtos e pedidos do Oracle do ERP
para esta API — a cada 10 segundos, das 07h às 18h:

```bash
python -m app.shared.sistema_origem.app
```

Detalhes (ordem do ciclo, checkpoints, renovação de token em 401) em
[`app/shared/sistema_origem/gestcom/sincronizacao/README.md`](app/shared/sistema_origem/gestcom/sincronizacao/README.md).
Essa integração morava num projeto separado (`ello`) e foi trazida para cá
porque a conexão com o Oracle (`app/shared/sistema_origem/gestcom/conexao.py`) já era
deste backend.

## Inteligência de Mercado: cotações do Bionexo (OuroWeb)

O domínio `app/domains/cotacoes/` lê as cotações que os hospitais publicam no
Bionexo. **Os dados não são nossos e não estão no nosso MySQL**: vêm do
**OuroWeb**, o SQL Server em `192.168.20.14` (banco `Ourobase`), que é a base
de outro sistema.

O acesso é **somente leitura** — nada é gravado lá, nem tabela temporária é
criada. Ver ARCHITECTURE.md → "Domínio de consulta a banco externo" para o
padrão completo e o porquê de cada trava.

### Configuração

As credenciais ficam no `.env`, com prefixo `OUROWEB_SQLSERVER_` (ver
[`.env.example`](.env.example)). O driver é o `pymssql`, já no
`requirements.txt` — ele foi escolhido em vez do `pyodbc` porque não exige
instalar o ODBC Driver da Microsoft no Windows e no servidor Ubuntu; resolve
com um `pip install` nos dois.

Teste a conexão antes de qualquer coisa:

```bash
python -m app.shared.sistema_origem.ouroweb.testar_conexao
```

Ele imprime a versão do SQL Server, o banco default do login e os bancos
visíveis. Se falhar, a mensagem separa os dois casos: não conseguir conectar
(rede, firewall, TCP/IP desabilitado) e conectar mas não conseguir consultar
(permissão).

### Endpoints

| Método | Rota | O que faz |
|---|---|---|
| GET | `/cotacoes` | uma página de itens de cotação, com filtros |
| GET | `/cotacoes/opcoes-filtro` | estados e empresas para os selects da tela |

Ambos exigem `cotacoes.acessar` — a única chave do domínio, porque não há nada
para incluir, editar ou apagar.

Filtros de `/cotacoes`: `dataInicio` e `dataFim` (**obrigatórios**, janela
máxima de 90 dias), `q` (descrição ou código do produto), `hospital`, `cidade`,
`estado`, `empresaId`, `situacao` (`todas` | `respondidas` |
`nao_respondidas`), mais `page`, `perPage` (teto 100), `sort` e `sortType`.

### Três coisas que surpreendem quem lê os dados pela primeira vez

**A mesma cotação aparece repetida.** O Bionexo entrega uma cópia para cada
CNPJ da nossa distribuidora, então o mesmo `int_IdPdc` e o mesmo item vêm uma
vez por empresa. Não é erro de join. A coluna `empresa` distingue, e o filtro
por empresa é o jeito de ver uma linha por item.

**Cidade e estado não existem nas tabelas do Bionexo.** Vêm do cadastro do
hospital (`Tab_Cadastro` → `Cidade`). Cerca de 23% dos cabeçalhos não têm
cadastro com cidade, e essas linhas ficam de fora: sem hospital e cidade a
linha não serve para análise de mercado.

**`precoUnitario` e `quantidadeRespondida` vêm quase sempre nulos.** São o que
*nós* respondemos, não o que o hospital pediu — só estão preenchidos nas
cotações já cotadas. O nulo é justamente o sinal do que ainda falta responder,
e é o filtro `situacao=nao_respondidas` que isola isso.

### O SQL para rodar à mão

[`app/shared/sistema_origem/ouroweb/cotacoes_bionexo.sql`](app/shared/sistema_origem/ouroweb/cotacoes_bionexo.sql)
é a versão legível da consulta, para abrir direto no SQL Server. A versão que a
API usa vive em `cotacao_service.py`, montada em pedaços porque os filtros são
opcionais — e com uma ordem de JOIN diferente, por desempenho (a explicação
está no comentário do arquivo).

## Login de desenvolvimento (criado pelo seed)

- **Admin (acesso total):** `admin` / `123456`

Todo `POST /auth/login` exige o header `X-Device-Id` (um UUID estável gerado
pelo cliente). Sem ele, a API responde 400.

## Migrações (Alembic)

```bash
# depois de alterar um model:
.venv/bin/alembic revision --autogenerate -m "descrição da mudança"
.venv/bin/alembic upgrade head
```

## Stack

FastAPI · SQLAlchemy 2 · Alembic · MySQL (PyMySQL) · Pydantic v2 · python-jose (JWT) · passlib/bcrypt

## Deploy em produção (192.168.20.12)

O deploy é automático: todo push na branch `main` dispara
[`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml), que roda num
**runner self-hosted** instalado no próprio servidor Ubuntu.

O ponto que mais confunde quem chega agora: existem **duas** cópias do projeto
no servidor, e elas têm papéis diferentes.

| Pasta | O que é |
|---|---|
| `/home/ello/actions-runner/ellotec2/_work/ellotec2/ellotec2` | clone completo que o runner faz a cada job — é onde o build acontece, e é descartável |
| `/home/ello/projetos/ellotec2` | o que está no ar: recebe só `backend/` e `front/` via `rsync`. **Não é um repositório git** e não deve ser conectado ao GitHub |

### O que roda no servidor

| O quê | Como sobe | Porta |
|---|---|---|
| API FastAPI | serviço systemd **`ellotec2-api`** | 8000 |
| Sincronização com o GESTCOM | serviço systemd **`ellotec2-sincronizacao`** | — |
| Front Angular | nginx, site `ellotec2` | 8504 |

Os arquivos dos dois serviços, do site do nginx e da regra de sudo estão em
[`deploy/`](../deploy/). São instalados **uma única vez**; o deploy depois só
faz `systemctl restart`. Se algum deles mudar no git, é preciso repetir o `cp`
para `/etc` e o `daemon-reload` à mão — o deploy não mexe em `/etc` de
propósito, porque isso quebraria o servidor sem ninguém perceber.

---

## Montando o servidor do zero (ordem cronológica)

Tudo abaixo roda **no servidor**, como o usuário `ello`. Foi assim que o
ambiente atual foi montado; seguindo na ordem, uma máquina Ubuntu limpa chega
no mesmo estado.

### 1. Pacotes do sistema

O Ubuntu Server não traz nada disso por padrão, e cada um que falta derruba o
deploy num passo diferente:

```bash
sudo apt update
sudo apt install -y rsync nginx python3-venv build-essential curl mysql-server
```

- **rsync** — é ele que copia o build para a pasta de produção
- **nginx** — serve o front na 8504
- **python3-venv** — sem ele o passo que cria a `.venv` falha
- **build-essential** — necessário se algum pacote do `requirements.txt` precisar compilar
- **mysql-server** — o banco da aplicação (pule se o MySQL já existir na rede)

O **Node** não vem do `apt` do Ubuntu numa versão nova o bastante para o
Angular 20. Use o repositório oficial do Node:

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
node -v   # precisa ser 20 ou maior
```

### 2. Banco de dados

```bash
sudo mysql -e "
  CREATE DATABASE IF NOT EXISTS ELLOTEC_erp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
  CREATE USER IF NOT EXISTS 'ELLOTEC_erp'@'localhost' IDENTIFIED BY 'sua-senha-aqui';
  GRANT ALL PRIVILEGES ON ELLOTEC_erp.* TO 'ELLOTEC_erp'@'localhost';
"
```

### 3. Runner do GitHub Actions

Cada repositório precisa do **seu próprio** runner, numa pasta própria — dois
runners não dividem a mesma pasta de instalação.

```bash
mkdir -p ~/actions-runner/ellotec2 && cd ~/actions-runner/ellotec2
curl -o actions-runner-linux-x64-2.336.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.336.0/actions-runner-linux-x64-2.336.0.tar.gz
tar xzf ./actions-runner-linux-x64-2.336.0.tar.gz
./config.sh --url https://github.com/DeyversonCaiado/ellotec2 --token TOKEN
```

O `TOKEN` sai de **Settings → Actions → Runners → New self-hosted runner** no
GitHub. Ele vale cerca de uma hora e é consumido no primeiro uso — token velho
ou já usado responde `404 Not Found`.

Instale como serviço. Rodar `./run.sh` só funciona enquanto o terminal estiver
aberto; fechando o terminal, o runner morre e os jobs ficam presos na fila:

```bash
sudo ./svc.sh install
sudo ./svc.sh start
sudo systemctl status actions.runner.*
```

Se instalar o Node (ou qualquer coisa nova no `PATH`) **depois** do runner,
reinicie-o — o serviço guarda o `PATH` de quando subiu:

```bash
cd ~/actions-runner/ellotec2 && sudo ./svc.sh stop && sudo ./svc.sh start
```

### 4. Pasta de produção e o `.env`

Só o `.env` é criado à mão. O resto (`front/`, `.venv/`, `log/`) o próprio
deploy cria na primeira execução.

```bash
mkdir -p /home/ello/projetos/ellotec2/backend
```

Copie [`.env.example`](.env.example) para
`/home/ello/projetos/ellotec2/backend/.env` e ajuste:

- `AMBIENTE=producao` e `DEBUG=false`
- `JWT_SEGREDO` — uma chave aleatória forte, nunca a do exemplo
- credenciais do MySQL criadas no passo 2
- `CORS_ORIGENS=["http://192.168.20.12:8504"]` — o front roda numa porta
  diferente da API, então é **outra origem** para o navegador. Sem isso o login
  responde "e-mail ou senha inválidos", porque a tela trata falha de rede igual
  a credencial errada
- `ELLOTEC_ORACLE_CLIENT_DIR` — **deixe vazio**. O caminho do Instant Client é
  descoberto pelo sistema operacional onde o processo roda: `/opt/oracle/
  instantclient_12_2` no Linux, `C:\oracle\instantclient_19_28` no Windows
  (ver `diretorio_padrao_do_client` em `app/shared/sistema_origem/gestcom/
  config.py`). Preencha só se o Instant Client estiver fora do lugar de sempre.

  Se o `.env` de produção ainda tiver o caminho Windows de uma cópia antiga,
  **apague o valor**: o `.env` vence a detecção quando preenchido, e um caminho
  Windows no Linux derruba a sincronização com `DPI-1047: Cannot locate a
  64-bit Oracle Client library`

O `.env` é lido a partir do diretório onde o processo roda, não da pasta do
código — é por isso que os dois serviços definem
`WorkingDirectory=/home/ello/projetos/ellotec2/backend`. Sem essa linha a API
sobe normalmente, mas com os valores default do `settings.py`, apontando para o
banco errado. Variável de ambiente, quando existe, tem prioridade sobre o `.env`.

### 5. Serviços, nginx e a regra de sudo

Os arquivos estão no clone do runner (a pasta `deploy/` não é copiada para a
pasta de produção):

```bash
cd /home/ello/actions-runner/ellotec2/_work/ellotec2/ellotec2
```

Os dois serviços systemd:

```bash
sudo cp deploy/ellotec2-api.service deploy/ellotec2-sincronizacao.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ellotec2-api ellotec2-sincronizacao
```

A regra de sudo sem senha do runner. **É obrigatória**: sem ela o deploy trava
no `systemctl restart` esperando uma senha que ninguém vai digitar. O
`visudo -c` valida a sintaxe — um erro aqui pode travar o `sudo` da máquina
inteira:

```bash
sudo cp deploy/ellotec2-runner-sudoers /etc/sudoers.d/ellotec2-deploy
sudo chmod 0440 /etc/sudoers.d/ellotec2-deploy
sudo visudo -c
```

O site do nginx. O `chmod o+x` libera o `www-data` a atravessar a home do
`ello` até a pasta do front — sem ele o nginx devolve 403 mesmo com os arquivos
no lugar certo:

```bash
sudo cp deploy/ellotec2-front.nginx.conf /etc/nginx/sites-available/ellotec2
sudo ln -sf /etc/nginx/sites-available/ellotec2 /etc/nginx/sites-enabled/
sudo chmod o+x /home/ello /home/ello/projetos /home/ello/projetos/ellotec2
sudo nginx -t && sudo systemctl reload nginx
```

### 6. Rodar o deploy

Push na `main`, ou **Actions → Deploy producao → Run workflow**. O workflow, em
ordem: `npm ci` → build de produção → `rsync` do front → `rsync` do backend →
`pip install -r requirements.txt` → `alembic upgrade head` → restart dos dois
serviços → `curl` no `/docs` para confirmar que a API subiu.

Conferindo:

```bash
curl -I http://192.168.20.12:8504/        # front — espera 200 OK
curl -I http://192.168.20.12:8000/docs    # API   — espera 200 OK
```

---

### O que o deploy NÃO toca

O `rsync` preserva no servidor quatro coisas que não vêm do git e não podem ser
apagadas: `.env` (credenciais de produção), `.venv/`, `log/` e os
`*_controle.txt` (checkpoints da sincronização — apagá-los faria o integrador
reprocessar o histórico inteiro do ERP).

### Comandos do dia a dia

```bash
sudo systemctl status ellotec2-api
sudo systemctl restart ellotec2-api
journalctl -u ellotec2-api -f              # log da API ao vivo
journalctl -u ellotec2-sincronizacao -f    # log do integrador ao vivo
sudo systemctl status actions.runner.*     # o runner está escutando?
```

### Quando algo dá errado

| Sintoma | Causa |
|---|---|
| Job fica **na fila** para sempre | o runner não está rodando como serviço (`sudo ./svc.sh install && sudo ./svc.sh start`) |
| `npm: command not found` | Node não instalado, ou instalado depois do runner subir — reinicie o runner |
| `rsync: command not found` | falta `sudo apt install rsync` |
| `sudo: a password is required` | a regra em `/etc/sudoers.d/ellotec2-deploy` não foi instalada, ou está com permissão diferente de `0440` (o sudo ignora o arquivo em silêncio) |
| Serviço falha com **`203/EXEC`** | o caminho do `ExecStart` não existe no servidor — confira `/etc/systemd/system/ellotec2-api.service` |
| Front não conecta na 8504 | nginx não instalado, ou o site não foi habilitado em `sites-enabled/` |
| Front dá **403** | falta o `chmod o+x` na home do `ello` |
| Login diz "e-mail ou senha inválidos" com senha certa | `CORS_ORIGENS` sem `http://192.168.20.12:8504` |

### Sobre as URLs

A API sobe com `--host 0.0.0.0` (nunca `--reload`), por isso responde em
`http://192.168.20.12:8000` e não só em `localhost`. O front não precisa de
configuração de URL: ele monta o endereço da API a partir do host da página
(ver `src/app/environments/environment.ts`), então abrir
`http://192.168.20.12:8504` já faz as chamadas irem para
`http://192.168.20.12:8000` — a mesma build funciona no PC, no coletor e em
produção.
