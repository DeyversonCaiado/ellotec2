import { Component, OnInit, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { debounceTime, distinctUntilChanged, Subject, switchMap } from 'rxjs';
import { ClienteService } from '../cliente.service';
import { CidadeService } from '../../cidades/cidade.service';
import { Cidade } from '../../cidades/cidade.model';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';

@Component({
  selector: 'app-cliente-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, FormsModule, RouterLink, IconComponent, PageHeaderComponent],
  templateUrl: './cliente-form.html',
})
export class ClienteForm implements OnInit {
  private fb = inject(FormBuilder);
  private service = inject(ClienteService);
  private cidadeService = inject(CidadeService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  modoEdicao = signal(false);
  carregando = signal(false);
  clienteId = signal<string | null>(null);

  // --- cidade --------------------------------------------------------------
  buscaCidadeTermo = signal('');
  buscaCidadeResultados = signal<Cidade[]>([]);
  buscaCidadeAberta = signal(false);
  cidadeSelecionada = signal<Cidade | null>(null);
  private buscaCidade$ = new Subject<string>();

  form = this.fb.nonNullable.group({
    codigo: [''],
    razaoSocial: ['', [Validators.required, Validators.minLength(3)]],
    nomeFantasia: ['', Validators.required],
    cpfCnpj: ['', [Validators.required, Validators.pattern(/^(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}\/\d{4}-\d{2})$/)]],
    email: ['', Validators.email],
    telefone: ['', Validators.required],
    celular: [''],
    logradouro: [''],
    numero: [''],
    complemento: [''],
    bairro: [''],
    cep: [''],
    cidadeId: ['', Validators.required],
    ativo: [true],
  });

  constructor() {
    this.buscaCidade$
      .pipe(
        debounceTime(250),
        distinctUntilChanged(),
        switchMap((termo) => this.cidadeService.buscar(termo)),
      )
      .subscribe((resultados) => this.buscaCidadeResultados.set(resultados));
  }

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) return;

    this.modoEdicao.set(true);
    this.clienteId.set(id);
    this.carregando.set(true);

    this.service.obterPorId(id).subscribe((cliente) => {
      this.carregando.set(false);
      if (!cliente) return;

      this.form.patchValue({
        ...cliente,
        codigo: cliente.codigo ?? '',
        email: cliente.email ?? '',
        celular: cliente.celular ?? '',
        logradouro: cliente.logradouro ?? '',
        numero: cliente.numero ?? '',
        complemento: cliente.complemento ?? '',
        bairro: cliente.bairro ?? '',
        cep: cliente.cep ?? '',
      });
      this.cidadeSelecionada.set({
        id: cliente.cidadeId,
        nome: cliente.cidadeNome,
        uf: cliente.cidadeUf,
      } as Cidade);
    });
  }

  digitarBuscaCidade(termo: string): void {
    this.buscaCidadeTermo.set(termo);
    this.buscaCidadeAberta.set(termo.length > 0);
    this.buscaCidade$.next(termo);
  }

  selecionarCidade(cidade: Cidade): void {
    this.cidadeSelecionada.set(cidade);
    this.form.patchValue({ cidadeId: cidade.id });
    this.buscaCidadeAberta.set(false);
    this.buscaCidadeTermo.set('');
  }

  removerCidade(): void {
    this.cidadeSelecionada.set(null);
    this.form.patchValue({ cidadeId: '' });
  }

  salvar(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.carregando.set(true);
    const dados = this.form.getRawValue();
    const id = this.clienteId();
    const operacao = id ? this.service.atualizar(id, dados) : this.service.criar(dados);

    operacao.subscribe(() => {
      this.carregando.set(false);
      this.router.navigate(['/clientes']);
    });
  }
}
