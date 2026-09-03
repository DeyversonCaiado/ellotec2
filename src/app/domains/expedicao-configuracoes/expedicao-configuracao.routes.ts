import { Routes } from '@angular/router';
import { permissionGuard } from '../../core/permissions/permission.guard';

export const EXPEDICAO_CONFIGURACAO_ROUTES: Routes = [
  {
    path: '',
    canActivate: [permissionGuard('expedicao_configuracoes.acessar')],
    loadComponent: () =>
      import('./expedicao-configuracao-page/expedicao-configuracao-page').then(
        (m) => m.ExpedicaoConfiguracaoPage,
      ),
  },
];
