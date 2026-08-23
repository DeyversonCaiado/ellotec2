import { Component, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AuthService } from '../../auth/auth.service';
import { IconComponent } from '../../../shared/ui/icon.component';

@Component({
  selector: 'app-home-page',
  standalone: true,
  imports: [CommonModule, IconComponent],
  templateUrl: './home-page.html',
})
export class HomePage {
  usuario = computed(() => this.auth.usuario());

  /** Pontos fictícios pro gráfico de barras semanal (só visual, fiel à referência). */
  graficoSemana = [
    { dia: 'Seg', valor: 28 },
    { dia: 'Ter', valor: 24 },
    { dia: 'Qua', valor: 22 },
    { dia: 'Qui', valor: 26 },
    { dia: 'Sex', valor: 20 },
    { dia: 'Sáb', valor: 18 },
    { dia: 'Dom', valor: 34 },
  ];

  constructor(private auth: AuthService) {}
}
