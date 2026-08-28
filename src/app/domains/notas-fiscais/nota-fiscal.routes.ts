import { Routes } from '@angular/router';
import { permissionGuard } from '../../core/permissions/permission.guard';

/**
 * Uma rota de listagem só, com entrada e saída como filtro dentro da tela —
 * não `/entradas` e `/saidas` separados. É o mesmo documento visto dos dois
 * lados, e o backend guarda os dois na mesma tabela.
 *
 * Não existe rota de `novo`/`editar`: nota fiscal não se digita, chega pela
 * integração (ERP ou XML da SEFAZ). As permissões de gravar existem no
 * catálogo porque o endpoint precisa delas, não porque haja formulário.
 */
export const NOTA_FISCAL_ROUTES: Routes = [
  {
    path: '',
    canActivate: [permissionGuard('notas_fiscais.acessar')],
    loadComponent: () => import('./nota-fiscal-list/nota-fiscal-list').then((m) => m.NotaFiscalList),
  },
  {
    path: ':id',
    canActivate: [permissionGuard('notas_fiscais.acessar')],
    loadComponent: () =>
      import('./nota-fiscal-detalhe/nota-fiscal-detalhe').then((m) => m.NotaFiscalDetalhe),
  },
];
