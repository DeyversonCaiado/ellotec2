import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { debounceTime, distinctUntilChanged, Subject, switchMap } from 'rxjs';
import { PedidoService } from '../pedido.service';
import { ClienteService } from '../../clientes/cliente.service';
import { ProdutoService } from '../../produtos/produto.service';
import { EmpresaService } from '../../empresas/empresa.service';
import { UsuarioService } from '../../usuarios/usuario.service';
import { Cliente } from '../../clientes/cliente.model';
import { Produto } from '../../produtos/produto.model';
import { Empresa } from '../../empresas/empresa.model';
import { UsuarioResumo } from '../../usuarios/usuario.model';
import { ItemPedido, PedidoStatusCatalogo, calcularTotalPedido } from '../pedido.model';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';

@Component({
  selector: 'app-pedido-form',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, IconComponent, PageHeaderComponent],
  templateUrl: './pedido-form.html',
})
export class PedidoForm implements OnInit {
  modoEdicao = signal(false);
  carregando = signal(false);
  pedidoId = signal<string | null>(null);

  // --- cliente ---------------------------------------------------------
  buscaClienteTermo = signal('');
  buscaClienteResultados = signal<Cliente[]>([]);
  buscaClienteAberta = signal(false);
  clienteSelecionado = signal<Cliente | null>(null);
  private buscaCliente$ = new Subject<string>();

  // --- empresa -------------------------------------------------------------
  empresas = signal<Empresa[]>([]);
  empresaId = signal<string>('');

  // --- vendedor --------------------------------------------------------------
  vendedores = signal<UsuarioResumo[]>([]);
  vendedorId = signal<string | null>(null);

  // --- status ----------------------------------------------------------------
  statusCatalogo = signal<PedidoStatusCatalogo[]>([]);
  statusId = signal<string>('');

  // --- produto -----------------------------------------------------------
  buscaProdutoTermo = signal('');
  buscaProdutoResultados = signal<Produto[]>([]);
  buscaProdutoAberta = signal(false);
  private buscaProduto$ = new Subject<string>();

  // --- itens + observações -------------------------------------------------
  itens = signal<ItemPedido[]>([]);
  observacoes = signal('');
  dataPedido = signal(new Date().toISOString().slice(0, 10));

  readonly calcularTotal = calcularTotalPedido;

  constructor(
    private service: PedidoService,
    private clienteService: ClienteService,
    private produtoService: ProdutoService,
    private empresaService: EmpresaService,
    private usuarioService: UsuarioService,
    private route: ActivatedRoute,
    private router: Router,
  ) {
    this.buscaCliente$
      .pipe(
        debounceTime(250),
        distinctUntilChanged(),
        switchMap((termo) => this.clienteService.buscar(termo)),
      )
      .subscribe((resultados) => this.buscaClienteResultados.set(resultados));

    this.buscaProduto$
      .pipe(
        debounceTime(250),
        distinctUntilChanged(),
        switchMap((termo) => this.produtoService.buscar(termo)),
      )
      .subscribe((resultados) => this.buscaProdutoResultados.set(resultados));
  }

  ngOnInit(): void {
    this.empresaService.listar().subscribe((lista) => this.empresas.set(lista));
    this.usuarioService.listarVendedores().subscribe((lista) => this.vendedores.set(lista));
    this.service.listarStatus().subscribe((lista) => {
      this.statusCatalogo.set(lista);
      // Novo pedido, sem status ainda escolhido: default pra chave
      // "rascunho" do catálogo, mesmo comportamento de antes.
      if (!this.modoEdicao() && !this.statusId()) {
        this.statusId.set(lista.find((s) => s.chave === 'rascunho')?.id ?? lista[0]?.id ?? '');
      }
    });

    const id = this.route.snapshot.paramMap.get('id');
    if (!id) return;

    this.modoEdicao.set(true);
    this.pedidoId.set(id);
    this.carregando.set(true);

    this.service.obterPorId(id).subscribe((pedido) => {
      this.carregando.set(false);
      if (!pedido) return;

      this.itens.set(pedido.itens);
      this.statusId.set(pedido.statusId);
      this.observacoes.set(pedido.observacoes);
      this.dataPedido.set(pedido.dataPedido);
      this.empresaId.set(pedido.empresaId);
      this.vendedorId.set(pedido.vendedorId);
      this.clienteSelecionado.set({
        id: pedido.clienteId,
        nomeFantasia: pedido.cliente.nomeFantasia,
        cpfCnpj: pedido.cliente.cnpj,
      } as Cliente);
    });
  }

  // --- cliente -----------------------------------------------------------

  digitarBuscaCliente(termo: string): void {
    this.buscaClienteTermo.set(termo);
    this.buscaClienteAberta.set(termo.length > 0);
    this.buscaCliente$.next(termo);
  }

  selecionarCliente(cliente: Cliente): void {
    this.clienteSelecionado.set(cliente);
    this.buscaClienteAberta.set(false);
    this.buscaClienteTermo.set('');
  }

  removerCliente(): void {
    this.clienteSelecionado.set(null);
  }

  // --- produto -----------------------------------------------------------

  digitarBuscaProduto(termo: string): void {
    this.buscaProdutoTermo.set(termo);
    this.buscaProdutoAberta.set(termo.length > 0);
    this.buscaProduto$.next(termo);
  }

  adicionarProduto(produto: Produto): void {
    const jaExiste = this.itens().some((item) => item.produtoId === produto.id);
    if (jaExiste) {
      this.itens.update((lista) =>
        lista.map((item) => (item.produtoId === produto.id ? { ...item, quantidade: item.quantidade + 1 } : item)),
      );
    } else {
      this.itens.update((lista) => [
        ...lista,
        {
          produtoId: produto.id,
          produtoCodigo: produto.codigo,
          produtoDescricao: produto.descricao,
          quantidade: 1,
          precoUnitario: 0,
        },
      ]);
    }
    this.buscaProdutoAberta.set(false);
    this.buscaProdutoTermo.set('');
  }

  atualizarQuantidade(produtoId: string, quantidade: number): void {
    const quantidadeValida = Math.max(1, quantidade || 1);
    this.itens.update((lista) =>
      lista.map((item) => (item.produtoId === produtoId ? { ...item, quantidade: quantidadeValida } : item)),
    );
  }

  removerItem(produtoId: string): void {
    this.itens.update((lista) => lista.filter((item) => item.produtoId !== produtoId));
  }

  // --- salvar --------------------------------------------------------------

  podeSalvar(): boolean {
    return !!this.clienteSelecionado() && !!this.empresaId() && !!this.statusId() && this.itens().length > 0;
  }

  salvar(): void {
    const cliente = this.clienteSelecionado();
    if (!cliente || !this.empresaId() || !this.statusId() || this.itens().length === 0) return;

    this.carregando.set(true);

    const dados = {
      dataPedido: this.dataPedido(),
      clienteId: cliente.id,
      clienteNomeFantasia: cliente.nomeFantasia,
      clienteCnpj: cliente.cpfCnpj,
      empresaId: this.empresaId(),
      vendedorId: this.vendedorId(),
      itens: this.itens(),
      statusId: this.statusId(),
      observacoes: this.observacoes(),
    };

    const id = this.pedidoId();
    const operacao = id ? this.service.atualizar(id, dados) : this.service.criar(dados);

    operacao.subscribe(() => {
      this.carregando.set(false);
      this.router.navigate(['/pedidos']);
    });
  }
}
