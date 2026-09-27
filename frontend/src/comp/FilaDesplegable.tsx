import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { CheckCircleIcon, ChevronRightIcon } from "@heroicons/react/20/solid";

import { claseIconoChip, type Icono } from "./icono";

/** Lo que tarda en abrirse o cerrarse. El mismo número que duration-200. */
const DURACION_MS = 200;

/** "moviendose": abriéndose o cerrándose, todavía en camino. */
type Fase = "cerrada" | "moviendose" | "abierta";

function reducirMovimiento(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Lo primero de adentro que se puede tocar y se ve. El <input hidden> del
 *  email para el gestor de contraseñas no cuenta: no tiene caja. */
function primerCampo(raiz: HTMLElement): HTMLElement | null {
  const candidatos = raiz.querySelectorAll<HTMLElement>(
    "input:not([type=hidden]), select, textarea, button, a[href]",
  );
  for (const el of candidatos) {
    if (el.matches(":disabled")) continue;
    if (el.getClientRects().length > 0) return el;
  }
  return null;
}

/**
 * Una fila de Ajustes de iOS que se despliega en el lugar: el ícono, el
 * título, lo que vale ahora a la derecha (en gris) y el chevron que gira al
 * abrir. Cerrada por defecto; la abre y la cierra quien la usa (`abierto`),
 * así puede cerrarla sola después de guardar.
 *
 * - El contenido se monta al abrir y se desmonta al terminar de cerrar: un
 *   formulario arranca limpio cada vez, y una contraseña a medio escribir no
 *   queda en memoria con la fila cerrada.
 * - Se abre creciendo en alto (grid-template-rows de 0fr a 1fr, sin medir
 *   nada) y apareciendo. Con "reducir movimiento", de golpe.
 * - Al abrir, el foco va al primer campo. Al cerrar, si el foco estaba
 *   adentro (o se perdió porque el botón de guardar se apagó mientras
 *   guardaba), vuelve a la fila: con teclado se sigue desde ahí, y en el
 *   celular el teclado baja.
 * - `confirmacion` ("Guardado") se ve debajo del título, en la fila misma, y
 *   el lector de pantalla la lee sola (role="status", siempre en el DOM).
 */
export default function FilaDesplegable({
  icono: IconoFila,
  titulo,
  resumen,
  resumenOculto = false,
  confirmacion = null,
  abierto,
  onCambiar,
  className = "",
  children,
}: {
  icono: Icono;
  titulo: string;
  /** Lo que vale ahora, a la derecha. Si no entra, se corta con "…". */
  resumen?: string;
  /** El resumen es un adorno (los puntitos de una contraseña): el lector de
   *  pantalla no lo lee. */
  resumenOculto?: boolean;
  confirmacion?: string | null;
  abierto: boolean;
  onCambiar: (abierto: boolean) => void;
  /** Para acomodarla en su tarjeta: el margen y la raya de arriba. */
  className?: string;
  children: ReactNode;
}) {
  const id = useId();
  const idContenido = `${id}-contenido`;
  const boton = useRef<HTMLButtonElement>(null);
  const contenido = useRef<HTMLDivElement>(null);
  const [fase, setFase] = useState<Fase>(abierto ? "abierta" : "cerrada");
  const antes = useRef(abierto);

  useEffect(() => {
    if (antes.current === abierto) return;
    antes.current = abierto;
    setFase("moviendose");

    if (abierto) {
      // Sin mover la página: la fila está donde se tocó, y el campo justo
      // debajo. En el celular, el navegador igual lo acomoda sobre el teclado.
      const primero = contenido.current && primerCampo(contenido.current);
      primero?.focus({ preventScroll: true });
    } else {
      const activo = document.activeElement;
      if (!activo || activo === document.body || contenido.current?.contains(activo)) {
        boton.current?.focus({ preventScroll: true });
      }
    }

    const reloj = window.setTimeout(
      () => setFase(abierto ? "abierta" : "cerrada"),
      reducirMovimiento() ? 0 : DURACION_MS,
    );
    return () => window.clearTimeout(reloj);
  }, [abierto]);

  // Montado mientras está abierta y mientras se cierra, para que se vea
  // cerrarse. Recortado (overflow-hidden) mientras se mueve; ya abierta, no:
  // el anillo de foco de un botón del borde no queda cortado.
  const montado = abierto || fase !== "cerrada";
  const quieta = abierto && fase === "abierta";

  return (
    <div className={className}>
      <button
        ref={boton}
        type="button"
        aria-expanded={abierto}
        aria-controls={idContenido}
        onClick={() => onCambiar(!abierto)}
        className={
          // -mx-2 px-2: el gris del toque sobresale un poco, como en iOS, y
          // el ícono queda alineado con el resto de la tarjeta.
          // El gris al pasar el mouse, sólo donde hay mouse: en el celular,
          // Safari deja :hover pegado en lo último que tocaste, y la fila
          // quedaba gris después de abrirla o cerrarla. Al tocar, active:.
          "-mx-2 flex min-h-12 w-[calc(100%+1rem)] items-center gap-3 rounded-xl px-2 py-2 text-left " +
          "transition-colors [@media(hover:hover)]:hover:bg-pulsado active:bg-pulsado " +
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-acento"
        }
      >
        <IconoFila aria-hidden className="h-6 w-6 shrink-0 text-acento" />
        <span className="min-w-0 break-words text-base font-medium">{titulo}</span>
        {/* El espacio no se ve (entre dos hijos de un flex no ocupa lugar),
            pero el lector de pantalla dice "Nombre Ana" y no "NombreAna". */}{" "}
        {/* flex-1 desde cero: el resumen se queda con lo que sobra y se corta
            él, nunca el título. */}
        <span
          aria-hidden={resumenOculto || undefined}
          className="min-w-0 flex-1 truncate text-right text-base text-tenue"
        >
          {resumen}
        </span>
        <ChevronRightIcon
          aria-hidden
          className={
            "h-5 w-5 shrink-0 text-tenue transition-transform duration-200 motion-reduce:transition-none " +
            (abierto ? "rotate-90" : "")
          }
        />
      </button>

      <div role="status">
        {confirmacion && (
          <p className="-mt-1 flex items-start gap-1.5 pb-2 pl-9 text-sm leading-snug text-verde-tinta">
            <CheckCircleIcon aria-hidden className={`mt-0.5 ${claseIconoChip}`} />
            <span className="min-w-0">{confirmacion}</span>
          </p>
        )}
      </div>

      <div
        id={idContenido}
        className={
          "grid transition-[grid-template-rows,opacity] duration-200 ease-out motion-reduce:transition-none " +
          (abierto ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0")
        }
      >
        <div ref={contenido} className={`min-h-0 ${quieta ? "" : "overflow-hidden"}`}>
          {montado && <div className="pb-4 pt-2">{children}</div>}
        </div>
      </div>
    </div>
  );
}
