import { Routes } from '@angular/router';
import { permissionGuard } from '../../core/permissions/permission.guard';

export const EMPRESA_ROUTES: Routes = [
  {
    path: '',
    canActivate: [permissionGuard('empresas.acessar')],
    loadComponent: () => import('./empresa-list/empresa-list').then((m) => m.EmpresaList),
  },
  {
    path: 'novo',
    canActivate: [permissionGuard('empresas.gravar.incluir')],
    loadComponent: () => import('./empresa-form/empresa-form').then((m) => m.EmpresaForm),
  },
  {
    path: ':id/editar',
    canActivate: [permissionGuard('empresas.gravar.editar')],
    loadComponent: () => import('./empresa-form/empresa-form').then((m) => m.EmpresaForm),
  },
];
