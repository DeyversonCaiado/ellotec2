import { Routes } from '@angular/router';
import { permissionGuard } from '../../core/permissions/permission.guard';

/**
 * Só listagem e detalhe: não existe formulário de "nova entrega". A nota e o
 * mapa de carga chegam pela integração — o que se cria pela tela é interação,
 * e isso acontece dentro do detalhe.
 *
 * As duas rotas pedem `entregas.acessar`. A restrição mais fina (vendedor sem
 * `entregas.ver_todas` só enxerga as próprias notas) é do backend, não daqui:
 * guard de rota é UX, e esconder linha no front não protege dado nenhum.
 */
export const ENTREGA_ROUTES: Routes = [
  {
    path: '',
    canActivate: [permissionGuard('entregas.acessar')],
    loadComponent: () => import('./entrega-list/entrega-list').then((m) => m.EntregaList),
  },
  {
    path: ':id',
    canActivate: [permissionGuard('entregas.acessar')],
    loadComponent: () =>
      import('./entrega-detalhe/entrega-detalhe').then((m) => m.EntregaDetalhe),
  },
];
