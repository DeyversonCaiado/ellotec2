import { Routes } from '@angular/router';
import { authGuard } from './core/auth/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./core/auth/login-page/login-page').then((m) => m.LoginPage),
  },
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () => import('./core/layout/shell').then((m) => m.Shell),
    children: [
      {
        path: '',
        loadComponent: () => import('./core/layout/home-page/home-page').then((m) => m.HomePage),
      },
      {
        path: 'usuarios',
        loadChildren: () => import('./domains/usuarios/usuario.routes').then((m) => m.USUARIO_ROUTES),
      },
      {
        path: 'clientes',
        loadChildren: () => import('./domains/clientes/cliente.routes').then((m) => m.CLIENTE_ROUTES),
      },
      {
        path: 'produtos',
        loadChildren: () => import('./domains/produtos/produto.routes').then((m) => m.PRODUTO_ROUTES),
      },
      {
        path: 'pedidos',
        loadChildren: () => import('./domains/pedidos/pedido.routes').then((m) => m.PEDIDO_ROUTES),
      },
      {
        path: 'cidades',
        loadChildren: () => import('./domains/cidades/cidade.routes').then((m) => m.CIDADE_ROUTES),
      },
      {
        path: 'marcas',
        loadChildren: () => import('./domains/marcas/marca.routes').then((m) => m.MARCA_ROUTES),
      },
      {
        path: 'expedicao',
        loadChildren: () => import('./domains/expedicao/expedicao.routes').then((m) => m.EXPEDICAO_ROUTES),
      },
      {
        path: 'empresas',
        loadChildren: () => import('./domains/empresas/empresa.routes').then((m) => m.EMPRESA_ROUTES),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
