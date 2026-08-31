import time
from datetime import date
from app.domains.cotacoes import cotacao_service as sv
from app.domains.cotacoes.cotacao_contrato import CotacaoFiltrosSchema
f = CotacaoFiltrosSchema(data_inicio=date(2026,8,25), data_fim=date(2026,8,28))
sql, p = sv._montar(f, sv._COLUNAS, "\nORDER BY c.dte_DataVencimento DESC, i.pk_int_IdCceBionexoPedidoItens ASC\nOFFSET %(offset)s ROWS FETCH NEXT %(limite)s ROWS ONLY")
print("=== SQL DA PAGINA ===")
print(sql)
print("=== parametros ===", p)
