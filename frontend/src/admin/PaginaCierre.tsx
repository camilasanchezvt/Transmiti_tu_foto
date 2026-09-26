import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ErrorApi, admin, haySesion } from "../api/client";
import type { EventoAdmin, VideoEvento } from "../api/tipos";
import Boton from "../comp/Boton";
import Cargando from "../comp/Cargando";
import MensajeError from "../comp/MensajeError";
import { colorDelEvento } from "./color";

export default function PaginaCierre() {
  const { id = "" } = useParams();
  const idEvento = Number(id);
  const navegar = useNavigate();

  const [evento, setEvento] = useState<EventoAdmin | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [cambiando, setCambiando] = useState(false);
  const [bajando, setBajando] = useState<"aprobadas" | "todas" | null>(null);

  const cargar = useCallback(async () => {
    try {
      const eventos = await admin.eventos();
      const mio = eventos.find((e) => e.id === idEvento);
      if (!mio) throw new ErrorApi("EVENTO_NO_ENCONTRADO", "No encontramos este evento", 404);
      setEvento(mio);
      document.title = `${mio.nombre} · Cierre`;
    } catch (e) {
      if (e instanceof ErrorApi && e.codigo === "NO_AUTORIZADO") {
        navegar("/admin/login");
        return;
      }
      setError(e);
    }
  }, [idEvento, navegar]);

  useEffect(() => {
    if (!haySesion()) {
      navegar("/admin/login");
      return;
    }
    cargar();
  }, [cargar, navegar]);

  async function cambiarEstado(estado: "activo" | "cerrado" | "borrador") {
    setCambiando(true);
    setError(null);
    try {
      setEvento(await admin.cambiarEstadoEvento(idEvento, estado));
    } catch (e) {
      setError(e);
    } finally {
      setCambiando(false);
    }
  }

  async function descargar(incluir: "aprobadas" | "todas") {
    setBajando(incluir);
    setError(null);
    try {
      const blob = await admin.descargar(idEvento, incluir);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      // El servidor ya manda el nombre en Content-Disposition, pero fetch no lo
      // aplica solo: se repite acá con el evento y la fecha, nunca un id.
      a.download = `${evento?.nombre ?? "evento"} - ${evento?.fecha_evento ?? ""}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e);
    } finally {
      setBajando(null);
    }
  }

  if (error && !evento) return <MensajeError error={error} onReintentar={cargar} />;
  if (!evento) return <Cargando texto="Cargando el evento…" />;

  const color = colorDelEvento(evento.codigo_publico);
  const total = evento.pendientes + evento.aprobadas + evento.rechazadas;

  return (
    <main className="mx-auto max-w-2xl p-6">
      <header
        className="mb-8 flex items-center justify-between gap-4 rounded-2xl border-l-8 bg-panel px-5 py-4"
        style={{ borderColor: color }}
      >
        <div>
          <h1 className="text-xl font-semibold">{evento.nombre}</h1>
          <p className="text-sm text-tenue">{evento.fecha_evento} · {evento.estado}</p>
        </div>
        <Link to="/admin" className="text-sm text-tenue underline underline-offset-4 hover:text-white">
          Eventos
        </Link>
      </header>

      <section className="mb-8 grid grid-cols-3 gap-3 text-center">
        {([["Pendientes", evento.pendientes], ["Aprobadas", evento.aprobadas], ["Rechazadas", evento.rechazadas]] as const).map(
          ([etiqueta, valor]) => (
            <div key={etiqueta} className="rounded-2xl border border-borde bg-panel p-4">
              <p className="text-3xl font-semibold tabular-nums">{valor}</p>
              <p className="text-sm text-tenue">{etiqueta}</p>
            </div>
          ),
        )}
      </section>

      <section className="mb-8 rounded-2xl border border-borde bg-panel p-5">
        <h2 className="mb-2 text-lg font-semibold">Estado del evento</h2>
        <p className="mb-4 text-sm text-tenue">
          Cerrar deja de aceptar fotos nuevas y muestra el mensaje de cierre en la
          pantalla, pero las aprobadas siguen pasando.
        </p>
        <div className="flex gap-3">
          {evento.estado !== "activo" && (
            <Boton variante="secundario" cargando={cambiando} onClick={() => cambiarEstado("activo")}>
              {evento.estado === "borrador" ? "Publicar" : "Reabrir"}
            </Boton>
          )}
          {evento.estado !== "cerrado" && (
            <Boton variante="peligro" cargando={cambiando} onClick={() => cambiarEstado("cerrado")}>
              Cerrar el evento
            </Boton>
          )}
        </div>
      </section>

      <Configuracion evento={evento} onGuardado={setEvento} />

      <VideoDelEvento idEvento={evento.id} aprobadas={evento.aprobadas} />

      <section className="rounded-2xl border border-borde bg-panel p-5">
        <h2 className="mb-2 text-lg font-semibold">Descargar las fotos</h2>
        <p className="mb-4 text-sm text-tenue">
          {total === 1 ? "1 foto" : `${total} fotos`} en total. Doscientas fotos no salen en dos segundos: el
          archivo se arma mientras se descarga.
        </p>
        <div className="flex flex-wrap gap-3">
          <Boton cargando={bajando === "aprobadas"} onClick={() => descargar("aprobadas")}>
            Sólo las aprobadas ({evento.aprobadas})
          </Boton>
          <Boton variante="secundario" cargando={bajando === "todas"} onClick={() => descargar("todas")}>
            Todas ({total})
          </Boton>
        </div>
        {bajando && (
          <p className="mt-4 text-sm text-acento">
            Armando el archivo… no cierres esta pestaña.
          </p>
        )}
      </section>

      {error ? <div className="mt-6"><MensajeError error={error} /></div> : null}
    </main>
  );
}

/** Los topes son los mismos que valida el backend (CambioEstadoEvento). */
const SEGUNDOS = { min: 3, max: 30 };
const CUPO = { min: 1, max: 50 };

function Configuracion({ evento, onGuardado }: { evento: EventoAdmin; onGuardado: (e: EventoAdmin) => void }) {
  const [segundos, setSegundos] = useState(String(evento.segundos_por_foto));
  const [cupo, setCupo] = useState(String(evento.max_fotos_por_dispositivo));
  const [guardando, setGuardando] = useState(false);
  const [guardado, setGuardado] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const s = Number(segundos);
  const c = Number(cupo);
  const valido =
    Number.isInteger(s) && s >= SEGUNDOS.min && s <= SEGUNDOS.max &&
    Number.isInteger(c) && c >= CUPO.min && c <= CUPO.max;
  const cambio = s !== evento.segundos_por_foto || c !== evento.max_fotos_por_dispositivo;

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    if (!valido || !cambio) return;
    setGuardando(true);
    setError(null);
    try {
      onGuardado(
        await admin.configurarEvento(evento.id, { segundos_por_foto: s, max_fotos_por_dispositivo: c }),
      );
      setGuardado(true);
      window.setTimeout(() => setGuardado(false), 2000);
    } catch (err) {
      setError(err);
    } finally {
      setGuardando(false);
    }
  }

  const campo =
    "mt-1 h-12 w-28 rounded-xl border border-borde bg-fondo px-3 text-base text-white outline-none focus:border-acento";

  return (
    <form onSubmit={guardar} className="mb-8 rounded-2xl border border-borde bg-panel p-5">
      <h2 className="mb-2 text-lg font-semibold">Configuración</h2>
      <p className="mb-4 text-sm text-tenue">
        La pantalla toma los segundos nuevos sola, en unos segundos, sin recargarla.
      </p>
      <div className="flex flex-wrap items-end gap-4">
        <label className="text-sm text-tenue">
          Segundos por foto
          <input
            type="number" inputMode="numeric" min={SEGUNDOS.min} max={SEGUNDOS.max}
            value={segundos} onChange={(e) => setSegundos(e.target.value)} className={`block ${campo}`}
          />
        </label>
        <label className="text-sm text-tenue">
          Fotos por invitado
          <input
            type="number" inputMode="numeric" min={CUPO.min} max={CUPO.max}
            value={cupo} onChange={(e) => setCupo(e.target.value)} className={`block ${campo}`}
          />
        </label>
        <div className="w-36">
          <Boton type="submit" variante="secundario" cargando={guardando} disabled={!valido || !cambio}>
            {guardado ? "Guardado" : "Guardar"}
          </Boton>
        </div>
      </div>
      {!valido && (
        <p className="mt-3 text-sm text-acento">
          Entre {SEGUNDOS.min} y {SEGUNDOS.max} segundos, y entre {CUPO.min} y {CUPO.max} fotos por invitado.
        </p>
      )}
      {error ? <div className="mt-4"><MensajeError error={error} /></div> : null}
    </form>
  );
}

/** Cada cuánto se pregunta si Cloudinary ya terminó el video. */
const CONSULTA_VIDEO_MS = 10_000;

/** `fl_attachment` hace que Cloudinary lo mande como descarga y no lo reproduzca. */
function urlDeDescarga(url: string): string {
  return url.replace("/video/upload/", "/video/upload/fl_attachment/");
}

function VideoDelEvento({ idEvento, aprobadas }: { idEvento: number; aprobadas: number }) {
  const [video, setVideo] = useState<VideoEvento | null>(null);
  const [pidiendo, setPidiendo] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let vivo = true;
    admin.video(idEvento).then((v) => vivo && setVideo(v)).catch((e) => vivo && setError(e));
    return () => {
      vivo = false;
    };
  }, [idEvento]);

  // Mientras Cloudinary lo arma, se pregunta cada tanto. Cada consulta hace que
  // el backend le pregunte a Cloudinary; no hay aviso del otro lado.
  useEffect(() => {
    if (video?.estado !== "procesando") return;
    const id = window.setInterval(() => {
      admin.video(idEvento).then(setVideo).catch(() => {});
    }, CONSULTA_VIDEO_MS);
    return () => window.clearInterval(id);
  }, [idEvento, video?.estado]);

  async function armar() {
    setPidiendo(true);
    setError(null);
    try {
      setVideo(await admin.armarVideo(idEvento));
    } catch (e) {
      setError(e);
    } finally {
      setPidiendo(false);
    }
  }

  const estado = video?.estado ?? "ninguno";
  const segundos = aprobadas * 3;

  return (
    <section className="mb-8 rounded-2xl border border-borde bg-panel p-5">
      <h2 className="mb-2 text-lg font-semibold">Video del evento</h2>
      <p className="mb-4 text-sm text-tenue">
        Un video con las fotos aprobadas, en el orden en que llegaron, 3 segundos cada una.
        {aprobadas > 150 && " Si pasan de 150, se eligen repartidas a lo largo de la noche."}
      </p>

      {estado === "procesando" && (
        <p className="mb-4 text-sm text-acento">
          Armando el video con {video?.fotos} fotos… puede tardar unos minutos. Podés salir de esta
          página: cuando vuelvas va a estar acá.
        </p>
      )}
      {estado === "fallo" && (
        <p className="mb-4 text-sm text-acento">No se pudo armar el video. Probá de nuevo.</p>
      )}
      {estado === "listo" && video?.url && (
        <div className="mb-4">
          <video src={video.url} controls className="mb-3 w-full rounded-xl bg-black" />
          <a
            href={urlDeDescarga(video.url)}
            className="inline-block rounded-xl border border-borde px-4 py-2 text-sm hover:border-acento"
          >
            Descargar video ({video.fotos} fotos)
          </a>
        </div>
      )}

      {estado !== "procesando" && (
        <div className="w-56">
          <Boton
            variante={estado === "listo" ? "secundario" : "principal"}
            cargando={pidiendo}
            disabled={aprobadas === 0}
            onClick={armar}
          >
            {estado === "listo" ? "Volver a armarlo" : `Armar video (${Math.min(segundos, 450)} s)`}
          </Boton>
        </div>
      )}
      {aprobadas === 0 && <p className="mt-3 text-sm text-tenue">Aprobá fotos para poder armarlo.</p>}
      {error ? <div className="mt-4"><MensajeError error={error} /></div> : null}
    </section>
  );
}
