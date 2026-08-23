import { Component, OnInit, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ProdutoService } from '../produto.service';
import { MarcaService } from '../../marcas/marca.service';
import { Marca } from '../../marcas/marca.model';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';

@Component({
  selector: 'app-produto-form',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule, RouterLink, IconComponent, PageHeaderComponent],
  templateUrl: './produto-form.html',
})
export class ProdutoForm implements OnInit {
  private fb = inject(FormBuilder);
  private service = inject(ProdutoService);
  private marcaService = inject(MarcaService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  modoEdicao = signal(false);
  carregando = signal(false);
  produtoId = signal<string | null>(null);
  marcas = signal<Marca[]>([]);

  /** Campo de entrada da seção de logística — fora do FormGroup de propósito:
   *  ele não é um campo do produto, é o que o operador está digitando antes de
   *  virar um item da lista. */
  novoCodigoLogistica = signal('');

  form = this.fb.nonNullable.group({
    codigo: ['', Validators.required],
    descricao: ['', [Validators.required, Validators.minLength(3)]],
    unidade: ['UN', Validators.required],
    codigoBarraNotas: [''],
    codigosBarrasLogistica: this.fb.nonNullable.array<string>([]),
    dun14: [''],
    quantidadeMultiplaVenda: [1, [Validators.required, Validators.min(1)]],
    registroAnvisa: [''],
    marcaId: ['', Validators.required],
    sistemaOrigemId: [''],
    ativo: [true],
  });

  protected get codigosLogistica() {
    return this.form.controls.codigosBarrasLogistica;
  }

  ngOnInit(): void {
    this.marcaService.listar().subscribe((marcas) => this.marcas.set(marcas));

    const id = this.route.snapshot.paramMap.get('id');
    if (!id) return;

    this.modoEdicao.set(true);
    this.produtoId.set(id);
    this.carregando.set(true);

    this.service.obterPorId(id).subscribe((produto) => {
      this.carregando.set(false);
      if (!produto) return;
      this.form.patchValue({
        ...produto,
        sistemaOrigemId: produto.sistemaOrigemId ?? '',
        codigoBarraNotas: produto.codigoBarraNotas ?? '',
        dun14: produto.dun14 ?? '',
        registroAnvisa: produto.registroAnvisa ?? '',
        quantidadeMultiplaVenda: produto.quantidadeMultiplaVenda ?? 1,
      });
      // FormArray não é preenchido por patchValue: ele não cria controle que
      // não existe. A lista tem que ser remontada a cada carga.
      this.codigosLogistica.clear();
      for (const codigo of produto.codigosBarrasLogistica ?? []) {
        this.codigosLogistica.push(this.fb.nonNullable.control(codigo));
      }
    });
  }

  /** Repetido é ignorado em silêncio: nesta tela o operador bipa um código
   *  atrás do outro, e bipar duas vezes o mesmo é acidente, não erro. */
  adicionarCodigoLogistica(): void {
    const codigo = this.novoCodigoLogistica().trim();
    this.novoCodigoLogistica.set('');
    if (!codigo || this.codigosLogistica.getRawValue().includes(codigo)) return;
    this.codigosLogistica.push(this.fb.nonNullable.control(codigo));
  }

  removerCodigoLogistica(indice: number): void {
    this.codigosLogistica.removeAt(indice);
  }

  salvar(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.carregando.set(true);
    const dados = this.form.getRawValue();
    const id = this.produtoId();
    const operacao = id ? this.service.atualizar(id, dados) : this.service.criar(dados);

    operacao.subscribe(() => {
      this.carregando.set(false);
      this.router.navigate(['/produtos']);
    });
  }
}
