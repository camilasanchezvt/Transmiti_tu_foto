import {
  ArrowDownTrayIcon,
  CalendarDaysIcon,
  ChevronDownIcon,
  ClockIcon as ClockIconMini,
  Cog6ToothIcon,
  ExclamationTriangleIcon,
  PhotoIcon,
  TrashIcon,
  UsersIcon,
} from "@heroicons/react/20/solid";
import { ClockIcon } from "@heroicons/react/24/outline";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import { admin } from "../api/client";
import type { Cuenta, EventoAdmin } from "../api/tipos";
import BotonChico, { claseBotonChico } from "../comp/BotonChico";
import Cargando from "../comp/Cargando";
import ChipEstado from "../comp/ChipEstado";
import { claseIconoChico, claseIconoChip, type Icono } from "../comp/icono";
import MensajeError from "../comp/MensajeError";
import { DIAS_DE_AVISO, diasParaElBorrado, sinArchivos, urlDescargaVideo } from "../lib/descargas";
import { fechaLarga } from "../lib/fecha";
import LayoutAdmin from "./LayoutAdmin";
import { anclaDelEvento, type DesdeLista } from "./navegacion";
import { comun } from "./textos/comun";
import { historial as t } from "./textos/historial";
import { useAlPerderSesion, useSesion } from "./useSesion";

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
 */
export default function PaginaHistorial() {
  const alPerderSesion = useAlPerderSesion();
  const sesion = useSesion();
  const { usuario, esAdmin } = sesion;
  const [parametros, setParametros] = useSearchParams();

  // A un organizador el backend le devuelve los suyos mande lo que mande: ni
  // se manda, y un ?organizador= que le quedó en un link no le cambia nada.
  const organizador = esAdmin ? leerId(parametros.get("organizador")) : undefined;

  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [intento, setIntento] = useState(0);
  const [cuentas, setCuentas] = useState<Cuenta[] | null>(null);

  useEffect(() => {
    document.title = comun.tituloPestana(comun.nav.historial);
  }, []);

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
    return (
      <>
        {error ? (
          <div className="mb-6">
            <MensajeError error={error} onReintentar={() => setIntento((n) => n + 1)} />
          </div>
        ) : null}

        <div aria-busy={recargando} className={`transition-opacity ${recargando ? "opacity-60" : ""}`}>
          {resultado.eventos.length === 0 ? (
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
              eventos={resultado.eventos}
              // Filtrando por una cuenta, repetir su nombre en cada tarjeta no
              // agrega nada.
              conOrganizador={esAdmin && resultado.organizador === undefined}
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
    </LayoutAdmin>
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

function ListaPorMes({ eventos, conOrganizador }: { eventos: EventoAdmin[]; conOrganizador: boolean }) {
  const grupos = useMemo(() => agruparPorMes(eventos), [eventos]);
  // Si se entra a Ajustes o a Revisar desde acá, esas páginas leen este estado
  // para volver al historial (con el filtro) y no a los eventos vigentes.
  const { pathname, search } = useLocation();
  const volver = useMemo<DesdeLista>(() => ({ volverA: pathname + search }), [pathname, search]);

  return (
    <div className="flex flex-col gap-8">
      {grupos.map((g) => (
        <section key={g.clave} aria-labelledby={`mes-${g.clave}`}>
          <h2 id={`mes-${g.clave}`} className="mb-3 px-1 text-lg font-semibold">
            {g.titulo}
          </h2>
          <ul className="flex flex-col gap-3">
            {g.eventos.map((e) => (
              <TarjetaEvento
                key={e.id}
                evento={e}
                conOrganizador={conOrganizador}
                volver={volver}
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
}: {
  evento: EventoAdmin;
  conOrganizador: boolean;
  volver: DesdeLista;
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
    </li>
  );
}

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
      <h2 className="text-lg font-semibold leading-snug">{titulo}</h2>
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

/** El backend ya los manda del más reciente al más viejo; un Map conserva ese
 *  orden y, si algún día no vinieran ordenados, igual no repite meses. */
function agruparPorMes(eventos: EventoAdmin[]): Grupo[] {
  const grupos = new Map<string, Grupo>();
  for (const e of eventos) {
    const clave = e.fecha_evento.slice(0, 7);
    const grupo = grupos.get(clave);
    if (grupo) grupo.eventos.push(e);
    else grupos.set(clave, { clave, titulo: tituloDeMes(clave), eventos: [e] });
  }
  return [...grupos.values()];
}
