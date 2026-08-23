import { Routes } from '@angular/router';
import { permissionGuard } from '../../core/permissions/permission.guard';

export const CIDADE_ROUTES: Routes = [
  {
    path: '',
    canActivate: [permissionGuard('cidades.acessar')],
    loadComponent: () => import('./cidade-list/cidade-list').then((m) => m.CidadeList),
  },
  {
    path: 'novo',
    canActivate: [permissionGuard('cidades.gravar.incluir')],
    loadComponent: () => import('./cidade-form/cidade-form').then((m) => m.CidadeForm),
  },
  {
    path: ':id/editar',
    canActivate: [permissionGuard('cidades.gravar.editar')],
    loadComponent: () => import('./cidade-form/cidade-form').then((m) => m.CidadeForm),
  },
];
