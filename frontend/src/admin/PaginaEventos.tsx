import { useCallback, useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { CalendarDaysIcon } from "@heroicons/react/24/outline";
import { PaperAirplaneIcon, PlusIcon } from "@heroicons/react/24/solid";
import {
  CheckCircleIcon,
  ChevronRightIcon,
  Cog6ToothIcon,
  ExclamationTriangleIcon,
  PhotoIcon,
  XMarkIcon,
} from "@heroicons/react/20/solid";

import { ErrorApi, admin, tokenDeSesion } from "../api/client";
import type { Cuenta, EventoAdmin } from "../api/tipos";
import Boton from "../comp/Boton";
import BotonChico, { claseBotonChico } from "../comp/BotonChico";
import Cargando from "../comp/Cargando";
import ChipEstado from "../comp/ChipEstado";
import { claseIconoChico } from "../comp/icono";
import MensajeError from "../comp/MensajeError";
import { sinArchivos } from "../lib/descargas";
import { fechaLarga, hoyEnArgentina } from "../lib/fecha";
import CompartirEvento from "./CompartirEvento";
import LayoutAdmin from "./LayoutAdmin";
import { anclaDelEvento, useEventoDelAncla } from "./navegacion";
import { comun } from "./textos/comun";
import { textosEventos as t } from "./textos/eventos";
import { useAlPerderSesion, useSesion } from "./useSesion";

type AlCambiar = (evento: EventoAdmin) => void;

const CAMPO =
  "mt-1 block h-12 w-full min-w-0 rounded-xl border border-borde bg-hundido px-3 " +
  "text-base text-white outline-none focus:border-acento";

/** Las fotos y el video se borran a los 30 días de la fecha del evento
 *  (backend, limpieza.DIAS_HASTA_BORRAR). */
const DIAS_HASTA_BORRAR = 30;

/**
 * La fecha más vieja con la que se puede crear un evento: hace 29 días. Una de
 * hace 30 o más nacería con las fotos vencidas y el backend la rechaza (casi
 * siempre es el año mal puesto). Una de hace menos sí vale: sirve para juntar
 * las fotos de una fiesta que ya pasó. Con "hoy" de Argentina, como el backend.
 */
function fechaMinima(hoy: string = hoyEnArgentina()): string {
  const dia = Date.parse(`${hoy}T00:00:00Z`) - (DIAS_HASTA_BORRAR - 1) * 86_400_000;
  return new Date(dia).toISOString().slice(0, 10);
}

/**
 * Los eventos que están por delante: crear uno, publicarlo y compartirlo.
 *
 * Los terminados o con la fecha ya pasada viven en Historial. Acá queda sólo lo
 * que todavía hay que preparar o que está pasando, así lo de esta noche no se
 * pierde entre veinte fiestas viejas.
 */
export default function PaginaEventos() {
  const { usuario, esAdmin } = useSesion();
  const alPerderSesion = useAlPerderSesion();
  const [eventos, setEventos] = useState<EventoAdmin[] | null>(null);
  const [errorLista, setErrorLista] = useState<unknown>(null);
  const [reciente, setReciente] = useState<EventoAdmin | null>(null);
  const cuentas = useCuentas(esAdmin);
  // Si se llegó desde Ajustes con #evento-12, esa tarjeta abre "Compartir y
  // pantalla" y se trae a la vista.
  const delAncla = useEventoDelAncla(eventos !== null);

  /** `silencioso`: para poner los números al día sin tapar la lista con un
   *  error si falla. La lista vieja sirve más que un cartel. */
  const cargar = useCallback(
    async (silencioso = false) => {
      // Sin token no se pregunta: useSesion ya está mandando al login.
      if (!tokenDeSesion()) return;
      if (!silencioso) setErrorLista(null);
      try {
        const lista = await admin.eventos({ alcance: "vigentes" });
        setEventos(lista);
        setReciente((r) => (r ? (lista.find((e) => e.id === r.id) ?? r) : r));
      } catch (e) {
        if (alPerderSesion(e)) return;
        if (!silencioso) setErrorLista(e);
      }
    },
    [alPerderSesion],
  );

  useEffect(() => {
    document.title = comun.tituloPestana(t.titulo);
    cargar();
  }, [cargar]);

  // Al volver a esta pestaña (por ejemplo, desde Revisar fotos en otra), los
  // números de fotos por revisar se ponen al día sin recargar.
  useEffect(() => {
    function alVolver() {
      if (document.visibilityState === "visible") cargar(true);
    }
    document.addEventListener("visibilitychange", alVolver);
    return () => document.removeEventListener("visibilitychange", alVolver);
  }, [cargar]);

  const actualizar = useCallback<AlCambiar>((evento) => {
    setEventos((lista) => lista?.map((e) => (e.id === evento.id ? evento : e)) ?? lista);
    setReciente((r) => (r?.id === evento.id ? evento : r));
  }, []);

  async function alCrear(nuevo: EventoAdmin) {
    setReciente(nuevo);
    await cargar(true);
  }

  // El recién creado ya se ve arriba, destacado: no se repite en la lista.
  // Al cerrarlo aparece en su lugar, porque la lista ya lo trae.
  const lista = eventos?.filter((e) => e.id !== reciente?.id) ?? [];

  let contenido: ReactNode;
  if (eventos === null) {
    contenido = errorLista ? (
      <MensajeError error={errorLista} onReintentar={() => cargar()} />
    ) : (
      <Cargando texto={t.cargando} />
    );
  } else if (lista.length === 0) {
    contenido = reciente ? null : <Vacio />;
  } else {
    contenido = (
      <ul className="flex flex-col gap-4">
        {lista.map((e) => (
          <TarjetaEvento
            key={e.id}
            evento={e}
            verOrganizador={esAdmin}
            compartirAbierto={e.id === delAncla}
            onCambio={actualizar}
          />
        ))}
      </ul>
    );
  }

  return (
    <LayoutAdmin
      titulo={t.titulo}
      // Las cuentas ya se piden acá para el selector "Para": se le pasa el
      // número de pendientes al layout para que no las pida otra vez. 0
      // mientras cargan (con undefined, el layout las pediría por su cuenta).
      pendientesCuentas={esAdmin ? (cuentas?.filter((c) => c.estado === "pendiente").length ?? 0) : undefined}
    >
      <FormularioCrear cuentas={cuentas} idPropio={usuario?.id ?? null} onCreado={alCrear} />

      {reciente && (
        <RecienCreado
          key={reciente.id}
          evento={reciente}
          verOrganizador={esAdmin}
          onCambio={actualizar}
          onCerrar={() => setReciente(null)}
        />
      )}

      {contenido}

      {eventos !== null && (
        <div className="mt-8 flex justify-center">
          <Link
            to="/admin/historial"
            className={
              "inline-flex min-h-11 items-center gap-1 rounded-full px-3 text-center text-sm text-acento " +
              "hover:brightness-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-acento"
            }
          >
            {t.alHistorial}
            <ChevronRightIcon aria-hidden className="h-5 w-5 shrink-0" />
          </Link>
        </div>
      )}
    </LayoutAdmin>
  );
}

function mensajeDe(error: unknown, porDefecto: string): string {
  return error instanceof ErrorApi ? error.message : porDefecto;
}

// ── Crear ────────────────────────────────────────────────────

/**
 * Las cuentas, sólo para un admin: el selector "Para" y el número de la
 * pestaña Cuentas. null mientras cargan o para un organizador. Si fallan, una
 * lista vacía: no hay selector y crear para uno mismo sigue andando, que es lo
 * que se hace casi siempre.
 */
function useCuentas(esAdmin: boolean): Cuenta[] | null {
  const [cuentas, setCuentas] = useState<Cuenta[] | null>(null);

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

  return esAdmin ? cuentas : null;
}

/** Las cuentas activas a las que un admin puede crearles un evento, sin la
 *  propia (esa es "Mí"). */
function otrasActivas(cuentas: Cuenta[] | null, idPropio: number | null): Cuenta[] {
  return (cuentas ?? [])
    .filter((c) => c.estado === "activa" && c.id !== idPropio)
    .sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
}

function FormularioCrear({
  cuentas,
  idPropio,
  onCreado,
}: {
  /** null para un organizador: sin selector "Para". */
  cuentas: Cuenta[] | null;
  idPropio: number | null;
  onCreado: (evento: EventoAdmin) => Promise<void>;
}) {
  const alPerderSesion = useAlPerderSesion();
  const idTitulo = useId();
  const [nombre, setNombre] = useState("");
  const [fecha, setFecha] = useState("");
  // "" es quien lo crea. Si no, el id (como texto) de la cuenta elegida.
  const [para, setPara] = useState("");
  const [creando, setCreando] = useState(false);
  const [falla, setFalla] = useState<string | null>(null);
  const otras = otrasActivas(cuentas, idPropio);

  // Si no hay a quién más elegir, el selector sobra.
  const conPara = otras.length > 0;
  const minima = fechaMinima();

  async function crear(evento: FormEvent) {
    evento.preventDefault();
    setCreando(true);
    setFalla(null);
    try {
      const nuevo = await admin.crearEvento({
        nombre: nombre.trim(),
        fecha_evento: fecha,
        ...(para ? { organizador_id: Number(para) } : {}),
      });
      setNombre("");
      setFecha("");
      setPara("");
      await onCreado(nuevo);
    } catch (e) {
      if (alPerderSesion(e)) return;
      setFalla(mensajeDe(e, t.crear.error));
    } finally {
      setCreando(false);
    }
  }

  return (
    <form
      onSubmit={crear}
      aria-labelledby={idTitulo}
      className="mb-6 rounded-3xl border border-borde bg-panel p-5"
    >
      <h2 id={idTitulo} className="mb-3 text-lg font-semibold">
        {t.crear.titulo}
      </h2>

      {/* Apilado en el celular; en fila desde sm. Con el selector "Para" son
          cuatro campos: en el celular la fecha y "Para" comparten fila (el
          formulario no puede tapar la lista), y hasta md van en dos filas,
          porque a 640 px cuatro columnas no entran. */}
      <div
        className={
          "grid gap-3 sm:items-end " +
          (conPara
            ? "grid-cols-2 md:grid-cols-[minmax(0,1fr)_9.5rem_9.5rem_auto]"
            : "sm:grid-cols-[minmax(0,1fr)_10rem_auto]")
        }
      >
        <label className={`min-w-0 text-sm text-tenue ${conPara ? "col-span-2 md:col-span-1" : ""}`}>
          {t.crear.nombre}
          <input
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            required
            maxLength={120}
            autoComplete="off"
            placeholder={t.crear.nombreEjemplo}
            className={CAMPO}
          />
        </label>

        <label className="min-w-0 text-sm text-tenue">
          {t.crear.fecha}
          {/* min: el selector no deja elegir una fecha que el backend
              rechazaría. Si se tipea igual (el año mal puesto), el aviso del
              navegador dice lo mismo que el backend y no el genérico. */}
          <input
            type="date"
            value={fecha}
            min={minima}
            onChange={(e) => {
              setFecha(e.target.value);
              e.currentTarget.setCustomValidity(
                e.target.value && e.target.value < minima ? t.crear.fechaVieja : "",
              );
            }}
            required
            className={CAMPO}
          />
        </label>

        {conPara && (
          <label className="min-w-0 text-sm text-tenue">
            {t.crear.para}
            {/* color-scheme oscuro: sin esto, en Windows la lista desplegada
                sale blanca con letras blancas. */}
            <select
              value={para}
              onChange={(e) => setPara(e.target.value)}
              className={`${CAMPO} [color-scheme:dark]`}
            >
              <option value="" className="bg-black">
                {t.crear.paraMi}
              </option>
              {otras.map((c) => (
                <option key={c.id} value={String(c.id)} className="bg-black">
                  {c.nombre}
                </option>
              ))}
            </select>
          </label>
        )}

        {/* En fila, 48 px como los campos; apilado en el celular, los 56 px
            del botón grande. En fila, px-5 y "Para" en 9.5rem: con el ícono,
            un px-8 le comía 24 px a Nombre y el ejemplo se cortaba ("…y Jua")
            de 768 px para arriba. */}
        <Boton
          type="submit"
          cargando={creando}
          icono={PlusIcon}
          className={`sm:min-h-12 sm:px-5 ${conPara ? "col-span-2 md:col-span-1" : ""}`}
        >
          {t.crear.boton}
        </Boton>
      </div>

      {falla && (
        <p role="alert" className="mt-3 text-sm text-rojo">
          {falla}
        </p>
      )}
    </form>
  );
}

// ── Lista ────────────────────────────────────────────────────

function Vacio() {
  return (
    <div className="rounded-3xl border border-borde bg-panel px-5 py-10 text-center">
      <CalendarDaysIcon aria-hidden className="mx-auto mb-3 h-12 w-12 text-tenue" />
      <p className="text-lg font-semibold">{t.vacio.titulo}</p>
      <p className="mx-auto mt-2 max-w-md text-base leading-snug text-tenue">{t.vacio.texto}</p>
    </div>
  );
}

/**
 * Liviana a propósito: el nombre, la fecha, en qué está y lo próximo que hay
 * que hacer. Compartir y la pantalla se usan una vez por evento, así que van
 * plegados.
 */
function TarjetaEvento({
  evento,
  verOrganizador,
  compartirAbierto,
  onCambio,
}: {
  evento: EventoAdmin;
  verOrganizador: boolean;
  /** Llegó con #evento-{id} desde Ajustes: "Compartir y pantalla" abierto. */
  compartirAbierto: boolean;
  onCambio: AlCambiar;
}) {
  // Un evento abierto el día en que se borran sus fotos (fecha + 30) sigue
  // acá hasta que la limpieza lo cierre, pero ya no hay nada que revisar: el
  // backend puede borrarlas en cualquier momento. Mismo corte que Historial.
  const borradas = sinArchivos(evento);
  const hayPorRevisar = evento.pendientes > 0 && !borradas;

  return (
    // scroll-mt: al traerla a la vista por el ancla, que no quede debajo de la
    // barra fija de arriba.
    <li id={anclaDelEvento(evento.id)} className="scroll-mt-24 rounded-3xl border border-borde bg-panel p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="break-words text-lg font-semibold leading-snug">{evento.nombre}</h2>
          <Datos evento={evento} verOrganizador={verOrganizador} />
        </div>
        <div className="mt-0.5 shrink-0">
          <ChipEstado estado={evento.estado} />
        </div>
      </div>

      {evento.estado === "borrador" ? (
        <Publicar evento={evento} texto={t.tarjeta.publicar} onCambio={onCambio} />
      ) : (
        hayPorRevisar && (
          <p className="mt-3 text-sm font-medium text-acento">{t.tarjeta.porRevisar(evento.pendientes)}</p>
        )
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        {!borradas && (
          <Link
            to={`/admin/eventos/${evento.id}/revisar`}
            className={claseBotonChico(hayPorRevisar ? "azul" : "vidrio")}
          >
            <PhotoIcon aria-hidden className={claseIconoChico} />
            {t.tarjeta.revisarFotos(evento.pendientes)}
          </Link>
        )}
        <Link to={`/admin/eventos/${evento.id}/ajustes`} className={claseBotonChico("vidrio")}>
          <Cog6ToothIcon aria-hidden className={claseIconoChico} />
          {t.tarjeta.ajustes}
        </Link>
      </div>

      <CompartirEvento evento={evento} abiertoAlInicio={compartirAbierto} />
    </li>
  );
}

/** "sábado 26 de septiembre" y, en otra línea, "Organiza Bruno". El dueño,
 *  sólo para un admin: un organizador ve sólo los suyos y ya sabe de quién
 *  son. En su línea y no después de un "·": igual que en Historial y Ajustes. */
function Datos({ evento, verOrganizador }: { evento: EventoAdmin; verOrganizador: boolean }) {
  return (
    <>
      <p className="mt-0.5 text-sm text-tenue">{fechaLarga(evento.fecha_evento)}</p>
      {verOrganizador && (
        <p className="break-words text-sm text-tenue">{comun.organiza(evento.organizador_nombre)}</p>
      )}
    </>
  );
}

/**
 * El botón grande de publicar, con el aviso de por qué hace falta. Mientras el
 * evento está sin publicar el QR lleva a un "no existe": es el error más fácil
 * de cometer y el que más se nota, con las mesas ya llenas de QR impresos.
 */
function Publicar({ evento, texto, onCambio }: { evento: EventoAdmin; texto: string; onCambio: AlCambiar }) {
  const alPerderSesion = useAlPerderSesion();
  const [publicando, setPublicando] = useState(false);
  const [falla, setFalla] = useState<string | null>(null);

  async function publicar() {
    setPublicando(true);
    setFalla(null);
    try {
      onCambio(await admin.cambiarEstadoEvento(evento.id, "activo"));
    } catch (e) {
      if (alPerderSesion(e)) return;
      setFalla(mensajeDe(e, t.publicar.error));
    } finally {
      setPublicando(false);
    }
  }

  return (
    <div className="mt-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="flex items-start gap-2 text-sm leading-5 text-naranja">
          <ExclamationTriangleIcon aria-hidden className="h-5 w-5 shrink-0" />
          {t.tarjeta.avisoSinPublicar}
        </p>
        <Boton
          onClick={publicar}
          cargando={publicando}
          icono={PaperAirplaneIcon}
          className="sm:w-auto sm:shrink-0 sm:px-10"
        >
          {texto}
        </Boton>
      </div>
      {falla && (
        <p role="alert" className="mt-2 text-sm text-rojo">
          {falla}
        </p>
      )}
    </div>
  );
}

// ── Recién creado ────────────────────────────────────────────

/**
 * Lo que se necesita de verdad al crear un evento: publicarlo, el QR para
 * imprimir y cómo conectar la pantalla. Compartir arranca abierto: es lo que
 * se viene a buscar después de crear.
 */
function RecienCreado({
  evento,
  verOrganizador,
  onCambio,
  onCerrar,
}: {
  evento: EventoAdmin;
  verOrganizador: boolean;
  onCambio: AlCambiar;
  onCerrar: () => void;
}) {
  const idTitulo = useId();
  const titulo = useRef<HTMLHeadingElement>(null);

  // El foco va al evento nuevo: el navegador lo trae a la vista (en el celular
  // queda debajo del formulario) y un lector de pantalla lo anuncia.
  useEffect(() => {
    titulo.current?.focus();
  }, []);

  return (
    <section aria-labelledby={idTitulo} className="mb-6 rounded-3xl border border-acento/70 bg-panel p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-acento">{t.recienCreado.etiqueta}</p>
          <h2
            id={idTitulo}
            ref={titulo}
            tabIndex={-1}
            className="break-words text-xl font-semibold leading-snug outline-none"
          >
            {evento.nombre}
          </h2>
          <Datos evento={evento} verOrganizador={verOrganizador} />
          <div className="mt-2">
            <ChipEstado estado={evento.estado} />
          </div>
        </div>
        <BotonChico onClick={onCerrar} icono={XMarkIcon} className="shrink-0">
          {t.recienCreado.cerrar}
        </BotonChico>
      </div>

      {evento.estado === "borrador" ? (
        <Publicar evento={evento} texto={t.recienCreado.publicarAhora} onCambio={onCambio} />
      ) : (
        <p role="status" className="mt-4 flex items-start gap-2 text-sm font-medium leading-5 text-verde">
          <CheckCircleIcon aria-hidden className="h-5 w-5 shrink-0" />
          {t.recienCreado.publicado}
        </p>
      )}

      <CompartirEvento evento={evento} abiertoAlInicio qrGrande />
    </section>
  );
}
