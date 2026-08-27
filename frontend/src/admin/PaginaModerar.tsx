import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ErrorApi, admin, haySesion } from "../api/client";
import type { EstadoFoto, EventoAdmin, FotoAdmin } from "../api/tipos";
import Cargando from "../comp/Cargando";
import MensajeError from "../comp/MensajeError";
import { colorDelEvento } from "./color";
import { useAtajos, type Accion } from "./useAtajos";

const REFRESCO_MS = 10_000;
const LIMITE = 200;

interface Decision {
  foto: FotoAdmin;
  indice: number;
  estado: EstadoFoto;
}

/**
 * La bandeja. Objetivo medible: cincuenta fotos en menos de dos minutos.
 *
 * Sin confirmaciones. Nada de "¿estás segura?" antes de rechazar: duplicaría los
 * clics de la tarea que más se repite para prevenir un error que se deshace con
 * una tecla. La red de seguridad es Z.
 */
export default function PaginaModerar() {
  const { id = "" } = useParams();
  const idEvento = Number(id);
  const navegar = useNavigate();

  const [evento, setEvento] = useState<EventoAdmin | null>(null);
  const [fotos, setFotos] = useState<FotoAdmin[]>([]);
  const [indice, setIndice] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  // Las que llegaron mientras se modera. NO se incorporan solas: una lista que
  // se reacomoda sola hace que se apruebe la foto equivocada.
  const [enEspera, setEnEspera] = useState<FotoAdmin[]>([]);

  const [seleccion, setSeleccion] = useState<Set<number>>(new Set());
  const anclaSeleccion = useRef<number | null>(null);
  const historial = useRef<Decision[]>([]);
  const ultimoId = useRef(0);

  // ── Carga inicial ───────────────────────────────────────────
  useEffect(() => {
    if (!haySesion()) {
      navegar("/admin/login");
      return;
    }
    let vivo = true;
    (async () => {
      try {
        const eventos = await admin.eventos();
        const mio = eventos.find((e) => e.id === idEvento);
        if (!mio) throw new ErrorApi("EVENTO_NO_ENCONTRADO", "No encontramos este evento", 404);
        const lista = await admin.fotos(idEvento, { estado: "pendiente", limite: LIMITE });
        if (!vivo) return;
        setEvento(mio);
        setFotos(lista.fotos);
        ultimoId.current = lista.ultimo_id;
        setCargando(false);
      } catch (e) {
        if (!vivo) return;
        if (e instanceof ErrorApi && e.codigo === "NO_AUTORIZADO") {
          navegar("/admin/login");
          return;
        }
        setError(e);
        setCargando(false);
      }
    })();
    return () => {
      vivo = false;
    };
  }, [idEvento, navegar]);

  // El nombre del evento en el título de la pestaña: con dos pestañas abiertas
  // es lo único que las distingue en la barra.
  useEffect(() => {
    if (evento) document.title = `${evento.pendientes ? "" : ""}${evento.nombre} · Moderar`;
  }, [evento]);

  // ── Auto-refresco que no mueve la posición ──────────────────
  useEffect(() => {
    if (!evento) return;
    const id = window.setInterval(async () => {
      try {
        const lista = await admin.fotos(idEvento, {
          estado: "pendiente",
          desde: ultimoId.current,
          limite: LIMITE,
        });
        if (lista.fotos.length === 0) return;
        ultimoId.current = lista.ultimo_id;
        setEnEspera((previas) => [...previas, ...lista.fotos]);
      } catch {
        /* que falle el refresco no puede interrumpir la tanda */
      }
    }, REFRESCO_MS);
    return () => window.clearInterval(id);
  }, [evento, idEvento]);

  const incorporar = useCallback(() => {
    setFotos((previas) => [...previas, ...enEspera]);
    setEnEspera([]);
  }, [enEspera]);

  // Al terminar la tanda se incorporan solas: ahí ya no hay posición que mover.
  useEffect(() => {
    if (fotos.length === 0 && enEspera.length > 0) incorporar();
  }, [fotos.length, enEspera.length, incorporar]);

  // ── Moderación optimista ────────────────────────────────────
  // OJO: nada de efectos secundarios adentro de un updater de estado. React
  // puede invocar el updater más de una vez —en StrictMode lo hace siempre— y
  // el historial terminaba con dos entradas por foto. Se notaba recién al
  // deshacer: Z seguía "deshaciendo" después de agotar el historial e insertaba
  // fotos duplicadas. Por eso todo el trabajo se hace acá afuera.
  const moderar = useCallback(
    (estado: EstadoFoto) => {
      const foto = fotos[indice];
      if (!foto) return;

      historial.current.push({ foto, indice, estado });
      const restantes = fotos.filter((_, i) => i !== indice);
      setFotos(restantes);
      setIndice(Math.min(indice, Math.max(0, restantes.length - 1)));
      setSeleccion(new Set());

      // El pedido viaja en segundo plano. Esperar la respuesta entre foto y
      // foto convierte dos minutos en diez.
      admin.moderar(foto.id, estado).catch(() => {
        setFotos((actuales) =>
          actuales.some((f) => f.id === foto.id)
            ? actuales
            : [...actuales.slice(0, indice), foto, ...actuales.slice(indice)],
        );
        setAviso("Una foto no se pudo guardar y volvió a la lista");
      });
    },
    [fotos, indice],
  );

  const deshacer = useCallback(() => {
    const ultima = historial.current.pop();
    if (!ultima) return;
    setFotos((previas) => {
      // Nunca insertar dos veces la misma foto, pase lo que pase.
      if (previas.some((f) => f.id === ultima.foto.id)) return previas;
      const copia = [...previas];
      copia.splice(Math.min(ultima.indice, copia.length), 0, ultima.foto);
      return copia;
    });
    setIndice(ultima.indice);
    admin.moderar(ultima.foto.id, "pendiente").catch(() => {
      setAviso("No pudimos deshacer. Probá de nuevo");
    });
  }, []);

  const alActuar = useCallback(
    (accion: Accion) => {
      switch (accion) {
        case "anterior":
          setIndice((i) => Math.max(0, i - 1));
          break;
        case "siguiente":
          setIndice((i) => Math.min(fotos.length - 1, i + 1));
          break;
        case "aprobar":
          if (seleccion.size > 0) moderarLote("aprobada");
          else moderar("aprobada");
          break;
        case "rechazar":
          if (seleccion.size > 0) moderarLote("rechazada");
          else moderar("rechazada");
          break;
        case "deshacer":
          deshacer();
          break;
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fotos.length, moderar, deshacer, seleccion],
  );

  useAtajos(alActuar, !cargando && !error);

  function moderarLote(estado: EstadoFoto) {
    const ids = [...seleccion];
    if (ids.length === 0) return;
    const guardadas = fotos.filter((f) => seleccion.has(f.id));
    guardadas.forEach((foto) =>
      historial.current.push({ foto, indice: fotos.indexOf(foto), estado }),
    );

    setFotos((previas) => previas.filter((f) => !seleccion.has(f.id)));
    setSeleccion(new Set());
    setIndice(0);

    // Un solo pedido: en una fiesta llegan ráfagas de veinte fotos casi todas
    // buenas.
    admin.moderarLote(ids, estado).catch(() => {
      setFotos((previas) => [...guardadas, ...previas]);
      setAviso("El lote no se pudo guardar y las fotos volvieron");
    });
  }

  function alClickMiniatura(i: number, conShift: boolean) {
    if (conShift && anclaSeleccion.current !== null) {
      const desde = Math.min(anclaSeleccion.current, i);
      const hasta = Math.max(anclaSeleccion.current, i);
      const nueva = new Set(seleccion);
      for (let k = desde; k <= hasta; k++) {
        const f = fotos[k];
        if (f) nueva.add(f.id);
      }
      setSeleccion(nueva);
      return;
    }
    anclaSeleccion.current = i;
    setIndice(i);
    if (seleccion.size > 0) setSeleccion(new Set());
  }

  if (error) return <MensajeError error={error} />;
  if (cargando || !evento) return <Cargando texto="Cargando la bandeja…" />;

  const actual = fotos[indice] ?? null;
  const color = colorDelEvento(evento.codigo_publico);

  return (
    <div className="flex h-full flex-col">
      {/* Barra de contexto fija: con dos pestañas abiertas, esto es lo que
          evita aprobar las fotos del evento equivocado. */}
      <header
        className="flex shrink-0 items-center justify-between gap-4 border-b-4 px-6 py-3"
        style={{ borderColor: color, background: "#16161d" }}
      >
        <div className="flex items-center gap-3">
          <span className="h-4 w-4 rounded-full" style={{ background: color }} />
          <h1 className="text-lg font-semibold">{evento.nombre}</h1>
          <span className="text-sm text-tenue">{evento.fecha_evento}</span>
        </div>
        <div className="flex items-center gap-6">
          <p className="text-right">
            <strong className="text-4xl tabular-nums" style={{ color }}>{fotos.length}</strong>
            <span className="ml-2 text-tenue">pendientes</span>
          </p>
          <Link to="/admin" className="text-sm text-tenue underline underline-offset-4 hover:text-white">
            Eventos
          </Link>
        </div>
      </header>

      {enEspera.length > 0 && (
        <button
          onClick={incorporar}
          className="shrink-0 bg-acento/20 py-2 text-center text-sm text-acento hover:bg-acento/30"
        >
          {enEspera.length === 1 ? "1 nueva" : `${enEspera.length} nuevas`} · tocá para incorporarlas
        </button>
      )}

      {aviso && (
        <button
          onClick={() => setAviso(null)}
          className="shrink-0 bg-red-900/40 py-2 text-center text-sm text-red-200"
        >
          {aviso} · tocá para cerrar
        </button>
      )}

      {/* Foto grande: se decide mirando la foto en grande, no la miniatura. */}
      <div className="relative min-h-0 flex-1 bg-fondo">
        {actual ? (
          <>
            <img src={actual.url} alt="" className="h-full w-full object-contain" />
            {actual.nombre_invitado && (
              <p className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-black/60 px-4 py-1 text-lg">
                {actual.nombre_invitado}
              </p>
            )}
          </>
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
            <p className="text-2xl font-semibold">No queda nada pendiente</p>
            <p className="text-tenue">Buen trabajo.</p>
          </div>
        )}
      </div>

      {/* Fila de miniaturas */}
      <div className="flex shrink-0 gap-2 overflow-x-auto border-t border-borde bg-panel p-3">
        {fotos.map((f, i) => (
          <button
            key={f.id}
            onClick={(e) => alClickMiniatura(i, e.shiftKey)}
            className={`h-16 w-16 shrink-0 overflow-hidden rounded-lg border-2 transition ${
              seleccion.has(f.id)
                ? "border-acento ring-2 ring-acento"
                : i === indice
                  ? "border-white"
                  : "border-transparent opacity-60 hover:opacity-100"
            }`}
          >
            <img src={f.url} alt="" className="h-full w-full object-cover" />
          </button>
        ))}
      </div>

      <footer className="shrink-0 border-t border-borde bg-panel px-6 py-2 text-center text-sm text-tenue">
        <kbd className="text-white">←</kbd> <kbd className="text-white">→</kbd> navegar ·{" "}
        <kbd className="text-white">A</kbd> aprobar · <kbd className="text-white">R</kbd> rechazar ·{" "}
        <kbd className="text-white">Z</kbd> deshacer · Shift+click para seleccionar varias
        {seleccion.size > 0 && (
          <span className="ml-3 text-acento">
            {seleccion.size} seleccionadas · A o R las modera todas juntas
          </span>
        )}
      </footer>
    </div>
  );
}
