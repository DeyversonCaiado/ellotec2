import { Routes } from '@angular/router';
import { permissionGuard } from '../../core/permissions/permission.guard';

export const PRODUTO_ROUTES: Routes = [
  {
    path: '',
    canActivate: [permissionGuard('produtos.acessar')],
    loadComponent: () => import('./produto-list/produto-list').then((m) => m.ProdutoList),
  },
  {
    path: 'novo',
    canActivate: [permissionGuard('produtos.gravar.incluir')],
    loadComponent: () => import('./produto-form/produto-form').then((m) => m.ProdutoForm),
  },
  {
    path: ':id/editar',
    canActivate: [permissionGuard('produtos.gravar.editar')],
    loadComponent: () => import('./produto-form/produto-form').then((m) => m.ProdutoForm),
  },
];
