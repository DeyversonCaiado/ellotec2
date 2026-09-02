import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { AccordionModule } from 'primeng/accordion';
import { TimelineModule } from 'primeng/timeline';
import { DialogModule } from 'primeng/dialog';
import { SelectModule } from 'primeng/select';
import { EntregaService } from '../entrega.service';
import {
  EntregaNota,
  InteracaoEntrega,
  STATUS_INTERACAO,
  STATUS_INTERACAO_PADRAO,
  STATUS_PRAZO,
  StatusInteracao,
  StatusPrazo,
  corStatus,
  corStatusDaNota,
  marcadorStatus,
  paraStatusEscolhivel,
  rotuloStatus,
  rotuloStatusDaNota,
  rotuloTipoNota,
} from '../entrega.model';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';
import { PermissaoDirective } from '../../../core/permissions/permissao.directive';
import { TempoRelativoPipe } from '../../../shared/ui/tempo-relativo.pipe';

@Component({
  selector: 'app-entrega-detalhe',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterLink,
    AccordionModule,
    TimelineModule,
    DialogModule,
    SelectModule,
    IconComponent,
    PageHeaderComponent,
    PermissaoDirective,
    TempoRelativoPipe,
  ],
  templateUrl: './entrega-detalhe.html',
})
export class EntregaDetalhe implements OnInit {
  nota = signal<EntregaNota | null>(null);
  carregando = signal(true);
  salvando = signal(false);

  dialogAberto = signal(false);
  /** Preenchido quando o dialog está corrigindo uma interação existente; nulo
   *  quando está lançando uma nova. É o mesmo formulário nos dois casos. */
  editandoId = signal<string | null>(null);
  formStatus = signal<StatusInteracao>(STATUS_INTERACAO_PADRAO);
  formObservacao = signal('');

  /** O que o dialog oferece: sem o status de nascimento — ver STATUS_INTERACAO. */
  readonly opcoesStatus = STATUS_INTERACAO;
  readonly rotuloStatus = rotuloStatus;
  readonly corStatus = corStatus;
  readonly rotuloStatusDaNota = rotuloStatusDaNota;
  readonly corStatusDaNota = corStatusDaNota;
  readonly marcadorStatus = marcadorStatus;
  readonly rotuloTipoNota = rotuloTipoNota;

  constructor(
    private route: ActivatedRoute,
    private service: EntregaService,
  ) {}

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      this.carregando.set(false);
      return;
    }
    this.service.obterPorId(id).subscribe({
      next: (nota) => {
        this.nota.set(nota);
        this.carregando.set(false);
      },
      error: () => this.carregando.set(false),
    });
  }

  rotuloPrazo(status: StatusPrazo): string {
    return STATUS_PRAZO[status]?.rotulo ?? status;
  }

  corPrazo(status: StatusPrazo): string {
    return STATUS_PRAZO[status]?.cor ?? 'text-gray-500 bg-gray-100';
  }

  abrirNova(): void {
    this.editandoId.set(null);
    // Pré-seleciona o status atual da nota: a maioria das interações confirma
    // ou avança a partir de onde a entrega está, e digitar do zero toda vez é
    // atrito sem ganho. Nota que ainda não tem interação está no status de
    // nascimento, que o formulário não oferece — aí cai no padrão.
    this.formStatus.set(paraStatusEscolhivel(this.nota()?.statusAtual ?? ''));
    this.formObservacao.set('');
    this.dialogAberto.set(true);
  }

  abrirEdicao(interacao: InteracaoEntrega): void {
    this.editandoId.set(interacao.id);
    this.formStatus.set(paraStatusEscolhivel(interacao.status));
    this.formObservacao.set(interacao.observacao);
    this.dialogAberto.set(true);
  }

  salvar(): void {
    const nota = this.nota();
    if (!nota || this.salvando()) return;

    this.salvando.set(true);
    const dados = { status: this.formStatus(), observacao: this.formObservacao().trim() };
    const editandoId = this.editandoId();

    // As duas rotas devolvem a NOTA inteira: registrar ou corrigir muda o
    // statusAtual e o statusPrazo, e a tela precisa dos dois sem um segundo
    // request.
    const requisicao = editandoId
      ? this.service.atualizarInteracao(nota.id, editandoId, dados)
      : this.service.registrarInteracao(nota.id, dados);

    requisicao.subscribe({
      next: (atualizada) => {
        this.nota.set(atualizada);
        this.salvando.set(false);
        this.dialogAberto.set(false);
      },
      error: () => this.salvando.set(false),
    });
  }

  apagar(interacao: InteracaoEntrega): void {
    const nota = this.nota();
    if (!nota) return;
    if (!confirm('Remover esta interação da linha do tempo?')) return;

    this.service.apagarInteracao(nota.id, interacao.id).subscribe((atualizada) => {
      this.nota.set(atualizada);
    });
  }
}
