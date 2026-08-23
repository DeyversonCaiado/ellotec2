import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../auth/auth.service';
import { PermissaoKey } from './permission.model';

/**
 * Guard parametrizado por uma única chave de permissão. Uso na rota:
 *
 *   { path: 'produtos', canActivate: [permissionGuard('produtos.acessar')], ... }
 *
 * Se o usuário não tiver a permissão, volta pra home em vez de quebrar a
 * navegação — a home já filtra o menu pelas mesmas permissões, então o
 * usuário nunca chega lá por engano, isso é só a segunda barreira.
 */
export function permissionGuard(chave: PermissaoKey): CanActivateFn {
  return () => {
    const auth = inject(AuthService);
    const router = inject(Router);

    const temPermissao = !!auth.usuario()?.permissoes.has(chave);

    if (temPermissao) {
      return true;
    }

    router.navigate(['/']);
    return false;
  };
}
