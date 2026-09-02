"""
Cliente HTTP genérico usado pelos scripts de sincronização (de qualquer sistema de origem) para falar com a
própria API ELLOTEC (http://localhost:8000) como um integrador externo
qualquer — via HTTP, com login e token, exatamente como o front faz.

Usa `httpx` (já é dependência do projeto) em vez de `requests`, que não
está nos requirements do backend.
"""

import httpx

MAX_TENTATIVAS_PADRAO = 3

# Um cliente só para o processo inteiro, em vez de `httpx.request(...)`, que
# abre e fecha uma conexão TCP por chamada.
#
# Não é micro-otimização: medido nesta máquina, a mesma chamada custa 2,5s
# abrindo conexão nova contra `localhost` e 0,06s reaproveitando a conexão —
# 40x. O grosso dos 2,5s é o `localhost` resolvendo para IPv6 primeiro no
# Windows e só depois caindo no IPv4; a API responde em 60ms. Num lote de
# centenas de registros isso é a diferença entre um minuto e uma hora.
_CLIENTE = httpx.Client(timeout=30)


def requisitar_com_retry(
    metodo,
    url,
    obter_token_fn,
    headers_fn,
    logger=None,
    max_tentativas=MAX_TENTATIVAS_PADRAO,
    **kwargs,
):
    """Faz uma chamada HTTP à API ELLOTEC renovando o token e tentando de novo
    quando a resposta é 401 (token inválido/expirado).

    O JWT da API tem validade curta, e os sincronizadores rodam em lotes que
    podem passar dessa validade no meio do processamento (visto em produção:
    login funcionou, token expirou 15-20min depois, e o restante do lote
    inteiro falhava com 401, derrubando a aplicação via RuntimeError).

    `obter_token_fn` deve aceitar `forcar_renovacao=True/False` — na primeira
    tentativa usa o token em cache (se houver), nas seguintes força um novo
    login. `headers_fn` recebe o token e monta os headers da chamada.
    """
    resposta = None
    for tentativa in range(1, max_tentativas + 1):
        token = obter_token_fn(forcar_renovacao=(tentativa > 1))
        headers = headers_fn(token)
        resposta = _CLIENTE.request(metodo, url, headers=headers, **kwargs)

        if resposta.status_code != 401:
            return resposta

        if logger:
            logger.warning(
                f"Token inválido/expirado (401) em {metodo} {url} "
                f"[tentativa {tentativa}/{max_tentativas}]."
            )

    return resposta
