import { Component, ElementRef, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { ExpedicaoService } from '../expedicao.service';
import { CredencialGerente, ItemProcesso, Processo, TipoProcesso, rotuloTipo } from '../expedicao.model';
import { VincularAnvisaResposta } from '../../produtos/produto.model';
import { SenhaGerenteComponent } from '../senha-gerente.component';
import { ProdutoService } from '../../produtos/produto.service';
import { AuthService } from '../../../core/auth/auth.service';
import { IconComponent } from '../../../shared/ui/icon.component';

/**
 * Tela de leitura no coletor (800×480). O campo de código de barras mantém o
 * foco sempre: o coletor não tem teclado confortável, então errar a leitura
 * não pode custar um toque pra voltar ao campo.
 */
@Component({
  selector: 'app-expedicao-bipagem',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, IconComponent, SenhaGerenteComponent],
  templateUrl: './expedicao-bipagem.html',
})
export class ExpedicaoBipagem implements OnInit {
  private service = inject(ExpedicaoService);
  // A verificação na CMED é do domínio de PRODUTOS: quem grava em
  // `produto_codigo_barras` é o dono da tabela, e todas as regras (conferir o
  // código, recusar conflito) moram no endpoint de lá. Esta tela só dispara e
  // mostra o resultado — ela não reimplementa nada (ver ARCHITECTURE.md).
  private produtoService = inject(ProdutoService);
  private auth = inject(AuthService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  private campoCodigo = viewChild<ElementRef<HTMLInputElement>>('campoCodigo');

  processo = signal<Processo | null>(null);
  carregando = signal(true);
  erro = signal<string | null>(null);
  ocupado = signal(false);

  codigoBarras = signal('');
  multiplicador = signal(1);

  pedindoSenha = signal(false);
  erroSenha = signal<string | null>(null);

  /** A última leitura foi recusada porque o cadastro do produto não bate com o
   *  que está impresso na caixa. Vira o aviso para procurar o cadastro — a
   *  correção acontece na tela de produtos, na seção "código de barras
   *  logística", e não mais daqui. */
  produtoNaoReconhecido = signal(false);

  pedidoId = '';
  tipo: TipoProcesso = 'separacao';
  processoId = '';
  pedidoItemId = '';

  readonly rotuloTipo = rotuloTipo;

  item = computed<ItemProcesso | undefined>(() =>
    this.processo()?.itens.find((linha) => linha.pedidoItemId === this.pedidoItemId),
  );

  falta = computed(() => {
    const item = this.item();
    return item ? item.quantidadePedida - item.quantidadeProcessada : 0;
  });

  completo = computed(() => this.falta() === 0);

  ngOnInit(): void {
    const params = this.route.snapshot.paramMap;
    this.pedidoId = params.get('pedidoId') ?? '';
    this.tipo = (params.get('tipo') as TipoProcesso) ?? 'separacao';
    this.processoId = params.get('processoId') ?? '';
    this.pedidoItemId = params.get('pedidoItemId') ?? '';

    this.service.obterProcesso(this.tipo, this.processoId).subscribe({
      next: (processo) => {
        this.processo.set(processo);
        this.carregando.set(false);
        this.focarCampo();
      },
      error: (resposta: HttpErrorResponse) => {
        this.erro.set(resposta.error?.detail ?? 'Não foi possível carregar o item.');
        this.carregando.set(false);
      },
    });
  }

  private focarCampo(): void {
    // setTimeout porque o input só existe depois que `carregando` vira false
    // e o @if do template renderiza.
    setTimeout(() => this.campoCodigo()?.nativeElement.focus());
  }

  bipar(): void {
    const codigo = this.codigoBarras().trim();
    if (!codigo || this.ocupado()) return;

    this.ocupado.set(true);
    this.erro.set(null);
    this.produtoNaoReconhecido.set(false);
    this.resultadoAnvisa.set(null);
    this.service
      .bipar(this.tipo, this.processoId, this.pedidoItemId, codigo, this.multiplicador())
      .subscribe({
        next: (processo) => {
          this.ocupado.set(false);
          this.processo.set(processo);
          this.codigoBarras.set('');
          this.multiplicador.set(1);
          this.focarCampo();
        },
        error: (resposta: HttpErrorResponse) => {
          this.ocupado.set(false);
          this.erro.set(resposta.error?.detail ?? 'Leitura recusada.');
          this.produtoNaoReconhecido.set(resposta.status === 422);
          this.ultimaLeituraRecusada.set(codigo);
          // Limpa e devolve o foco: no coletor, corrigir o conteúdo do campo
          // dá mais trabalho do que bipar de novo.
          this.codigoBarras.set('');
          this.focarCampo();
        },
      });
  }

  // -------------------------------------------------------------------------
  // Verificar ANVISA
  //
  // Aparece só quando a leitura foi recusada por código desconhecido. A caixa
  // na mão do operador é o que autoriza: se o código impresso nela está entre
  // os que a CMED publica para o registro do produto, ele passa a valer no
  // cadastro. Quem decide isso é o backend — aqui não há regra nenhuma.
  // -------------------------------------------------------------------------

  /** O código da última leitura recusada. Guardado porque `codigoBarras` é
   *  limpo a cada erro (para o operador poder bipar de novo), e é justamente
   *  ele que precisa ser conferido contra a CMED. */
  private ultimaLeituraRecusada = signal('');

  verificandoAnvisa = signal(false);
  resultadoAnvisa = signal<VincularAnvisaResposta | null>(null);

  podeVerificarAnvisa = computed(
    () => !!this.auth.usuario()?.permissoes.has('produtos.codigo_barras.vincular_anvisa'),
  );

  verificarAnvisa(): void {
    const item = this.item();
    const codigo = this.ultimaLeituraRecusada();
    if (!item || !codigo || this.verificandoAnvisa()) return;

    this.verificandoAnvisa.set(true);
    this.resultadoAnvisa.set(null);
    this.produtoService.vincularCodigosDaAnvisa(item.produtoId, codigo).subscribe({
      next: (resultado) => {
        this.verificandoAnvisa.set(false);
        this.resultadoAnvisa.set(resultado);
        if (resultado.situacao !== 'vinculado') return;
        // Deu match: o código já vale no cadastro, então a leitura que acabou de
        // ser recusada é registrada na hora. Obrigar a bipar de novo depois de
        // o sistema confirmar que é o produto certo seria trabalho à toa.
        this.erro.set(null);
        this.produtoNaoReconhecido.set(false);
        this.codigoBarras.set(codigo);
        this.bipar();
      },
      error: (resposta: HttpErrorResponse) => {
        this.verificandoAnvisa.set(false);
        this.erro.set(resposta.error?.detail ?? 'Não foi possível consultar a ANVISA.');
      },
    });
  }

  fecharResultadoAnvisa(): void {
    this.resultadoAnvisa.set(null);
    this.focarCampo();
  }

  /** Item completo fecha direto; item com falta passa pelo gerente. */
  finalizar(): void {
    if (this.completo()) {
      this.enviarFinalizacao();
      return;
    }
    this.erroSenha.set(null);
    this.pedindoSenha.set(true);
  }

  private enviarFinalizacao(credencial?: CredencialGerente): void {
    this.ocupado.set(true);
    this.service
      .finalizarItem(this.tipo, this.processoId, this.pedidoItemId, credencial)
      .subscribe({
        next: () => {
          this.ocupado.set(false);
          this.pedindoSenha.set(false);
          this.router.navigate(['/expedicao', this.pedidoId, this.tipo, this.processoId]);
        },
        error: (resposta: HttpErrorResponse) => {
          this.ocupado.set(false);
          const mensagem = resposta.error?.detail ?? 'Não foi possível finalizar o item.';
          if (this.pedindoSenha()) this.erroSenha.set(mensagem);
          else this.erro.set(mensagem);
        },
      });
  }

  confirmarComSenha(credencial: CredencialGerente): void {
    this.enviarFinalizacao(credencial);
  }
}
