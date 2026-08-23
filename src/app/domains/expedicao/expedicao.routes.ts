import { Routes } from '@angular/router';
import { permissionGuard } from '../../core/permissions/permission.guard';

/**
 * Todas as rotas exigem só `expedicao.acessar`. A separação entre quem pode
 * executar separação e quem pode executar conferência não dá pra expressar
 * num guard de rota (o tipo vem no path, e as duas etapas compartilham as
 * mesmas telas) — quem barra é o backend, em cada endpoint de escrita.
 */
export const EXPEDICAO_ROUTES: Routes = [
  {
    path: '',
    canActivate: [permissionGuard('expedicao.acessar')],
    loadComponent: () => import('./expedicao-list/expedicao-list').then((m) => m.ExpedicaoList),
  },
  {
    path: ':pedidoId',
    canActivate: [permissionGuard('expedicao.acessar')],
    loadComponent: () =>
      import('./expedicao-pedido/expedicao-pedido').then((m) => m.ExpedicaoPedido),
  },
  {
    path: ':pedidoId/:tipo/:processoId',
    canActivate: [permissionGuard('expedicao.acessar')],
    loadComponent: () => import('./expedicao-itens/expedicao-itens').then((m) => m.ExpedicaoItens),
  },
  {
    path: ':pedidoId/:tipo/:processoId/itens/:pedidoItemId',
    canActivate: [permissionGuard('expedicao.acessar')],
    loadComponent: () =>
      import('./expedicao-bipagem/expedicao-bipagem').then((m) => m.ExpedicaoBipagem),
  },
];
