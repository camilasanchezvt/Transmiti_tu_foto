import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { comun } from "../admin/textos/comun";
import Boton from "./Boton";

interface Props {
  abierto: boolean;
  titulo: string;
  mensaje: ReactNode;
  textoConfirmar: string;
  /** Por defecto "Cancelar". */
  textoCancelar?: string;
  /** Para lo que no tiene vuelta atrás fácil: el botón de confirmar va en rojo. */
  peligro?: boolean;
  /** Mientras se espera la respuesta: el botón muestra "Esperá…" y el diálogo
   *  no se cierra ni con Escape ni tocando afuera. */
  cargando?: boolean;
  onConfirmar: () => void;
  onCancelar: () => void;
}

/**
 * Diálogo de confirmación, de vidrio, para las pocas acciones que merecen una
 * pregunta (terminar el evento, dar de baja una cuenta). Revisar fotos NO lo
 * usa: ahí la red de seguridad es Deshacer.
 *
 * El foco arranca en Cancelar, no en Confirmar: un Enter de más no puede
 * terminar un evento. Escape y tocar afuera cancelan.
 *
 * Va en un portal sobre <body>: `.bg-panel` usa backdrop-filter, y cualquier
 * ancestro con backdrop-filter convierte a `position: fixed` en relativo a él.
 * Sin portal, un Confirmar dentro de una tarjeta quedaría encerrado en la
 * tarjeta.
 */
export default function Confirmar({
  abierto,
  titulo,
  mensaje,
  textoConfirmar,
  textoCancelar = comun.cancelar,
  peligro = false,
  cargando = false,
  onConfirmar,
  onCancelar,
}: Props) {
  const dialogo = useRef<HTMLDivElement>(null);
  const idTitulo = useId();
  const idMensaje = useId();

  // Se leen por ref para no volver a enganchar el teclado en cada render: la
  // página suele pasar una flecha nueva cada vez.
  const alCancelar = useRef(onCancelar);
  alCancelar.current = onCancelar;
  const ocupado = useRef(cargando);
  ocupado.current = cargando;

  useEffect(() => {
    if (!abierto) return;

    // Al cerrar, el foco vuelve a donde estaba (el botón que abrió el diálogo).
    const previo = document.activeElement as HTMLElement | null;
    dialogo.current?.querySelector<HTMLButtonElement>("[data-cancelar]")?.focus();

    // Que la página de atrás no se desplace mientras el diálogo está abierto.
    const desborde = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const alPresionar = (evento: globalThis.KeyboardEvent) => {
      // Es modal: ninguna tecla le llega a la página de atrás. Sin esto, una A
      // en Revisar fotos aprobaría la foto de abajo con el diálogo abierto.
      // (Los atajos escuchan en window; esto corre antes, en document.)
      evento.stopPropagation();
      if (evento.key === "Escape" && !ocupado.current) {
        evento.preventDefault();
        alCancelar.current();
      }
    };
    document.addEventListener("keydown", alPresionar);

    return () => {
      document.removeEventListener("keydown", alPresionar);
      document.body.style.overflow = desborde;
      previo?.focus?.();
    };
  }, [abierto]);

  if (!abierto) return null;

  // El foco no se escapa del diálogo con Tab: da la vuelta entre los botones.
  function atraparFoco(evento: KeyboardEvent<HTMLDivElement>) {
    if (evento.key !== "Tab" || !dialogo.current) return;
    const botones = Array.from(
      dialogo.current.querySelectorAll<HTMLButtonElement>("button:not([disabled])"),
    );
    const primero = botones[0];
    const ultimo = botones[botones.length - 1];
    if (!primero || !ultimo) return;
    if (evento.shiftKey && document.activeElement === primero) {
      evento.preventDefault();
      ultimo.focus();
    } else if (!evento.shiftKey && document.activeElement === ultimo) {
      evento.preventDefault();
      primero.focus();
    }
  }

  return createPortal(
    <div
      className={
        "fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 " +
        "pb-[max(1rem,env(safe-area-inset-bottom))] backdrop-blur-sm sm:items-center"
      }
      // Tocar afuera cancela. Con mousedown y no click: si se arrastra una
      // selección desde adentro y se suelta afuera, no se cierra.
      onMouseDown={(evento) => {
        if (evento.target === evento.currentTarget && !cargando) onCancelar();
      }}
    >
      <div
        ref={dialogo}
        role="dialog"
        aria-modal="true"
        aria-labelledby={idTitulo}
        aria-describedby={idMensaje}
        onKeyDown={atraparFoco}
        className="w-full max-w-sm rounded-3xl border border-borde bg-panel p-6"
      >
        <h2 id={idTitulo} className="text-xl font-semibold">
          {titulo}
        </h2>
        <div id={idMensaje} className="mt-2 text-base leading-snug text-tenue">
          {mensaje}
        </div>

        {/* En el celular van apilados y Confirmar queda arriba, Cancelar abajo
            al alcance del pulgar; desde sm, en fila con Confirmar a la derecha. */}
        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row">
          <Boton variante="secundario" data-cancelar="" onClick={onCancelar} disabled={cargando}>
            {textoCancelar}
          </Boton>
          <Boton variante={peligro ? "peligro" : "principal"} cargando={cargando} onClick={onConfirmar}>
            {textoConfirmar}
          </Boton>
        </div>
      </div>
    </div>,
    document.body,
  );
}
