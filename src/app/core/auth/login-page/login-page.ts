import { Component, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthService } from '../auth.service';

@Component({
  selector: 'app-login-page',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './login-page.html',
})
export class LoginPage {
  private fb = inject(FormBuilder);
  private auth = inject(AuthService);
  private router = inject(Router);

  carregando = signal(false);
  erro = signal<string | null>(null);
  mostrarSenha = signal(false);

  form = this.fb.nonNullable.group({
    email: ['', [Validators.required]],
    senha: ['', [Validators.required, Validators.minLength(4)]],
  });

  alternarSenha(): void {
    this.mostrarSenha.update((v) => !v);
  }

  enviar(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.erro.set(null);
    this.carregando.set(true);

    const { email, senha } = this.form.getRawValue();
    const payload = email.includes('@') ? { email, senha } : { usuario: email, senha };

    this.auth.login(payload).subscribe({
      next: () => {
        this.carregando.set(false);
        this.router.navigate(['/']);
      },
      error: (falha: HttpErrorResponse) => {
        this.carregando.set(false);
        // Status 0 = a resposta nunca chegou: servidor fora do ar, host errado
        // ou CORS bloqueando. Chamar isso de "senha inválida" mandou mais de
        // uma pessoa procurar erro na senha certa — principalmente no coletor,
        // onde o endereço da API é diferente do PC.
        if (falha?.status === 0) {
          this.erro.set(
            'Não foi possível falar com o servidor. Verifique se a API está no ar e se este endereço tem acesso a ela.',
          );
          return;
        }
        if (falha?.status === 400) {
          this.erro.set('Requisição recusada pelo servidor. Recarregue a página e tente de novo.');
          return;
        }
        this.erro.set('E-mail ou senha inválidos. Tente novamente.');
      },
    });
  }
}
