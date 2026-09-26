import { useEffect, useRef, useState, type FormEvent } from "react";
import { ExclamationTriangleIcon, TvIcon } from "@heroicons/react/24/outline";

import { ErrorApi, pantalla } from "../api/client";
import { textos } from "./textos";

const t = textos.conectar;

interface Props {
  onVinculada: (token: string) => void;
}

/**
 * Lo que ve una tele en `/p`, sin token.
 *
 * El link completo de la pantalla mide 68 caracteres, de los cuales 32 son el
 * token al azar. Tipearlo con un control remoto, en un teclado en pantalla y con
 * la cruceta, son cinco minutos y un error de tipeo de volver a empezar. Acá se
 * cargan seis dígitos, que es lo único que un control hace bien: tiene teclado
 * numérico.
 *
 * Todo está dimensionado para leerse desde el otro lado de un salón, no desde
 * una silla frente a un monitor.
 */
export default function PaginaVincular({ onVinculada }: Props) {
  const [codigo, setCodigo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const entrada = useRef<HTMLInputElement>(null);

  useEffect(() => {
    document.title = t.pestana;
    // El foco va puesto solo: en una tele nadie quiere buscar el campo con la
    // cruceta antes de poder escribir.
    entrada.current?.focus();
  }, []);

  const soloDigitos = codigo.replace(/\D/g, "");

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (soloDigitos.length !== 6 || enviando) return;
    setEnviando(true);
    setError(null);
    try {
      onVinculada(await pantalla.canjear(soloDigitos));
    } catch (e) {
      setError(mensajeDeCanje(e));
      setCodigo("");
      entrada.current?.focus();
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="flex min-h-full flex-col items-center justify-center gap-6 p-4 text-center sm:gap-8 sm:p-8">
      <div className="flex flex-col items-center">
        {/* La tele dibujada dice qué se conecta antes de leer el título: quien
            abrió /p en el celular por error se da cuenta de un vistazo. No más
            grande: en una tele de 1280×720 con el error a la vista, un ícono
            de 80 px ya hace scroll. */}
        <TvIcon aria-hidden className="mb-3 h-12 w-12 shrink-0 text-acento sm:h-14 sm:w-14" />
        <h1 className="text-3xl font-semibold leading-tight sm:text-5xl">{t.titulo}</h1>
        <p className="mx-auto mt-3 max-w-2xl text-lg leading-snug text-tenue sm:text-2xl">
          {t.instrucciones}
        </p>
      </div>

      <form onSubmit={enviar} className="flex w-full max-w-md flex-col items-center gap-6 rounded-3xl border border-borde bg-panel p-6 sm:p-8">
        <input
          ref={entrada}
          value={codigo}
          onChange={(e) => setCodigo(e.target.value.replace(/[^\d\s-]/g, "").slice(0, 9))}
          // `tel` y no `number`: en una tele y en un celular abre el teclado
          // numérico, y no muestra las flechitas de incremento.
          type="tel"
          inputMode="numeric"
          autoComplete="off"
          placeholder="000000"
          aria-label={t.campo}
          // 12ch y no menos: con `tracking-[0.2em]`, el relleno y el borde, en 9ch
          // se cortaba el último dígito. Así entra también «800 181» con espacio.
          className="w-[12ch] max-w-full rounded-2xl border-4 border-borde bg-hundido px-3 py-4 text-center font-mono text-4xl tracking-[0.2em] text-white outline-none focus:border-acento sm:px-6 sm:text-6xl"
        />

        <button
          type="submit"
          disabled={soloDigitos.length !== 6 || enviando}
          className="min-h-boton rounded-full bg-acento px-10 text-xl font-semibold text-white transition disabled:opacity-40 sm:text-2xl"
        >
          {enviando ? t.conectando : t.boton}
        </button>
      </form>

      {/* role="alert": se anuncia aunque el foco siga en el campo. */}
      {error && (
        <p
          role="alert"
          className="flex max-w-xl items-start gap-2 text-left text-lg leading-snug text-naranja sm:gap-3 sm:text-2xl"
        >
          {/* Alineado a la primera línea: el mensaje puede ocupar dos. */}
          <ExclamationTriangleIcon aria-hidden className="mt-0.5 h-6 w-6 shrink-0 sm:h-8 sm:w-8" />
          <span>{error}</span>
        </p>
      )}

      <p className="max-w-xl text-base text-tenue sm:text-lg">{t.vigencia}</p>
    </main>
  );
}

/**
 * Los mensajes del canje, escritos para quien está frente a la tele: cada uno
 * dice qué hacer. El del backend para un código malo ("Generá uno nuevo") le
 * habla a quien tiene el panel, que acá suele ser otra persona.
 */
function mensajeDeCanje(error: unknown): string {
  if (!(error instanceof ErrorApi)) return t.sinRed;
  switch (error.codigo) {
    case "EVENTO_NO_ENCONTRADO":
      return t.codigoNoSirve;
    case "DEMASIADOS_PEDIDOS":
      // El tope es de 30 intentos cada diez minutos: "esperá un momento" se
      // queda corto.
      return t.demasiados;
    case "SIN_RED":
      // http 0 es que no hubo respuesta: la tele no tiene red. Con otro
      // número respondió algo que no era la app (Render despertando).
      return error.http === 0 ? t.sinRed : error.message;
    default:
      return error.message;
  }
}
