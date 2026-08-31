import { Routes } from '@angular/router';
import { permissionGuard } from '../../core/permissions/permission.guard';

export const COTACOES_ROUTES: Routes = [
  {
    path: '',
    canActivate: [permissionGuard('cotacoes.acessar')],
    loadComponent: () => import('./cotacao-list/cotacao-list').then((m) => m.CotacaoList),
  },
];
