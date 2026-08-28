import { Component, OnInit, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MultiSelectModule } from 'primeng/multiselect';
import { AuthService } from '../../../core/auth/auth.service';
import { IconComponent } from '../../../shared/ui/icon.component';
import { EmpresaService } from '../../empresas/empresa.service';
import { Empresa } from '../../empresas/empresa.model';

/**
 * A tela inicial. Morava em `core/layout/home-page/` e foi movida para cá
 * quando passou a exibir dado de negócio (as empresas do grupo): o
 * `ARCHITECTURE.md` proíbe `core/*` importar de `domains/*`, e injetar o
 * `EmpresaService` lá dentro fecharia essa dependência na direção errada.
 *
 * Aqui, em `domains/`, injetar o service do domínio dono do dado é o caminho
 * previsto — é leitura, que atravessa fronteira livremente.
 */
@Component({
  selector: 'app-inicio-page',
  standalone: true,
  imports: [CommonModule, FormsModule, MultiSelectModule, IconComponent],
  templateUrl: './inicio-page.html',
})
export class InicioPage implements OnInit {
  usuario = computed(() => this.auth.usuario());

  empresas = signal<Empresa[]>([]);

  /** As empresas marcadas no seletor. Começa com TODAS marcadas — a home é do
   *  grupo inteiro, e abrir com nada selecionado passaria a ideia errada de
   *  que os números estão filtrados.
   *
   *  A seleção ainda não filtra nada: os cards e o gráfico desta tela são
   *  fixos (ver "O que é decoração visual" no ARCHITECTURE.md). O seletor
   *  existe para o lugar da escolha já estar definido quando os indicadores
   *  forem reais — não para dar a impressão de que já funciona. */
  empresasSelecionadas = signal<string[]>([]);

  /** O que o multiselect consome: id + o rótulo já resolvido. Montado aqui, e
   *  não no template, para a regra do apelido existir num lugar só. */
  opcoesEmpresa = computed(() =>
    this.empresas().map((empresa) => ({
      id: empresa.id,
      rotulo: this.identificacao(empresa),
      nomeFantasia: empresa.nomeFantasia,
      cnpj: empresa.cnpj,
    })),
  );

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

  constructor(
    private auth: AuthService,
    private empresaService: EmpresaService,
  ) {}

  ngOnInit(): void {
    // Falha silenciosa de propósito: a lista de empresas é informativa no topo
    // da tela inicial. Se a API não responder, o bloco some — derrubar a home
    // inteira com um erro por causa dela seria desproporcional.
    this.empresaService.listar().subscribe({
      next: (lista) => {
        const ativas = lista.filter((e) => e.ativo);
        this.empresas.set(ativas);
        this.empresasSelecionadas.set(ativas.map((e) => e.id));
      },
      error: () => this.empresas.set([]),
    });
  }

  /** O apelido é o nome curto do dia a dia ("MTZ", "BSB"). Nem toda empresa
   *  precisa ter um cadastrado, e nesse caso o nome fantasia é o que sobra —
   *  a tela não inventa sigla a partir do nome. */
  identificacao(empresa: Empresa): string {
    return empresa.apelido || empresa.nomeFantasia;
  }
}
