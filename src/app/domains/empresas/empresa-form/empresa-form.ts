import { Component, OnInit, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { EmpresaService } from '../empresa.service';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';

@Component({
  selector: 'app-empresa-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink, IconComponent, PageHeaderComponent],
  templateUrl: './empresa-form.html',
})
export class EmpresaForm implements OnInit {
  private fb = inject(FormBuilder);
  private service = inject(EmpresaService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  modoEdicao = signal(false);
  carregando = signal(false);
  empresaId = signal<string | null>(null);

  form = this.fb.nonNullable.group({
    codigo: [''],
    razaoSocial: ['', Validators.required],
    nomeFantasia: ['', Validators.required],
    // O apelido precisa estar no formulário, e não só no model: o PUT manda o
    // objeto inteiro, então um campo ausente aqui chegava ao backend como nulo
    // e APAGAVA o apelido a cada edição de empresa.
    apelido: [''],
    cnpj: ['', Validators.required],
    ativo: [true],
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) return;

    this.modoEdicao.set(true);
    this.empresaId.set(id);
    this.carregando.set(true);

    this.service.obterPorId(id).subscribe((empresa) => {
      this.carregando.set(false);
      if (empresa) {
        this.form.patchValue({
          ...empresa,
          codigo: empresa.codigo ?? '',
          apelido: empresa.apelido ?? '',
        });
      }
    });
  }

  salvar(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.carregando.set(true);
    const dados = this.form.getRawValue();
    const id = this.empresaId();
    const operacao = id ? this.service.atualizar(id, dados) : this.service.criar(dados);

    operacao.subscribe(() => {
      this.carregando.set(false);
      this.router.navigate(['/empresas']);
    });
  }
}
