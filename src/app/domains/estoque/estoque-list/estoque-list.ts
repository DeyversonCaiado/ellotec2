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
import { EstoqueService } from '../estoque.service';
import { AbaEstoque, LoteEstoque, SaldoEstoque } from '../estoque.model';
import { EmpresaService } from '../../empresas/empresa.service';
import { Empresa } from '../../empresas/empresa.model';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';

const PER_PAGE = 20;

@Component({
  selector: 'app-estoque-list',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent, PageHeaderComponent],
  templateUrl: './estoque-list.html',
})
export class EstoqueList implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('sentinela') sentinela?: ElementRef<HTMLElement>;

  private service = inject(EstoqueService);
  private empresaService = inject(EmpresaService);

  aba = signal<AbaEstoque>('saldos');
  saldos = signal<SaldoEstoque[]>([]);
  lotes = signal<LoteEstoque[]>([]);
  empresas = signal<Empresa[]>([]);
  empresaId = signal('');
  carregando = signal(true);
  carregandoMais = signal(false);
  temMais = signal(true);

  private pagina = 1;
  private observer?: IntersectionObserver;

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
  }

  trocarAba(aba: AbaEstoque): void {
    if (this.aba() === aba) return;
    this.aba.set(aba);
    this.buscarDoInicio();
  }

  onEmpresaChange(valor: string): void {
    this.empresaId.set(valor);
    this.buscarDoInicio();
  }

  nomeEmpresa(id: string): string {
    const empresa = this.empresas().find((e) => e.id === id);
    return empresa?.apelido || empresa?.nomeFantasia || '—';
  }

  /** Quantos dias faltam para o lote vencer. Negativo = já venceu. */
  diasParaVencer(vencimento: string | null): number | null {
    if (!vencimento) return null;
    const hoje = new Date();
    hoje.setHours(0, 0, 0, 0);
    const alvo = new Date(vencimento + 'T00:00:00');
    return Math.round((alvo.getTime() - hoje.getTime()) / 86_400_000);
  }

  private buscarDoInicio(): void {
    this.pagina = 1;
    this.temMais.set(true);
    this.carregando.set(true);
    this.saldos.set([]);
    this.lotes.set([]);
    this.buscar(1, (resposta) => {
      if (this.aba() === 'saldos') this.saldos.set(resposta.items as SaldoEstoque[]);
      else this.lotes.set(resposta.items as LoteEstoque[]);
      this.aplicarPagina(resposta);
      this.carregando.set(false);
    });
  }

  carregarMais(): void {
    if (this.carregando() || this.carregandoMais() || !this.temMais()) return;
    this.carregandoMais.set(true);
    const proximaPagina = this.pagina + 1;
    this.buscar(proximaPagina, (resposta) => {
      this.pagina = proximaPagina;
      if (this.aba() === 'saldos')
        this.saldos.update((lista) => [...lista, ...(resposta.items as SaldoEstoque[])]);
      else this.lotes.update((lista) => [...lista, ...(resposta.items as LoteEstoque[])]);
      this.aplicarPagina(resposta);
      this.carregandoMais.set(false);
    });
  }

  private buscar(
    page: number,
    aoResponder: (resposta: { items: unknown[]; page: number; perPage: number; total: number }) => void,
  ): void {
    const requisicao =
      this.aba() === 'saldos'
        ? this.service.listarSaldos(page, PER_PAGE, this.empresaId())
        : this.service.listarLotes(page, PER_PAGE, this.empresaId());
    requisicao.subscribe((resposta) => aoResponder(resposta));
  }

  private aplicarPagina(resposta: { items: unknown[]; page: number; perPage: number; total: number }): void {
    this.temMais.set(resposta.items.length > 0 && resposta.page * resposta.perPage < resposta.total);
  }
}
