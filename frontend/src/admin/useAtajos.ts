import { useEffect } from "react";

export type Accion = "anterior" | "siguiente" | "aprobar" | "rechazar" | "deshacer";

const TECLAS: Record<string, Accion> = {
  ArrowLeft: "anterior",
  ArrowRight: "siguiente",
  a: "aprobar",
  A: "aprobar",
  r: "rechazar",
  R: "rechazar",
  z: "deshacer",
  Z: "deshacer",
};

/**
 * Teclado antes que mouse.
 *
 * Con mouse son cincuenta apuntadas y cincuenta clics. Con teclado son
 * cincuenta pulsaciones sin mover la mano, y ese es todo el objetivo de la
 * bandeja: cincuenta fotos en menos de dos minutos.
 */
export function useAtajos(alActuar: (accion: Accion) => void, activo = true) {
  useEffect(() => {
    if (!activo) return;

    const alPresionar = (evento: KeyboardEvent) => {
      // No robarle las teclas a un campo de texto.
      const destino = evento.target as HTMLElement | null;
      if (destino) {
        const etiqueta = destino.tagName;
        if (etiqueta === "INPUT" || etiqueta === "TEXTAREA" || destino.isContentEditable) return;
      }
      if (evento.metaKey || evento.ctrlKey || evento.altKey) return;

      const accion = TECLAS[evento.key];
      if (!accion) return;
      evento.preventDefault();
      alActuar(accion);
    };

    window.addEventListener("keydown", alPresionar);
    return () => window.removeEventListener("keydown", alPresionar);
  }, [alActuar, activo]);
}
