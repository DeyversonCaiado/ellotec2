"""
Cliente HTTP genérico usado pelos scripts de sincronização (de qualquer sistema de origem) para falar com a
própria API ELLOTEC (http://localhost:8000) como um integrador externo
qualquer — via HTTP, com login e token, exatamente como o front faz.

Usa `httpx` (já é dependência do projeto) em vez de `requests`, que não
está nos requirements do backend.
"""

import httpx

MAX_TENTATIVAS_PADRAO = 3


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
        resposta = httpx.request(metodo, url, headers=headers, timeout=30, **kwargs)

        if resposta.status_code != 401:
            return resposta

        if logger:
            logger.warning(
                f"Token inválido/expirado (401) em {metodo} {url} "
                f"[tentativa {tentativa}/{max_tentativas}]."
            )

    return resposta
