import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";

import { ErrorApi, admin } from "../api/client";
import { claseBotonChico } from "../comp/BotonChico";
import { comun } from "./textos/comun";
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
  icono: ReactNode;
  soloAdmin?: boolean;
}

const SECCIONES: Seccion[] = [
  { a: "/admin", texto: comun.nav.eventos, icono: <IconoEventos /> },
  { a: "/admin/historial", texto: comun.nav.historial, icono: <IconoHistorial /> },
  { a: "/admin/cuentas", texto: comun.nav.cuentas, icono: <IconoCuentas />, soloAdmin: true },
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
      <header className="sticky top-0 z-40 border-b border-borde bg-black/60 pt-[env(safe-area-inset-top)] backdrop-blur-2xl backdrop-saturate-150">
        <div className="mx-auto flex h-16 max-w-5xl items-center gap-3 px-4 sm:px-6 md:gap-6">
          {/* min-h-11: también la marca es un objetivo táctil (lleva a Eventos). */}
          <Link
            to="/admin"
            className="inline-flex min-h-11 shrink-0 items-center text-base font-semibold tracking-tight sm:text-lg"
          >
            {comun.marca}
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
                      (isActive ? "bg-white/20 text-white" : "text-tenue hover:text-white")
                    }
                  >
                    {s.texto}
                    {s.soloAdmin && <Contador n={pendientes} />}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>

          <div className="ml-auto flex min-w-0 items-center gap-3">
            {usuario && <span className="min-w-0 truncate text-sm text-tenue">{usuario.nombre}</span>}
            <button type="button" onClick={salir} className={`shrink-0 ${claseBotonChico("vidrio")}`}>
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
            className="-ml-1 mb-2 inline-flex min-h-11 items-center gap-1 rounded-full px-1 text-base text-acento hover:brightness-110"
          >
            <span aria-hidden className="text-2xl leading-none">‹</span>
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
        className="fixed inset-x-0 bottom-0 z-40 border-t border-borde bg-black/60 pb-[env(safe-area-inset-bottom)] backdrop-blur-2xl backdrop-saturate-150 md:hidden"
      >
        <ul className="flex">
          {secciones.map((s) => (
            <li key={s.a} className="flex-1">
              <NavLink
                to={s.a}
                end
                className={({ isActive }) =>
                  "flex min-h-14 flex-col items-center justify-center gap-0.5 pt-1 text-[11px] font-medium " +
                  "focus:outline-none focus-visible:bg-white/10 " +
                  (isActive ? "text-acento" : "text-tenue")
                }
              >
                <span className="relative">
                  {s.icono}
                  {s.soloAdmin && (
                    <span className="absolute -right-3 -top-1.5">
                      <Contador n={pendientes} />
                    </span>
                  )}
                </span>
                {s.texto}
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
      className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-rojo px-1.5 text-xs font-semibold tabular-nums text-white"
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

// Íconos de trazo, del tamaño y el grosor de los de la barra de iOS.

function Icono({ children }: { children: ReactNode }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      className="h-6 w-6"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  );
}

function IconoEventos() {
  return (
    <Icono>
      <rect x="3.5" y="5" width="17" height="15.5" rx="3" />
      <path d="M3.5 10h17M8 3v4M16 3v4" />
    </Icono>
  );
}

function IconoHistorial() {
  return (
    <Icono>
      <path d="M4 12a8 8 0 1 0 2.3-5.6" />
      <path d="M4 4v4h4" />
      <path d="M12 8v4l2.5 2" />
    </Icono>
  );
}

function IconoCuentas() {
  return (
    <Icono>
      <circle cx="9" cy="8.5" r="3.5" />
      <path d="M2.5 20c.8-3.4 3.3-5.5 6.5-5.5s5.7 2.1 6.5 5.5" />
      <path d="M15.5 5.2a3.5 3.5 0 0 1 0 6.6M18 14.9c1.8.8 3 2.5 3.5 5.1" />
    </Icono>
  );
}
