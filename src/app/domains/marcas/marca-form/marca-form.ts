import { Component, OnInit, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MarcaService } from '../marca.service';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';

@Component({
  selector: 'app-marca-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink, IconComponent, PageHeaderComponent],
  templateUrl: './marca-form.html',
})
export class MarcaForm implements OnInit {
  private fb = inject(FormBuilder);
  private service = inject(MarcaService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  modoEdicao = signal(false);
  carregando = signal(false);
  marcaId = signal<string | null>(null);

  form = this.fb.nonNullable.group({
    nome: ['', Validators.required],
    ativo: [true],
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) return;

    this.modoEdicao.set(true);
    this.marcaId.set(id);
    this.carregando.set(true);

    this.service.obterPorId(id).subscribe((marca) => {
      this.carregando.set(false);
      if (marca) this.form.patchValue(marca);
    });
  }

  salvar(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.carregando.set(true);
    const dados = this.form.getRawValue();
    const id = this.marcaId();
    const operacao = id ? this.service.atualizar(id, dados) : this.service.criar(dados);

    operacao.subscribe(() => {
      this.carregando.set(false);
      this.router.navigate(['/marcas']);
    });
  }
}
