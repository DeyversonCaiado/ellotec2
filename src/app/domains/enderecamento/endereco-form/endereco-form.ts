import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { EnderecamentoService } from '../enderecamento.service';
import { EmpresaService } from '../../empresas/empresa.service';
import { Empresa } from '../../empresas/empresa.model';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';

@Component({
  selector: 'app-endereco-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink, IconComponent, PageHeaderComponent],
  templateUrl: './endereco-form.html',
})
export class EnderecoForm implements OnInit {
  private fb = inject(FormBuilder);
  private service = inject(EnderecamentoService);
  private empresaService = inject(EmpresaService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  modoEdicao = signal(false);
  carregando = signal(false);
  erro = signal<string | null>(null);
  enderecoId = signal<string | null>(null);
  empresas = signal<Empresa[]>([]);

  form = this.fb.nonNullable.group({
    descricao: ['', Validators.required],
    // Obrigatória: o mesmo código de prateleira existe em cada filial, então
    // é o par (empresa, descrição) que identifica o endereço.
    empresaId: ['', Validators.required],
  });

  ngOnInit(): void {
    this.empresaService.listar().subscribe((lista) => this.empresas.set(lista));

    const id = this.route.snapshot.paramMap.get('id');
    if (!id) return;

    this.modoEdicao.set(true);
    this.enderecoId.set(id);
    this.carregando.set(true);

    this.service.obterPorId(id).subscribe({
      next: (endereco) => {
        this.carregando.set(false);
        this.form.patchValue({
          descricao: endereco.descricao,
          empresaId: endereco.empresaId,
        });
      },
      error: () => {
        this.carregando.set(false);
        this.erro.set('Não foi possível carregar o endereço.');
      },
    });
  }

  salvar(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.carregando.set(true);
    this.erro.set(null);
    const dados = this.form.getRawValue();
    const id = this.enderecoId();
    const operacao = id ? this.service.atualizar(id, dados) : this.service.criar(dados);

    operacao.subscribe({
      next: () => {
        this.carregando.set(false);
        this.router.navigate(['/enderecamento']);
      },
      error: (resposta) => {
        this.carregando.set(false);
        // 409 é o caso esperado: descrição repetida na mesma empresa.
        this.erro.set(resposta?.error?.detail ?? 'Não foi possível salvar o endereço.');
      },
    });
  }
}
