// Fechas como las dice una persona: "sábado 26 de septiembre", no "2026-09-26".
//
// OJO con el día corrido. `new Date("2026-09-26")` es la medianoche en UTC, que
// en Argentina todavía es el viernes 25 a las nueve de la noche: formateada con
// la zona local, la fiesta aparece un día antes. Por eso una fecha sin hora se
// arma y se formatea en UTC de punta a punta, y nunca pasa por la zona local.

const SOLO_DIA = /^(\d{4})-(\d{2})-(\d{2})$/;

const NOMBRES = new Intl.DateTimeFormat("es-AR", {
  weekday: "long",
  month: "long",
  timeZone: "UTC",
});

interface Dia {
  anio: number;
  mes: number; // 1 a 12
  dia: number;
}

/**
 * "2026-09-26" se toma tal cual, como día de calendario. Cualquier otra cosa
 * (un timestamptz como `creado_en`, o un Date) es un instante: se lleva al día
 * que era en la zona de quien mira.
 */
function aDia(fecha: string | Date): Dia | null {
  if (typeof fecha === "string") {
    const partes = SOLO_DIA.exec(fecha);
    if (partes) {
      return { anio: Number(partes[1]), mes: Number(partes[2]), dia: Number(partes[3]) };
    }
  }
  const instante = typeof fecha === "string" ? new Date(fecha) : fecha;
  if (Number.isNaN(instante.getTime())) return null;
  return { anio: instante.getFullYear(), mes: instante.getMonth() + 1, dia: instante.getDate() };
}

function nombres({ anio, mes, dia }: Dia): { diaSemana: string; mes: string } {
  const partes = NOMBRES.formatToParts(new Date(Date.UTC(anio, mes - 1, dia)));
  const parte = (tipo: Intl.DateTimeFormatPartTypes) =>
    partes.find((p) => p.type === tipo)?.value ?? "";
  return { diaSemana: parte("weekday"), mes: parte("month") };
}

/** El año sólo se dice cuando no es el que corre. */
function conAnio(texto: string, anio: number, separador: string): string {
  return anio === new Date().getFullYear() ? texto : `${texto}${separador}${anio}`;
}

/**
 * fechaLarga("2026-09-26") → "sábado 26 de septiembre"
 * fechaLarga("2027-01-09") → "sábado 9 de enero de 2027" (si no es el año actual)
 *
 * Se arma a mano con las partes: es-AR pone una coma después del día de la
 * semana ("sábado, 26 de septiembre") y así no se habla.
 */
export function fechaLarga(fecha: string | Date): string {
  const d = aDia(fecha);
  if (!d) return String(fecha);
  const { diaSemana, mes } = nombres(d);
  return conAnio(`${diaSemana} ${d.dia} de ${mes}`, d.anio, " de ");
}

/**
 * fechaCorta("2026-09-26") → "26 sep"
 * fechaCorta("2025-12-31") → "31 dic 2025" (si no es el año actual; en el
 * historial conviven años distintos y "31 dic" solo sería ambiguo)
 *
 * Las tres primeras letras del mes y no el `month: "short"` de Intl: según el
 * navegador ese devuelve "sep", "sept" o "sept.".
 */
export function fechaCorta(fecha: string | Date): string {
  const d = aDia(fecha);
  if (!d) return String(fecha);
  return conAnio(`${d.dia} ${nombres(d).mes.slice(0, 3)}`, d.anio, " ");
}

/**
 * "Hoy" como lo cuenta el backend, "2026-09-26": zona fija UTC-3 (Argentina no
 * cambia la hora desde 2009), no la de quien mira. Sirve para saber si un
 * evento vive en Eventos o ya pasó a Historial con la misma regla que
 * `alcance=historial`, aunque la compu esté en otra zona.
 */
export function hoyEnArgentina(ahora: number = Date.now()): string {
  return new Date(ahora - 3 * 60 * 60 * 1000).toISOString().slice(0, 10);
}
