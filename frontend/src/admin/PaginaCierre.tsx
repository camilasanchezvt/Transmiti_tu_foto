import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ErrorApi, admin, haySesion } from "../api/client";
import type { EventoAdmin } from "../api/tipos";
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
