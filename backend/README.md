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
