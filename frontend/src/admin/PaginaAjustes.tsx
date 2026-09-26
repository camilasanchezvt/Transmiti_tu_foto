import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorApi, admin, haySesion } from "../api/client";
import type { EstadoEvento, EventoAdmin, VideoEvento } from "../api/tipos";
import Boton, { claseBoton } from "../comp/Boton";
import BotonChico from "../comp/BotonChico";
import Cargando from "../comp/Cargando";
import ChipEstado from "../comp/ChipEstado";
import Confirmar from "../comp/Confirmar";
import MensajeError from "../comp/MensajeError";
import { fechaLarga } from "../lib/fecha";
import LayoutAdmin from "./LayoutAdmin";
import { esDelHistorial, rutaACompartir, useVolverALista } from "./navegacion";
import { ajustes as t } from "./textos/ajustes";
import { comun } from "./textos/comun";
import { useAlPerderSesion, useSesion } from "./useSesion";

// Ajustes de un evento (antes "Cierre"), ordenado por el momento en que se usa
// cada cosa: antes (publicar, configurar la pantalla), durante (revisar
// fotos), después (video, descargas) y, al final y aparte, Terminar. Quien la
// abre busca UNA cosa y tiene que encontrarla sin leer el resto.

const TARJETA = "rounded-3xl border border-borde bg-panel p-5";

/** Los botones grandes ocupan todo el ancho en el celular (se tocan con el
 *  pulgar); en la compu, el de su texto: una cápsula de 680 px no es un botón. */
const ANCHO_BOTON = "sm:w-auto sm:min-w-56 sm:px-8";

/** Para los botones cuyo texto puede no entrar en una línea a 375 px
 *  ("Descargar las aprobadas (123)"): que partan prolijo y no se desborden. */
const DOS_LINEAS = "py-2 leading-tight";

/** Cada cuánto se refrescan los números de fotos mientras el evento recibe. */
const CONSULTA_RESUMEN_MS = 30_000;

/** Cada cuánto se pregunta si Cloudinary ya terminó el video. */
const CONSULTA_VIDEO_MS = 10_000;

/** Los mismos topes que el backend (cloudinary_service.py): hasta 150 fotos,
 *  3 segundos cada una. */
const MAX_FOTOS_VIDEO = 150;
const SEGUNDOS_POR_FOTO_VIDEO = 3;

/** Los topes que valida el backend (CambioEstadoEvento). */
const SEGUNDOS = { min: 3, max: 30 };
const CUPO = { min: 1, max: 50 };

type Incluir = "aprobadas" | "todas";

/** Ante un 401 (sesión vencida o cuenta dada de baja) se sale y se va al login.
 *  Devuelve true si era eso, para que quien llama no muestre el error. Un 403
 *  NO manda al login: hay sesión, falta permiso. */
type AlPerderSesion = (error: unknown) => boolean;

function conMayuscula(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

function mensajeDe(error: unknown): string {
  return error instanceof ErrorApi ? error.message : comun.errores.generico;
}

export default function PaginaAjustes() {
  const { id = "" } = useParams();
  const idEvento = Number(id);
  const { esAdmin } = useSesion();
  const alPerderSesion = useAlPerderSesion();

  const [evento, setEvento] = useState<EventoAdmin | null>(null);
  const [noExiste, setNoExiste] = useState(false);
  const [errorCarga, setErrorCarga] = useState<unknown>(null);
  const [intento, setIntento] = useState(0);

  const [cambiando, setCambiando] = useState<EstadoEvento | null>(null);
  const [errorEstado, setErrorEstado] = useState<unknown>(null);
  const [confirmando, setConfirmando] = useState(false);

  // No hay un GET de un evento solo: se pide la lista (sin alcance, así vienen
  // todos) y se busca por id. Si no está, no existe o no es de esta cuenta: el
  // backend no distingue, y acá tampoco.
  useEffect(() => {
    // Sin token, LayoutAdmin (useSesion) ya manda al login.
    if (!haySesion()) return;
    let vivo = true;
    setErrorCarga(null);
    admin.eventos().then(
      (lista) => {
        if (!vivo) return;
        const este = lista.find((e) => e.id === idEvento) ?? null;
        setEvento(este);
        setNoExiste(este === null);
      },
      (e: unknown) => {
        if (vivo && !alPerderSesion(e)) setErrorCarga(e);
      },
    );
    return () => {
      vivo = false;
    };
  }, [idEvento, intento, alPerderSesion]);

  const nombre = evento?.nombre;
  useEffect(() => {
    if (nombre) document.title = comun.tituloPestana(t.pestana(nombre));
  }, [nombre]);

  // Mientras el evento recibe fotos, los números se refrescan solos: esta
  // página puede quedar abierta toda la fiesta y "Revisar fotos (3)" no puede
  // quedarse en 3. Con la pestaña oculta no se pregunta; al volver, sí.
  const recibe = evento?.estado === "activo";
  useEffect(() => {
    if (!recibe) return;
    let vivo = true;
    const refrescar = () => {
      if (document.visibilityState !== "visible") return;
      admin.resumen(idEvento).then(
        (r) => {
          if (!vivo) return;
          setEvento((ev) =>
            ev ? { ...ev, pendientes: r.pendientes, aprobadas: r.aprobadas, rechazadas: r.rechazadas } : ev,
          );
        },
        (e: unknown) => {
          // Un aviso que no llegó no interrumpe nada; sólo una sesión vencida.
          if (vivo) alPerderSesion(e);
        },
      );
    };
    const reloj = window.setInterval(refrescar, CONSULTA_RESUMEN_MS);
    document.addEventListener("visibilitychange", refrescar);
    return () => {
      vivo = false;
      window.clearInterval(reloj);
      document.removeEventListener("visibilitychange", refrescar);
    };
  }, [recibe, idEvento, alPerderSesion]);

  async function cambiarEstado(estado: EstadoEvento): Promise<boolean> {
    setCambiando(estado);
    setErrorEstado(null);
    try {
      setEvento(await admin.cambiarEstadoEvento(idEvento, estado));
      return true;
    } catch (e) {
      if (!alPerderSesion(e)) setErrorEstado(e);
      return false;
    } finally {
      setCambiando(null);
    }
  }

  async function terminar() {
    // El diálogo se cierra sólo si salió bien; si no, queda abierto con el
    // error adentro, que es donde se está mirando.
    if (await cambiarEstado("cerrado")) setConfirmando(false);
  }

  // A qué lista vuelve: a la que dejó dicho de dónde se vino (el historial con
  // su filtro) o, si no, a la lista donde vive el evento (misma regla que el
  // backend para el historial).
  const lista = useVolverALista(evento);

  if (!evento) {
    return (
      <LayoutAdmin volver={lista}>
        {noExiste ? (
          <div className={`${TARJETA} text-center`}>
            <p className="text-xl font-semibold">{t.noEncontrado}</p>
            <p className="mt-2 text-sm text-tenue">{t.noEncontradoDetalle}</p>
          </div>
        ) : errorCarga ? (
          <MensajeError error={errorCarga} onReintentar={() => setIntento((n) => n + 1)} />
        ) : (
          <Cargando texto={t.cargando} />
        )}
      </LayoutAdmin>
    );
  }

  const ocupado = cambiando !== null;

  return (
    <LayoutAdmin volver={lista} titulo={evento.nombre}>
      {/* Pegado al título: qué estado tiene, cuándo es y de quién (esto
          último sólo le sirve a un admin, que ve los eventos de todos). */}
      <p className="-mt-3 mb-8 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-tenue">
        <ChipEstado estado={evento.estado} />
        <span>{conMayuscula(fechaLarga(evento.fecha_evento))}</span>
        {/* En su propia línea: con un separador, en el celular el "·" quedaba
            colgando al final de la primera. */}
        {esAdmin && <span className="min-w-0 basis-full break-words">{comun.organiza(evento.organizador_nombre)}</span>}
      </p>

      <div className="flex flex-col gap-10">
        {/* ── Antes ─────────────────────────────────────────── */}
        <Seccion titulo={t.antes}>
          {evento.estado === "borrador" && (
            // Lo primero que ve quien acaba de crear el evento: sin publicar,
            // el QR que ya imprimió no sirve.
            <div className="rounded-3xl border border-acento/60 bg-panel p-5">
              <h3 className="text-lg font-semibold">{t.publicarTitulo}</h3>
              <p className="mt-1 text-sm text-tenue">{t.publicarAviso}</p>
              <Boton
                className={`mt-4 ${ANCHO_BOTON}`}
                cargando={cambiando === "activo"}
                disabled={ocupado}
                onClick={() => cambiarEstado("activo")}
              >
                {comun.verbos.publicar}
              </Boton>
              {errorEstado ? <ErrorEnLinea error={errorEstado} /> : null}
            </div>
          )}

          {evento.estado === "cerrado" && (
            <div className={TARJETA}>
              <h3 className="text-lg font-semibold">{t.terminadoTitulo}</h3>
              <p className="mt-1 text-sm text-tenue">{t.terminadoAviso}</p>
              <Boton
                variante="secundario"
                className={`mt-4 ${ANCHO_BOTON}`}
                cargando={cambiando === "activo"}
                disabled={ocupado}
                onClick={() => cambiarEstado("activo")}
              >
                {t.reabrir}
              </Boton>
              {errorEstado ? <ErrorEnLinea error={errorEstado} /> : null}
            </div>
          )}

          {evento.estado === "activo" && (
            <p className="flex items-center gap-2 px-1 text-sm text-tenue">
              <span aria-hidden className="h-2 w-2 shrink-0 rounded-full bg-verde" />
              {t.publicadoAviso}
            </p>
          )}

          <Configuracion key={evento.id} evento={evento} onGuardado={setEvento} alPerderSesion={alPerderSesion} />

          {/* El QR, el link y la pantalla viven en la tarjeta del evento, en
              Eventos: no se duplican acá. El hash le dice a la lista cuál
              abrir. Un evento del historial no los tiene: terminado o sin
              publicar a tiempo, ya no le sirven. Uno abierto nunca es del
              historial, aunque haya pasado la medianoche. */}
          {!esDelHistorial(evento) && (
            <Link
              to={rutaACompartir(evento, lista)}
              className={
                "flex min-h-16 items-center gap-4 rounded-3xl border border-borde bg-panel px-5 py-4 " +
                "transition hover:bg-white/15 active:scale-[0.99] " +
                "focus:outline-none focus-visible:ring-2 focus-visible:ring-acento"
              }
            >
              <span className="min-w-0 flex-1">
                <span className="block text-base font-semibold">{t.compartirTitulo}</span>
                <span className="mt-0.5 block text-sm text-tenue">{t.compartirDetalle}</span>
              </span>
              <span aria-hidden className="text-3xl leading-none text-tenue">
                ›
              </span>
            </Link>
          )}
        </Seccion>

        {/* ── Durante ───────────────────────────────────────── */}
        <Seccion titulo={t.durante}>
          <ResumenFotos evento={evento} desdeLista={lista.state} />
        </Seccion>

        {/* ── Después ───────────────────────────────────────── */}
        <Seccion titulo={t.despues}>
          <VideoDelEvento idEvento={evento.id} aprobadas={evento.aprobadas} alPerderSesion={alPerderSesion} />
          <Descargas evento={evento} alPerderSesion={alPerderSesion} />
        </Seccion>

        {/* ── Terminar: al final y aparte, para que no se toque de pasada. Un
            evento terminado se reabre desde arriba; uno sin publicar no tiene
            nada que terminar. ─────────────────────────────────────────────── */}
        {evento.estado === "activo" && (
          <Seccion titulo={t.final}>
            <div className={TARJETA}>
              <p className="text-sm text-tenue">{t.terminarDetalle}</p>
              <Boton
                variante="peligro"
                className={`mt-4 ${ANCHO_BOTON}`}
                disabled={ocupado}
                onClick={() => {
                  setErrorEstado(null);
                  setConfirmando(true);
                }}
              >
                {comun.verbos.terminarEvento}
              </Boton>
            </div>
          </Seccion>
        )}
      </div>

      <Confirmar
        abierto={confirmando}
        titulo={t.confirmarTitulo}
        mensaje={
          <>
            {t.confirmarMensaje}
            {errorEstado ? (
              <span role="alert" className="mt-3 block text-rojo">
                {mensajeDe(errorEstado)}
              </span>
            ) : null}
          </>
        }
        textoConfirmar={comun.verbos.terminarEvento}
        peligro
        cargando={cambiando === "cerrado"}
        onConfirmar={terminar}
        onCancelar={() => {
          setConfirmando(false);
          setErrorEstado(null);
        }}
      />
    </LayoutAdmin>
  );
}

// ── Piezas ───────────────────────────────────────────────────

/** Un momento del evento: el encabezado chico de los grupos de Ajustes de iOS
 *  y sus tarjetas debajo. */
function Seccion({ titulo, children }: { titulo: string; children: ReactNode }) {
  const idTitulo = useId();
  return (
    <section aria-labelledby={idTitulo} className="flex flex-col gap-3">
      <h2 id={idTitulo} className="px-1 text-[13px] font-medium uppercase tracking-wide text-tenue">
        {titulo}
      </h2>
      {children}
    </section>
  );
}

/** Un error chico al lado de lo que falló, no una pantalla entera. */
function ErrorEnLinea({ error, reintentar }: { error: unknown; reintentar?: () => void }) {
  return (
    <div role="alert" className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-rojo">
      <p>{mensajeDe(error)}</p>
      {reintentar && <BotonChico onClick={reintentar}>{comun.errores.reintentar}</BotonChico>}
    </div>
  );
}

/** Un <Link> o un <a> con forma de botón grande: ir a otra página o bajar un
 *  archivo es un link, no un botón (se puede abrir en otra pestaña). */
function claseBotonGrande(variante: "principal" | "secundario"): string {
  return `${claseBoton(variante)} ${DOS_LINEAS} ${ANCHO_BOTON}`;
}

function Girando() {
  return (
    <span
      aria-hidden
      className="mt-0.5 inline-block h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-borde border-t-acento"
    />
  );
}

// ── Configuración de la pantalla ─────────────────────────────

function aEntero(texto: string): number {
  return /^\d{1,3}$/.test(texto.trim()) ? Number(texto.trim()) : Number.NaN;
}

function enRango(n: number, rango: { min: number; max: number }): boolean {
  return Number.isInteger(n) && n >= rango.min && n <= rango.max;
}

function Configuracion({
  evento,
  onGuardado,
  alPerderSesion,
}: {
  evento: EventoAdmin;
  onGuardado: (e: EventoAdmin) => void;
  alPerderSesion: AlPerderSesion;
}) {
  const [segundos, setSegundos] = useState(String(evento.segundos_por_foto));
  const [cupo, setCupo] = useState(String(evento.max_fotos_por_dispositivo));
  const [guardando, setGuardando] = useState(false);
  const [guardado, setGuardado] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const reloj = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(reloj.current), []);

  const s = aEntero(segundos);
  const c = aEntero(cupo);
  const valido = enRango(s, SEGUNDOS) && enRango(c, CUPO);
  const cambio = s !== evento.segundos_por_foto || c !== evento.max_fotos_por_dispositivo;

  async function guardar(e: FormEvent) {
    e.preventDefault();
    if (!valido || !cambio || guardando) return;
    setGuardando(true);
    setGuardado(false);
    setError(null);
    try {
      onGuardado(await admin.configurarEvento(evento.id, { segundos_por_foto: s, max_fotos_por_dispositivo: c }));
      setGuardado(true);
      window.clearTimeout(reloj.current);
      reloj.current = window.setTimeout(() => setGuardado(false), 2500);
    } catch (err) {
      if (!alPerderSesion(err)) setError(err);
    } finally {
      setGuardando(false);
    }
  }

  function editar(poner: (v: string) => void) {
    return (v: string) => {
      poner(v);
      setGuardado(false);
    };
  }

  return (
    <form onSubmit={guardar} className={TARJETA}>
      <h3 className="text-lg font-semibold">{t.configTitulo}</h3>
      <div className="mt-1 divide-y divide-borde">
        <Ajuste
          etiqueta={t.segundos}
          ayuda={t.segundosAyuda}
          valor={segundos}
          onCambiar={editar(setSegundos)}
          rango={SEGUNDOS}
          textoMenos={t.segundosMenos}
          textoMas={t.segundosMas}
        />
        <Ajuste
          etiqueta={t.cupo}
          ayuda={t.cupoAyuda}
          valor={cupo}
          onCambiar={editar(setCupo)}
          rango={CUPO}
          textoMenos={t.cupoMenos}
          textoMas={t.cupoMas}
        />
      </div>

      <div className="mt-2 flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
        <Boton
          type="submit"
          className={ANCHO_BOTON}
          variante={cambio && valido ? "principal" : "secundario"}
          cargando={guardando}
          disabled={!valido || !cambio}
        >
          {comun.verbos.guardar}
        </Boton>
        {/* Siempre en el DOM: una región viva que aparece de golpe no se
            anuncia en todos los lectores de pantalla. */}
        <p role="status" className="text-center text-sm text-verde sm:text-left">
          {guardado ? `✓ ${comun.verbos.guardado}` : ""}
        </p>
      </div>
      {error ? <ErrorEnLinea error={error} /> : null}
    </form>
  );
}

/**
 * Una fila de ajuste con un control de − y +, como el stepper de iOS. En el
 * celular el número se cambia con el dedo sin abrir el teclado; el campo
 * igual se puede tipear, para ir de 3 a 30 sin 27 toques.
 */
function Ajuste({
  etiqueta,
  ayuda,
  valor,
  onCambiar,
  rango,
  textoMenos,
  textoMas,
}: {
  etiqueta: string;
  ayuda: string;
  valor: string;
  onCambiar: (v: string) => void;
  rango: { min: number; max: number };
  textoMenos: string;
  textoMas: string;
}) {
  const idCampo = useId();
  const idAyuda = useId();
  const n = aEntero(valor);
  const valido = enRango(n, rango);

  function mover(paso: number) {
    // Con el campo vacío o fuera de rango, el primer toque lo trae al borde
    // más cercano en vez de sumar sobre algo que no vale.
    const base = Number.isNaN(n) ? rango.min - paso : n;
    onCambiar(String(Math.min(rango.max, Math.max(rango.min, base + paso))));
  }

  const paso =
    "flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-borde bg-panel " +
    "text-2xl leading-none text-white transition hover:bg-white/15 active:scale-[0.94] " +
    "disabled:cursor-not-allowed disabled:opacity-40 disabled:active:scale-100 " +
    "focus:outline-none focus-visible:ring-2 focus-visible:ring-acento";

  return (
    <div className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <div className="min-w-0">
        <label htmlFor={idCampo} className="text-base font-medium">
          {etiqueta}
        </label>
        <p id={idAyuda} className={`mt-0.5 text-sm ${valido ? "text-tenue" : "text-naranja"}`}>
          {valido ? ayuda : t.fueraDeRango(rango.min, rango.max)}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          aria-label={textoMenos}
          aria-controls={idCampo}
          className={paso}
          disabled={valido && n <= rango.min}
          onClick={() => mover(-1)}
        >
          −
        </button>
        <input
          id={idCampo}
          inputMode="numeric"
          autoComplete="off"
          maxLength={3}
          aria-describedby={idAyuda}
          aria-invalid={!valido}
          value={valor}
          onChange={(e) => onCambiar(e.target.value.replace(/\D/g, ""))}
          className={
            "h-12 w-16 rounded-xl border bg-hundido px-2 text-center text-lg font-semibold tabular-nums " +
            `text-white outline-none focus:border-acento ${valido ? "border-borde" : "border-naranja"}`
          }
        />
        <button
          type="button"
          aria-label={textoMas}
          aria-controls={idCampo}
          className={paso}
          disabled={valido && n >= rango.max}
          onClick={() => mover(1)}
        >
          +
        </button>
      </div>
    </div>
  );
}

// ── Durante: fotos ───────────────────────────────────────────

function ResumenFotos({ evento, desdeLista }: { evento: EventoAdmin; desdeLista: unknown }) {
  const cifras: { etiqueta: string; valor: number; color: string }[] = [
    // Pendientes en naranja sólo si hay: es lo único que espera a alguien.
    { etiqueta: t.pendientes, valor: evento.pendientes, color: evento.pendientes > 0 ? "text-naranja" : "" },
    { etiqueta: t.aprobadas, valor: evento.aprobadas, color: "" },
    { etiqueta: t.rechazadas, valor: evento.rechazadas, color: "" },
  ];
  const hayPendientes = evento.pendientes > 0;

  return (
    <div className={TARJETA}>
      <dl className="grid grid-cols-3 gap-2 text-center">
        {cifras.map(({ etiqueta, valor, color }) => (
          // dt antes que dd en el DOM (así se lee); el número arriba a la vista.
          <div key={etiqueta} className="flex flex-col-reverse rounded-2xl bg-hundido px-1 py-3">
            <dt className="truncate text-xs text-tenue sm:text-sm">{etiqueta}</dt>
            <dd className={`text-3xl font-semibold tabular-nums ${color}`}>{valor}</dd>
          </div>
        ))}
      </dl>
      {/* Con el mismo state con que se llegó acá: el "‹ Volver" de Revisar
          fotos lleva a la misma lista de origen (el historial con su filtro). */}
      <Link
        to={`/admin/eventos/${evento.id}/revisar`}
        state={desdeLista}
        className={`mt-4 ${claseBotonGrande(hayPendientes ? "principal" : "secundario")}`}
      >
        {hayPendientes ? t.revisarConPendientes(evento.pendientes) : comun.verbos.revisarFotos}
      </Link>
      {!hayPendientes && (
        <p className="mt-3 text-sm text-tenue">
          {evento.aprobadas + evento.rechazadas === 0 ? t.sinFotos : t.sinPendientes}
        </p>
      )}
    </div>
  );
}

// ── Después: video ───────────────────────────────────────────

/** `fl_attachment` hace que Cloudinary lo mande como descarga y no lo reproduzca. */
function urlDeDescarga(url: string): string {
  return url.replace("/video/upload/", "/video/upload/fl_attachment/");
}

function VideoDelEvento({
  idEvento,
  aprobadas,
  alPerderSesion,
}: {
  idEvento: number;
  aprobadas: number;
  alPerderSesion: AlPerderSesion;
}) {
  const [video, setVideo] = useState<VideoEvento | null>(null);
  const [errorCarga, setErrorCarga] = useState<unknown>(null);
  const [intento, setIntento] = useState(0);
  const [pidiendo, setPidiendo] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let vivo = true;
    setErrorCarga(null);
    admin.video(idEvento).then(
      (v) => {
        if (vivo) setVideo(v);
      },
      (e: unknown) => {
        if (vivo && !alPerderSesion(e)) setErrorCarga(e);
      },
    );
    return () => {
      vivo = false;
    };
  }, [idEvento, intento, alPerderSesion]);

  // Mientras Cloudinary lo crea, se pregunta cada tanto. Cada consulta hace que
  // el backend le pregunte a Cloudinary; no hay aviso del otro lado.
  const estado = video?.estado ?? "ninguno";
  useEffect(() => {
    if (estado !== "procesando") return;
    let vivo = true;
    const reloj = window.setInterval(() => {
      admin.video(idEvento).then(
        (v) => {
          if (vivo) setVideo(v);
        },
        (e: unknown) => {
          if (vivo) alPerderSesion(e);
        },
      );
    }, CONSULTA_VIDEO_MS);
    return () => {
      vivo = false;
      window.clearInterval(reloj);
    };
  }, [idEvento, estado, alPerderSesion]);

  async function crear() {
    setPidiendo(true);
    setError(null);
    try {
      setVideo(await admin.armarVideo(idEvento));
    } catch (e) {
      if (!alPerderSesion(e)) setError(e);
    } finally {
      setPidiendo(false);
    }
  }

  const fotosQueEntran = Math.min(aprobadas, MAX_FOTOS_VIDEO);
  const duracion = fotosQueEntran * SEGUNDOS_POR_FOTO_VIDEO;
  // Si se aprobaron fotos después de crearlo, el video no las tiene.
  const desactualizado = estado === "listo" && video?.fotos != null && video.fotos < fotosQueEntran;

  return (
    <div className={TARJETA}>
      <h3 className="text-lg font-semibold">{t.videoTitulo}</h3>
      <p className="mt-1 text-sm text-tenue">
        {t.videoDetalle}
        {aprobadas > MAX_FOTOS_VIDEO && t.videoMuchas}
      </p>

      {video === null ? (
        errorCarga ? (
          <ErrorEnLinea error={errorCarga} reintentar={() => setIntento((n) => n + 1)} />
        ) : (
          <p className="mt-4 flex items-center gap-2 text-sm text-tenue">
            <Girando />
            {t.videoCargando}
          </p>
        )
      ) : (
        <>
          {estado === "procesando" && (
            <div role="status" className="mt-4 flex items-start gap-3 rounded-2xl bg-hundido p-4 text-sm">
              <Girando />
              <p>{t.videoProcesando(video.fotos)}</p>
            </div>
          )}

          {estado === "fallo" && (
            <p role="alert" className="mt-4 text-sm text-rojo">
              {t.videoFallo}
            </p>
          )}

          {estado === "listo" && video.url && (
            <video
              src={video.url}
              controls
              playsInline
              preload="metadata"
              className="mt-4 aspect-video w-full rounded-2xl bg-black"
            />
          )}
          {desactualizado && <p className="mt-3 text-sm text-naranja">{t.videoDesactualizado}</p>}

          {estado !== "procesando" && (
            <div className="mt-4 flex flex-col gap-3 sm:flex-row">
              {estado === "listo" && video.url && (
                <a href={urlDeDescarga(video.url)} className={claseBotonGrande("principal")}>
                  {t.descargarVideo}
                </a>
              )}
              <Boton
                variante={estado === "listo" ? "secundario" : "principal"}
                className={`${ANCHO_BOTON} ${DOS_LINEAS}`}
                cargando={pidiendo}
                disabled={aprobadas === 0}
                onClick={crear}
              >
                {estado === "ninguno"
                  ? aprobadas > 0
                    ? t.crearVideo(duracion)
                    : t.crearVideoSolo
                  : t.crearDeNuevo}
              </Boton>
            </div>
          )}
          {aprobadas === 0 && estado !== "procesando" && (
            <p className="mt-3 text-sm text-tenue">{t.videoSinAprobadas}</p>
          )}
          {error ? <ErrorEnLinea error={error} /> : null}
        </>
      )}
    </div>
  );
}

// ── Después: descargas ───────────────────────────────────────

function Descargas({ evento, alPerderSesion }: { evento: EventoAdmin; alPerderSesion: AlPerderSesion }) {
  const [bajando, setBajando] = useState<Incluir | null>(null);
  const [error, setError] = useState<unknown>(null);
  const total = evento.pendientes + evento.aprobadas + evento.rechazadas;

  async function descargar(incluir: Incluir) {
    setBajando(incluir);
    setError(null);
    try {
      const blob = await admin.descargar(evento.id, incluir);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      // El servidor ya manda el nombre en Content-Disposition, pero fetch no lo
      // aplica solo: se repite acá con el evento y la fecha, nunca un id.
      a.download = t.nombreArchivo(evento.nombre, evento.fecha_evento, incluir);
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Revocar en el acto corta la descarga en algunos navegadores (Safari):
      // se le da un rato para que la tome.
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (e) {
      if (!alPerderSesion(e)) setError(e);
    } finally {
      setBajando(null);
    }
  }

  return (
    <div className={TARJETA}>
      <h3 className="text-lg font-semibold">{t.descargaTitulo}</h3>
      <p className="mt-1 text-sm text-tenue">{t.descargaDetalle(comun.fotos(total))}</p>
      <div className="mt-4 flex flex-col gap-3 sm:flex-row">
        <Boton
          className={`${ANCHO_BOTON} ${DOS_LINEAS}`}
          cargando={bajando === "aprobadas"}
          disabled={evento.aprobadas === 0 || bajando !== null}
          onClick={() => descargar("aprobadas")}
        >
          {t.descargarAprobadas(evento.aprobadas)}
        </Boton>
        <Boton
          variante="secundario"
          className={`${ANCHO_BOTON} ${DOS_LINEAS}`}
          cargando={bajando === "todas"}
          disabled={total === 0 || bajando !== null}
          onClick={() => descargar("todas")}
        >
          {t.descargarTodas(total)}
        </Boton>
      </div>
      {bajando && (
        <p role="status" className="mt-3 flex items-center gap-2 text-sm text-acento">
          <Girando />
          {t.preparando}
        </p>
      )}
      {error ? <ErrorEnLinea error={error} /> : null}
    </div>
  );
}
