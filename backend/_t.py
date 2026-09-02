# -*- coding: utf-8 -*-
import io, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from app.shared.sistema_origem.ouroweb.conexao import conectar
with conectar(timeout=600) as cx:
    cur = cx.cursor(as_dict=True)
    print("== servidor esta calmo? ==")
    cur.execute("""SELECT r.session_id sid, s.host_name maq, r.total_elapsed_time/1000 seg,
       ISNULL(OBJECT_NAME(t.objectid),'?') nome
       FROM sys.dm_exec_requests r JOIN sys.dm_exec_sessions s ON s.session_id=r.session_id
       OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) t
       WHERE s.is_user_process=1 AND r.session_id<>@@SPID""")
    x = cur.fetchall()
    print("  ", x if x else "nada rodando alem de mim")

    # mesmo teste de ontem: 67 produtos mais frequentes, cadastro 47449
    cur.execute("""SELECT TOP 67 fk_int_Estoque p FROM Tab_CceApoioPedidoItens WITH (NOLOCK)
       WHERE fk_int_Estoque > 0 GROUP BY fk_int_Estoque ORDER BY COUNT(*) DESC""")
    prods = [r["p"] for r in cur.fetchall()]
    vals = ",".join(f"('{p}')" for p in prods)
    t0 = time.time()
    cur.execute(f"""DECLARE @R [dbo].[UdtSpParameterString];
INSERT INTO @R (Id) VALUES {vals};
EXEC dbo.usp_lst_UltimaCotacaoItemApoio @Registros=@R, @FkIntCadastro='47449';""")
    n = len(cur.fetchall())
    print(f"\n== APOIO, mesmo teste de ontem ({len(prods)} produtos) ==")
    print(f"   ONTEM (sem correcao): 99,9 s")
    print(f"   AGORA:                {time.time()-t0:.1f} s, {n} linhas")
    cur.close()
