import { Routes } from '@angular/router';
import { permissionGuard } from '../../core/permissions/permission.guard';

export const ESTOQUE_ROUTES: Routes = [
  {
    path: '',
    canActivate: [permissionGuard('estoque.acessar')],
    loadComponent: () => import('./estoque-list/estoque-list').then((m) => m.EstoqueList),
  },
];
