import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { ExclamationTriangleIcon } from "@heroicons/react/24/outline";

import { comun } from "../admin/textos/comun";
import Boton from "./Boton";
import type { Icono } from "./icono";

interface Props {
  abierto: boolean;
  titulo: string;
  mensaje: ReactNode;
  textoConfirmar: string;
  /** Por defecto "Cancelar". */
  textoCancelar?: string;
  /** Para lo que no tiene vuelta atrás fácil: el botón de confirmar va en rojo
   *  y el título lleva el triángulo de aviso. */
  peligro?: boolean;
  /**
   * El ícono del botón de confirmar, el mismo que tiene la acción en la página
   * (StopCircleIcon para terminar, NoSymbolIcon para dar de baja…). Del juego
   * 24/solid si confirma algo común, 24/outline si es `peligro`. Opcional.
   */
  iconoConfirmar?: Icono;
  /** Mientras se espera la respuesta: el botón muestra "Esperá…" y el diálogo
   *  no se cierra ni con Escape ni tocando afuera. */
  cargando?: boolean;
  /**
   * Confirmación escrita, para lo que no tiene vuelta atrás de ninguna forma
   * (eliminar una cuenta, borrar un evento). Debajo del mensaje va un campo con
   * `etiqueta`, y debajo de la etiqueta, destacado, el `texto` a escribir.
   * Confirmar queda deshabilitado hasta que lo escrito coincida con lo que se
   * ve (ver `normalizar`); vacío no coincide nunca. El foco arranca en el campo
   * y Enter confirma sólo si coincide. `teclado: "email"` abre el teclado con @
   * en el celular. Sin esto, el diálogo es el de siempre.
   */
  aEscribir?: { texto: string; etiqueta: string; teclado?: "text" | "email" };
  /**
   * El error de la acción, si falló y el diálogo sigue abierto para reintentar.
   * Va donde no mueve los botones en el celular: con `aEscribir` el diálogo
   * está anclado arriba, así que va DEBAJO de los botones; sin campo está
   * anclado abajo y va arriba de ellos. Si empujara los botones, el de
   * confirmar quedaría justo donde estaba Cancelar, bajo el pulgar.
   */
  error?: ReactNode;
  /** Recibe lo que se escribió en el campo, tal cual (sin campo, ""): con
   *  `aEscribir`, eso es lo que se le manda al backend para que confirme él
   *  también, y no el texto que ya se sabía. */
  onConfirmar: (escrito: string) => void;
  onCancelar: () => void;
}

/** Los dos botones, desde sm: ver el comentario donde se usan. */
const BOTON_EN_FILA = "sm:min-w-fit sm:flex-1";

/**
 * Cómo se compara lo escrito: como se ve. Sin mayúsculas, sin espacios
 * alrededor, con los de adentro juntados en uno y las tildes en una sola forma
 * (NFC: una "é" pegada desde macOS viene en dos caracteres). El navegador junta
 * los espacios al mostrar el texto, así que un espacio doble no se ve ni se
 * puede copiar, y en el celular dos espacios seguidos escriben ". ".
 * "  Ana@Mail.com " vale por "ana@mail.com"; "Boda  de Ana", por "boda de ana".
 *
 * El backend compara igual: `_nombre_comparable` al borrar un evento. Al
 * eliminar una cuenta compara sin mayúsculas ni espacios alrededor, que para
 * un email (sin espacios adentro, en ASCII) es lo mismo.
 */
function normalizar(texto: string): string {
  return texto.normalize("NFC").trim().replace(/\s+/g, " ").toLowerCase();
}

/**
 * Diálogo de confirmación, de vidrio, para las pocas acciones que merecen una
 * pregunta (terminar el evento, dar de baja una cuenta, aprobar todas las
 * fotos de una vez). Aprobar o rechazar una sola foto NO lo usa: ahí la red de
 * seguridad es Deshacer.
 *
 * El foco arranca en Cancelar, no en Confirmar: un Enter de más no puede
 * terminar un evento. Escape y tocar afuera cancelan. Con `aEscribir`, arranca
 * en el campo: escribir es lo único que se puede hacer.
 *
 * Va en un portal sobre <body>: `.bg-panel` usa backdrop-filter, y cualquier
 * ancestro con backdrop-filter convierte a `position: fixed` en relativo a él.
 * Sin portal, un Confirmar dentro de una tarjeta quedaría encerrado en la
 * tarjeta.
 */
export default function Confirmar(props: Props) {
  // Cerrado no se monta: así cada vez que se abre, lo escrito arranca vacío.
  if (!props.abierto) return null;
  return <Dialogo {...props} />;
}

function Dialogo({
  titulo,
  mensaje,
  textoConfirmar,
  textoCancelar = comun.cancelar,
  peligro = false,
  iconoConfirmar,
  cargando = false,
  aEscribir,
  error,
  onConfirmar,
  onCancelar,
}: Props) {
  const dialogo = useRef<HTMLDivElement>(null);
  const idTitulo = useId();
  const idMensaje = useId();
  const idCampo = useId();
  const [escrito, setEscrito] = useState("");

  // Sin confirmación escrita, se puede confirmar siempre. Con ella, lo vacío
  // no coincide nunca: un texto a escribir en blanco no habilita Confirmar
  // apenas se abre el diálogo.
  const normalizado = normalizar(escrito);
  const coincide =
    !aEscribir || (normalizado !== "" && normalizado === normalizar(aEscribir.texto));

  // Se leen por ref para no volver a enganchar el teclado en cada render: la
  // página suele pasar una flecha nueva cada vez.
  const alCancelar = useRef(onCancelar);
  alCancelar.current = onCancelar;
  const ocupado = useRef(cargando);
  ocupado.current = cargando;

  useEffect(() => {
    // Al cerrar, el foco vuelve a donde estaba (el botón que abrió el diálogo).
    const previo = document.activeElement as HTMLElement | null;
    const inicial =
      dialogo.current?.querySelector<HTMLElement>("[data-escribir]") ??
      dialogo.current?.querySelector<HTMLElement>("[data-cancelar]");
    inicial?.focus();

    // Que la página de atrás no se desplace mientras el diálogo está abierto.
    const desborde = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const alPresionar = (evento: globalThis.KeyboardEvent) => {
      // Es modal: ninguna tecla le llega a la página de atrás. Sin esto, una A
      // en Revisar fotos aprobaría la foto de abajo con el diálogo abierto (o
      // al escribir un email con A en el campo). Los atajos escuchan en
      // window; esto corre antes, en document.
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
  }, []);

  // Mientras se espera, los dos botones se deshabilitan y el que tenía el foco
  // (se confirmó con un toque o un clic) lo pierde: queda en <body>, afuera, y
  // Tab se iría a la página de atrás. Si el diálogo sigue abierto cuando
  // termina, es que falló y se puede reintentar: el foco vuelve a Cancelar. Un
  // Enter de más no reintenta, y si se había confirmado con Enter desde el
  // campo, en el celular se cierra el teclado, que taparía el error (va debajo
  // de los botones). Sólo al terminar una espera: al abrir, el foco es el del
  // efecto de arriba.
  const esperaba = useRef(cargando);
  useEffect(() => {
    const termino = esperaba.current && !cargando;
    esperaba.current = cargando;
    const caja = dialogo.current;
    if (!termino || !caja) return;
    const enfocado = document.activeElement;
    const enUnBoton = caja.contains(enfocado) && !(enfocado as HTMLElement).hasAttribute("data-escribir");
    if (!enUnBoton) caja.querySelector<HTMLElement>("[data-cancelar]")?.focus();
  }, [cargando]);

  // El foco no se escapa del diálogo con Tab: da la vuelta entre el campo y
  // los botones.
  function atraparFoco(evento: KeyboardEvent<HTMLDivElement>) {
    if (evento.key !== "Tab" || !dialogo.current) return;
    const enfocables = Array.from(
      dialogo.current.querySelectorAll<HTMLElement>("input:not([disabled]), button:not([disabled])"),
    );
    const primero = enfocables[0];
    const ultimo = enfocables[enfocables.length - 1];
    if (!primero || !ultimo) return;
    if (evento.shiftKey && document.activeElement === primero) {
      evento.preventDefault();
      ultimo.focus();
    } else if (!evento.shiftKey && document.activeElement === ultimo) {
      evento.preventDefault();
      primero.focus();
    }
  }

  // Enter en el campo confirma, pero sólo si coincide: si no, no hace nada.
  // No es un <form> a propósito: Cancelar sería un submit más.
  function alTeclearEnCampo(evento: KeyboardEvent<HTMLInputElement>) {
    if (evento.key !== "Enter" || evento.nativeEvent.isComposing) return;
    evento.preventDefault();
    if (coincide && !cargando) onConfirmar(escrito);
  }

  return createPortal(
    <div
      className={
        "fixed inset-0 z-50 flex justify-center overflow-y-auto bg-velo p-4 " +
        "pb-[max(1rem,env(safe-area-inset-bottom))] backdrop-blur-sm sm:items-center " +
        // En el celular, abajo, al alcance del pulgar. Con campo, arriba: el
        // teclado ocupa la mitad de abajo y taparía lo que se está escribiendo.
        (aEscribir ? "items-start pt-[max(1rem,env(safe-area-inset-top))]" : "items-end")
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
        className="w-full max-w-sm rounded-3xl border border-borde bg-hoja p-6"
      >
        {/* Con peligro, el triángulo rojo va pegado al título, alineado a la
            primera línea: el título puede ocupar dos con un nombre largo. */}
        <h2
          id={idTitulo}
          className={`text-xl font-semibold ${peligro ? "flex items-start gap-2" : ""}`}
        >
          {peligro && (
            <ExclamationTriangleIcon aria-hidden className="mt-0.5 h-6 w-6 shrink-0 text-rojo" />
          )}
          <span className="min-w-0 break-words">{titulo}</span>
        </h2>
        <div id={idMensaje} className="mt-2 text-base leading-snug text-tenue">
          {mensaje}
        </div>

        {aEscribir && (
          <div className="mt-5">
            {/* La etiqueta incluye el texto a escribir: un lector de pantalla
                lee las dos cosas al llegar al campo. break-words y no
                break-all: el nombre de un evento se parte entre palabras
                ("Fernánde / z" invitaba a escribir un espacio de más), y sólo
                se parte una palabra que no entra sola en el renglón, como un
                email largo, que si no desbordaría a 375 px. */}
            <label htmlFor={idCampo} className="block text-sm leading-snug text-tenue">
              {aEscribir.etiqueta}
              <span className="mt-0.5 block break-words text-base font-semibold text-texto">
                {aEscribir.texto}
              </span>
            </label>
            {/* Siempre type="text", también para un email: no es algo a
                validar, es un texto a copiar a mano; inputMode elige el
                teclado. Sin autocompletar ni corrector: lo tiene que escribir
                la persona. */}
            <input
              id={idCampo}
              data-escribir=""
              type="text"
              inputMode={aEscribir.teclado ?? "text"}
              autoComplete="off"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              value={escrito}
              readOnly={cargando}
              onChange={(evento) => setEscrito(evento.target.value)}
              onKeyDown={alTeclearEnCampo}
              className={
                "mt-2 block h-12 w-full min-w-0 rounded-xl border border-borde bg-hundido px-3 " +
                "text-base text-texto outline-none focus:border-acento"
              }
            />
          </div>
        )}

        {/* Sin campo, anclado abajo: el error va arriba de los botones y el
            diálogo crece hacia arriba (ver la prop `error`). */}
        {!aEscribir && error ? <ErrorDelDialogo>{error}</ErrorDelDialogo> : null}

        {/* En el celular van apilados y Confirmar queda arriba, Cancelar abajo
            al alcance del pulgar. Desde sm, en fila con Confirmar a la derecha,
            pero sólo si los dos entran con el texto entero: el diálogo mide
            384 px y "Eliminar definitivamente" o "Habilitar como admin" se
            partían en dos renglones. Cada botón mide al menos su texto en un
            renglón (min-w-fit, sin pasarse del diálogo) y, si no entran, el de
            confirmar baja de renglón; wrap-reverse lo deja arriba, como en el
            celular. Si entran, flex-1 los deja del mismo ancho. */}
        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:flex-wrap-reverse">
          <Boton
            variante="secundario"
            data-cancelar=""
            onClick={onCancelar}
            disabled={cargando}
            className={BOTON_EN_FILA}
          >
            {textoCancelar}
          </Boton>
          <Boton
            variante={peligro ? "peligro" : "principal"}
            icono={iconoConfirmar}
            cargando={cargando}
            disabled={!coincide}
            onClick={() => onConfirmar(escrito)}
            className={BOTON_EN_FILA}
          >
            {textoConfirmar}
          </Boton>
        </div>

        {/* Con campo, anclado arriba: el error va debajo de los botones, que
            así no se mueven (ver la prop `error`). */}
        {aEscribir && error ? <ErrorDelDialogo>{error}</ErrorDelDialogo> : null}
      </div>
    </div>,
    document.body,
  );
}

function ErrorDelDialogo({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="mt-4 text-base leading-snug text-rojo-tinta">
      {children}
    </p>
  );
}
