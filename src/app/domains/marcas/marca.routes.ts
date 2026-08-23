import { Routes } from '@angular/router';
import { permissionGuard } from '../../core/permissions/permission.guard';

export const MARCA_ROUTES: Routes = [
  {
    path: '',
    canActivate: [permissionGuard('marcas.acessar')],
    loadComponent: () => import('./marca-list/marca-list').then((m) => m.MarcaList),
  },
  {
    path: 'novo',
    canActivate: [permissionGuard('marcas.gravar.incluir')],
    loadComponent: () => import('./marca-form/marca-form').then((m) => m.MarcaForm),
  },
  {
    path: ':id/editar',
    canActivate: [permissionGuard('marcas.gravar.editar')],
    loadComponent: () => import('./marca-form/marca-form').then((m) => m.MarcaForm),
  },
];
