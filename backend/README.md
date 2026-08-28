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
**runner self-hosted** instalado no próprio servidor. O runner clona o
repositório numa pasta descartável e publica o resultado em `/home/ello/projetos/ellotec2` —
a pasta que fica no ar não é um clone do git.

### O que roda no servidor

| O quê | Como sobe | Porta |
|---|---|---|
| API FastAPI | serviço systemd **`ellotec2-api`** | 8000 |
| Sincronização com o GESTCOM | serviço systemd **`ellotec2-sincronizacao`** | — |
| Front Angular | nginx, site `ellotec2` | 8504 |

Os arquivos dos dois serviços e do site do nginx estão em
[`deploy/`](../deploy/), com o comando de instalação no cabeçalho de cada um.
São instalados **uma única vez**; o deploy depois só faz `systemctl restart`.

### Comandos do dia a dia

```bash
sudo systemctl status ellotec2-api
sudo systemctl restart ellotec2-api
journalctl -u ellotec2-api -f              # log da API ao vivo
journalctl -u ellotec2-sincronizacao -f    # log do integrador ao vivo
```

### O que o deploy NÃO toca

O `rsync` do workflow preserva no servidor quatro coisas que não vêm do git e
não podem ser apagadas: `.env` (credenciais de produção), `.venv/`, `log/` e os
`*_controle.txt` (checkpoints da sincronização — apagá-los faria o integrador
reprocessar o histórico inteiro do ERP).

### Configuração inicial do servidor (uma vez)

1. Criar `/home/ello/projetos/ellotec2/backend/.env` a partir de [`.env.example`](.env.example),
   com `AMBIENTE=producao`, `DEBUG=false`, um `JWT_SEGREDO` forte e
   `CORS_ORIGENS=["http://192.168.20.12:8504"]` — o front roda numa porta
   diferente da API, então é outra origem para o navegador.
2. Instalar os dois serviços, o site do nginx e a regra de sudo do runner
   (comandos no cabeçalho de cada arquivo em `deploy/`). A regra de sudo é
   obrigatória: sem ela o deploy trava esperando uma senha que ninguém digita.
3. Liberar o nginx (que roda como `www-data`) a atravessar a home do `ello`
   até a pasta do front:
   `sudo chmod o+x /home/ello /home/ello/projetos /home/ello/projetos/ellotec2`
4. `sudo systemctl enable --now ellotec2-api ellotec2-sincronizacao`

A API sobe com `--host 0.0.0.0` (nunca `--reload`), por isso responde em
`http://192.168.20.12:8000` e não só em `localhost`. O front não precisa de
configuração de URL: ele monta o endereço da API a partir do host da página
(ver `src/app/environments/environment.ts`), então abrir
`http://192.168.20.12:8504` já faz as chamadas irem para
`http://192.168.20.12:8000`.
