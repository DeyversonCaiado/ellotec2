import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { AuthService } from './auth.service';
import { DispositivoService } from './dispositivo.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const dispositivo = inject(DispositivoService);
  const router = inject(Router);

  const token = auth.obterToken();

  // Injeta X-Device-Id em TODOS os requests (inclusive o login, que precisa
  // dele para criar a sessão vinculada ao dispositivo). Injeta Bearer token
  // apenas nos requests onde já há sessão ativa.
  const headers: Record<string, string> = {
    'X-Device-Id': dispositivo.deviceId,
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const requisicao = req.clone({ setHeaders: headers });

  return next(requisicao).pipe(
    catchError((erro) => {
      if (erro.status === 401) {
        auth.logout();
        router.navigate(['/login']);
      }

      // Backend recusou por falta de permissão — provavelmente alguém
      // (um admin, em outra sessão) mudou as permissões deste usuário
      // depois do login. O AuthService local ainda acha que ele tem
      // acesso (é só um snapshot do login), então o menu/guards client-
      // side não teriam como saber. Resincroniza com /auth/me e tira o
      // usuário da tela que ele não pode mais ver.
      if (erro.status === 403) {
        auth.sincronizarUsuarioLogado().subscribe(() => router.navigate(['/']));
      }

      return throwError(() => erro);
    }),
  );
};
