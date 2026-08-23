import { Component, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
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
      error: () => {
        this.carregando.set(false);
        this.erro.set('E-mail ou senha inválidos. Tente novamente.');
      },
    });
  }
}
