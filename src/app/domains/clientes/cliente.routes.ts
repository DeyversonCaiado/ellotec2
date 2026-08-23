import { Routes } from '@angular/router';
import { permissionGuard } from '../../core/permissions/permission.guard';

export const CLIENTE_ROUTES: Routes = [
  {
    path: '',
    canActivate: [permissionGuard('clientes.acessar')],
    loadComponent: () => import('./cliente-list/cliente-list').then((m) => m.ClienteList),
  },
  {
    path: 'novo',
    canActivate: [permissionGuard('clientes.gravar.incluir')],
    loadComponent: () => import('./cliente-form/cliente-form').then((m) => m.ClienteForm),
  },
  {
    path: ':id/editar',
    canActivate: [permissionGuard('clientes.gravar.editar')],
    loadComponent: () => import('./cliente-form/cliente-form').then((m) => m.ClienteForm),
  },
];
