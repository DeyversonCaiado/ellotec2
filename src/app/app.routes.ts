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
        loadComponent: () =>
          import('./domains/inicio/inicio-page/inicio-page').then((m) => m.InicioPage),
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
        path: 'notas-fiscais',
        loadChildren: () =>
          import('./domains/notas-fiscais/nota-fiscal.routes').then((m) => m.NOTA_FISCAL_ROUTES),
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
        path: 'entregas',
        loadChildren: () =>
          import('./domains/entregas/entrega.routes').then((m) => m.ENTREGA_ROUTES),
      },
      {
        path: 'expedicao',
        loadChildren: () => import('./domains/expedicao/expedicao.routes').then((m) => m.EXPEDICAO_ROUTES),
      },
      {
        path: 'empresas',
        loadChildren: () => import('./domains/empresas/empresa.routes').then((m) => m.EMPRESA_ROUTES),
      },
      {
        path: 'estoque',
        loadChildren: () => import('./domains/estoque/estoque.routes').then((m) => m.ESTOQUE_ROUTES),
      },
      {
        path: 'enderecamento',
        loadChildren: () =>
          import('./domains/enderecamento/enderecamento.routes').then((m) => m.ENDERECAMENTO_ROUTES),
      },
      {
        path: 'cotacoes',
        loadChildren: () =>
          import('./domains/cotacoes/cotacao.routes').then((m) => m.COTACOES_ROUTES),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
