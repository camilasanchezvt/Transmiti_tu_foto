import {
  ArrowDownTrayIcon,
  CalendarDaysIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  ClockIcon as ClockIconMini,
  Cog6ToothIcon,
  ExclamationTriangleIcon,
  PhotoIcon,
  TrashIcon,
  UsersIcon,
} from "@heroicons/react/20/solid";
import { ClockIcon, TrashIcon as BorrarGrande } from "@heroicons/react/24/outline";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { ErrorApi, admin } from "../api/client";
import type { Cuenta, EventoAdmin, EventoBorrado } from "../api/tipos";
import BotonChico, { claseBotonChico } from "../comp/BotonChico";
import Cargando from "../comp/Cargando";
import ChipEstado from "../comp/ChipEstado";
import Confirmar from "../comp/Confirmar";
import { claseIconoChico, claseIconoChip, type Icono } from "../comp/icono";
import MensajeError from "../comp/MensajeError";
import { DIAS_DE_AVISO, diasParaElBorrado, sinArchivos, urlDescargaVideo } from "../lib/descargas";
import { fechaLarga } from "../lib/fecha";
import LayoutAdmin from "./LayoutAdmin";
import { anclaDelEvento, esDelHistorial, type DesdeLista } from "./navegacion";
import { comun } from "./textos/comun";
import { historial as t } from "./textos/historial";
import { revalidarSesion, useAlPerderSesion, useSesion } from "./useSesion";

/** Lo que Ajustes le deja en el `state` al volver acá después de borrar un
 *  evento: que se muestre el aviso "Evento borrado." */
export interface LlegadaTrasBorrar {
  eventoBorrado: true;
}

/** El título de la lista vacía: adonde va el foco si se borró el último. */
const ID_VACIO = "historial-vacio";

/** Lo que devolvió el backend y para qué filtro. Guardar el filtro junto a la
 *  lista permite seguir mostrando la anterior mientras llega la nueva, sin
 *  confundirla con la que corresponde a lo que está elegido. */
interface Resultado {
  organizador: number | undefined;
  eventos: EventoAdmin[];
}

/**
 * Los eventos terminados y los que pasaron su fecha sin publicarse, del más
 * reciente al más viejo, agrupados por mes. Uno abierto nunca está acá, aunque
 * su fecha haya pasado: es la regla de medianoche (ver navegacion.ts).
 *
 * Se viene acá después de la fiesta: a crear el video, a descargar las fotos o
 * a revisar las que quedaron sin mirar. Por eso cada evento muestra cuántas
 * fotos tiene en cada estado y lleva a Ajustes, que es donde están el video y
 * las descargas. El video, si ya está listo, se descarga desde acá mismo.
 *
 * 30 días después de la fecha del evento se borran de Cloudinary las fotos y el
 * video (las filas quedan). Cada tarjeta dice cuándo, en naranja la última
 * semana, y una vez borradas ya no ofrece revisar ni descargar nada.
 *
 * Un admin ve los de todas las cuentas y puede quedarse con los de una. Ese
 * filtro va en la URL (?organizador=ID): así la página de Cuentas linkea "Ver
 * historial" de una cuenta, y recargar no lo pierde.
 *
 * Un admin además puede borrar un evento para siempre, con sus fotos y su
 * video: la segunda excepción a "nada se borra". Va al pie de cada tarjeta,
 * aparte de las demás acciones, y se confirma escribiendo el nombre del evento.
 * Desde Ajustes se borra con el mismo diálogo (DialogoBorrarEvento) y se vuelve
 * acá con el mismo aviso.
 */
export default function PaginaHistorial() {
  const alPerderSesion = useAlPerderSesion();
  const sesion = useSesion();
  const { usuario, esAdmin } = sesion;
  const [parametros, setParametros] = useSearchParams();
  const navegar = useNavigate();
  const { pathname, search, hash, state } = useLocation();

  // A un organizador el backend le devuelve los suyos mande lo que mande: ni
  // se manda, y un ?organizador= que le quedó en un link no le cambia nada.
  const organizador = esAdmin ? leerId(parametros.get("organizador")) : undefined;

  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [intento, setIntento] = useState(0);
  const [cuentas, setCuentas] = useState<Cuenta[] | null>(null);

  /** Los que se borraron desde esta página. Se sacan al mostrar la lista y no
   *  de la lista misma: una recarga que salió antes del borrado y llega
   *  después no los trae de vuelta. */
  const [borrados, setBorrados] = useState<ReadonlySet<number>>(() => new Set());
  /** El evento que se está por borrar: el diálogo que pide su nombre. */
  const [aBorrar, setABorrar] = useState<EventoAdmin | null>(null);
  const [aviso, setAviso] = useState<{ texto: string; vez: number } | null>(null);

  // Al borrar, la tarjeta sale y la lista se corre hacia arriba: un segundo
  // toque en "Borrar evento" del diálogo caería sobre el "Borrar evento" de la
  // tarjeta que quedó debajo del dedo. Medio segundo después de cerrar, esos
  // botones no responden. Lo mismo que Eliminar definitivamente en Cuentas.
  const cerradoEn = useRef(0);
  // El botón que abrió el diálogo ya no existe: el foco va al título del mes
  // donde estaba el evento, y no se pierde en <body>.
  const enfocarTras = useRef<string | null>(null);

  useEffect(() => {
    document.title = comun.tituloPestana(comun.nav.historial);
  }, []);

  // Se borró desde Ajustes y se vino acá: el mismo aviso que borrando desde
  // la lista. Después se limpia el `state`, así recargar o volver con "Atrás"
  // no lo repite.
  const llegoTrasBorrar = (state as Partial<LlegadaTrasBorrar> | null)?.eventoBorrado === true;
  useEffect(() => {
    if (!llegoTrasBorrar) return;
    setAviso({ texto: t.borrar.hecho, vez: Date.now() });
    navegar({ pathname, search, hash }, { replace: true, state: null });
  }, [llegoTrasBorrar, navegar, pathname, search, hash]);

  // El aviso de abajo se va solo.
  useEffect(() => {
    if (!aviso) return;
    const id = window.setTimeout(() => setAviso(null), 4000);
    return () => window.clearTimeout(id);
  }, [aviso]);

  // Corre después de que el diálogo se desmonta (y de que intenta devolver el
  // foco a un botón que ya no está). Sin mover la página: sólo el foco.
  useEffect(() => {
    if (aBorrar || !enfocarTras.current) return;
    const destino =
      document.getElementById(enfocarTras.current) ??
      document.querySelector<HTMLElement>("[data-titulo-mes]") ??
      document.getElementById(ID_VACIO);
    enfocarTras.current = null;
    destino?.focus({ preventScroll: true });
  }, [aBorrar, borrados]);

  function abrirBorrar(evento: EventoAdmin) {
    if (Date.now() - cerradoEn.current < 500) return;
    setABorrar(evento);
  }

  function alBorrar(evento: EventoAdmin) {
    cerradoEn.current = Date.now();
    enfocarTras.current = idDelMes(claveDelMes(evento));
    setBorrados((b) => new Set(b).add(evento.id));
    // Que el selector de organizador lo cuente: una cuenta que se quedó sin
    // eventos deja de aparecer, como si se hubiera recargado.
    setCuentas(
      (lista) =>
        lista &&
        lista.map((c) => (c.id === evento.organizador_id ? { ...c, eventos: Math.max(0, c.eventos - 1) } : c)),
    );
    setABorrar(null);
    setAviso({ texto: t.borrar.hecho, vez: Date.now() });
  }

  function alCerrarBorrar(yaNoEsta: boolean) {
    setABorrar(null);
    // El backend dijo que no existe (lo borró otra persona, desde otra
    // pestaña): se vuelve a pedir la lista para que tampoco esté acá.
    if (yaNoEsta) setIntento((n) => n + 1);
  }

  // Se espera a saber quién es antes de pedir: si fuera admin y se pidiera
  // antes, saldría un pedido sin filtro que el siguiente pisa enseguida.
  const idUsuario = usuario?.id;
  useEffect(() => {
    if (idUsuario === undefined) return;
    let vivo = true;
    setCargando(true);
    setError(null);
    admin
      .eventos({ alcance: "historial", organizador })
      .then(
        (eventos) => {
          if (vivo) setResultado({ organizador, eventos });
        },
        (e: unknown) => {
          if (vivo && !alPerderSesion(e)) setError(e);
        },
      )
      .finally(() => {
        if (vivo) setCargando(false);
      });
    return () => {
      vivo = false;
    };
  }, [idUsuario, organizador, intento, alPerderSesion]);

  // Las cuentas, sólo para el selector. Si fallan no es grave: el filtro que
  // venga en la URL sigue andando y "Todos" siempre está.
  useEffect(() => {
    if (!esAdmin) return;
    let vivo = true;
    admin.cuentas().then(
      (lista) => {
        if (vivo) setCuentas(lista);
      },
      () => {
        if (vivo) setCuentas([]);
      },
    );
    return () => {
      vivo = false;
    };
  }, [esAdmin]);

  // Se le pasa al layout para que no pida las cuentas otra vez sólo para
  // contar las pendientes. A un organizador el layout no le muestra el número.
  const pendientesCuentas = cuentas?.filter((c) => c.estado === "pendiente").length ?? 0;

  const vigente = resultado !== null && resultado.organizador === organizador ? resultado : null;
  const nombreFiltrado =
    organizador === undefined
      ? null
      : cuentas?.find((c) => c.id === organizador)?.nombre ??
        vigente?.eventos[0]?.organizador_nombre ??
        t.filtro.sinNombre(organizador);

  function elegirOrganizador(valor: string) {
    const siguientes = new URLSearchParams(parametros);
    if (valor) siguientes.set("organizador", valor);
    else siguientes.delete("organizador");
    // replace: cambiar el filtro no es navegar. "Atrás" tiene que volver a
    // donde se estaba antes (por ejemplo, a Cuentas), no al filtro anterior.
    setParametros(siguientes, { replace: true });
  }

  function contenido() {
    if (!usuario && sesion.error) {
      return <MensajeError error={sesion.error} onReintentar={sesion.reintentar} />;
    }
    if (!resultado) {
      if (error) return <MensajeError error={error} onReintentar={() => setIntento((n) => n + 1)} />;
      return <Cargando texto={t.cargando} />;
    }

    const recargando = cargando || vigente === null;
    const eventos = resultado.eventos.filter((e) => !borrados.has(e.id));
    return (
      <>
        {error ? (
          <div className="mb-6">
            <MensajeError error={error} onReintentar={() => setIntento((n) => n + 1)} />
          </div>
        ) : null}

        <div aria-busy={recargando} className={`transition-opacity ${recargando ? "opacity-60" : ""}`}>
          {eventos.length === 0 ? (
            <Vacio
              titulo={
                nombreFiltrado
                  ? t.vacio.tituloDe(nombreFiltrado)
                  : esAdmin
                    ? t.vacio.titulo
                    : t.vacio.tituloPropio
              }
              filtrado={nombreFiltrado !== null}
              onVerTodos={() => elegirOrganizador("")}
            />
          ) : (
            <ListaPorMes
              eventos={eventos}
              // Filtrando por una cuenta, repetir su nombre en cada tarjeta no
              // agrega nada.
              conOrganizador={esAdmin && resultado.organizador === undefined}
              // Sólo un admin borra. A un organizador ni se le ofrece: el
              // backend le respondería 403.
              onBorrar={esAdmin ? abrirBorrar : undefined}
            />
          )}
        </div>
      </>
    );
  }

  return (
    <LayoutAdmin titulo={comun.nav.historial} pendientesCuentas={pendientesCuentas}>
      <p className="-mt-3 mb-6 text-base leading-snug text-tenue">{t.bajada}</p>

      {esAdmin && (
        <FiltroOrganizador
          cuentas={cuentas}
          elegido={organizador}
          nombreElegido={nombreFiltrado}
          onElegir={elegirOrganizador}
        />
      )}

      {contenido()}

      {aBorrar && (
        <DialogoBorrarEvento
          evento={aBorrar}
          onBorrado={() => alBorrar(aBorrar)}
          onCerrar={alCerrarBorrar}
        />
      )}

      <AvisoHecho aviso={aviso} />
    </LayoutAdmin>
  );
}

// ── Borrar un evento ─────────────────────────────────────────

function mensajeDe(error: unknown): string {
  return error instanceof ErrorApi ? error.message : comun.errores.generico;
}

/** Cuánto no responde Borrar después de un error (ver DialogoBorrarEvento). */
const GRACIA_TRAS_ERROR = 600;

/**
 * "¿Borrar “…” para siempre?": el diálogo de Borrar evento, el mismo desde el
 * Historial y desde Ajustes. Hace el pedido él mismo y avisa con `onBorrado`
 * sólo si salió; quien lo muestra decide qué pasa después (sacar la tarjeta,
 * volver al Historial).
 *
 * Se confirma escribiendo el nombre del evento, y eso escrito, tal cual, es lo
 * que se le manda al backend para que confirme él también. Un error del
 * backend queda adentro del diálogo, donde se está mirando, y el diálogo
 * sigue abierto: si Cloudinary no respondió, o se está armando el video, se
 * puede probar de nuevo sin volver a escribir. `onCerrar(yaNoEsta)` avisa si
 * en el medio el backend dijo que el evento ya no existe (404), para que quien
 * lo muestra se ponga al día.
 *
 * Que un reintento sea siempre a propósito: el error va debajo de los botones
 * (la prop `error` de Confirmar), así al aparecer no los corre y "Borrar
 * evento" no queda donde estaba Cancelar; y durante `GRACIA_TRAS_ERROR` después
 * del error, Borrar no responde, por si el dedo ya venía en camino.
 */
export function DialogoBorrarEvento({
  evento,
  onBorrado,
  onCerrar,
}: {
  evento: EventoAdmin;
  onBorrado: (respuesta: EventoBorrado) => void;
  onCerrar: (yaNoEsta: boolean) => void;
}) {
  const alPerderSesion = useAlPerderSesion();
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const yaNoEsta = useRef(false);
  const errorEn = useRef(0);

  async function borrar(escrito: string) {
    if (Date.now() - errorEn.current < GRACIA_TRAS_ERROR) return;
    setCargando(true);
    setError(null);
    try {
      const respuesta = await admin.borrarEvento(evento.id, escrito);
      setCargando(false);
      onBorrado(respuesta);
    } catch (e) {
      setCargando(false);
      if (alPerderSesion(e)) return;
      if (e instanceof ErrorApi) {
        // Sólo se ofrece a un admin: un 403 es que cambió el rol de quien
        // mira. Se pregunta de nuevo y la página deja de ofrecerlo.
        if (e.esSinPermiso) revalidarSesion();
        if (e.http === 404) yaNoEsta.current = true;
      }
      errorEn.current = Date.now();
      setError(e);
    }
  }

  const fotos = evento.aprobadas + evento.rechazadas + evento.pendientes;

  return (
    <Confirmar
      abierto
      peligro
      titulo={t.borrar.titulo(evento.nombre)}
      mensaje={
        <>
          <p className="font-semibold text-texto">{t.borrar.noSeDeshace}</p>
          <p className="mt-1">
            {evento.fotos_borradas_en
              ? t.borrar.yaBorradas
              : t.borrar.seBorran(fotos, evento.video_url_listo !== null)}
          </p>
        </>
      }
      error={error ? mensajeDe(error) : null}
      aEscribir={{ texto: evento.nombre, etiqueta: t.borrar.etiqueta }}
      textoConfirmar={t.borrar.confirmar}
      iconoConfirmar={BorrarGrande}
      cargando={cargando}
      onConfirmar={(escrito) => void borrar(escrito)}
      onCancelar={() => onCerrar(yaNoEsta.current)}
    />
  );
}

/** Aviso de lo que se acaba de hacer, abajo y solo por unos segundos, como en
 *  Cuentas. En el celular va por encima de la barra de pestañas de abajo.
 *
 *  `!bg-sombra/75`: el 40 % de `.vidrio-oscuro` está pensado para ir sobre una
 *  foto; sobre la página clara, el blanco quedaba en 3,3:1. Con 75 % pasa de
 *  10:1 en claro y en oscuro no cambia. Lleva `!` porque `.vidrio-oscuro` es
 *  de `@layer utilities` y sale después: sin él, gana su 40 %. */
function AvisoHecho({ aviso }: { aviso: { texto: string; vez: number } | null }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 bottom-[calc(4.5rem+env(safe-area-inset-bottom))] z-30 flex justify-center px-4 md:bottom-8"
    >
      {aviso && (
        <p
          key={aviso.vez}
          className="vidrio-oscuro !bg-sombra/75 flex items-center gap-2 rounded-full px-5 py-3 text-sm font-medium text-luz"
        >
          <CheckCircleIcon aria-hidden className="h-5 w-5 shrink-0 text-verde" />
          <span className="min-w-0">{aviso.texto}</span>
        </p>
      )}
    </div>
  );
}

// ── Filtro ───────────────────────────────────────────────────

function FiltroOrganizador({
  cuentas,
  elegido,
  nombreElegido,
  onElegir,
}: {
  cuentas: Cuenta[] | null;
  elegido: number | undefined;
  nombreElegido: string | null;
  onElegir: (valor: string) => void;
}) {
  // Sólo las cuentas que tienen algún evento: una pendiente nunca pudo crear
  // uno, y elegir una cuenta sin eventos siempre da la lista vacía. Las de baja
  // sí van, marcadas: sus eventos quedaron y se siguen pudiendo mirar.
  const opciones = useMemo(() => {
    const conEventos = (cuentas ?? []).filter((c) => c.eventos > 0 || c.id === elegido);
    return conEventos.sort((a, b) => a.nombre.localeCompare(b.nombre, "es", { sensitivity: "base" }));
  }, [cuentas, elegido]);

  // Si el link trae una cuenta que no está en la lista (o la lista no cargó),
  // igual tiene que verse elegida: si no, el selector diría "Todos" sobre una
  // lista filtrada.
  const falta = elegido !== undefined && !opciones.some((c) => c.id === elegido);

  return (
    <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
      <label htmlFor="filtro-organizador" className="text-sm text-tenue">
        {t.filtro.etiqueta}
      </label>
      <div className="relative w-full sm:w-72">
        <select
          id="filtro-organizador"
          value={elegido === undefined ? "" : String(elegido)}
          onChange={(e) => onElegir(e.target.value)}
          // appearance-none y una flecha propia: la nativa de Windows es un
          // cuadrado gris que no pega con el vidrio. Las opciones llevan el
          // fondo sólido del tema (index.css): algunos navegadores pintan la
          // lista con el fondo del select, y el hundido es translúcido.
          className={
            "h-12 w-full cursor-pointer appearance-none text-ellipsis rounded-xl border border-borde bg-hundido pl-3 pr-10 " +
            "text-base text-texto outline-none focus:border-acento"
          }
        >
          <option value="">{t.filtro.todos}</option>
          {falta && <option value={String(elegido)}>{nombreElegido}</option>}
          {opciones.map((c) => (
            <option key={c.id} value={String(c.id)}>
              {c.estado === "baja" ? t.filtro.deBaja(c.nombre) : c.nombre}
            </option>
          ))}
        </select>
        <ChevronDownIcon
          aria-hidden
          className="pointer-events-none absolute right-3 top-1/2 h-5 w-5 -translate-y-1/2 text-tenue"
        />
      </div>
    </div>
  );
}

// ── Lista ────────────────────────────────────────────────────

function ListaPorMes({
  eventos,
  conOrganizador,
  onBorrar,
}: {
  eventos: EventoAdmin[];
  conOrganizador: boolean;
  /** Sólo si quien mira es admin. */
  onBorrar?: (evento: EventoAdmin) => void;
}) {
  const grupos = useMemo(() => agruparPorMes(eventos), [eventos]);
  // Si se entra a Ajustes o a Revisar desde acá, esas páginas leen este estado
  // para volver al historial (con el filtro) y no a los eventos vigentes.
  const { pathname, search } = useLocation();
  const volver = useMemo<DesdeLista>(() => ({ volverA: pathname + search }), [pathname, search]);

  return (
    <div className="flex flex-col gap-8">
      {grupos.map((g) => (
        <section key={g.clave} aria-labelledby={idDelMes(g.clave)}>
          {/* tabIndex -1: recibe el foco después de borrar un evento del mes. */}
          <h2
            id={idDelMes(g.clave)}
            data-titulo-mes=""
            tabIndex={-1}
            className="mb-3 px-1 text-lg font-semibold outline-none"
          >
            {g.titulo}
          </h2>
          <ul className="flex flex-col gap-3">
            {g.eventos.map((e) => (
              <TarjetaEvento
                key={e.id}
                evento={e}
                conOrganizador={conOrganizador}
                volver={volver}
                // Por las dudas, sólo si es del Historial con la regla de hoy:
                // uno que no lo fuera, el backend no lo borra.
                onBorrar={onBorrar && esDelHistorial(e) ? () => onBorrar(e) : undefined}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function TarjetaEvento({
  evento: e,
  conOrganizador,
  volver,
  onBorrar,
}: {
  evento: EventoAdmin;
  conOrganizador: boolean;
  volver: DesdeLista;
  onBorrar?: () => void;
}) {
  const hayFotos = e.aprobadas + e.rechazadas + e.pendientes > 0;
  // Con las fotos borradas (o desde el día del borrado, aunque la limpieza no
  // haya pasado) no queda nada que mirar ni que bajar: Revisar mostraría la
  // grilla vacía y el backend ya no manda el video. Mismo corte que Ajustes.
  const borradas = sinArchivos(e);
  const video = borradas ? null : e.video_url_listo;

  return (
    // scroll-mt: al traerla a la vista por el ancla, que no quede debajo de la
    // barra fija de arriba.
    <li id={anclaDelEvento(e.id)} className="scroll-mt-24 rounded-3xl border border-borde bg-panel p-5">
      <div className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 break-words text-lg font-semibold leading-snug">{e.nombre}</h3>
        <div className="shrink-0 pt-1">
          <ChipEstado estado={e.estado} />
        </div>
      </div>
      <p className="mt-1 text-sm text-tenue">{fechaLarga(e.fecha_evento)}</p>
      {conOrganizador && <p className="break-words text-sm text-tenue">{comun.organiza(e.organizador_nombre)}</p>}

      {e.estado === "borrador" && <p className="mt-3 text-sm leading-snug text-tenue">{t.nuncaPublicado}</p>}

      <Totales evento={e} borradas={borradas} />

      {/* Sin fotos no hay nada que se vaya a borrar: la fecha sería ruido. */}
      {hayFotos && <Borrado evento={e} />}

      {/* flex-1 y wrap: en un celular el botón que no entra en la fila baja a
          la siguiente y ocupa todo el ancho, sin cortar el texto. */}
      <div className="mt-4 flex flex-wrap gap-2">
        {e.pendientes > 0 && !borradas && (
          <Link
            to={`/admin/eventos/${e.id}/revisar`}
            state={volver}
            aria-label={t.revisarDe(e.nombre)}
            className={`flex-1 whitespace-nowrap sm:flex-none ${claseBotonChico("azul")}`}
          >
            <PhotoIcon aria-hidden className={claseIconoChico} />
            {comun.verbos.revisarFotos}
          </Link>
        )}
        {video && (
          // fl_attachment en la URL hace que Cloudinary lo mande como archivo,
          // con un nombre que se entiende: en el celular se descarga en vez de
          // abrirse en el reproductor. `download` solo no alcanza, porque el
          // navegador lo ignora en un link a otro dominio.
          <a
            href={urlDescargaVideo(video, e.nombre, e.fecha_evento)}
            download
            aria-label={t.descargarVideoDe(e.nombre)}
            className={`flex-1 whitespace-nowrap sm:flex-none ${claseBotonChico("vidrio")}`}
          >
            <ArrowDownTrayIcon aria-hidden className={claseIconoChico} />
            {t.descargarVideo}
          </a>
        )}
        <Link
          to={`/admin/eventos/${e.id}/ajustes`}
          state={volver}
          aria-label={t.ajustesDe(e.nombre)}
          className={`flex-1 whitespace-nowrap sm:flex-none ${claseBotonChico("vidrio")}`}
        >
          <Cog6ToothIcon aria-hidden className={claseIconoChico} />
          {comun.verbos.ajustes}
        </Link>
      </div>

      {/* Aparte, al pie y después de una línea: es la única acción de la
          tarjeta que no tiene vuelta atrás, y no se tiene que poder tocar
          yendo a Ajustes. Sin fondo ni borde, como el "Eliminar" de los
          Ajustes de iOS y el "Eliminar definitivamente" de Cuentas, y a la
          izquierda, lejos del pulgar derecho. */}
      {onBorrar && (
        <div className="mt-4 border-t border-borde pt-3">
          {/* Nunca deshabilitado mientras el diálogo está abierto: el foco se
              iría a <body> y Cancelar no podría devolverlo acá. El diálogo ya
              tapa todo, y el medio segundo de gracia evita el doble toque. */}
          <button
            type="button"
            onClick={onBorrar}
            aria-label={t.borrar.accionDe(e.nombre)}
            className={CLASE_BORRAR}
          >
            <TrashIcon aria-hidden className={claseIconoChico} />
            {t.borrar.accion}
          </button>
        </div>
      )}
    </li>
  );
}

/** Rojo, sin fondo ni borde, con los 44 px de alto de todo botón chico. El
 *  -ml-3 alinea el ícono con el texto de la tarjeta. Igual que en Cuentas. */
const CLASE_BORRAR =
  "-ml-3 inline-flex min-h-11 items-center gap-1.5 rounded-full px-3 text-sm font-medium text-rojo-tinta " +
  "transition hover:bg-pulsado active:scale-[0.97] " +
  "disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100 " +
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-acento";

/** Tres números, como los resúmenes de Salud o de Fitness: el número grande,
 *  qué es debajo. Lo sin revisar va en naranja porque es lo único que pide
 *  hacer algo; con las fotos borradas ya no hay nada que hacer y va tenue. */
function Totales({ evento: e, borradas }: { evento: EventoAdmin; borradas: boolean }) {
  const total = e.aprobadas + e.rechazadas + e.pendientes;
  if (total === 0) {
    // Un evento sin publicar no pudo recibir fotos: ya lo dice su aviso.
    if (e.estado === "borrador") return null;
    return <p className="mt-4 text-sm text-tenue">{t.totales.ninguna}</p>;
  }

  return (
    <dl className="mt-4 grid grid-cols-3 gap-1 rounded-2xl bg-hundido px-2 py-3 text-center">
      <Total n={e.aprobadas} etiqueta={t.totales.aprobadas(e.aprobadas)} />
      <Total n={e.rechazadas} etiqueta={t.totales.rechazadas(e.rechazadas)} />
      <Total n={e.pendientes} etiqueta={t.totales.pendientes} destacado={e.pendientes > 0 && !borradas} />
    </dl>
  );
}

function Total({ n, etiqueta, destacado = false }: { n: number; etiqueta: string; destacado?: boolean }) {
  // En el HTML primero va qué es y después el número (así lo lee un lector de
  // pantalla: "aprobadas, 12"); flex-col-reverse los da vuelta a la vista.
  return (
    <div className="flex min-w-0 flex-col-reverse">
      <dt className={`truncate text-xs ${destacado ? "text-naranja-tinta" : "text-tenue"}`}>{etiqueta}</dt>
      <dd className={`text-2xl font-semibold tabular-nums ${destacado ? "text-naranja-tinta" : ""}`}>{n}</dd>
    </div>
  );
}

// ── Borrado ──────────────────────────────────────────────────

/**
 * Cuándo se borran de Cloudinary las fotos y el video, o cuándo se borraron.
 * Con el mismo margen de aviso que Ajustes (DIAS_DE_AVISO) y los días contados
 * con "hoy" en Argentina, como la pasada de limpieza del backend: si no, desde
 * una compu en otra zona el aviso saldría corrido.
 */
function Borrado({ evento: e }: { evento: EventoAdmin }) {
  if (e.fotos_borradas_en) {
    return <LineaBorrado icono={TrashIcon} texto={t.borrado.borradas(fechaLarga(e.fotos_borradas_en))} />;
  }
  const fecha = fechaLarga(e.fotos_se_borran_el);
  const dias = diasParaElBorrado(e.fotos_se_borran_el);
  if (dias !== null && dias <= DIAS_DE_AVISO) {
    return <LineaBorrado icono={ExclamationTriangleIcon} texto={t.borrado.pronto(fecha, dias)} aviso />;
  }
  return <LineaBorrado icono={ClockIconMini} texto={t.borrado.seBorran(fecha)} />;
}

function LineaBorrado({
  icono: IconoLinea,
  texto,
  aviso = false,
}: {
  icono: Icono;
  texto: string;
  aviso?: boolean;
}) {
  // items-start y el ícono bajado 2 px (el renglón mide 19, el ícono 16): si el
  // texto ocupa dos renglones, el ícono queda a la altura del primero.
  const color = aviso ? "font-medium text-naranja-tinta" : "text-tenue";
  return (
    <p className={`mt-3 flex items-start gap-1.5 text-sm leading-snug ${color}`}>
      <IconoLinea aria-hidden className={`mt-0.5 ${claseIconoChip}`} />
      <span className="min-w-0">{texto}</span>
    </p>
  );
}

// ── Vacío ────────────────────────────────────────────────────

function Vacio({ titulo, filtrado, onVerTodos }: { titulo: string; filtrado: boolean; onVerTodos: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-3xl border border-borde bg-panel px-5 py-10 text-center">
      {/* El símbolo grande arriba, como los estados vacíos de iOS: el mismo
          reloj de la pestaña Historial. */}
      <ClockIcon aria-hidden className="h-10 w-10 text-tenue" />
      {/* tabIndex -1: recibe el foco si se borró el último evento. */}
      <h2 id={ID_VACIO} tabIndex={-1} className="text-lg font-semibold leading-snug outline-none">
        {titulo}
      </h2>
      <p className="max-w-sm leading-snug text-tenue">{filtrado ? t.vacio.textoFiltrado : t.vacio.texto}</p>
      <div className="mt-2">
        {filtrado ? (
          <BotonChico icono={UsersIcon} onClick={onVerTodos}>
            {t.vacio.verTodos}
          </BotonChico>
        ) : (
          <Link to="/admin" className={claseBotonChico("vidrio")}>
            <CalendarDaysIcon aria-hidden className={claseIconoChico} />
            {t.vacio.irAEventos}
          </Link>
        )}
      </div>
    </div>
  );
}

// ── Ayudas ───────────────────────────────────────────────────

/** "12" → 12. Cualquier otra cosa (vacío, "abc", "-3") → sin filtro. */
function leerId(valor: string | null): number | undefined {
  if (!valor) return undefined;
  const n = Number(valor);
  return Number.isInteger(n) && n > 0 ? n : undefined;
}

const MES = new Intl.DateTimeFormat("es-AR", { month: "long", timeZone: "UTC" });

/** "2026-09" → "Septiembre 2026". Con el año siempre: en el historial conviven
 *  años distintos. En UTC por lo mismo que lib/fecha.ts: una fecha sin hora
 *  formateada con la zona local se corre al día (y al mes) anterior. */
function tituloDeMes(clave: string): string {
  const [anio, mes] = clave.split("-").map(Number);
  if (!anio || !mes) return clave;
  const nombre = MES.format(new Date(Date.UTC(anio, mes - 1, 1)));
  return `${nombre.charAt(0).toUpperCase()}${nombre.slice(1)} ${anio}`;
}

interface Grupo {
  clave: string;
  titulo: string;
  eventos: EventoAdmin[];
}

/** "2026-09": de qué mes es un evento. */
function claveDelMes(evento: EventoAdmin): string {
  return evento.fecha_evento.slice(0, 7);
}

/** El id del título de un mes: `mes-2026-09`. */
function idDelMes(clave: string): string {
  return `mes-${clave}`;
}

/** El backend ya los manda del más reciente al más viejo; un Map conserva ese
 *  orden y, si algún día no vinieran ordenados, igual no repite meses. */
function agruparPorMes(eventos: EventoAdmin[]): Grupo[] {
  const grupos = new Map<string, Grupo>();
  for (const e of eventos) {
    const clave = claveDelMes(e);
    const grupo = grupos.get(clave);
    if (grupo) grupo.eventos.push(e);
    else grupos.set(clave, { clave, titulo: tituloDeMes(clave), eventos: [e] });
  }
  return [...grupos.values()];
}
