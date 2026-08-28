import {
  AfterViewInit,
  Component,
  ElementRef,
  OnDestroy,
  OnInit,
  ViewChild,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Observable, Subject, Subscription, debounceTime, distinctUntilChanged } from 'rxjs';
import { EnderecamentoService } from '../enderecamento.service';
import {
  AbaEnderecamento,
  EnderecoEstoque,
  VinculoEnderecoLote,
} from '../enderecamento.model';
import { EmpresaService } from '../../empresas/empresa.service';
import { Empresa } from '../../empresas/empresa.model';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';
import { PermissaoDirective } from '../../../core/permissions/permissao.directive';

const PER_PAGE = 20;

/**
 * Tela de endereçamento, em duas abas.
 *
 * A aba padrão é **"Onde está"**: a pergunta do dia a dia é "onde eu acho este
 * produto", não "que prateleiras existem". A aba "Endereços" é o cadastro dos
 * lugares, que muda pouco — nasce quando o galpão monta uma prateleira nova.
 *
 * A busca é UM campo só para os dois casos, porque quem procura não quer
 * escolher em qual campo procurar: ele digita o que tem na mão (o código da
 * caixa, o número da etiqueta da prateleira, o lote) e espera achar. Quem
 * decide o que casa com o quê é o backend — ver `listarVinculos` no service.
 */
@Component({
  selector: 'app-endereco-list',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterLink,
    IconComponent,
    PageHeaderComponent,
    PermissaoDirective,
  ],
  templateUrl: './endereco-list.html',
})
export class EnderecoList implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('sentinela') sentinela?: ElementRef<HTMLElement>;

  private service = inject(EnderecamentoService);
  // Leitura do domínio dono do cadastro de empresas — o canal correto no
  // front é injetar o service (ver ARCHITECTURE.md → "Regras de import").
  private empresaService = inject(EmpresaService);

  aba = signal<AbaEnderecamento>('vinculos');
  vinculos = signal<VinculoEnderecoLote[]>([]);
  enderecos = signal<EnderecoEstoque[]>([]);
  empresas = signal<Empresa[]>([]);
  carregando = signal(true);
  carregandoMais = signal(false);
  termoBusca = signal('');
  empresaId = signal('');
  temMais = signal(true);

  private pagina = 1;
  private observer?: IntersectionObserver;
  private readonly busca$ = new Subject<string>();
  private readonly buscaSub: Subscription;

  constructor() {
    this.buscaSub = this.busca$
      .pipe(debounceTime(400), distinctUntilChanged())
      .subscribe(() => this.buscarDoInicio());
  }

  ngOnInit(): void {
    this.empresaService.listar().subscribe((lista) => this.empresas.set(lista));
    this.buscarDoInicio();
  }

  ngAfterViewInit(): void {
    if (!this.sentinela) return;
    this.observer = new IntersectionObserver((entradas) => {
      if (entradas[0].isIntersecting) this.carregarMais();
    });
    this.observer.observe(this.sentinela.nativeElement);
  }

  ngOnDestroy(): void {
    this.observer?.disconnect();
    this.buscaSub.unsubscribe();
  }

  trocarAba(aba: AbaEnderecamento): void {
    if (this.aba() === aba) return;
    this.aba.set(aba);
    this.buscarDoInicio();
  }

  /** O placeholder muda com a aba porque a busca de fato procura coisas
   *  diferentes em cada uma — prometer "código de barras" na aba de cadastro
   *  seria mentira. */
  placeholderBusca(): string {
    return this.aba() === 'vinculos'
      ? 'Buscar por produto, código, código de barras, endereço ou lote...'
      : 'Buscar por descrição do endereço...';
  }

  onTermoBuscaChange(valor: string): void {
    this.termoBusca.set(valor);
    this.busca$.next(valor);
  }

  onEmpresaChange(valor: string): void {
    this.empresaId.set(valor);
    this.buscarDoInicio();
  }

  nomeEmpresa(id: string): string {
    const empresa = this.empresas().find((e) => e.id === id);
    return empresa?.apelido || empresa?.nomeFantasia || '—';
  }

  vazio(): boolean {
    return this.aba() === 'vinculos'
      ? this.vinculos().length === 0
      : this.enderecos().length === 0;
  }

  /** As duas abas devolvem páginas de tipos diferentes; o retorno é declarado
   *  no formato comum para o `?:` ter um tipo só — sem isso o TypeScript vê uma
   *  união de dois Observables e não deixa nem chamar `.subscribe`. */
  private carregarPagina(pagina: number): Observable<{
    items: (VinculoEnderecoLote | EnderecoEstoque)[];
    total: number;
    page: number;
    perPage: number;
  }> {
    return this.aba() === 'vinculos'
      ? this.service.listarVinculos(pagina, PER_PAGE, this.termoBusca(), this.empresaId())
      : this.service.listarPagina(pagina, PER_PAGE, this.termoBusca(), this.empresaId());
  }

  private buscarDoInicio(): void {
    this.pagina = 1;
    this.temMais.set(true);
    this.carregando.set(true);
    this.carregarPagina(this.pagina).subscribe((resposta) => {
      if (this.aba() === 'vinculos') {
        this.vinculos.set(resposta.items as VinculoEnderecoLote[]);
      } else {
        this.enderecos.set(resposta.items as EnderecoEstoque[]);
      }
      this.temMais.set(
        resposta.items.length > 0 && resposta.page * resposta.perPage < resposta.total,
      );
      this.carregando.set(false);
    });
  }

  carregarMais(): void {
    if (this.carregando() || this.carregandoMais() || !this.temMais()) return;
    this.carregandoMais.set(true);
    const proximaPagina = this.pagina + 1;
    this.carregarPagina(proximaPagina).subscribe((resposta) => {
      this.pagina = proximaPagina;
      if (this.aba() === 'vinculos') {
        this.vinculos.update((lista) => [...lista, ...(resposta.items as VinculoEnderecoLote[])]);
      } else {
        this.enderecos.update((lista) => [...lista, ...(resposta.items as EnderecoEstoque[])]);
      }
      this.temMais.set(
        resposta.items.length > 0 && resposta.page * resposta.perPage < resposta.total,
      );
      this.carregandoMais.set(false);
    });
  }

  apagar(endereco: EnderecoEstoque): void {
    if (!confirm(`Apagar o endereço "${endereco.descricao}"? Essa ação não pode ser desfeita.`))
      return;
    this.service.apagar(endereco.id).subscribe(() => {
      this.enderecos.update((lista) => lista.filter((e) => e.id !== endereco.id));
    });
  }
}
