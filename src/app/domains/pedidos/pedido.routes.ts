import { Routes } from '@angular/router';
import { permissionGuard } from '../../core/permissions/permission.guard';

export const PEDIDO_ROUTES: Routes = [
  {
    path: '',
    canActivate: [permissionGuard('pedidos.acessar')],
    loadComponent: () => import('./pedido-list/pedido-list').then((m) => m.PedidoList),
  },
  {
    path: 'novo',
    canActivate: [permissionGuard('pedidos.gravar.incluir')],
    loadComponent: () => import('./pedido-form/pedido-form').then((m) => m.PedidoForm),
  },
  {
    path: ':id/editar',
    canActivate: [permissionGuard('pedidos.gravar.editar')],
    loadComponent: () => import('./pedido-form/pedido-form').then((m) => m.PedidoForm),
  },
];
