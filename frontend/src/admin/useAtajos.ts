import { useEffect } from "react";

export type Accion = "anterior" | "siguiente" | "aprobar" | "rechazar" | "deshacer" | "cancelar";

const TECLAS: Record<string, Accion> = {
  ArrowLeft: "anterior",
  ArrowRight: "siguiente",
  a: "aprobar",
  A: "aprobar",
  r: "rechazar",
  R: "rechazar",
  z: "deshacer",
  Z: "deshacer",
  // Sale del modo de selección. Si hay un diálogo abierto, Escape nunca llega
  // acá: Confirmar la frena antes, en document.
  Escape: "cancelar",
};

/** Las únicas que pueden repetirse al dejar la tecla apretada: moverse rápido
 *  por la fila está bien; aprobar treinta fotos por apoyar un dedo, no. */
const REPETIBLES: ReadonlySet<Accion> = new Set(["anterior", "siguiente"]);

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
        if (
          etiqueta === "INPUT" ||
          etiqueta === "TEXTAREA" ||
          etiqueta === "SELECT" ||
          destino.isContentEditable
        ) {
          return;
        }
      }
      if (evento.metaKey || evento.ctrlKey || evento.altKey) return;

      const accion = TECLAS[evento.key];
      if (!accion) return;
      evento.preventDefault();
      // La repetición automática del sistema dispara ~30 pulsaciones por
      // segundo: una A apoyada un segundo de más aprobaba media tanda.
      if (evento.repeat && !REPETIBLES.has(accion)) return;
      alActuar(accion);
    };

    window.addEventListener("keydown", alPresionar);
    return () => window.removeEventListener("keydown", alPresionar);
  }, [alActuar, activo]);
}
