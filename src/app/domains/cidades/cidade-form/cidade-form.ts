import { Component, OnInit, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { CidadeService } from '../cidade.service';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';

@Component({
  selector: 'app-cidade-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink, IconComponent, PageHeaderComponent],
  templateUrl: './cidade-form.html',
})
export class CidadeForm implements OnInit {
  private fb = inject(FormBuilder);
  private service = inject(CidadeService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  modoEdicao = signal(false);
  carregando = signal(false);
  cidadeId = signal<string | null>(null);

  form = this.fb.nonNullable.group({
    codigoMunicipio: [0, [Validators.required, Validators.min(1)]],
    nome: ['', Validators.required],
    uf: ['', [Validators.required, Validators.maxLength(2), Validators.minLength(2)]],
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) return;

    this.modoEdicao.set(true);
    this.cidadeId.set(id);
    this.carregando.set(true);

    this.service.obterPorId(id).subscribe((cidade) => {
      this.carregando.set(false);
      if (cidade) this.form.patchValue(cidade);
      // Código do município, UF e nome vêm do cadastro oficial do IBGE — não editáveis.
      this.form.controls.codigoMunicipio.disable();
      this.form.controls.uf.disable();
      this.form.controls.nome.disable();
    });
  }

  salvar(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.carregando.set(true);
    const dados = this.form.getRawValue();
    const id = this.cidadeId();
    const operacao = id ? this.service.atualizar(id, dados) : this.service.criar(dados);

    operacao.subscribe(() => {
      this.carregando.set(false);
      this.router.navigate(['/cidades']);
    });
  }
}
