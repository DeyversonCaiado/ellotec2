/**
 * O host da API é derivado de ONDE A PÁGINA FOI ABERTA, não fixado.
 *
 * Esta URL é resolvida pelo NAVEGADOR. Fixar `localhost` funciona no PC, mas
 * quebra no coletor: lá `localhost` é o próprio coletor, e a chamada nunca
 * chega na máquina de desenvolvimento. O sintoma é cruel — o login responde
 * "e-mail ou senha inválidos", porque a tela trata falha de rede igual a
 * credencial errada.
 *
 * Usando `location.hostname`, a mesma build serve os dois casos:
 *   PC       → http://localhost:8000
 *   coletor  → http://192.168.20.143:8000  (ou o IP da vez)
 *
 * O que continua sendo manual é o CORS: o IP da máquina de desenvolvimento
 * precisa estar em `CORS_ORIGENS` no `.env` do backend, senão o navegador
 * bloqueia a resposta.
 */
const PORTA_API = 8000;
const HOST_API = `${window.location.protocol}//${window.location.hostname}:${PORTA_API}`;

export const environment = {
  production: false,
  apiUrl: HOST_API,
  /**
   * Quando true, o AuthService responde com dados fictícios em memória
   * em vez de chamar a API real. Existe só pra permitir desenvolver o
   * front antes do backend estar pronto. O contrato (Observable<LoginResponse>)
   * é o mesmo dos dois jeitos, então trocar pra false não exige mudar
   * nenhum componente que consome o AuthService.
   */
  mockAuth: false,
};
