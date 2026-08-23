import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IconComponent } from './icon.component';

@Component({
  selector: 'app-page-header',
  standalone: true,
  imports: [CommonModule, IconComponent],
  template: `
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
      <div>
        <nav class="text-xs text-gray-400 dark:text-gray-500 flex items-center gap-1.5 mb-1.5">
          <span>Início</span>
          <app-icon name="chevron-right" class="size-3" />
          <span class="text-gray-600 dark:text-gray-300 font-medium">{{ titulo }}</span>
        </nav>
        <h1 class="text-xl font-bold text-gray-900 dark:text-gray-50">{{ titulo }}</h1>
        @if (subtitulo) {
          <p class="text-sm text-gray-400 dark:text-gray-500 mt-0.5">{{ subtitulo }}</p>
        }
      </div>
      <div class="flex items-center gap-2">
        <ng-content />
      </div>
    </div>
  `,
})
export class PageHeaderComponent {
  @Input() titulo = '';
  @Input() subtitulo?: string;
}
