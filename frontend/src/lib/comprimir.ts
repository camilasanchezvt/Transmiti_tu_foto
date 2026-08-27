// Compresión en el navegador, antes de subir.
//
// Es lo que decide si la app funciona el día del evento. Una foto de celular
// pesa entre 4 y 6 MB. Ochenta invitados colgados de la misma antena de datos no
// pueden subir eso: son unos 38 segundos por foto. Comprimida son unos 3.
//
// Pasar la foto por acá también convierte los HEIC de iPhone a JPEG, que es lo
// que los navegadores muestran sin problemas.

/** El lado mayor de la foto subida. Nunca se agranda una foto más chica. */
export const LADO_MAYOR = 1600;

/** Calidad del JPEG. Por debajo de 0,8 se empiezan a ver bloques en el proyector. */
export const CALIDAD = 0.82;

/** Tope después de comprimir. Una foto de 1600 px nunca llega acá; está por si acaso. */
export const MAXIMO_BYTES = 10 * 1024 * 1024;

export const TIPOS_ACEPTADOS = [
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/heic",
  "image/heif",
];

export class ArchivoInvalido extends Error {
  constructor(mensaje = "El archivo no es una foto") {
    super(mensaje);
    this.name = "ArchivoInvalido";
  }
}

export interface FotoLista {
  blob: Blob;
  ancho: number;
  alto: number;
  /** Para mostrar la vista previa. Hay que revocarla cuando ya no se usa. */
  vistaPrevia: string;
}

/**
 * Rechaza cualquier cosa que no sea una imagen, antes de tocar un solo byte.
 *
 * Un iPhone puede reportar `type` vacío para un HEIC, así que si el tipo no
 * viene se mira la extensión en vez de rechazar de una.
 */
export function esImagen(archivo: File): boolean {
  if (archivo.type) {
    if (archivo.type.startsWith("video/")) return false;
    return TIPOS_ACEPTADOS.includes(archivo.type.toLowerCase());
  }
  return /\.(jpe?g|png|webp|heic|heif)$/i.test(archivo.name);
}

function escala(ancho: number, alto: number): number {
  const mayor = Math.max(ancho, alto);
  // Nunca agrandar: una foto de 800 px se sube tal cual.
  return mayor <= LADO_MAYOR ? 1 : LADO_MAYOR / mayor;
}

async function aBlob(lienzo: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolver, rechazar) => {
    lienzo.toBlob(
      (blob) => (blob ? resolver(blob) : rechazar(new ArchivoInvalido())),
      "image/jpeg",
      CALIDAD,
    );
  });
}

/**
 * Redimensiona y recomprime. Devuelve el original si comprimir no lo mejoró.
 *
 * `imageOrientation: "from-image"` es lo que resuelve la rotación EXIF de las
 * fotos de iPhone. Sin eso aparecen acostadas en el proyector, que es el tipo de
 * error que no se ve en la notebook de desarrollo y sí delante de cien personas.
 */
export async function comprimir(archivo: File): Promise<FotoLista> {
  if (!esImagen(archivo)) throw new ArchivoInvalido();

  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(archivo, { imageOrientation: "from-image" });
  } catch {
    // Un HEIC que este navegador no sabe decodificar, o un archivo corrupto.
    throw new ArchivoInvalido();
  }

  try {
    const factor = escala(bitmap.width, bitmap.height);
    const ancho = Math.round(bitmap.width * factor);
    const alto = Math.round(bitmap.height * factor);

    const lienzo = document.createElement("canvas");
    lienzo.width = ancho;
    lienzo.height = alto;

    const contexto = lienzo.getContext("2d");
    if (!contexto) throw new ArchivoInvalido();
    contexto.drawImage(bitmap, 0, 0, ancho, alto);

    const comprimido = await aBlob(lienzo);

    // Si comprimir no achicó nada, se manda el original: recomprimir un JPEG ya
    // chico sólo le saca calidad. Pero si el original es HEIC o PNG hay que
    // mandar el comprimido igual, porque el HEIC no se ve en muchos navegadores
    // y el PNG de una foto pesa muchísimo más que su JPEG.
    const convieneElOriginal =
      comprimido.size >= archivo.size &&
      factor === 1 &&
      archivo.type === "image/jpeg";

    const blob = convieneElOriginal ? archivo : comprimido;

    if (blob.size > MAXIMO_BYTES) throw new ArchivoInvalido("La foto es demasiado grande");

    return {
      blob,
      ancho,
      alto,
      vistaPrevia: URL.createObjectURL(blob),
    };
  } finally {
    // Sin esto, mandar diez fotos seguidas deja diez bitmaps sin liberar y el
    // navegador del celular se queda sin memoria.
    bitmap.close();
  }
}
