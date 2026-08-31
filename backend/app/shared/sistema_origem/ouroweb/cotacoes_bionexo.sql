-- Cotações Bionexo com vencimento nos últimos 3 dias.
--
-- Uma linha por ITEM de cotação. As tabelas envolvidas:
--   Tab_CceBionexoPedido           1 linha por (cotação x empresa nossa)
--   Tab_CceBionexoPedidoCabecalho  dados do hospital e da cotação (1:1 com Pedido)
--   Tab_CceBionexoPedidoItens      os produtos pedidos (N por Pedido)
--
-- ATENÇÃO à repetição: a mesma cotação (int_IdPdc) aparece uma vez para CADA
-- CNPJ da nossa distribuidora — é assim que o Bionexo entrega, não é erro de
-- join. Por isso `empresa_id` está no SELECT. Para uma linha por item, filtre
-- uma empresa (descomente o filtro no WHERE).
--
-- Cidade e estado NÃO existem nas tabelas Bionexo; vêm do cadastro do hospital
-- (Tab_Cadastro -> Cidade) pelo fk_int_Cadastro do cabeçalho. Os JOINs são
-- INNER e há filtro de NOT NULL: linha sem hospital ou sem cidade não serve
-- para inteligência de mercado, então fica de fora (~23% dos cabeçalhos).

SELECT
    cab.int_IdPdc                AS cotacao,
    cab.str_TituloPdc            AS titulo_cotacao,
    cab.dte_DataVencimento       AS data_vencimento,
    cab.str_NomeHospital         AS hospital,
    cab.str_CnpjHospital         AS cnpj_hospital,
    cid.Cidade                   AS cidade,
    cid.Estado                   AS estado,
    ped.fk_int_IdEmpresa         AS empresa_id,
    emp.NomeFantasia             AS empresa,
    itens.str_CodigoProduto      AS codigo_produto_hospital,
    itens.str_DescricaoProduto   AS produto_hospital,
    itens.cur_Quantidade                   AS quantidade_solicitada,
    itens.cur_QuantidadeProdutoVinculado   AS quantidade_respondida,
    itens.cur_QuantidadeFaturadaProdutoVinculado AS quantidade_faturada,
    itens.str_UnidadeMedida      AS unidade,
    itens.cur_PrecoUnitario      AS preco_unitario
FROM Tab_CceBionexoPedido AS ped
INNER JOIN Tab_CceBionexoPedidoCabecalho AS cab
        ON cab.fk_int_IdCceBionexoPedido = ped.pk_int_IdCceBionexoPedido
INNER JOIN Tab_CceBionexoPedidoItens AS itens
        ON itens.fk_int_IdCceBionexoPedido = ped.pk_int_IdCceBionexoPedido
INNER JOIN Tab_Cadastro AS cad ON cad.pk_int_Cadastro = cab.fk_int_Cadastro
INNER JOIN Cidade       AS cid ON cid.IdCidade        = cad.IdCidade
LEFT JOIN Tab_Empresa  AS emp ON emp.IdEmpresa       = ped.fk_int_IdEmpresa
WHERE cab.dte_DataVencimento >= DATEADD(day, -3, CAST(GETDATE() AS date))
  AND cab.dte_DataVencimento <  DATEADD(day,  1, CAST(GETDATE() AS date))
  -- Sem hospital ou sem cidade a linha não serve para análise de mercado.
  AND cab.str_NomeHospital IS NOT NULL
  AND cab.str_NomeHospital <> ''
  AND cid.Cidade IS NOT NULL
  -- Uma empresa só, para não repetir a cotação por CNPJ da distribuidora:
  -- AND ped.fk_int_IdEmpresa = 1
ORDER BY cab.dte_DataVencimento DESC,
         cab.int_IdPdc,
         ped.fk_int_IdEmpresa;
