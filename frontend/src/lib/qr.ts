import QRCode from "qrcode";

/**
 * Dibuja un QR en blanco y negro puros sobre un canvas.
 *
 * `qrcode` le escribe `style.width` y `style.height` en píxeles al canvas, y un
 * estilo en línea le gana a cualquier clase: el QR terminaba mostrándose al
 * tamaño con que se dibujó y no al que pedía el CSS. Después de dibujar se
 * borran esos dos estilos, así el tamaño en pantalla lo deciden las clases.
 */
export async function dibujarQR(lienzo: HTMLCanvasElement, url: string, lado: number): Promise<void> {
  await QRCode.toCanvas(lienzo, url, {
    width: lado,
    margin: 2,
    // Corrección media: aguanta que el proyector desenfoque un poco los
    // bordes sin agrandar demasiado el código.
    errorCorrectionLevel: "M",
    color: { dark: "#000000", light: "#ffffff" },
  });
  lienzo.style.removeProperty("width");
  lienzo.style.removeProperty("height");
}
