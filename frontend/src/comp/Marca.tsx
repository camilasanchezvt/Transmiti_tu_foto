import { CameraIcon } from "@heroicons/react/24/solid";

import { comun } from "../admin/textos/comun";

/**
 * La marca de la app: el símbolo y el nombre.
 *
 * El símbolo es un ícono de app de iOS: un cuadrado con las esquinas de iOS
 * (el radio es el 22 % del lado), relleno con el azul de acento y la cámara de
 * heroicons (24/solid) en blanco, al 58 % del lado, como los glifos de las apps
 * de Apple. Sin degradés, sin brillos, sin sombra: en iOS 7 en adelante los
 * íconos son planos, y cualquier efecto encima se ve fabricado.
 *
 * El mismo símbolo es el favicon (public/favicon.svg) y el ícono que guarda el
 * iPhone al agregar el panel a la pantalla de inicio (public/apple-touch-icon.png,
 * sin las esquinas: iOS las recorta solo). Si cambia uno, cambian los tres.
 *
 * Dos tamaños:
 *
 *   <Marca />                      la barra del panel: símbolo de 32 px y el
 *                                  nombre al lado, a 17 px como el título de
 *                                  una barra de iOS. En un celular angosto no
 *                                  entra al lado de la foto de perfil y de
 *                                  Salir: por debajo de 360 px va sólo el
 *                                  símbolo, y el nombre queda para el lector
 *                                  de pantalla (le sigue dando nombre al link).
 *   <Marca tamano="grande" />      arriba de la tarjeta en las páginas de
 *                                  acceso (la pone MarcoAcceso): el nombre
 *                                  debajo del símbolo. En Entrar, donde es el
 *                                  título, 64 px y el nombre a 28; en las
 *                                  demás, 56 px y el nombre a 17.
 *
 * El nombre es texto, no parte de una imagen: lo lee un lector de pantalla y
 * nombra al link que lo envuelve. El símbolo es decorativo (aria-hidden).
 */

export type TamanoMarca = "barra" | "grande";

interface Props {
  tamano?: TamanoMarca;
  /** Sólo "grande": una línea debajo del nombre, en gris. */
  subtitulo?: string;
  /**
   * Sólo "grande": el nombre es el título de la página (un <h1> con este id,
   * para el aria-labelledby del formulario). En Entrar la marca ES el título;
   * en las otras páginas de acceso el título es otro ("Creá tu cuenta") y el
   * nombre va más chico, para no competir con él.
   */
  idTitulo?: string;
  className?: string;
}

/** El cuadrado azul con la cámara. `clase` trae el tamaño (h-8 w-8…). */
export function SimboloMarca({ clase }: { clase: string }) {
  return (
    <span
      aria-hidden
      className={`inline-flex shrink-0 items-center justify-center rounded-[22%] bg-acento text-luz ${clase}`}
    >
      <CameraIcon className="h-[58%] w-[58%]" />
    </span>
  );
}

export default function Marca({ tamano = "barra", subtitulo, idTitulo, className = "" }: Props) {
  if (tamano === "barra") {
    return (
      <span className={`inline-flex min-w-0 items-center gap-2.5 ${className}`}>
        <SimboloMarca clase="h-8 w-8" />
        {/* Por debajo de 360 px, sólo el símbolo: el nombre sigue ahí para el
            lector de pantalla y le da nombre al link. */}
        <span className="sr-only whitespace-nowrap text-[17px] font-semibold leading-none tracking-[-0.022em] min-[360px]:not-sr-only">
          {comun.marca}
        </span>
      </span>
    );
  }

  const esTitulo = idTitulo !== undefined;
  const Nombre = esTitulo ? "h1" : "p";

  return (
    <div className={`flex flex-col items-center text-center ${className}`}>
      <SimboloMarca clase={esTitulo ? "h-16 w-16" : "h-14 w-14"} />
      <Nombre
        id={idTitulo}
        className={
          "text-balance font-semibold text-texto " +
          (esTitulo
            ? "mt-4 text-[28px] leading-tight tracking-[-0.025em]"
            : "mt-3 text-[17px] leading-snug tracking-[-0.022em]")
        }
      >
        {comun.marca}
      </Nombre>
      {subtitulo && <p className="mt-1 text-balance text-base leading-snug text-tenue">{subtitulo}</p>}
    </div>
  );
}
