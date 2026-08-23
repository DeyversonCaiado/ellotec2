export const environment = {
  production: false,
  // Esta URL é resolvida pelo NAVEGADOR. Em desenvolvimento no próprio PC,
  // `localhost` é o certo. Para testar no coletor, troque pelo IP da máquina
  // de desenvolvimento na LAN daquele momento (o coletor resolveria
  // `localhost` como sendo ele mesmo) e acrescente esse IP em CORS_ORIGENS
  // no .env do backend — os dois precisam bater.
  apiUrl: 'http://localhost:8000',
  /**
   * Quando true, o AuthService responde com dados fictícios em memória
   * em vez de chamar a API real. Existe só pra permitir desenvolver o
   * front antes do backend estar pronto. O contrato (Observable<LoginResponse>)
   * é o mesmo dos dois jeitos, então trocar pra false não exige mudar
   * nenhum componente que consome o AuthService.
   */
  mockAuth: false,
};
