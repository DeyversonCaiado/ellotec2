from app.core.permissions.permission_model import PERMISSOES_VALIDAS_SET


def validar_chaves_permissao(valor: list[str]) -> list[str]:
    """Validador reutilizável nos schemas que carregam `permissoes: list[str]`
    (UsuarioCriarSchema, UsuarioAtualizarSchema, UsuarioLogadoSchema).
    Garante que nenhuma chave desconhecida seja gravada ou aceita."""
    desconhecidas = set(valor) - PERMISSOES_VALIDAS_SET
    if desconhecidas:
        raise ValueError(f"Chaves de permissão desconhecidas: {sorted(desconhecidas)}")
    return valor
