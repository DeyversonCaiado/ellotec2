import { Routes } from '@angular/router';
import { permissionGuard } from '../../core/permissions/permission.guard';

export const ENDERECAMENTO_ROUTES: Routes = [
  {
    path: '',
    canActivate: [permissionGuard('enderecamento.acessar')],
    loadComponent: () =>
      import('./endereco-list/endereco-list').then((m) => m.EnderecoList),
  },
  {
    path: 'novo',
    canActivate: [permissionGuard('enderecamento.gravar.incluir')],
    loadComponent: () =>
      import('./endereco-form/endereco-form').then((m) => m.EnderecoForm),
  },
  {
    path: ':id/editar',
    canActivate: [permissionGuard('enderecamento.gravar.editar')],
    loadComponent: () =>
      import('./endereco-form/endereco-form').then((m) => m.EnderecoForm),
  },
];
