# Sincronização com o sistema de origem (ERP Oracle)

Scripts responsáveis por sincronizar os cadastros do ERP (Oracle) com o
próprio banco do ELLOTEC2, falando com a API local (`http://localhost:8000`)
exatamente como um integrador externo — com login e token, via HTTP.

Migrados de `C:\projetos\ello\ellotec\cadastros\` para dentro do backend
porque a responsabilidade é do domínio `sistema_origem`: a conexão Oracle
(`app/shared/sistema_origem/conexao.py`) já morava aqui.

## Ciclo de sincronização

`app/shared/sistema_origem/app.py` roda em loop, entre 07h e 18h, sempre
nesta ordem (cada uma depende da anterior já ter sido enviada):

1. `funcionarios.sincronizar_funcionarios()`
2. `clientes.sincronizar_clientes()`
3. `marcas.sincronizar_marcas()`
4. `produtos.sincronizar_produtos()`
5. `pedidos.sincronizar_pedidos()`

Falha definitiva num registro (rejeição real da API, não um 409 normal)
propaga como `RuntimeError` e derruba o processo — dado de origem precisa
ser corrigido antes de reiniciar.

`estoque_saldos.py`, `estoque_lotes.py`, `endereco_lotes.py` e
`enderecos.py` existem e estão prontos, mas **não fazem parte do ciclo
automático** hoje (não eram chamados pelo `app.py` original tampouco) — rode
manualmente quando precisar.

## Como rodar

A partir de `C:\projetos\ellotec2\backend` (para que o pacote `app` resolva):

```bash
python -m app.shared.sistema_origem.app
```

Isso sobe o loop completo. Para rodar uma sincronização isolada uma única
vez:

```bash
python -m app.shared.sistema_origem.cadastros.funcionarios
```

## Arquivos gerados

- `log/<nome>.log` (relativo ao diretório de onde o processo foi iniciado):
  log diário da execução (rotacionado à meia-noite, mantém 7 dias).
- `<nome>_controle.txt` neste diretório: guarda a última `DATA_HORA_ALTERACAO`
  processada de cada cadastro, para que a próxima execução envie apenas os
  registros alterados desde então.

## Configuração da API

As credenciais e o endpoint da API ELLOTEC estão definidos no topo de cada
arquivo (`funcionarios.py`, `clientes.py`, etc.):

```python
BASE_URL = "http://localhost:8000"
DEVICE_ID = "3f1c2d2a-6b6e-4b61-9f2c-0d0f7b7d9a11"
LOGIN_USUARIO = "admin"
LOGIN_SENHA = "123456"
```

A conexão com o Oracle do ERP é a mesma usada pelo resto do backend —
configurada em `app/shared/sistema_origem/config.py` (variáveis `ELLOTEC_ORACLE_*`
no `.env`).

## Scripts legados (não fazem parte do ciclo)

`migrar_*_mysql.py`, `criar_tabela_cotacao_cmed.py` e
`importar_cotacao_cmed.py` são ferramentas avulsas usadas na migração inicial
de dados; foram copiadas para cá por completude, mas ainda apontam para o
antigo `sys.path`/`core.*` do projeto `ello` e não foram adaptadas — não
tente rodá-las sem revisar os imports primeiro.
