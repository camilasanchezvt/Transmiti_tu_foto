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
    <main className="flex h-full flex-col items-center justify-center gap-8 p-8 text-center">
      <div>
        <h1 className="text-5xl font-semibold leading-tight">Vinculá esta pantalla</h1>
        <p className="mt-3 text-2xl text-tenue">
          Pedí el código en el panel y cargalo acá
        </p>
      </div>

      <form onSubmit={enviar} className="flex flex-col items-center gap-6">
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
          className="w-[9ch] rounded-2xl border-4 border-borde bg-panel px-6 py-4 text-center font-mono text-6xl tracking-[0.2em] text-white outline-none focus:border-acento"
        />

        <button
          type="submit"
          disabled={soloDigitos.length !== 6 || enviando}
          className="min-h-boton rounded-2xl bg-acento px-10 text-2xl font-semibold text-black transition disabled:opacity-40"
        >
          {enviando ? "Vinculando…" : "Vincular"}
        </button>
      </form>

      {error && <p className="max-w-xl text-2xl text-amber-300">{error}</p>}

      <p className="max-w-xl text-lg text-tenue">
        El código dura diez minutos y sirve una sola vez.
      </p>
    </main>
  );
}
