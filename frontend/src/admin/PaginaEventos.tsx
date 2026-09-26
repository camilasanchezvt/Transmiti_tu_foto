import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ErrorApi, admin, haySesion } from "../api/client";
import type { EventoAdmin } from "../api/tipos";
import Boton from "../comp/Boton";
import Cargando from "../comp/Cargando";
import MensajeError from "../comp/MensajeError";
import { dibujarQR } from "../lib/qr";
import { colorDelEvento } from "./color";

export default function PaginaEventos() {
  const navegar = useNavigate();
  const [eventos, setEventos] = useState<EventoAdmin[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [creando, setCreando] = useState(false);
  const [nombre, setNombre] = useState("");
  const [fecha, setFecha] = useState("");
  const [reciencreado, setRecienCreado] = useState<EventoAdmin | null>(null);

  const cargar = useCallback(async () => {
    try {
      setEventos(await admin.eventos());
    } catch (e) {
      if (e instanceof ErrorApi && e.codigo === "NO_AUTORIZADO") {
        navegar("/admin/login");
        return;
      }
      setError(e);
    }
  }, [navegar]);

  useEffect(() => {
    if (!haySesion()) {
      navegar("/admin/login");
      return;
    }
    document.title = "Eventos · Transmití tu foto";
    cargar();
  }, [cargar, navegar]);

  async function crear(evento: FormEvent) {
    evento.preventDefault();
    setCreando(true);
    setError(null);
    try {
      const nuevo = await admin.crearEvento({ nombre, fecha_evento: fecha });
      setNombre("");
      setFecha("");
      setRecienCreado(nuevo);
      await cargar();
    } catch (e) {
      setError(e);
    } finally {
      setCreando(false);
    }
  }

  if (error && !eventos) return <MensajeError error={error} onReintentar={cargar} />;
  if (!eventos) return <Cargando texto="Cargando eventos…" />;

  return (
    <main className="mx-auto max-w-3xl p-6">
      <header className="mb-8 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Eventos</h1>
        <button
          onClick={() => {
            admin.salir();
            navegar("/admin/login");
          }}
          className="text-sm text-tenue underline underline-offset-4 hover:text-white"
        >
          Salir
        </button>
      </header>

      <form onSubmit={crear} className="mb-10 flex flex-wrap items-end gap-3 rounded-2xl border border-borde bg-panel p-4">
        <label className="flex-1 text-sm text-tenue">
          Nombre
          <input
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            required
            maxLength={120}
            placeholder="Casamiento Ana y Juan"
            className="mt-1 h-12 w-full rounded-xl border border-borde bg-fondo px-3 text-base text-white outline-none focus:border-acento"
          />
        </label>
        <label className="text-sm text-tenue">
          Fecha
          <input
            type="date"
            value={fecha}
            onChange={(e) => setFecha(e.target.value)}
            required
            className="mt-1 h-12 rounded-xl border border-borde bg-fondo px-3 text-base text-white outline-none focus:border-acento"
          />
        </label>
        <div className="w-40">
          <Boton type="submit" cargando={creando}>Crear</Boton>
        </div>
      </form>

      {error ? <div className="mb-6"><MensajeError error={error} /></div> : null}

      {reciencreado && (
        <RecienCreado evento={reciencreado} onCerrar={() => setRecienCreado(null)} />
      )}

      {eventos.length === 0 ? (
        <p className="text-tenue">Todavía no creaste ningún evento.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {eventos.map((e) => (
            <li
              key={e.id}
              className="rounded-2xl border border-borde bg-panel p-4"
              style={{ borderLeft: `6px solid ${colorDelEvento(e.codigo_publico)}` }}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold">{e.nombre}</h2>
                  <p className="text-sm text-tenue">
                    {e.fecha_evento} · {e.estado}
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  <p className="text-sm">
                    <strong className="text-xl text-acento">{e.pendientes}</strong>
                    <span className="text-tenue">{e.pendientes === 1 ? " pendiente" : " pendientes"}</span>
                  </p>
                  <Link
                    to={`/admin/eventos/${e.id}/moderar`}
                    className="rounded-xl border border-borde px-4 py-2 text-sm hover:border-acento"
                  >
                    Moderar
                  </Link>
                  <Link
                    to={`/admin/eventos/${e.id}/cierre`}
                    className="rounded-xl border border-borde px-4 py-2 text-sm hover:border-acento"
                  >
                    Cierre
                  </Link>
                </div>
              </div>
              <ClavesDelEvento evento={e} />
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

/** Lo que se necesita de verdad al crear un evento: el QR para imprimir y el
 *  link de la pantalla para abrir en la notebook del proyector. */
function RecienCreado({ evento, onCerrar }: { evento: EventoAdmin; onCerrar: () => void }) {
  return (
    <div className="mb-10 rounded-2xl border border-acento bg-panel p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xl font-semibold">Listo: {evento.nombre}</h2>
        <button onClick={onCerrar} className="text-sm text-tenue hover:text-white">Cerrar</button>
      </div>
      <ClavesDelEvento evento={evento} destacado />
    </div>
  );
}

function ClavesDelEvento({ evento, destacado = false }: { evento: EventoAdmin; destacado?: boolean }) {
  const urlInvitado = `${window.location.origin}/e/${evento.codigo_publico}`;
  const urlPantalla = `${window.location.origin}/p/${evento.token_pantalla}`;

  return (
    <div className={`mt-4 flex flex-wrap items-center gap-6 ${destacado ? "" : "text-sm"}`}>
      {destacado && <QrDescargable url={urlInvitado} nombre={evento.nombre} />}
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <Copiable etiqueta="Link para los invitados (el del QR)" valor={urlInvitado} />
        <Copiable etiqueta="Link de la pantalla" valor={urlPantalla} />
        <VincularPantalla evento={evento} />
      </div>
      {!destacado && <QrDescargable url={urlInvitado} nombre={evento.nombre} chico />}
    </div>
  );
}

function QrDescargable({ url, nombre, chico = false }: { url: string; nombre: string; chico?: boolean }) {
  const lienzo = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!lienzo.current) return;
    // Se dibuja grande siempre y se muestra chico por CSS: el PNG que se baja
    // tiene que servir para imprimir, no para la pantalla.
    dibujarQR(lienzo.current, url, 1024).catch(() => {});
  }, [url]);

  function bajar() {
    const png = lienzo.current?.toDataURL("image/png");
    if (!png) return;
    const a = document.createElement("a");
    a.href = png;
    a.download = `QR ${nombre}.png`;
    a.click();
  }

  return (
    <div className="flex flex-col items-center gap-2">
      <canvas ref={lienzo} className={`rounded-xl bg-white ${chico ? "h-24 w-24" : "h-[220px] w-[220px]"}`} />
      <button onClick={bajar} className="text-xs text-tenue underline underline-offset-4 hover:text-white">
        Bajar PNG
      </button>
    </div>
  );
}

/**
 * El código de seis dígitos para vincular una tele.
 *
 * El link de la pantalla mide 68 caracteres. Con una notebook se copia y pega;
 * con el control remoto de una tele es imposible. Esto lo reemplaza por seis
 * dígitos, que es lo único que un control hace bien.
 */
function VincularPantalla({ evento }: { evento: EventoAdmin }) {
  const [codigo, setCodigo] = useState<string | null>(null);
  const [restante, setRestante] = useState(0);
  const [pidiendo, setPidiendo] = useState(false);
  const [falla, setFalla] = useState<string | null>(null);

  useEffect(() => {
    if (restante <= 0) return;
    const id = window.setTimeout(() => setRestante((s) => s - 1), 1000);
    return () => window.clearTimeout(id);
  }, [restante]);

  useEffect(() => {
    if (restante === 0) setCodigo(null);
  }, [restante]);

  async function pedirCodigo() {
    setPidiendo(true);
    setFalla(null);
    try {
      const respuesta = await admin.vincularPantalla(evento.id);
      setCodigo(respuesta.codigo);
      setRestante(Math.max(0, Math.round((Date.parse(respuesta.expira_en) - Date.now()) / 1000)));
    } catch (e) {
      setFalla(e instanceof ErrorApi ? e.message : "No pudimos generar el código");
    } finally {
      setPidiendo(false);
    }
  }

  const minutos = Math.floor(restante / 60);
  const segundos = String(restante % 60).padStart(2, "0");

  return (
    <div className="min-w-0">
      <p className="text-xs text-tenue">Vincular una tele o un proyector con navegador</p>
      {codigo ? (
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <code className="rounded-lg bg-fondo px-3 py-1 font-mono text-2xl tracking-widest text-acento">
            {codigo.slice(0, 3)} {codigo.slice(3)}
          </code>
          <span className="text-xs text-tenue">
            Abrí <strong className="text-white">{window.location.origin}/p</strong> en la tele y
            cargá estos dígitos · vence en {minutos}:{segundos}
          </span>
        </div>
      ) : (
        <div className="mt-1 flex items-center gap-2">
          <button
            onClick={pedirCodigo}
            disabled={pidiendo}
            className="rounded-lg border border-borde px-3 py-1 text-xs hover:border-acento disabled:opacity-50"
          >
            {pidiendo ? "Generando…" : "Generar código de 6 dígitos"}
          </button>
          {falla && <span className="text-xs text-red-300">{falla}</span>}
        </div>
      )}
    </div>
  );
}

function Copiable({ etiqueta, valor }: { etiqueta: string; valor: string }) {
  const [copiado, setCopiado] = useState(false);

  async function copiar() {
    try {
      await navigator.clipboard.writeText(valor);
    } catch {
      // Sin permiso de portapapeles: se selecciona para que el usuario copie.
      window.prompt(etiqueta, valor);
      return;
    }
    setCopiado(true);
    window.setTimeout(() => setCopiado(false), 1500);
  }

  return (
    <div className="min-w-0">
      <p className="text-xs text-tenue">{etiqueta}</p>
      <div className="flex items-center gap-2">
        <code className="min-w-0 flex-1 truncate rounded-lg bg-fondo px-2 py-1 text-xs">{valor}</code>
        <button
          onClick={copiar}
          className="shrink-0 rounded-lg border border-borde px-3 py-1 text-xs hover:border-acento"
        >
          {copiado ? "Copiado" : "Copiar"}
        </button>
      </div>
    </div>
  );
}
