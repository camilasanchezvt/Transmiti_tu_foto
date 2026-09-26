import { useId, useState, type InputHTMLAttributes, type ReactNode, type Ref } from "react";
import { Link } from "react-router-dom";
import { CheckIcon, ExclamationTriangleIcon, EyeIcon, EyeSlashIcon } from "@heroicons/react/20/solid";

import { ErrorApi } from "../api/client";
import { claseIconoChip } from "../comp/icono";
import { acceso } from "./textos/acceso";
import { comun } from "./textos/comun";

// Piezas de las páginas de acceso: Entrar y Crear cuenta, y ninguna otra. El
// resto del panel vive dentro de LayoutAdmin y tiene sus propios formularios;
// por eso están acá y no en comp/.

/** Centrado en la pantalla, angosto como un formulario de iOS. En el celular,
 *  p-4 a los costados; el py extra es para que con el teclado abierto la
 *  tarjeta no quede pegada al borde. */
export function MarcoAcceso({ children }: { children: ReactNode }) {
  return (
    <main className="mx-auto flex min-h-full w-full max-w-sm flex-col justify-center gap-4 px-4 py-10 sm:px-8">
      {children}
    </main>
  );
}

interface PropsCampo extends Omit<InputHTMLAttributes<HTMLInputElement>, "className" | "id"> {
  etiqueta: string;
  /** Si hay error, reemplaza a la ayuda y el campo queda marcado en rojo. */
  error?: string | null;
  /** Texto chico debajo del campo, siempre visible: el mínimo de la contraseña. */
  ayuda?: string | null;
  /** La ayuda en verde: lo que pedía ya se cumple. */
  ayudaCumplida?: boolean;
  refCampo?: Ref<HTMLInputElement>;
}

/**
 * Un campo con su etiqueta visible arriba (el placeholder solo desaparece al
 * escribir y deja a quien vuelve al campo sin saber qué era). 48 px de alto y
 * texto de 16 px: con menos, Safari del iPhone hace zoom al tocarlo.
 *
 * Los de contraseña traen "Mostrar", con el ojo: en el celular se escribe sin
 * ver las teclas y una contraseña de diez caracteres con un error adentro no
 * se encuentra de otra forma.
 */
export function Campo({
  etiqueta,
  error,
  ayuda,
  ayudaCumplida = false,
  refCampo,
  type = "text",
  ...resto
}: PropsCampo) {
  const id = useId();
  const idNota = `${id}-nota`;
  const esPassword = type === "password";
  const [visible, setVisible] = useState(false);
  const nota = error || ayuda;
  const cumplida = !error && ayudaCumplida;
  const IconoOjo = visible ? EyeSlashIcon : EyeIcon;

  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <label htmlFor={id} className="text-sm text-tenue">
        {etiqueta}
      </label>
      <div className="relative">
        <input
          {...resto}
          ref={refCampo}
          id={id}
          type={esPassword && visible ? "text" : type}
          aria-invalid={error ? true : undefined}
          aria-describedby={nota ? idNota : undefined}
          className={
            "h-12 w-full min-w-0 rounded-xl border bg-hundido px-3 text-base text-white outline-none " +
            "transition-colors focus:border-acento " +
            (error ? "border-rojo " : "border-borde ") +
            // El mismo ancho que el botón de adentro: lo escrito no pasa por
            // debajo del ojo.
            (esPassword ? "pr-28" : "")
          }
        />
        {esPassword && (
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            // En la compu, que el clic no le saque el foco al campo: se sigue
            // escribiendo sin volver a hacer clic adentro.
            onMouseDown={(e) => e.preventDefault()}
            // Sin aria-label ni aria-pressed: el nombre sale del contenido y
            // empieza con la palabra que se ve ("Mostrar lo que escribiste en
            // Contraseña"). Con control por voz, "tocar Mostrar" lo encuentra.
            // Ancho fijo (w-28): "Mostrar" y "Ocultar" no miden lo mismo, y
            // sin esto el botón saltaría de lugar con cada toque.
            className={
              "absolute inset-y-0 right-0 flex min-h-11 w-28 items-center justify-center gap-1.5 rounded-r-xl px-3 " +
              "text-sm font-medium text-acento transition hover:brightness-125 " +
              "focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-acento"
            }
          >
            <IconoOjo aria-hidden className="h-5 w-5 shrink-0" />
            {visible ? acceso.ocultarPassword : acceso.mostrarPassword}
            {/* sr-only es absolute: no ocupa lugar en el flex ni suma gap. */}
            <span className="sr-only">{acceso.sufijoPasswordOculto(etiqueta)}</span>
          </button>
        )}
      </div>
      {nota && (
        <p
          id={idNota}
          className={
            "flex items-start gap-1 text-sm leading-snug " +
            (error ? "text-rojo" : cumplida ? "text-verde" : "text-tenue")
          }
        >
          {/* El tilde no es sólo color: con el brillo bajo o con daltonismo,
              el verde solo no se distingue del gris. Para quien no lo ve, lo
              dice el texto oculto. */}
          {cumplida && (
            <>
              <CheckIcon aria-hidden className={`mt-0.5 ${claseIconoChip}`} />
              <span className="sr-only">{acceso.cumplido}</span>
            </>
          )}
          <span className="min-w-0">{nota}</span>
        </p>
      )}
    </div>
  );
}

type TonoAviso = "error" | "aviso";

/** Un recuadro de color dentro de la tarjeta, arriba del botón, con el
 *  triángulo de advertencia. `aviso` es para lo que no es un error de tipeo:
 *  una cuenta que espera que la habiliten no se arregla escribiendo otra
 *  cosa. */
export function Aviso({
  tono = "error",
  refAviso,
  children,
}: {
  tono?: TonoAviso;
  refAviso?: Ref<HTMLParagraphElement>;
  children: ReactNode;
}) {
  return (
    <p
      ref={refAviso}
      role="alert"
      className={
        "flex items-start gap-2 rounded-2xl px-4 py-3 text-base leading-snug " +
        (tono === "aviso" ? "bg-naranja/15 text-naranja" : "bg-rojo/15 text-rojo")
      }
    >
      {/* 20 px contra un renglón de 22: baja 1 px para quedar centrado en el
          primero aunque el mensaje ocupe dos. */}
      <ExclamationTriangleIcon aria-hidden className="mt-px h-5 w-5 shrink-0" />
      <span className="min-w-0 break-words">{children}</span>
    </p>
  );
}

/** El mensaje del backend, tal cual. Un 403 en el acceso es una cuenta
 *  pendiente o dada de baja: va como aviso, no como error. */
export function AvisoDeError({
  error,
  refAviso,
}: {
  error: unknown;
  refAviso?: Ref<HTMLParagraphElement>;
}) {
  const mensaje = error instanceof ErrorApi ? error.message : comun.errores.generico;
  const tono: TonoAviso = error instanceof ErrorApi && error.esSinPermiso ? "aviso" : "error";
  return (
    <Aviso tono={tono} refAviso={refAviso}>
      {mensaje}
    </Aviso>
  );
}

/** "¿No tenés cuenta? Creá una", debajo de la tarjeta. El link mide 44 px de
 *  alto aunque el texto sea chico: se toca con el dedo. */
export function PieAcceso({ pregunta, a, texto }: { pregunta: string; a: string; texto: string }) {
  return (
    <p className="flex flex-wrap items-center justify-center gap-x-1 text-center text-base text-tenue">
      <span>{pregunta}</span>
      <Link
        to={a}
        className={
          "inline-flex min-h-11 items-center rounded-full px-2 font-semibold text-acento " +
          "transition hover:brightness-125 focus:outline-none focus-visible:ring-2 focus-visible:ring-acento"
        }
      >
        {texto}
      </Link>
    </p>
  );
}
