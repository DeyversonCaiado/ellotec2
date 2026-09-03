import { Routes } from '@angular/router';
import { permissionGuard } from '../../core/permissions/permission.guard';

export const SISTEMA_ORIGEM_ROUTES: Routes = [
  {
    path: '',
    canActivate: [permissionGuard('sistema_origem.acessar')],
    loadComponent: () =>
      import('./sistema-origem-page/sistema-origem-page').then((m) => m.SistemaOrigemPage),
  },
];
