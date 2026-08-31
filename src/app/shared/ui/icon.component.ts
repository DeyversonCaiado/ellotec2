import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

/**
 * Ícone simples por nome. Não é uma biblioteca de ícones de verdade —
 * é só um switch de paths SVG pros ícones que o layout usa. Trocar isso
 * por lucide-angular ou outra lib no futuro é uma troca de implementação
 * isolada nesse único arquivo (abstração por dor: hoje não tem dor
 * nenhuma em manter assim).
 */
@Component({
  selector: 'app-icon',
  standalone: true,
  imports: [CommonModule],
  template: `
    <svg [class]="class" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      @switch (name) {
        @case ('layout') { <rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/> }
        @case ('activity') { <path d="M22 12h-4l-3 9L9 3l-3 9H2"/> }
        @case ('chart') { <path d="M3 3v18h18"/><rect x="7" y="12" width="3" height="6" rx="1"/><rect x="12" y="8" width="3" height="10" rx="1"/><rect x="17" y="4" width="3" height="14" rx="1"/> }
        @case ('dollar') { <line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/> }
        @case ('crypto') { <circle cx="12" cy="12" r="9"/><path d="M9.5 8h3.2a2 2 0 1 1 0 4H9.5m0 0h3.6a2 2 0 1 1 0 4H9.5M11 6v2m0 8v2"/> }
        @case ('users') { <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/> }
        @case ('contacts') { <circle cx="12" cy="8" r="4"/><path d="M5 21v-1a7 7 0 0 1 14 0v1"/> }
        @case ('box') { <path d="M21 8 12 3 3 8l9 5 9-5Z"/><path d="M3 8v8l9 5 9-5V8"/><path d="M12 13v8"/> }
        @case ('file-text') { <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M9 13h6M9 17h6M9 9h1"/> }
        @case ('image') { <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/> }
        @case ('academy') { <path d="M22 10 12 5 2 10l10 5 10-5Z"/><path d="M6 12v5c0 1.5 2.5 3 6 3s6-1.5 6-3v-5"/> }
        @case ('calendar') { <rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/> }
        @case ('message') { <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/> }
        @case ('shopping') { <circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.7 13.4a2 2 0 0 0 2 1.6h9.7a2 2 0 0 0 2-1.6L23 6H6"/> }
        @case ('folder') { <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/> }
        @case ('help') { <circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 2-3 4"/><path d="M12 17h.01"/> }
        @case ('mail') { <rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 5L2 7"/> }
        @case ('notes') { <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M7 8h10M7 12h6"/> }
        @case ('scrumboard') { <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18M15 3v18"/> }
        @case ('star') { <path d="m12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.9L12 17.8 5.8 21l1.2-6.9-5-4.9 6.9-1Z"/> }
        @case ('bell') { <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a2 2 0 0 0 3.4 0"/> }
        @case ('search') { <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/> }
        @case ('settings') { <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/> }
        @case ('logout') { <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/> }
        @case ('chevron-down') { <path d="m6 9 6 6 6-6"/> }
        @case ('plus') { <path d="M12 5v14M5 12h14"/> }
        @case ('edit') { <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="m18.5 2.5 3 3L12 15l-4 1 1-4Z"/> }
        @case ('trash') { <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L4 6"/> }
        @case ('eye') { <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z"/><circle cx="12" cy="12" r="3"/> }
        @case ('grip') { <circle cx="9" cy="6" r="1.2"/><circle cx="15" cy="6" r="1.2"/><circle cx="9" cy="12" r="1.2"/><circle cx="15" cy="12" r="1.2"/><circle cx="9" cy="18" r="1.2"/><circle cx="15" cy="18" r="1.2"/> }
        @case ('chevron-right') { <path d="m9 6 6 6-6 6"/> }
        @case ('chevron-left') { <path d="m15 6-6 6 6 6"/> }
        @case ('check') { <path d="M20 6 9 17l-5-5"/> }
        @case ('x') { <path d="M18 6 6 18M6 6l12 12"/> }
        @case ('sun') { <circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/> }
        @case ('truck') { <path d="M10 17V5a1 1 0 0 0-1-1H2v12a1 1 0 0 0 1 1h1"/><path d="M14 17h-4"/><path d="M20 17h1a1 1 0 0 0 1-1v-4l-3-4h-5v9h1"/><circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/> }
        @case ('barcode') { <path d="M3 5v14M7 5v14M11 5v10M15 5v14M18 5v14M21 5v14"/> }
        @case ('clock') { <circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/> }
        @case ('lock') { <rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/> }
        @case ('rotate') { <path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/> }
        @case ('arrow-left') { <path d="M19 12H5"/><path d="m12 19-7-7 7-7"/> }
        @case ('alert') { <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/> }
        @case ('moon') { <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z"/> }
      }
    </svg>
  `,
})
export class IconComponent {
  @Input() name = '';
  @Input() class = 'size-5';
}
