import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { NotaFiscalService } from '../nota-fiscal.service';
import { NotaFiscal } from '../nota-fiscal.model';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';

@Component({
  selector: 'app-nota-fiscal-detalhe',
  standalone: true,
  imports: [CommonModule, RouterLink, IconComponent, PageHeaderComponent],
  templateUrl: './nota-fiscal-detalhe.html',
})
export class NotaFiscalDetalhe implements OnInit {
  nota = signal<NotaFiscal | null>(null);
  carregando = signal(true);
  baixandoXml = signal(false);

  constructor(
    private route: ActivatedRoute,
    private service: NotaFiscalService,
  ) {}

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      this.carregando.set(false);
      return;
    }
    this.service.obterPorId(id).subscribe({
      next: (nota) => {
        this.nota.set(nota);
        this.carregando.set(false);
      },
      error: () => this.carregando.set(false),
    });
  }

  /**
   * O XML não vem junto com o detalhe (são dezenas de KB que a tela não
   * exibe) — só é buscado quando alguém clica em baixar. O arquivo é montado
   * aqui a partir do texto, sem passar por outra rota: o backend já devolveu
   * o conteúdo e o navegador só precisa salvá-lo.
   */
  baixarXml(): void {
    const nota = this.nota();
    if (!nota || this.baixandoXml()) return;

    this.baixandoXml.set(true);
    this.service.obterXml(nota.id).subscribe({
      next: (resposta) => {
        this.baixandoXml.set(false);
        if (!resposta.xmlOriginal) {
          alert('Esta nota não tem XML guardado — foi lançada sem o arquivo original.');
          return;
        }
        const blob = new Blob([resposta.xmlOriginal], { type: 'application/xml' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        // A chave de acesso é o nome canônico do arquivo de uma NF-e. Quando
        // não existe (NFS-e), cai para número e série.
        link.download = `${resposta.chaveAcesso ?? `${nota.numero}-${nota.serie}`}.xml`;
        link.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.baixandoXml.set(false),
    });
  }
}
