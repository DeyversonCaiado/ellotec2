"""
Popula o banco com dados iniciais de desenvolvimento: um usuário admin
com acesso total, e alguns clientes/produtos de exemplo (mesmos dados
fictícios que o front usa no modo mock, pra facilitar comparação).

Uso:
    .venv/bin/python -m scripts.seed
"""

from app.core.database import todos_os_models  # noqa: F401
from app.core.database.conexao import Base, SessionLocal, engine
from app.core.auth.seguranca import gerar_hash_senha
from app.core.permissions.permission_model import PERMISSOES_VALIDAS
from app.domains.clientes.cliente_model import Cliente
from app.domains.produtos.produto_model import Produto
from app.domains.usuarios.cargo_model import Cargo
from app.domains.usuarios.usuario_model import Usuario, UsuarioPermissao


def criar_tabelas_se_necessario() -> None:
    Base.metadata.create_all(bind=engine)


def seed() -> None:
    sessao = SessionLocal()
    try:
        if sessao.query(Usuario).filter(Usuario.email == "admin@dumontek.com").first():
            print("Seed já aplicado anteriormente (admin@dumontek.com já existe). Nada a fazer.")
            return

        gerente = Cargo(nome="Gerente")
        funcionario = Cargo(nome="Funcionario")
        sessao.add_all([gerente, funcionario])
        sessao.flush()

        admin = Usuario(
            usuario="admin",
            nome="Abbott Keitch",
            email="admin@dumontek.com",
            senha_hash=gerar_hash_senha("admin123"),
            cargo_id=gerente.id,
            ativo=True,
        )
        sessao.add(admin)
        sessao.flush()

        for chave in PERMISSOES_VALIDAS:
            sessao.add(UsuarioPermissao(usuario_id=admin.id, chave=chave))

        leitora = Usuario(
            usuario="mariana.silva",
            nome="Mariana Silva",
            email="mariana.silva@dumontek.com",
            senha_hash=gerar_hash_senha("mariana123"),
            cargo_id=funcionario.id,
            ativo=True,
        )
        sessao.add(leitora)
        sessao.flush()

        for chave in [
            "usuarios.acessar",
            "clientes.acessar",
            "clientes.gravar.incluir",
            "clientes.gravar.editar",
            "produtos.acessar",
            "pedidos.acessar",
            "pedidos.gravar.incluir",
            "pedidos.gravar.editar",
        ]:
            sessao.add(UsuarioPermissao(usuario_id=leitora.id, chave=chave))

        clientes = [
            Cliente(
                razao_social="Distribuidora Saúde Total Ltda",
                nome_fantasia="Saúde Total",
                cnpj="12.345.678/0001-90",
                email="compras@saudetotal.com.br",
                telefone="(62) 3201-4455",
                cidade="Goiânia",
                uf="GO",
                ativo=True,
            ),
            Cliente(
                razao_social="Hospital Vida Plena S.A.",
                nome_fantasia="Vida Plena",
                cnpj="23.456.789/0001-11",
                email="suprimentos@vidaplena.com.br",
                telefone="(62) 3322-7788",
                cidade="Anápolis",
                uf="GO",
                ativo=True,
            ),
            Cliente(
                razao_social="Farmácia Popular Center Oeste",
                nome_fantasia="Popular Center Oeste",
                cnpj="34.567.890/0001-22",
                email="contato@popularco.com.br",
                telefone="(64) 3411-2200",
                cidade="Rio Verde",
                uf="GO",
                ativo=False,
            ),
        ]
        sessao.add_all(clientes)

        produtos = [
            Produto(
                codigo="MED-0012",
                descricao="Luva de Procedimento Látex P (cx c/100)",
                unidade="CX",
                ativo=True,
            ),
            Produto(
                codigo="MED-0045",
                descricao="Seringa Descartável 5ml c/ Agulha",
                unidade="UN",
                ativo=True,
            ),
            Produto(
                codigo="MED-0103",
                descricao="Álcool Etílico 70% 1L",
                unidade="UN",
                ativo=True,
            ),
            Produto(
                codigo="MED-0210",
                descricao="Termômetro Digital Clínico",
                unidade="UN",
                ativo=False,
            ),
        ]
        sessao.add_all(produtos)

        sessao.commit()
        print("Seed aplicado com sucesso:")
        print("  admin@dumontek.com / admin123 (acesso total)")
        print("  mariana.silva@dumontek.com / mariana123 (acesso parcial)")
        print(f"  {len(clientes)} clientes e {len(produtos)} produtos de exemplo criados")
    finally:
        sessao.close()


if __name__ == "__main__":
    criar_tabelas_se_necessario()
    seed()
