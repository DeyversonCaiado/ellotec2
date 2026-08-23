import { AfterViewInit, Component, ElementRef, OnDestroy, OnInit, signal, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Subject, debounceTime, distinctUntilChanged, Subscription } from 'rxjs';
import { MarcaService } from '../marca.service';
import { Marca } from '../marca.model';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';
import { PermissaoDirective } from '../../../core/permissions/permissao.directive';

const PER_PAGE = 20;

@Component({
  selector: 'app-marca-list',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, IconComponent, PageHeaderComponent, PermissaoDirective],
  templateUrl: './marca-list.html',
})
export class MarcaList implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('sentinela') sentinela?: ElementRef<HTMLElement>;

  marcas = signal<Marca[]>([]);
  carregando = signal(true);
  carregandoMais = signal(false);
  termoBusca = signal('');
  temMais = signal(true);

  private pagina = 1;
  private observer?: IntersectionObserver;
  private readonly busca$ = new Subject<string>();
  private readonly buscaSub: Subscription;

  constructor(private service: MarcaService) {
    this.buscaSub = this.busca$.pipe(debounceTime(400), distinctUntilChanged()).subscribe(() => this.buscarDoInicio());
  }

  ngOnInit(): void {
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

  onTermoBuscaChange(valor: string): void {
    this.termoBusca.set(valor);
    this.busca$.next(valor);
  }

  private buscarDoInicio(): void {
    this.pagina = 1;
    this.temMais.set(true);
    this.carregando.set(true);
    this.service.listarPagina(this.pagina, PER_PAGE, this.termoBusca()).subscribe((resposta) => {
      this.marcas.set(resposta.items);
      this.temMais.set(resposta.items.length > 0 && resposta.page * resposta.perPage < resposta.total);
      this.carregando.set(false);
    });
  }

  carregarMais(): void {
    if (this.carregando() || this.carregandoMais() || !this.temMais()) return;
    this.carregandoMais.set(true);
    const proximaPagina = this.pagina + 1;
    this.service.listarPagina(proximaPagina, PER_PAGE, this.termoBusca()).subscribe((resposta) => {
      this.pagina = proximaPagina;
      this.marcas.update((lista) => [...lista, ...resposta.items]);
      this.temMais.set(resposta.items.length > 0 && resposta.page * resposta.perPage < resposta.total);
      this.carregandoMais.set(false);
    });
  }

  apagar(marca: Marca): void {
    if (!confirm(`Apagar a marca "${marca.nome}"? Essa ação não pode ser desfeita.`)) return;
    this.service.apagar(marca.id).subscribe(() => {
      this.marcas.update((lista) => lista.filter((m) => m.id !== marca.id));
    });
  }
}
