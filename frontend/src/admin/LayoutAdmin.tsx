import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import {
  CalendarDaysIcon as EventosReposo,
  ClockIcon as HistorialReposo,
  UsersIcon as CuentasReposo,
} from "@heroicons/react/24/outline";
import {
  CalendarDaysIcon as EventosActivo,
  ClockIcon as HistorialActivo,
  UsersIcon as CuentasActivo,
} from "@heroicons/react/24/solid";
import { ArrowRightStartOnRectangleIcon, ChevronLeftIcon } from "@heroicons/react/20/solid";

import { ErrorApi, admin } from "../api/client";
import Avatar from "../comp/Avatar";
import { claseBotonChico } from "../comp/BotonChico";
import { claseIconoChico, type Icono } from "../comp/icono";
import Marca from "../comp/Marca";
import { comun } from "./textos/comun";
import { cuenta as textosCuenta } from "./textos/cuenta";
import { olvidarSesion, revalidarSesion, useSesion } from "./useSesion";

interface Props {
  /** Encabezado de la página, debajo de la barra. */
  titulo?: ReactNode;
  /** Botones a la derecha del título (en el celular bajan si no entran). */
  acciones?: ReactNode;
  /** Link chico arriba del título, para volver a la lista: "‹ Eventos". */
  volver?: { a: string; texto: string };
  /**
   * Cuántas cuentas esperan que las habiliten. Si la página ya las tiene (la
   * de Cuentas), las pasa acá y el número de la pestaña se actualiza en el
   * acto al habilitar una. Si no se pasa y quien mira es admin, el layout las
   * pregunta una vez.
   */
  pendientesCuentas?: number;
  children: ReactNode;
}

interface Seccion {
  a: string;
  texto: string;
  /** Como en la barra de iOS: de trazo en reposo, relleno en la activa. */
  icono: { reposo: Icono; activo: Icono };
  soloAdmin?: boolean;
}

const SECCIONES: Seccion[] = [
  { a: "/admin", texto: comun.nav.eventos, icono: { reposo: EventosReposo, activo: EventosActivo } },
  {
    a: "/admin/historial",
    texto: comun.nav.historial,
    icono: { reposo: HistorialReposo, activo: HistorialActivo },
  },
  {
    a: "/admin/cuentas",
    texto: comun.nav.cuentas,
    icono: { reposo: CuentasReposo, activo: CuentasActivo },
    soloAdmin: true,
  },
];

/**
 * El marco de las páginas del panel, menos Revisar fotos, que es pantalla
 * completa y no puede perder ni un píxel de foto.
 *
 * Arriba, una barra de vidrio fija con la marca, las pestañas, quién está y
 * Salir. En el celular las pestañas bajan a una barra inferior como la de iOS:
 * arriba no entran al lado del nombre sin achicarse hasta ilegibles, y abajo
 * quedan donde llega el pulgar.
 */
export default function LayoutAdmin({ titulo, acciones, volver, pendientesCuentas, children }: Props) {
  const navegar = useNavigate();
  const { usuario, esAdmin } = useSesion();
  const pendientes = usePendientes(esAdmin, pendientesCuentas);

  const secciones = SECCIONES.filter((s) => !s.soloAdmin || esAdmin);

  function salir() {
    olvidarSesion();
    navegar("/admin/login");
  }

  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-40 border-b border-borde bg-barra pt-[env(safe-area-inset-top)] backdrop-blur-2xl backdrop-saturate-150">
        <div className="mx-auto flex h-16 max-w-5xl items-center gap-3 px-4 sm:px-6 md:gap-6">
          {/* La marca: el símbolo y el nombre (comp/Marca). min-h-11: también
              es un objetivo táctil, y lleva a Eventos. En un celular de menos
              de 360 px va sólo el símbolo; el nombre queda para el lector de
              pantalla y le da nombre al link. Ahí el símbolo (32) y el px-1
              suman 40: min-w-11 lo lleva a 44. Sin justify-center, a propósito:
              el -ml-1 con el px-1 deja el símbolo sobre el margen del <main>
              (px-4), y los 4 px de más quedan como zona táctil a su derecha. */}
          <Link
            to="/admin"
            className={
              "-ml-1 inline-flex min-h-11 min-w-11 shrink-0 items-center rounded-xl px-1 " +
              "focus:outline-none focus-visible:ring-2 focus-visible:ring-acento"
            }
          >
            <Marca />
          </Link>

          {/* Pestañas arriba, desde md: control segmentado de iOS. Desde sm no:
              a 640 px la marca, tres pestañas, el nombre y Salir no entran. */}
          <nav aria-label={comun.nav.etiqueta} className="hidden md:block">
            <ul className="flex items-center gap-1 rounded-full bg-hundido p-1">
              {secciones.map((s) => (
                <li key={s.a}>
                  <NavLink
                    to={s.a}
                    end
                    className={({ isActive }) =>
                      "flex min-h-11 items-center gap-2 rounded-full px-4 text-sm font-medium transition " +
                      "focus:outline-none focus-visible:ring-2 focus-visible:ring-acento " +
                      (isActive ? "bg-elegido text-texto shadow-sm shadow-sombra/10" : "text-tenue hover:text-texto")
                    }
                  >
                    {s.texto}
                    {s.soloAdmin && <Contador n={pendientes} />}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>

          <div className="ml-auto flex min-w-0 items-center gap-2 sm:gap-3">
            {/* Quién está, y el camino a Mi cuenta: como la foto de perfil de
                arriba a la derecha en las apps de iOS. En el celular, sólo el
                círculo (el nombre cortado a la mitad no se lee); desde sm,
                también el nombre. Entre md y lg, otra vez sólo el círculo:
                ahí aparecen las pestañas al lado de la marca, y el nombre
                quedaba en "Ana …". 44 px de alto siempre. */}
            {usuario && (
              <NavLink
                to="/admin/cuenta"
                end
                className={({ isActive }) =>
                  "group flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-full p-1.5 transition " +
                  "hover:bg-pulsado focus:outline-none focus-visible:ring-2 focus-visible:ring-acento " +
                  "sm:min-w-0 sm:justify-start sm:py-1.5 sm:pl-1.5 sm:pr-3 " +
                  "md:min-w-11 md:justify-center md:p-1.5 " +
                  "lg:min-w-0 lg:justify-start lg:py-1.5 lg:pl-1.5 lg:pr-3 " +
                  (isActive ? "text-texto" : "text-tenue hover:text-texto")
                }
              >
                {({ isActive }) => (
                  <>
                    <Avatar
                      nombre={usuario.nombre}
                      url={usuario.avatar_url}
                      tamano="barra"
                      // En Mi cuenta, el aro azul dice "estás acá", como la
                      // pestaña elegida.
                      className={isActive ? "ring-2 ring-acento" : ""}
                    />
                    <span className="sr-only min-w-0 text-sm sm:not-sr-only sm:truncate md:sr-only lg:not-sr-only">
                      {usuario.nombre}
                    </span>
                    <span className="sr-only">{textosCuenta.enLaBarra}</span>
                  </>
                )}
              </NavLink>
            )}
            <button type="button" onClick={salir} className={`shrink-0 ${claseBotonChico("vidrio")}`}>
              <ArrowRightStartOnRectangleIcon aria-hidden className={claseIconoChico} />
              {comun.salir}
            </button>
          </div>
        </div>
      </header>

      {/* pb grande en el celular: el contenido no puede quedar debajo de la
          barra de pestañas de abajo. */}
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 pb-32 pt-6 sm:px-6 sm:pt-8 md:pb-12">
        {volver && (
          <Link
            to={volver.a}
            className="-ml-1.5 mb-2 inline-flex min-h-11 items-center gap-0.5 rounded-full pr-1 text-base text-acento-tinta hover:underline"
          >
            <ChevronLeftIcon aria-hidden className="h-6 w-6 shrink-0" />
            {volver.texto}
          </Link>
        )}
        {(titulo || acciones) && (
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
            {titulo && <h1 className="min-w-0 break-words text-2xl font-semibold sm:text-3xl">{titulo}</h1>}
            {acciones && <div className="flex flex-wrap items-center gap-2">{acciones}</div>}
          </div>
        )}
        {children}
      </main>

      {/* Pestañas abajo, en el celular: la barra de pestañas de iOS. */}
      <nav
        aria-label={comun.nav.etiqueta}
        className="fixed inset-x-0 bottom-0 z-40 border-t border-borde bg-barra pb-[env(safe-area-inset-bottom)] backdrop-blur-2xl backdrop-saturate-150 md:hidden"
      >
        <ul className="flex">
          {secciones.map((s) => (
            <li key={s.a} className="flex-1">
              <NavLink
                to={s.a}
                end
                className={({ isActive }) =>
                  "flex min-h-14 flex-col items-center justify-center gap-0.5 pt-1 text-[11px] font-medium " +
                  "focus:outline-none focus-visible:bg-pulsado " +
                  // La etiqueta es de 11 px: va en `-tinta`. El ícono hereda el
                  // mismo color, así la pestaña no queda de dos azules.
                  (isActive ? "text-acento-tinta" : "text-tenue")
                }
              >
                {({ isActive }) => {
                  const IconoPestana = isActive ? s.icono.activo : s.icono.reposo;
                  return (
                    <>
                      <span className="relative">
                        <IconoPestana aria-hidden className="h-6 w-6" />
                        {s.soloAdmin && (
                          <span className="absolute -right-3 -top-1.5">
                            <Contador n={pendientes} />
                          </span>
                        )}
                      </span>
                      {s.texto}
                    </>
                  );
                }}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}

/** El numerito rojo de iOS. Sin pendientes no se muestra. */
function Contador({ n }: { n: number }) {
  if (n <= 0) return null;
  return (
    <span
      aria-label={comun.pendientesCuentas(n)}
      className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-rojo px-1.5 text-xs font-semibold tabular-nums text-luz"
    >
      {n}
    </span>
  );
}

/** Si la página no pasa el número, un admin lo pregunta una vez por montaje.
 *  Si falla, no hay número: es un aviso, no algo que tenga que interrumpir.
 *  Un 403 quiere decir que esta cuenta ya no es admin: se vuelve a preguntar
 *  quién es, y la pestaña Cuentas desaparece. */
function usePendientes(esAdmin: boolean, dado: number | undefined): number {
  const [contadas, setContadas] = useState(0);

  useEffect(() => {
    if (!esAdmin || dado !== undefined) return;
    let vivo = true;
    admin
      .cuentas()
      .then((lista) => {
        if (vivo) setContadas(lista.filter((c) => c.estado === "pendiente").length);
      })
      .catch((e: unknown) => {
        if (vivo && e instanceof ErrorApi && e.esSinPermiso) revalidarSesion();
      });
    return () => {
      vivo = false;
    };
  }, [esAdmin, dado]);

  if (!esAdmin) return 0;
  return dado ?? contadas;
}
