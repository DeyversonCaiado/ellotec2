import pymssql
from app.shared.sistema_origem.ouroweb.config import obter_sqlserver_settings

s = obter_sqlserver_settings()
con = pymssql.connect(server=s.host, port=str(s.porta), user=s.user,
                      password=s.password, database="Ourobase", login_timeout=10, timeout=60)
cur = con.cursor()

cur.execute("""
SELECT t.name, (SELECT SUM(p.rows) FROM sys.partitions p
                WHERE p.object_id = t.object_id AND p.index_id IN (0,1))
FROM sys.tables t WHERE t.name LIKE '%Bionexo%' ORDER BY t.name
""")
tabelas = cur.fetchall()
print("=== TABELAS BIONEXO ===")
for nome, linhas in tabelas:
    print(f"{nome:<50} {linhas}")

print("\n=== COLUNAS ===")
for nome, _ in tabelas:
    cur.execute("""
    SELECT c.name, ty.name, c.max_length, c.is_nullable
    FROM sys.columns c JOIN sys.types ty ON ty.user_type_id = c.user_type_id
    WHERE c.object_id = OBJECT_ID(%s) ORDER BY c.column_id
    """, (nome,))
    print(f"\n-- {nome}")
    for col, tipo, tam, nulo in cur.fetchall():
        print(f"   {col:<38} {tipo}({tam}){'' if nulo else ' NOT NULL'}")

con.close()
