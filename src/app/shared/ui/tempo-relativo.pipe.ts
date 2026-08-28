import { Pipe, PipeTransform } from '@angular/core';

/**
 * Converte um instante em "há quanto tempo": `Há 30 min`, `Há 1d 4h`, `Há 12d`.
 *
 * Existe porque na linha do tempo da entrega a pergunta não é "que dia foi
 * isso?", é "faz quanto tempo?". Quem acompanha entrega quer saber se o último
 * evento é de agora ou de três dias atrás — e uma data absoluta obriga a fazer
 * a conta de cabeça toda vez.
 *
 * Fica em `shared/` porque não sabe nada de entrega: recebe uma data e devolve
 * texto. Qualquer domínio pode usar.
 */
@Pipe({ name: 'tempoRelativo', standalone: true })
export class TempoRelativoPipe implements PipeTransform {
  transform(valor: string | Date | null | undefined, agora: Date = new Date()): string {
    if (!valor) return '—';

    const data = valor instanceof Date ? valor : new Date(valor);
    if (Number.isNaN(data.getTime())) return '—';

    const segundos = Math.floor((agora.getTime() - data.getTime()) / 1000);

    // Data no futuro só acontece por relógio dessincronizado entre o servidor
    // e a máquina de quem olha. "Há -3 min" seria pior que "agora".
    if (segundos < 60) return 'Agora';

    const minutos = Math.floor(segundos / 60);
    if (minutos < 60) return `Há ${minutos} min`;

    const horas = Math.floor(minutos / 60);
    if (horas < 24) {
      const restoMin = minutos % 60;
      return restoMin ? `Há ${horas}h ${restoMin}min` : `Há ${horas}h`;
    }

    const dias = Math.floor(horas / 24);
    // Acima de uma semana o resto em horas não ajuda ninguém a decidir nada —
    // "há 12d" e "há 12d 5h" levam à mesma conclusão.
    if (dias > 7) return `Há ${dias}d`;

    const restoHoras = horas % 24;
    return restoHoras ? `Há ${dias}d ${restoHoras}h` : `Há ${dias}d`;
  }
}
