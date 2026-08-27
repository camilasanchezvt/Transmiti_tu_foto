import { useEffect, useRef } from "react";
import QRCode from "qrcode";

interface Props {
  /** La URL completa que se codifica, no sólo el código. */
  url: string;
  /** Lado en píxeles. En la pantalla de proyección va enorme. */
  lado: number;
  className?: string;
}

/**
 * Un QR se escanea cómodo hasta unas diez veces su propio lado. Con la persona
 * más lejana a ocho metros, el QR proyectado tiene que medir cerca de ochenta
 * centímetros: más de un cuarto del ancho de una proyección de tres metros.
 * Se ve exagerado en la notebook y es el tamaño correcto en la pared.
 *
 * Se dibuja en blanco y negro puros aunque el resto de la pantalla sea oscura:
 * un proyector pierde contraste y un QR gris no escanea.
 */
export default function QR({ url, lado, className = "" }: Props) {
  const lienzo = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!lienzo.current) return;
    QRCode.toCanvas(lienzo.current, url, {
      width: lado,
      margin: 2,
      // Corrección media: aguanta que el proyector desenfoque un poco los
      // bordes sin agrandar demasiado el código.
      errorCorrectionLevel: "M",
      color: { dark: "#000000", light: "#ffffff" },
    }).catch(() => {
      /* una URL imposible de codificar no puede tirar abajo la pantalla */
    });
  }, [url, lado]);

  return (
    <canvas
      ref={lienzo}
      className={`rounded-2xl bg-white ${className}`}
      aria-label="Código para mandar tu foto"
    />
  );
}
