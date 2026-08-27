// Identifica al dispositivo para poder contar cuántas fotos mandó, sin pedirle
// ningún dato al invitado. No es una cuenta ni un login: es un número al azar
// que vive en el navegador.

const CLAVE = "transmiti.dispositivo";

function nuevoHash(): string {
  // 32 caracteres hexadecimales, como los del seed.
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

let enMemoria: string | null = null;

/**
 * Devuelve el mismo hash mientras el invitado no borre los datos del navegador.
 *
 * Si localStorage no está disponible —modo privado en iOS, o el usuario bloqueó
 * el almacenamiento— se usa uno que vive sólo en memoria. El invitado va a poder
 * mandar más fotos de las que le tocan si recarga la página, y está bien: es
 * preferible a que no pueda mandar ninguna.
 */
export function hashDelDispositivo(): string {
  if (enMemoria) return enMemoria;

  try {
    const guardado = window.localStorage.getItem(CLAVE);
    if (guardado && guardado.length >= 8) {
      enMemoria = guardado;
      return guardado;
    }
    const nuevo = nuevoHash();
    window.localStorage.setItem(CLAVE, nuevo);
    enMemoria = nuevo;
    return nuevo;
  } catch {
    enMemoria = nuevoHash();
    return enMemoria;
  }
}
