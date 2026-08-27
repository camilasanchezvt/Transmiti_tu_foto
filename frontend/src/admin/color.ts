/**
 * Un color por evento, siempre el mismo.
 *
 * El backend garantiza que las fotos no se mezclen. Lo que ninguna base
 * previene es que el moderador apruebe fotos del evento equivocado con dos
 * pestañas abiertas. El color es lo que las distingue de un vistazo.
 */
export function colorDelEvento(codigo: string): string {
  let acumulado = 0;
  for (let i = 0; i < codigo.length; i++) {
    acumulado = (acumulado * 31 + codigo.charCodeAt(i)) >>> 0;
  }
  // Saturación y luminosidad fijas para que todos se lean igual de bien sobre
  // el fondo oscuro.
  return `hsl(${acumulado % 360} 70% 55%)`;
}
