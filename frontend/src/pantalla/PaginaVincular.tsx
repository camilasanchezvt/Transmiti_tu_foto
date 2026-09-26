import { useEffect, useRef, useState, type FormEvent } from "react";

import { ErrorApi, pantalla } from "../api/client";

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
    document.title = "Vincular pantalla · Transmití tu foto";
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
      setError(e instanceof ErrorApi ? e.message : "No pudimos conectarnos. Probá de nuevo");
      setCodigo("");
      entrada.current?.focus();
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="flex min-h-full flex-col items-center justify-center gap-6 p-4 text-center sm:gap-8 sm:p-8">
      <div>
        <h1 className="text-3xl font-semibold leading-tight sm:text-5xl">Vinculá esta pantalla</h1>
        <p className="mt-3 text-lg text-tenue sm:text-2xl">
          Pedí el código en el panel y cargalo acá
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
          aria-label="Código de seis dígitos"
          // 12ch y no menos: con `tracking-[0.2em]`, el relleno y el borde, en 9ch
          // se cortaba el último dígito. Así entra también «800 181» con espacio.
          className="w-[12ch] max-w-full rounded-2xl border-4 border-borde bg-hundido px-3 py-4 text-center font-mono text-4xl tracking-[0.2em] text-white outline-none focus:border-acento sm:px-6 sm:text-6xl"
        />

        <button
          type="submit"
          disabled={soloDigitos.length !== 6 || enviando}
          className="min-h-boton rounded-full bg-acento px-10 text-xl font-semibold text-white transition disabled:opacity-40 sm:text-2xl"
        >
          {enviando ? "Vinculando…" : "Vincular"}
        </button>
      </form>

      {error && <p className="max-w-xl text-lg text-naranja sm:text-2xl">{error}</p>}

      <p className="max-w-xl text-base text-tenue sm:text-lg">
        El código dura diez minutos y sirve una sola vez.
      </p>
    </main>
  );
}
