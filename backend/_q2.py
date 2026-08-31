import time
from datetime import date
from app.domains.cotacoes import cotacao_service as sv
from app.domains.cotacoes.cotacao_contrato import CotacaoFiltrosSchema
from app.shared.sistema_origem.ouroweb import conexao as ow

f = CotacaoFiltrosSchema(data_inicio=date(2026,8,25), data_fim=date(2026,8,28))

sql_total, p = sv._montar(f, "COUNT(*) AS total")
sql_pag, _ = sv._montar(f, sv._COLUNAS, "\nORDER BY c.dte_DataVencimento DESC, i.pk_int_IdCceBionexoPedidoItens ASC\nOFFSET %(offset)s ROWS FETCH NEXT %(limite)s ROWS ONLY")

for nome, sql, par in [("COUNT(*)", sql_total, p),
                       ("pagina 1 (50 linhas)", sql_pag, {**p,"offset":0,"limite":50})]:
    for tentativa in (1,2):
        t0=time.perf_counter()
        try:
            r = ow.buscar_todos(sql, par)
            print(f"{nome} [tentativa {tentativa}]: {time.perf_counter()-t0:6.2f}s ({len(r)} linhas)")
        except Exception as e:
            print(f"{nome} [tentativa {tentativa}]: FALHOU em {time.perf_counter()-t0:.1f}s -> {type(e).__name__}")
