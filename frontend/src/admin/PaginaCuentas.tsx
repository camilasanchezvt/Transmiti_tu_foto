import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import {
  ArrowPathIcon,
  CheckBadgeIcon,
  CheckCircleIcon,
  CheckIcon,
  ChevronRightIcon,
  ClipboardDocumentIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  LockClosedIcon,
  NoSymbolIcon,
  ShieldCheckIcon,
  ShieldExclamationIcon,
} from "@heroicons/react/20/solid";
import { NoSymbolIcon as QuitarAccesoGrande } from "@heroicons/react/24/outline";
import {
  ShieldCheckIcon as DarAdminGrande,
  ShieldExclamationIcon as QuitarAdminGrande,
} from "@heroicons/react/24/solid";

import { ErrorApi, admin, haySesion } from "../api/client";
import type { CambioCuenta, Cuenta } from "../api/tipos";
import BotonChico, { claseBotonChico } from "../comp/BotonChico";
import Cargando from "../comp/Cargando";
import { ChipRol } from "../comp/ChipEstado";
import Confirmar from "../comp/Confirmar";
import { claseIconoChico, claseIconoChip, type Icono } from "../comp/icono";
import MensajeError from "../comp/MensajeError";
import { fechaLarga } from "../lib/fecha";
import LayoutAdmin from "./LayoutAdmin";
import { comun } from "./textos/comun";
import { textosCuentas as t, type AccionConfirmada, type AccionCuenta } from "./textos/cuentas";
import { useCopiar } from "./useCopiar";
import { revalidarSesion, useAlPerderSesion, useSesion } from "./useSesion";

/** Qué le manda cada botón a PATCH /api/admin/cuentas/{id}. */
const CAMBIOS: Record<AccionCuenta, CambioCuenta> = {
  // Habilitar manda el rol aunque la cuenta ya nazca organizador: el botón
  // hace lo que dice aunque alguien la haya tocado desde otra pestaña.
  habilitar: { estado: "activa", rol: "organizador" },
  habilitarAdmin: { estado: "activa", rol: "admin" },
  rechazar: { estado: "baja" },
  hacerAdmin: { rol: "admin" },
  quitarAdmin: { rol: "organizador" },
  darBaja: { estado: "baja" },
  reactivar: { estado: "activa" },
};

/** Habilitar y reactivar van directo: dan acceso, no lo quitan. */
function pideConfirmacion(accion: AccionCuenta): accion is AccionConfirmada {
  return accion !== "habilitar" && accion !== "reactivar";
}

// El mismo orden que usa el backend. Se repite acá porque después de cada
// cambio la tarjeta se muda de sección sin volver a pedir la lista.
const porNombre = (a: Cuenta, b: Cuenta) =>
  a.nombre.localeCompare(b.nombre, "es", { sensitivity: "base" }) || a.id - b.id;
const masNuevaPrimero = (a: Cuenta, b: Cuenta) =>
  Date.parse(b.creado_en) - Date.parse(a.creado_en) || b.id - a.id;

/**
 * Cuentas: sólo para admins y superadmins.
 *
 * Nadie crea cuentas desde acá. Las personas se registran solas y esperan; un
 * admin las habilita, las rechaza, las hace admin o las da de baja. Nada se
 * borra: una cuenta de baja no entra, pero sus eventos quedan y se puede
 * reactivar.
 *
 * Cada tarjeta muestra sólo lo que el backend va a aceptar (la matriz está en
 * `accionesPermitidas`). Sobre una cuenta que no se puede tocar, en vez de
 * botones que terminan en "No tenés permiso", una línea dice por qué.
 *
 * Arriba lo que espera respuesta (las pendientes), después las activas, y las
 * de baja plegadas al final: se miran poco.
 */
export default function PaginaCuentas() {
  const navegar = useNavigate();
  const alPerderSesion = useAlPerderSesion();
  const {
    usuario,
    esAdmin,
    esSuperadmin,
    error: errorSesion,
    reintentar: reintentarSesion,
  } = useSesion();

  const [cuentas, setCuentas] = useState<Cuenta[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  /** Las cuentas con un cambio en camino, y cuál. */
  const [ocupadas, setOcupadas] = useState<Record<number, AccionCuenta>>({});
  /** El último error de cada tarjeta, tal cual lo mandó el backend. */
  const [fallas, setFallas] = useState<Record<number, string>>({});
  const [preguntando, setPreguntando] = useState<{ cuenta: Cuenta; accion: AccionConfirmada } | null>(
    null,
  );
  const [aviso, setAviso] = useState<{ texto: string; vez: number } | null>(null);

  // Cuenta los cambios hechos desde esta página. Una recarga de fondo que
  // salió antes de un cambio y llega después traería la lista vieja: si el
  // número se movió mientras esperaba, se descarta.
  const cambios = useRef(0);

  // Si /yo falló (sin red) y después la lista llega bien, la API volvió: se
  // pregunta de nuevo quién es. Por ref para no rehacer `cargar` en cada render.
  const sesionFallida = useRef(errorSesion);
  sesionFallida.current = errorSesion;

  /** `callado`: la recarga al volver a la pestaña. Si falla, queda lo que había. */
  const cargar = useCallback(
    async (callado = false) => {
      const antes = cambios.current;
      try {
        const lista = await admin.cuentas();
        if (callado && cambios.current !== antes) return;
        setCuentas(lista);
        setError(null);
        if (sesionFallida.current) reintentarSesion();
      } catch (e) {
        if (alPerderSesion(e)) return;
        // Un organizador que llegó por un link guardado, o un admin al que le
        // quitaron el rol con el panel abierto: a sus eventos. Se vuelve a
        // preguntar quién es, así la pestaña Cuentas no queda rebotando.
        if (e instanceof ErrorApi && e.esSinPermiso) {
          revalidarSesion();
          return navegar("/admin", { replace: true });
        }
        if (!callado) setError(e);
      }
    },
    [navegar, alPerderSesion, reintentarSesion],
  );

  useEffect(() => {
    document.title = comun.tituloPestana(t.titulo);
  }, []);

  useEffect(() => {
    // Sin token, useSesion ya manda al login.
    if (!haySesion()) return;
    void cargar();

    // Lo típico: alguien avisa por WhatsApp "ya me registré" y el admin vuelve
    // a esta pestaña. Que la cuenta ya esté ahí, sin tener que recargar.
    const alVolver = () => {
      if (document.visibilityState === "visible") void cargar(true);
    };
    document.addEventListener("visibilitychange", alVolver);
    return () => document.removeEventListener("visibilitychange", alVolver);
  }, [cargar]);

  // El aviso de abajo se va solo.
  useEffect(() => {
    if (!aviso) return;
    const id = window.setTimeout(() => setAviso(null), 4000);
    return () => window.clearTimeout(id);
  }, [aviso]);

  const grupos = useMemo(() => {
    const lista = cuentas ?? [];
    return {
      pendientes: lista.filter((c) => c.estado === "pendiente").sort(masNuevaPrimero),
      activas: lista.filter((c) => c.estado === "activa").sort(porNombre),
      bajas: lista.filter((c) => c.estado === "baja").sort(porNombre),
    };
  }, [cuentas]);

  async function aplicar(cuenta: Cuenta, accion: AccionCuenta) {
    cambios.current += 1;
    setOcupadas((o) => ({ ...o, [cuenta.id]: accion }));
    setFallas((f) => sinClave(f, cuenta.id));
    try {
      const nueva = await admin.cambiarCuenta(cuenta.id, CAMBIOS[accion]);
      cambios.current += 1;
      setCuentas((lista) => lista && lista.map((c) => (c.id === nueva.id ? nueva : c)));
      setAviso({ texto: t.hecho[accion](nueva.nombre), vez: Date.now() });
    } catch (e) {
      if (alPerderSesion(e)) return;
      // Los botones son los que el backend acepta: un 403 acá es que cambió el
      // rol de quien mira. Se pregunta de nuevo y las tarjetas se redibujan.
      if (e instanceof ErrorApi && e.esSinPermiso) revalidarSesion();
      setFallas((f) => ({
        ...f,
        [cuenta.id]: e instanceof ErrorApi ? e.message : comun.errores.generico,
      }));
    } finally {
      setOcupadas((o) => sinClave(o, cuenta.id));
      // Si vino del diálogo, se cierra; si falló, el error queda en la tarjeta.
      setPreguntando((p) => (p?.cuenta.id === cuenta.id ? null : p));
    }
  }

  function pedir(cuenta: Cuenta, accion: AccionCuenta) {
    if (pideConfirmacion(accion)) setPreguntando({ cuenta, accion });
    else void aplicar(cuenta, accion);
  }

  // Un organizador no tiene nada que hacer acá.
  if (usuario && !esAdmin) return <Navigate to="/admin" replace />;

  // Hasta saber quién mira no se muestra la lista: sin eso, la tarjeta propia
  // tendría botones de rol y de estado que el backend después rechaza.
  const listo = cuentas !== null && usuario !== null;
  const falla = error ?? (usuario ? null : errorSesion);

  let contenido: ReactNode;
  if (!listo) {
    contenido = falla ? (
      <MensajeError
        error={falla}
        onReintentar={() => {
          reintentarSesion();
          void cargar();
        }}
      />
    ) : (
      <Cargando texto={t.cargando} />
    );
  } else {
    const tarjeta = (cuenta: Cuenta) => (
      <TarjetaCuenta
        key={cuenta.id}
        cuenta={cuenta}
        propia={cuenta.id === usuario?.id}
        actorEsSuperadmin={esSuperadmin}
        ocupada={ocupadas[cuenta.id] ?? null}
        falla={fallas[cuenta.id]}
        onAccion={(accion) => pedir(cuenta, accion)}
      />
    );

    contenido = (
      <div className="flex flex-col gap-10">
        <section aria-labelledby="cuentas-pendientes">
          <Encabezado id="cuentas-pendientes" titulo={t.pendientes.titulo}>
            {grupos.pendientes.length > 0 && (
              <span className="inline-flex h-6 min-w-6 items-center justify-center rounded-full bg-naranja/15 px-2 text-sm font-semibold tabular-nums text-naranja">
                {grupos.pendientes.length}
              </span>
            )}
          </Encabezado>
          {grupos.pendientes.length === 0 && (
            <p className="mt-2 flex items-center gap-2 text-base text-white">
              <CheckCircleIcon aria-hidden className="h-5 w-5 shrink-0 text-verde" />
              {t.pendientes.vacio}
            </p>
          )}
          <p className="mt-1 text-sm leading-snug text-tenue">{t.pendientes.explicacion}</p>
          {grupos.pendientes.length > 0 && (
            <ul className="mt-4 flex flex-col gap-3">{grupos.pendientes.map(tarjeta)}</ul>
          )}
        </section>

        {grupos.activas.length > 0 && (
          <section aria-labelledby="cuentas-activas">
            <Encabezado id="cuentas-activas" titulo={t.activas.titulo}>
              <span className="text-base font-normal tabular-nums text-tenue">
                {grupos.activas.length}
              </span>
            </Encabezado>
            <ul className="mt-4 flex flex-col gap-3">{grupos.activas.map(tarjeta)}</ul>
          </section>
        )}

        {grupos.bajas.length > 0 && (
          // Plegada por defecto: se consulta poco y no tiene que competir con
          // las que esperan respuesta.
          <details className="group">
            <summary
              className={
                "-mx-1 flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-xl px-1 " +
                "text-xl font-semibold focus:outline-none focus-visible:ring-2 focus-visible:ring-acento " +
                "[&::-webkit-details-marker]:hidden"
              }
            >
              <ChevronRightIcon
                aria-hidden
                className="h-5 w-5 shrink-0 text-tenue transition-transform group-open:rotate-90"
              />
              {t.bajas.titulo}
              <span className="text-base font-normal tabular-nums text-tenue">
                {grupos.bajas.length}
              </span>
            </summary>
            <ul className="mt-4 flex flex-col gap-3">{grupos.bajas.map(tarjeta)}</ul>
          </details>
        )}
      </div>
    );
  }

  const confirmacion = preguntando ? t.confirmaciones[preguntando.accion] : null;

  return (
    <LayoutAdmin
      titulo={t.titulo}
      acciones={<CopiarLinkRegistro />}
      // 0 mientras carga, y no undefined: con undefined el layout pediría la
      // misma lista por su cuenta.
      pendientesCuentas={grupos.pendientes.length}
    >
      {contenido}

      {preguntando && confirmacion && (
        <Confirmar
          abierto
          titulo={confirmacion.titulo(preguntando.cuenta.nombre)}
          mensaje={confirmacion.mensaje}
          textoConfirmar={confirmacion.confirmar}
          peligro={preguntando.accion === "rechazar" || preguntando.accion === "darBaja"}
          iconoConfirmar={ICONO_GRANDE[preguntando.accion]}
          cargando={ocupadas[preguntando.cuenta.id] !== undefined}
          onConfirmar={() => void aplicar(preguntando.cuenta, preguntando.accion)}
          onCancelar={() => setPreguntando(null)}
        />
      )}

      {/* Aviso de lo que se acaba de hacer. En el celular va por encima de la
          barra de pestañas de abajo. */}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-[calc(4.5rem+env(safe-area-inset-bottom))] z-30 flex justify-center px-4 md:bottom-8"
      >
        {aviso && (
          <p
            key={aviso.vez}
            className="vidrio-oscuro flex items-center gap-2 rounded-full px-5 py-3 text-sm font-medium text-white"
          >
            <CheckCircleIcon aria-hidden className="h-5 w-5 shrink-0 text-verde" />
            <span className="min-w-0">{aviso.texto}</span>
          </p>
        )}
      </div>
    </LayoutAdmin>
  );
}

function sinClave<T>(registro: Record<number, T>, clave: number): Record<number, T> {
  if (!(clave in registro)) return registro;
  const copia = { ...registro };
  delete copia[clave];
  return copia;
}

function Encabezado({ id, titulo, children }: { id: string; titulo: string; children?: ReactNode }) {
  return (
    <h2 id={id} className="flex items-center gap-2 text-xl font-semibold">
      {titulo}
      {children}
    </h2>
  );
}

/**
 * Qué puede hacer quien mira con esta cuenta: la misma matriz que
 * `_exigir_permiso` en el backend. `motivo` es la línea que explica por qué no
 * hay botones; null cuando los hay.
 *
 * - La propia: ni rol ni estado.
 * - Una superadmin: nadie la cambia desde el panel.
 * - Un admin: sólo lo cambia una superadmin.
 * - Un organizador, en cualquier estado: admin y superadmin.
 */
function accionesPermitidas(
  cuenta: Cuenta,
  propia: boolean,
  actorEsSuperadmin: boolean,
): { acciones: AccionCuenta[]; motivo: string | null } {
  if (propia) return { acciones: [], motivo: actorEsSuperadmin ? t.propiaSuperadmin : t.propia };
  if (cuenta.rol === "superadmin") return { acciones: [], motivo: t.intocableSuperadmin };
  if (cuenta.rol === "admin" && !actorEsSuperadmin) return { acciones: [], motivo: t.soloSuperadmin };

  if (cuenta.estado === "pendiente") return { acciones: ["habilitar", "habilitarAdmin", "rechazar"], motivo: null };
  if (cuenta.estado === "activa") {
    return { acciones: [cuenta.rol === "admin" ? "quitarAdmin" : "hacerAdmin", "darBaja"], motivo: null };
  }
  return { acciones: ["reactivar"], motivo: null };
}

/** El que da acceso de entrada va en azul; los que lo quitan, en rojo. */
const VARIANTE: Record<AccionCuenta, "vidrio" | "azul" | "peligro"> = {
  habilitar: "azul",
  habilitarAdmin: "vidrio",
  rechazar: "peligro",
  hacerAdmin: "vidrio",
  quitarAdmin: "vidrio",
  darBaja: "peligro",
  reactivar: "vidrio",
};

/** Del juego mini (20/solid), como todo botón chico. Dar acceso lleva un
 *  sello; quitarlo, el círculo tachado; el rol de admin, el escudo. */
const ICONO: Record<AccionCuenta, Icono> = {
  habilitar: CheckBadgeIcon,
  habilitarAdmin: ShieldCheckIcon,
  rechazar: NoSymbolIcon,
  hacerAdmin: ShieldCheckIcon,
  quitarAdmin: ShieldExclamationIcon,
  darBaja: NoSymbolIcon,
  reactivar: ArrowPathIcon,
};

/** Los mismos, en grande, para el botón de confirmar del diálogo: 24/outline
 *  los que quitan acceso (van en rojo, con `peligro`), 24/solid los demás. */
const ICONO_GRANDE: Record<AccionConfirmada, Icono> = {
  habilitarAdmin: DarAdminGrande,
  rechazar: QuitarAccesoGrande,
  hacerAdmin: DarAdminGrande,
  quitarAdmin: QuitarAdminGrande,
  darBaja: QuitarAccesoGrande,
};

interface PropsTarjeta {
  cuenta: Cuenta;
  /** La cuenta de quien mira: no se puede cambiar su propio rol ni su estado. */
  propia: boolean;
  /** Quien mira es superadmin: además de los organizadores, gestiona a los admins. */
  actorEsSuperadmin: boolean;
  /** El cambio en camino sobre esta cuenta, si hay uno. */
  ocupada: AccionCuenta | null;
  falla?: string;
  onAccion: (accion: AccionCuenta) => void;
}

/**
 * Una cuenta, como tarjeta: nombre y email arriba, qué hizo, y las acciones
 * debajo. Nada de tablas: en un celular de 375 px una tabla de cuentas
 * desborda o se vuelve ilegible.
 */
function TarjetaCuenta({ cuenta, propia, actorEsSuperadmin, ocupada, falla, onAccion }: PropsTarjeta) {
  const pendiente = cuenta.estado === "pendiente";

  const detalle = pendiente
    ? t.pendientes.pidio(fechaLarga(cuenta.creado_en))
    : cuenta.eventos > 0 && cuenta.ultimo_evento
      ? `${t.eventos(cuenta.eventos)} · ${t.ultimoEvento(fechaLarga(cuenta.ultimo_evento))}`
      : t.sinEventos;

  // Los botones crecen para llenar la fila en el celular (grow) y vuelven a
  // su ancho desde sm. Sin nowrap, "Habilitar como admin" se partiría en dos
  // renglones en vez de bajar entero a la fila de abajo.
  const ancho = "grow whitespace-nowrap sm:grow-0";

  const permitidas = accionesPermitidas(cuenta, propia, actorEsSuperadmin);

  const boton = (accion: AccionCuenta) => (
    <BotonChico
      key={accion}
      variante={VARIANTE[accion]}
      icono={ICONO[accion]}
      className={ancho}
      cargando={ocupada === accion}
      disabled={ocupada !== null}
      onClick={() => onAccion(accion)}
    >
      {t.acciones[accion]}
    </BotonChico>
  );

  const acciones: ReactNode[] = [];
  // Sin eventos no hay historial que ver: el link llevaría a una lista vacía.
  if (!pendiente && cuenta.eventos > 0) {
    acciones.push(
      <Link
        key="historial"
        to={`/admin/historial?organizador=${cuenta.id}`}
        className={`${claseBotonChico("vidrio")} ${ancho}`}
      >
        <ClockIcon aria-hidden className={claseIconoChico} />
        {t.verHistorial}
      </Link>,
    );
  }
  acciones.push(...permitidas.acciones.map(boton));

  return (
    <li
      className={
        "rounded-3xl border bg-panel p-5 " + (pendiente ? "border-naranja/50" : "border-borde")
      }
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <h3 className="min-w-0 break-words text-lg font-semibold leading-snug">{cuenta.nombre}</h3>
        {propia && (
          <span className="inline-flex h-fit shrink-0 items-center whitespace-nowrap rounded-full bg-white/15 px-2.5 py-0.5 text-xs font-medium text-white">
            {t.vos}
          </span>
        )}
        {/* Una pendiente no lleva chip: la sección y el borde naranja ya lo
            dicen, y su rol todavía no significa nada. */}
        {!pendiente && <ChipRol rol={cuenta.rol} />}
      </div>
      <p className="break-words text-sm text-tenue">{cuenta.email}</p>
      <p className="mt-1 text-sm text-tenue">{detalle}</p>

      {acciones.length > 0 && <div className="mt-4 flex flex-wrap gap-2">{acciones}</div>}

      {/* El candado dice "esto no se toca" antes de leer el motivo. Los
          íconos de 16 px bajan 2 px para quedar a la altura del primer
          renglón aunque el texto se parta en dos. */}
      {permitidas.motivo && (
        <p className="mt-3 flex items-start gap-1.5 text-sm leading-snug text-tenue">
          <LockClosedIcon aria-hidden className={`mt-0.5 ${claseIconoChip}`} />
          <span className="min-w-0">{permitidas.motivo}</span>
        </p>
      )}

      {falla && (
        <p role="alert" className="mt-3 flex items-start gap-1.5 text-sm leading-snug text-rojo">
          <ExclamationTriangleIcon aria-hidden className={`mt-0.5 ${claseIconoChip}`} />
          <span className="min-w-0 break-words">{falla}</span>
        </p>
      )}
    </li>
  );
}

/**
 * Para invitar a alguien: el admin le pasa este link por WhatsApp o por mail y
 * la persona crea su cuenta sola. El admin nunca conoce su contraseña.
 */
function CopiarLinkRegistro() {
  const [copiado, copiar] = useCopiar();
  const link = `${window.location.origin}/admin/registro`;

  return (
    // Sin permiso de portapapeles (o sin HTTPS), useCopiar lo muestra en un
    // cuadro para copiarlo a mano.
    <BotonChico
      icono={copiado ? CheckIcon : ClipboardDocumentIcon}
      onClick={() => copiar(link, t.pendientes.etiquetaLink)}
      aria-live="polite"
    >
      {copiado ? comun.verbos.copiado : t.pendientes.copiarLink}
    </BotonChico>
  );
}
