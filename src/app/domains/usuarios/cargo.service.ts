import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, delay, of, tap } from 'rxjs';
import { environment } from '../../environments/environment';
import { Cargo } from './cargo.model';

const ENDPOINT = `${environment.apiUrl}/cargos`;

@Injectable({ providedIn: 'root' })
export class CargoService {
  private readonly _cargos = signal<Cargo[]>(this.dadosFicticios());
  readonly cargos = this._cargos.asReadonly();

  constructor(private http: HttpClient) {}

  listar(): Observable<Cargo[]> {
    if (environment.mockAuth) {
      return of(this._cargos()).pipe(delay(300));
    }
    return this.http.get<Cargo[]>(ENDPOINT).pipe(tap((lista) => this._cargos.set(lista)));
  }

  private dadosFicticios(): Cargo[] {
    return [
      { id: 'crg-001', nome: 'Gerente' },
      { id: 'crg-002', nome: 'Funcionario' },
    ];
  }
}
