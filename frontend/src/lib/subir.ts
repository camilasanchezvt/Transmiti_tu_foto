// Subida directa a Cloudinary, con progreso real.
//
// Los bytes de la foto nunca pasan por el servidor: el navegador le pide una
// firma al backend y sube directo. Se usa XMLHttpRequest y no fetch porque es la
// única forma de leer el progreso de subida de verdad. Un girador falso mientras
// una foto tarda 30 segundos por datos móviles es peor que no mostrar nada.

import type { Firma } from "../api/tipos";

export interface ResultadoSubida {
  public_id: string;
  url: string;
  ancho: number;
  alto: number;
  bytes: number;
}

export class ErrorSubida extends Error {
  readonly http: number;

  constructor(mensaje: string, http = 0) {
    super(mensaje);
    this.name = "ErrorSubida";
    this.http = http;
  }
}

interface Opciones {
  firma: Firma;
  blob: Blob;
  onProgreso?: (porcentaje: number) => void;
  senal?: AbortSignal;
}

function subirUnaVez({ firma, blob, onProgreso, senal }: Opciones): Promise<ResultadoSubida> {
  return new Promise((resolver, rechazar) => {
    const url = `https://api.cloudinary.com/v1_1/${firma.cloud_name}/image/upload`;

    // Los parámetros firmados tienen que coincidir EXACTAMENTE con los que se
    // mandan acá. Uno de más o de menos y Cloudinary responde "Invalid
    // Signature". El backend firma sólo folder y timestamp.
    const datos = new FormData();
    datos.append("file", blob);
    datos.append("api_key", firma.api_key);
    datos.append("timestamp", String(firma.timestamp));
    datos.append("signature", firma.signature);
    datos.append("folder", firma.folder);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", url, true);

    xhr.upload.onprogress = (evento) => {
      if (!evento.lengthComputable || !onProgreso) return;
      // Se corta en 99: el 100% recién es cuando Cloudinary contesta, y mostrar
      // 100 mientras todavía se espera parece que se colgó.
      onProgreso(Math.min(99, Math.round((evento.loaded / evento.total) * 100)));
    };

    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        rechazar(new ErrorSubida("Cloudinary rechazó la subida", xhr.status));
        return;
      }
      try {
        const cuerpo = JSON.parse(xhr.responseText) as {
          public_id: string;
          secure_url: string;
          width: number;
          height: number;
          bytes: number;
          format: string;
        };
        onProgreso?.(100);
        resolver({
          // El public_id que devuelve Cloudinary no trae extensión, pero la URL
          // sí. El backend valida que la URL contenga el public_id, así que se
          // manda el que vino.
          public_id: cuerpo.public_id,
          url: cuerpo.secure_url,
          ancho: cuerpo.width,
          alto: cuerpo.height,
          bytes: cuerpo.bytes,
        });
      } catch {
        rechazar(new ErrorSubida("Cloudinary respondió algo que no entendemos", xhr.status));
      }
    };

    xhr.onerror = () => rechazar(new ErrorSubida("Se cortó la conexión"));
    xhr.ontimeout = () => rechazar(new ErrorSubida("La subida tardó demasiado"));
    xhr.onabort = () => rechazar(new DOMException("Cancelada", "AbortError"));

    // Datos móviles en un salón lleno: dos minutos es poco optimista, pero
    // menos que eso corta subidas que iban a llegar.
    xhr.timeout = 120_000;

    if (senal) {
      if (senal.aborted) {
        xhr.abort();
        return;
      }
      senal.addEventListener("abort", () => xhr.abort(), { once: true });
    }

    xhr.send(datos);
  });
}

/**
 * Sube con **un solo reintento**, como pide el brief.
 *
 * Un reintento cubre el corte momentáneo de señal, que es lo que pasa de verdad
 * en un salón. Más reintentos, con ochenta celulares colgados de la misma
 * antena, sólo agregan tráfico y hacen esperar más al invitado antes de
 * mostrarle que puede probar de nuevo.
 *
 * No se reintenta si el error es de Cloudinary (4xx): una firma vencida o mal
 * armada va a fallar igual la segunda vez.
 */
export async function subirAcloudinary(opciones: Opciones): Promise<ResultadoSubida> {
  try {
    return await subirUnaVez(opciones);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    const esDeCloudinary =
      error instanceof ErrorSubida && error.http >= 400 && error.http < 500;
    if (esDeCloudinary) throw error;

    opciones.onProgreso?.(0);
    return subirUnaVez(opciones);
  }
}
