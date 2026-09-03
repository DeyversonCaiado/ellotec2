import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { PopoverModule } from 'primeng/popover';
import { AuthService } from '../../../core/auth/auth.service';
import { PermissaoDirective } from '../../../core/permissions/permissao.directive';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';
import { ExpedicaoConfiguracaoService } from '../expedicao-configuracao.service';

/**
 * O painel de parâmetros da expedição.
 *
 * É uma tela de configuração, não um cadastro: não tem listagem, não tem
 * "novo", não tem "apagar". O usuário abre, muda o que precisa e salva.
 *
 * Cada parâmetro tem um "?" ao lado que abre um popover explicando o que ele
 * faz, com exemplo. Isso não é enfeite: quem decide ligar ou desligar a trava
 * de endereçamento é o coordenador do galpão, e o efeito da escolha aparece
 * longe daqui — num pedido que trava (ou não trava) na mão do operador, dias
 * depois. Um rótulo de uma linha não dá conta de explicar isso.
 */
@Component({
  selector: 'app-expedicao-configuracao-page',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    PopoverModule,
    PermissaoDirective,
    IconComponent,
    PageHeaderComponent,
  ],
  templateUrl: './expedicao-configuracao-page.html',
})
export class ExpedicaoConfiguracaoPage implements OnInit {
  private fb = inject(FormBuilder);
  private service = inject(ExpedicaoConfiguracaoService);
  private auth = inject(AuthService);

  carregando = signal(false);
  salvando = signal(false);
  erro = signal<string | null>(null);
  salvo = signal(false);

  form = this.fb.nonNullable.group({
    permiteConferirComDivergencia: [false],
    permiteConferirForaDoMultiploDeVenda: [false],
  });

  /** Sem a permissão de gravar, o painel vira leitura: os campos ficam
   * desabilitados e o botão some (`*appPermissao` no template). Desabilitar é
   * o que evita a tela mentir — um checkbox que responde ao clique e não salva
   * é pior do que um que não responde. */
  podeEditar = this.auth.usuario()?.permissoes.has('expedicao_configuracoes.gravar.editar') ?? false;

  ngOnInit(): void {
    if (!this.podeEditar) this.form.disable();

    this.carregando.set(true);
    this.service.obter().subscribe({
      next: (configuracao) => {
        this.carregando.set(false);
        this.form.patchValue(configuracao);
      },
      error: () => {
        this.carregando.set(false);
        this.erro.set('Não foi possível carregar os parâmetros da expedição.');
      },
    });
  }

  salvar(): void {
    this.salvando.set(true);
    this.erro.set(null);
    this.salvo.set(false);

    this.service.salvar(this.form.getRawValue()).subscribe({
      next: (configuracao) => {
        this.salvando.set(false);
        this.salvo.set(true);
        this.form.patchValue(configuracao);
      },
      error: (resposta) => {
        this.salvando.set(false);
        this.erro.set(resposta?.error?.detail ?? 'Não foi possível salvar os parâmetros.');
      },
    });
  }
}
