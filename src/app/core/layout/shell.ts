import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { NavigationEnd, Router, RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { DrawerModule } from 'primeng/drawer';
import { AuthService } from '../auth/auth.service';
import { TemaService } from './tema.service';
import { IconComponent } from '../../shared/ui/icon.component';
import { GrupoMenu, MENU_PRINCIPAL, SecaoMenu } from '../navegacao/navegacao.model';
import { PermissaoKey } from '../permissions/permission.model';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [CommonModule, RouterOutlet, RouterLink, RouterLinkActive, IconComponent, DrawerModule],
  templateUrl: './shell.html',
})
export class Shell {
  private auth = inject(AuthService);
  private temaService = inject(TemaService);
  private router = inject(Router);

  /** Menu com todos os itens que o usuário não pode ver já removidos — grupo
   *  (e seção) que fica vazio some inteiro, cabeçalho incluído. */
  secoesMenu = computed<SecaoMenu[]>(() =>
    MENU_PRINCIPAL.map((secao) => ({
      ...secao,
      grupos: secao.grupos
        .map((grupo) => ({ ...grupo, itens: grupo.itens.filter((item) => this.itemVisivel(item.permissao)) }))
        .filter((grupo) => grupo.itens.length > 0),
    })).filter((secao) => secao.grupos.length > 0),
  );

  /** Títulos dos grupos expandidos. Começa com TODOS abertos: o menu tem que
   *  mostrar de cara tudo que existe, mesmo que no coletor (320x453) isso
   *  signifique rolar — colapsar é uma escolha do usuário, não o estado
   *  inicial. Fechar um grupo aqui não persiste entre reloads. */
  gruposAbertos = signal<Set<string>>(
    new Set(
      MENU_PRINCIPAL.flatMap((secao) => secao.grupos).flatMap((grupo) => (grupo.titulo ? [grupo.titulo] : [])),
    ),
  );

  /** Só grupo com título vira acordeão. O grupo sem título (o do Início)
   *  fica com os itens soltos sob o cabeçalho da seção, sempre visíveis. */
  grupoAberto(grupo: GrupoMenu): boolean {
    return !grupo.titulo || this.gruposAbertos().has(grupo.titulo);
  }

  alternarGrupo(grupo: GrupoMenu): void {
    const titulo = grupo.titulo;
    if (!titulo) return;

    this.gruposAbertos.update((abertos) => {
      const proximo = new Set(abertos);
      if (proximo.has(titulo)) proximo.delete(titulo);
      else proximo.add(titulo);
      return proximo;
    });
  }

  /** Abre o grupo que contém a rota atual — sem fechar os que o usuário
   *  abriu na mão. Roda também no primeiro load (F5 direto numa rota). */
  private abrirGrupoDaRotaAtual(url: string): void {
    const grupo = MENU_PRINCIPAL.flatMap((secao) => secao.grupos).find(
      (g) => g.titulo && g.itens.some((item) => item.rota && item.rota !== '/' && url.startsWith(item.rota)),
    );
    if (!grupo?.titulo) return;

    const titulo = grupo.titulo;
    this.gruposAbertos.update((abertos) => new Set(abertos).add(titulo));
  }

  /**
   * Abaixo disso o menu vira offcanvas (`p-drawer` com máscara) e some da
   * área útil. Acima, vira um rail de ícones de 64px que expande no hover.
   * No coletor (320px de largura CSS) um menu de 288px empurrando o conteúdo
   * deixaria 32px para o app.
   */
  private static readonly LIMITE_OFFCANVAS = 800;

  /** matchMedia em vez de escutar `window:resize`: o evento de resize não é
   *  disparado de forma confiável em toda troca de viewport (rotação de tela,
   *  barra de endereço recolhendo, viewport forçado por ferramenta), e a
   *  media query avisa em todas elas. */
  private consultaTelaLarga = window.matchMedia(`(min-width: ${Shell.LIMITE_OFFCANVAS}px)`);
  private telaLarga = signal(this.consultaTelaLarga.matches);
  ehEstreito = computed(() => !this.telaLarga());

  /** Telas largas: rail recolhido é o estado inicial (e para o qual se volta
   *  ao clicar num item). Expandido por clique fica preso até fechar; por
   *  hover, solta sozinho. */
  menuExpandido = signal(false);
  menuHover = signal(false);
  menuVisivelExpandido = computed(() => this.menuExpandido() || this.menuHover());

  /** Telas estreitas: o drawer da PrimeNG, que já traz a máscara. */
  drawerAberto = signal(false);

  painelEquipeAberto = true;

  constructor() {
    this.abrirGrupoDaRotaAtual(this.router.url);
    this.router.events.subscribe((evento) => {
      if (evento instanceof NavigationEnd) this.abrirGrupoDaRotaAtual(evento.urlAfterRedirects);
    });

    this.consultaTelaLarga.addEventListener('change', (evento) => {
      this.telaLarga.set(evento.matches);
      // Atravessar o limite reseta o menu: um drawer aberto que vira rail
      // (ou o contrário) deixaria a tela num estado que o usuário não pediu.
      this.recolherMenu();
    });
  }

  usuario = computed(() => this.auth.usuario());
  tema = computed(() => this.temaService.tema());

  /** Avatares fictícios pro painel da direita, só pra fidelidade visual com a referência. */
  equipeFicticia = [
    { iniciais: 'JM', online: true },
    { iniciais: 'AR', online: true },
    { iniciais: 'CS', online: false },
    { iniciais: 'PD', online: true },
    { iniciais: 'M', online: false },
    { iniciais: 'D', online: true },
    { iniciais: 'M', online: true },
    { iniciais: 'T', online: false },
    { iniciais: 'TS', online: true },
  ];

  alternarTema(): void {
    this.temaService.alternar();
  }

  /** Botão de menu da topbar: em tela estreita abre o drawer, em tela larga
   *  prende/solta a expansão do rail. */
  alternarSidebar(): void {
    if (this.ehEstreito()) {
      this.drawerAberto.update((aberto) => !aberto);
      return;
    }
    this.menuExpandido.update((expandido) => !expandido);
  }

  /** Chamado ao clicar em qualquer item do menu: volta ao estado inicial —
   *  drawer fechado nas telas estreitas, rail recolhido nas largas. */
  recolherMenu(): void {
    this.drawerAberto.set(false);
    this.menuExpandido.set(false);
    this.menuHover.set(false);
  }

  alternarPainelEquipe(): void {
    this.painelEquipeAberto = !this.painelEquipeAberto;
  }

  itemVisivel(chave?: PermissaoKey): boolean {
    if (!chave) return true;
    return !!this.usuario()?.permissoes.has(chave);
  }

  sair(): void {
    this.auth.logout();
    location.href = '/login';
  }
}
