// La cola de la pantalla de proyección.
//
// Corre sola durante horas delante de cien personas. Todo lo que hay acá está
// para que no se note: sin parpadeos entre fotos, sin frenarse porque se cortó
// la red, y sin que una foto rota trabe el pase.

import { useCallback, useEffect, useRef, useState } from "react";

import { ErrorApi, pantalla as api } from "../api/client";
import type { FotoPantalla, Pantalla } from "../api/tipos";

/** Espera creciente cuando el polling falla. Tope en 60 s. */
const ESPERAS_MS = [5_000, 10_000, 20_000, 40_000, 60_000];

/** Cuánto dura la marca de "llegó una nueva". */
const MARCA_MS = 4_000;

/** Fundido entre fotos. Lo usa la pantalla para la transición. */
export const FUNDIDO_MS = 700;

/** Cuánto queda la foto que sale debajo de la que entra. Un poco más que el
 *  fundido: la que entra arranca un cuadro después. Tiene que ser bastante
 *  menos que el mínimo de segundos por foto (3 s), o se pisa con el avance. */
const RETIRO_ANTERIOR_MS = FUNDIDO_MS + 300;

const LIMITE_ARRANQUE = 40;

/**
 * Cada cuántas pasadas se pide la lista completa en vez de sólo lo nuevo.
 *
 * El polling incremental pide `id > ultimo_id`, y eso deja un agujero: una foto
 * que estaba pendiente tiene un id MENOR que el de las que ya se aprobaron
 * después. Si el moderador la aprueba más tarde, `desde=ultimo_id` no la
 * devuelve nunca y esa foto no se proyecta jamás.
 *
 * No es hipotético. En los datos de desarrollo el arranque en frío deja
 * `ultimo_id` en 18 y quedan pendientes las 14, 17, 19 y 20: aprobar la 14 o la
 * 17 no las hace aparecer. Es la mitad de las pendientes.
 *
 * La resincronización lo tapa sin salirse del contrato: usa el mismo endpoint y
 * el mismo parámetro documentado (`desde=0`), sólo que cada tantas pasadas.
 */
const PASADAS_ENTRE_RESINCRONIZACIONES = 5;

export interface Cola {
  cargando: boolean;
  error: unknown;
  datos: Pantalla | null;
  /** La foto que se está mostrando. */
  foto: FotoPantalla | null;
  /** La anterior, mientras dura el fundido. */
  anterior: FotoPantalla | null;
  hayFotos: boolean;
  sinConexion: boolean;
  /** Cuántas aprobadas entraron recién. Se apaga sola. */
  llegaron: number;
}

/** Baraja suave: intercambia algunos pares vecinos, nada más.
 *
 *  Un evento de tres horas con cincuenta fotos las repite muchas veces. Sin
 *  esto, la vuelta doce es idéntica a la uno y se nota. Barajar del todo sería
 *  peor: la gente busca su foto y quiere que aparezca cerca de donde apareció. */
function reordenarLeve<T>(lista: T[]): T[] {
  const salida = [...lista];
  for (let i = 0; i < salida.length - 1; i++) {
    if (Math.random() < 0.35) {
      const a = salida[i]!;
      salida[i] = salida[i + 1]!;
      salida[i + 1] = a;
      i++;
    }
  }
  return salida;
}

/** Espera a que la imagen esté en memoria. Sin esto hay un parpadeo gris en
 *  cada cambio, que en un proyector se nota muchísimo. */
function precargar(url: string): Promise<boolean> {
  return new Promise((resolver) => {
    const img = new Image();
    img.onload = () => resolver(true);
    img.onerror = () => resolver(false);
    img.src = url;
  });
}

export function useCola(token: string): Cola {
  const [datos, setDatos] = useState<Pantalla | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [cargando, setCargando] = useState(true);
  const [sinConexion, setSinConexion] = useState(false);
  const [llegaron, setLlegaron] = useState(0);

  const [foto, setFoto] = useState<FotoPantalla | null>(null);
  const [anterior, setAnterior] = useState<FotoPantalla | null>(null);
  const [hayFotos, setHayFotos] = useState(false);

  // El buffer y el índice viven en refs y no en estado: los toca el polling y
  // el avance al mismo tiempo, y no queremos re-renderizar por cada cambio.
  const buffer = useRef<FotoPantalla[]>([]);
  const indice = useRef(0);
  const ultimoId = useRef(0);
  const vivo = useRef(true);

  // Se usan los valores sueltos y no el objeto `config`: el polling vuelve a
  // pedir la configuración en cada pasada y cada respuesta es un objeto nuevo.
  // Con el objeto en las dependencias, el temporizador del avance se reiniciaba
  // cada 6 s y, con 7 s por foto, no llegaba a cumplirse nunca.
  const segundosPorFoto = datos?.config.segundos_por_foto;
  const intervaloPolling = datos?.config.intervalo_polling_ms;
  const maximoBuffer = datos?.config.maximo_buffer;

  // Cuenta avances. Con una sola foto, la "siguiente" es la misma y `foto` no
  // cambia: sin este contador el avance no se volvía a programar nunca, ni
  // siquiera cuando después llegaban más.
  const [avances, setAvances] = useState(0);

  // ── Arranque en frío ────────────────────────────────────────
  useEffect(() => {
    vivo.current = true;
    const control = new AbortController();

    (async () => {
      try {
        const info = await api.config(token, control.signal);
        if (!vivo.current) return;
        setDatos(info);

        const cola = await api.fotos(token, 0, LIMITE_ARRANQUE, control.signal);
        if (!vivo.current) return;

        buffer.current = cola.fotos;
        ultimoId.current = cola.ultimo_id;
        indice.current = 0;
        setHayFotos(cola.fotos.length > 0);
        setFoto(cola.fotos[0] ?? null);
        setCargando(false);
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") return;
        if (!vivo.current) return;
        setError(e);
        setCargando(false);
      }
    })();

    return () => {
      vivo.current = false;
      control.abort();
    };
  }, [token]);

  // ── Polling incremental, con espera creciente ───────────────
  const fallos = useRef(0);

  const pasadas = useRef(0);

  const buscarNuevas = useCallback(async () => {
    if (!maximoBuffer) return;
    try {
      pasadas.current++;
      const toca = pasadas.current % PASADAS_ENTRE_RESINCRONIZACIONES === 0;

      const cola = toca
        ? await api.fotos(token, 0, maximoBuffer)
        : await api.fotos(token, ultimoId.current);
      if (!vivo.current) return;

      fallos.current = 0;
      setSinConexion(false);

      // El estado del evento puede haber cambiado (lo cerraron desde el panel).
      api.config(token).then((info) => vivo.current && setDatos(info)).catch(() => {});

      // En una resincronización vuelve todo, no sólo lo nuevo: hay que quedarse
      // con lo que la pantalla todavía no tiene.
      const conocidas = new Set(buffer.current.map((f) => f.id));
      const recien = cola.fotos.filter((f) => !conocidas.has(f.id));

      ultimoId.current = Math.max(ultimoId.current, cola.ultimo_id);

      if (recien.length === 0) return;

      // Las nuevas entran DETRÁS de la que está en pantalla, no al final: así
      // el invitado que la mandó la ve antes de irse de la mesa.
      const corte = Math.min(indice.current + 1, buffer.current.length);
      buffer.current = [
        ...buffer.current.slice(0, corte),
        ...recien,
        ...buffer.current.slice(corte),
      ];

      // Si se pasó del tope, se descartan las más VIEJAS, nunca las recién
      // insertadas.
      const tope = maximoBuffer;
      if (buffer.current.length > tope) {
        const sobran = buffer.current.length - tope;
        const nuevas = new Set(recien.map((f) => f.id));
        let quitadas = 0;
        buffer.current = buffer.current.filter((f, i) => {
          if (quitadas >= sobran || nuevas.has(f.id) || i >= corte) return true;
          quitadas++;
          if (i <= indice.current) indice.current--;
          return false;
        });
      }

      if (!hayFotos) {
        setHayFotos(true);
        indice.current = 0;
        // Entra sola, desde el fondo: no hay de dónde fundir.
        setAnterior(null);
        setFoto(buffer.current[0] ?? null);
      }

      setLlegaron(recien.length);
      window.setTimeout(() => vivo.current && setLlegaron(0), MARCA_MS);
    } catch (e) {
      if (!vivo.current) return;
      if (e instanceof ErrorApi && !e.esDeRed && e.http >= 400 && e.http < 500) {
        // El evento dejó de existir o el token cambió: no tiene sentido seguir.
        setError(e);
        return;
      }
      fallos.current++;
      setSinConexion(true);
    }
  }, [token, maximoBuffer, hayFotos]);

  useEffect(() => {
    if (!intervaloPolling) return;
    let cancelado = false;
    let id: number;

    const programar = () => {
      const espera =
        fallos.current === 0
          ? intervaloPolling
          : ESPERAS_MS[Math.min(fallos.current - 1, ESPERAS_MS.length - 1)]!;
      id = window.setTimeout(async () => {
        if (cancelado) return;
        await buscarNuevas();
        if (!cancelado) programar();
      }, espera);
    };

    programar();
    return () => {
      cancelado = true;
      window.clearTimeout(id);
    };
  }, [intervaloPolling, buscarNuevas]);

  // ── Avance, con precarga ────────────────────────────────────
  useEffect(() => {
    if (!segundosPorFoto || !hayFotos || !foto) return;
    let cancelado = false;

    const id = window.setTimeout(async () => {
      if (cancelado) return;

      // Se busca la próxima que cargue. Una imagen rota se saca del buffer y se
      // sigue: un 404 puntual no puede frenar el pase.
      for (let intentos = 0; intentos < buffer.current.length + 1; intentos++) {
        if (cancelado || buffer.current.length === 0) return;

        let siguiente = indice.current + 1;
        if (siguiente >= buffer.current.length) {
          buffer.current = reordenarLeve(buffer.current);
          siguiente = 0;
        }

        const candidata = buffer.current[siguiente];
        if (!candidata) return;

        if (await precargar(candidata.url)) {
          if (cancelado) return;
          indice.current = siguiente;
          if (candidata.id !== foto.id) {
            setAnterior(foto);
            setFoto(candidata);
          }
          setAvances((n) => n + 1);
          return;
        }

        buffer.current.splice(siguiente, 1);
        if (siguiente <= indice.current) indice.current--;
        if (buffer.current.length === 0) {
          setHayFotos(false);
          setAnterior(null);
          setFoto(null);
          return;
        }
      }
    }, segundosPorFoto * 1000);

    return () => {
      cancelado = true;
      window.clearTimeout(id);
    };
  }, [segundosPorFoto, foto, hayFotos, avances]);

  // ── La anterior se va cuando termina el fundido ─────────────
  // La pantalla usa la foto como key de cada capa. Si la que salió se quedaba
  // montada, volver a ella la reutilizaba ya visible y el cambio era un corte
  // seco: con dos fotos pasaba en cada cambio, y con tres cuando la baraja la
  // dejaba primera. Retirándola, la que entra siempre se monta de nuevo,
  // transparente, y hace el fundido. De paso queda una sola capa desenfocada
  // en vez de dos, que en la notebook del proyector se nota.
  useEffect(() => {
    if (!anterior) return;
    const id = window.setTimeout(() => setAnterior(null), RETIRO_ANTERIOR_MS);
    return () => window.clearTimeout(id);
  }, [anterior]);

  return { cargando, error, datos, foto, anterior, hayFotos, sinConexion, llegaron };
}
