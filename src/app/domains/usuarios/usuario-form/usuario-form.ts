import { Component, OnInit, signal, inject, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TreeModule } from 'primeng/tree';
import { ButtonModule } from 'primeng/button';
import { TreeNode } from 'primeng/api';
import { UsuarioService } from '../usuario.service';
import { CargoService } from '../cargo.service';
import { Cargo } from '../cargo.model';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';
import { NoArvorePermissao, PermissaoKey } from '../../../core/permissions/permission.model';
import { ARVORE_PERMISSOES } from '../../../core/navegacao/navegacao.model';
import { AuthService } from '../../../core/auth/auth.service';

/**
 * Constrói a árvore de nós do p-tree do zero a partir de ARVORE_PERMISSOES,
 * já calculando `partialSelected` nos nós-pai e retornando o array de
 * seleção (folhas + grupos totalmente marcados).
 *
 * Sempre cria objetos NOVOS — nunca reaproveita nem muta nós de uma árvore
 * anterior. Isso é proposital: o p-tree usa componentes internos OnPush por
 * nó, então mutar `partialSelected` num objeto já renderizado não dispara
 * re-render nenhum (o Angular só reavalia esses componentes quando a
 * referência do `node` que eles recebem muda). Construir uma árvore nova a
 * cada mudança de seleção programática garante que o checkbox de grupo
 * (indeterminado/marcado) reflita o estado real assim que os dados chegam
 * — sem isso, ao abrir a edição de um usuário com permissões já salvas,
 * os checkboxes de grupo aparecem todos desmarcados (as folhas por baixo
 * ficam certas, mas ninguém expande os grupos pra ver isso), dando a
 * falsa impressão de que as permissões se perderam.
 */
function construirArvore(
  nos: NoArvorePermissao[],
  chavesSelecionadas: Set<PermissaoKey>,
  selecao: TreeNode[],
  indice = 0,
): TreeNode[] {
  return nos.map((no, i) => {
    const filhos = no.filhos ? construirArvore(no.filhos, chavesSelecionadas, selecao, i) : undefined;

    if (!filhos) {
      const selecionado = !!no.chave && chavesSelecionadas.has(no.chave);
      const treeNode: TreeNode = {
        key: no.chave ?? `grupo-${no.label}-${indice}-${i}`,
        label: no.label,
        data: no.chave,
        partialSelected: false,
      };
      if (selecionado) selecao.push(treeNode);
      return treeNode;
    }

    const filhosSelecionados = filhos.filter((filho) => selecao.includes(filho)).length;
    const totalmenteSelecionado = filhosSelecionados === filhos.length;
    const algumSelecionado = filhosSelecionados > 0 || filhos.some((f) => f.partialSelected);
    const treeNode: TreeNode = {
      key: `grupo-${no.label}-${indice}-${i}`,
      label: no.label,
      children: filhos,
      partialSelected: !totalmenteSelecionado && algumSelecionado,
      // O p-tree não recalcula o indeterminado do grupo quando a seleção é
      // atribuída via código (só reage a cliques do usuário) — expandir de
      // início os grupos com alguma permissão já marcada garante que as
      // folhas (essas sim sempre corretas) fiquem visíveis, em vez do
      // usuário ver um grupo fechado com aparência de "nada selecionado".
      expanded: totalmenteSelecionado || algumSelecionado,
    };
    if (totalmenteSelecionado) selecao.push(treeNode);
    return treeNode;
  });
}

function todosOsNos(nos: TreeNode[]): TreeNode[] {
  return nos.flatMap((no) => [no, ...(no.children ? todosOsNos(no.children) : [])]);
}

@Component({
  selector: 'app-usuario-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink, IconComponent, PageHeaderComponent, TreeModule, ButtonModule],
  templateUrl: './usuario-form.html',
})
export class UsuarioForm implements OnInit {
  private fb = inject(FormBuilder);
  private service = inject(UsuarioService);
  private cargoService = inject(CargoService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private auth = inject(AuthService);

  cargos = signal<Cargo[]>([]);

  modoEdicao = signal(false);
  carregando = signal(false);
  /** Carregamento inicial dos dados do usuário (modo edição). Separado de
   * `carregando` (usado no botão salvar) para poder esconder a árvore de
   * permissões até os dados chegarem — a montagem inicial do estado dos
   * checkboxes de grupo depende dos dados já estarem disponíveis. */
  carregandoDados = signal(false);
  usuarioId = signal<string | null>(null);
  erro = signal<string | null>(null);

  nosPermissao = signal<TreeNode[]>(construirArvore(ARVORE_PERMISSOES, new Set(), []));
  private readonly todosOsNosFlat = computed(() => todosOsNos(this.nosPermissao()));

  selecaoPermissoes = signal<TreeNode[]>([]);
  readonly tudoSelecionado = computed(
    () => this.selecaoPermissoes().length > 0 && this.selecaoPermissoes().length === this.todosOsNosFlat().length,
  );

  form = this.fb.nonNullable.group({
    usuario: ['', [Validators.required, Validators.minLength(3)]],
    nome: ['', [Validators.required, Validators.minLength(3)]],
    email: ['', [Validators.required, Validators.email]],
    cargoId: ['', Validators.required],
    ativo: [true],
  });

  ngOnInit(): void {
    this.cargoService.listar().subscribe((cargos) => this.cargos.set(cargos));

    const id = this.route.snapshot.paramMap.get('id');
    if (!id) return;

    this.modoEdicao.set(true);
    this.usuarioId.set(id);
    this.carregandoDados.set(true);

    this.service.obterPorId(id).subscribe((usuario) => {
      this.carregandoDados.set(false);
      if (!usuario) return;

      this.form.patchValue({
        usuario: usuario.usuario,
        nome: usuario.nome,
        email: usuario.email,
        cargoId: usuario.cargoId,
        ativo: usuario.ativo,
      });
      this.aplicarSelecao(new Set(usuario.permissoes));
    });
  }

  alternarSelecionarTudo(): void {
    const todasAsChaves = new Set(
      this.todosOsNosFlat()
        .map((no) => no.data as PermissaoKey | undefined)
        .filter((chave): chave is PermissaoKey => !!chave),
    );
    this.aplicarSelecao(this.tudoSelecionado() ? new Set() : todasAsChaves);
  }

  onSelecaoPermissoesChange(selecao: TreeNode | TreeNode[] | null | undefined): void {
    this.selecaoPermissoes.set(selecao ? (Array.isArray(selecao) ? selecao : [selecao]) : []);
  }

  salvar(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.erro.set('Corrija os campos destacados antes de salvar.');
      return;
    }

    const permissoes = this.selecaoPermissoes()
      .map((no) => no.data as PermissaoKey | undefined)
      .filter((chave): chave is PermissaoKey => !!chave);

    const dados = { ...this.form.getRawValue(), permissoes };
    this.carregando.set(true);
    this.erro.set(null);

    const id = this.usuarioId();
    const operacao = id ? this.service.atualizar(id, dados) : this.service.criar(dados);

    operacao.subscribe({
      next: (usuarioSalvo) => {
        this.carregando.set(false);
        this.auth.atualizarUsuarioLogado(usuarioSalvo);
        this.router.navigate(['/usuarios']);
      },
      error: (erro) => {
        this.carregando.set(false);
        this.erro.set(erro?.error?.detail ?? 'Não foi possível salvar o usuário. Tente novamente.');
      },
    });
  }

  private aplicarSelecao(chavesSelecionadas: Set<PermissaoKey>): void {
    const selecao: TreeNode[] = [];
    const arvore = construirArvore(ARVORE_PERMISSOES, chavesSelecionadas, selecao);
    this.nosPermissao.set(arvore);
    this.selecaoPermissoes.set(selecao);
  }
}
