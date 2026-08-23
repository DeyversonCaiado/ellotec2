import { Routes } from '@angular/router';
import { permissionGuard } from '../../core/permissions/permission.guard';

export const USUARIO_ROUTES: Routes = [
  {
    path: '',
    canActivate: [permissionGuard('usuarios.acessar')],
    loadComponent: () => import('./usuario-list/usuario-list').then((m) => m.UsuarioList),
  },
  {
    path: 'novo',
    canActivate: [permissionGuard('usuarios.gravar.incluir')],
    loadComponent: () => import('./usuario-form/usuario-form').then((m) => m.UsuarioForm),
  },
  {
    path: ':id/editar',
    canActivate: [permissionGuard('usuarios.gravar.editar')],
    loadComponent: () => import('./usuario-form/usuario-form').then((m) => m.UsuarioForm),
  },
];
