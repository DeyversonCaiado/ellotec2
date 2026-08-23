import { Directive, Input, TemplateRef, ViewContainerRef, effect, inject } from '@angular/core';
import { AuthService } from '../auth/auth.service';
import { PermissaoKey } from './permission.model';

/**
 * Esconde/mostra um elemento de acordo com a permissão do usuário logado.
 *
 *   <button *appPermissao="'produtos.gravar.incluir'">Novo produto</button>
 *
 * Mesma chave PermissaoKey do permissionGuard, então não tem "duas fontes
 * de verdade" pra decidir quem pode o quê.
 */
@Directive({
  selector: '[appPermissao]',
  standalone: true,
})
export class PermissaoDirective {
  private templateRef = inject(TemplateRef<unknown>);
  private viewContainer = inject(ViewContainerRef);
  private auth = inject(AuthService);

  private chave: PermissaoKey | null = null;
  private renderizado = false;

  @Input() set appPermissao(valor: PermissaoKey) {
    this.chave = valor;
  }

  constructor() {
    effect(() => {
      const temPermissao = !!(this.chave && this.auth.usuario()?.permissoes.has(this.chave));

      if (temPermissao && !this.renderizado) {
        this.viewContainer.createEmbeddedView(this.templateRef);
        this.renderizado = true;
      } else if (!temPermissao && this.renderizado) {
        this.viewContainer.clear();
        this.renderizado = false;
      }
    });
  }
}
