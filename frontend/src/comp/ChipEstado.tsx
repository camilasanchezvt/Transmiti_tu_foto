import { NoSymbolIcon, ShieldCheckIcon } from "@heroicons/react/20/solid";

import type { EstadoCuenta, EstadoEvento, RolUsuario } from "../api/tipos";
import { comun } from "../admin/textos/comun";
import { claseIconoChip } from "./icono";

// Cápsulas chicas de estado, como las etiquetas de iOS. El color acompaña a la
// palabra, nunca la reemplaza: con el brillo bajo o con daltonismo, la palabra
// es lo que se lee.
//
// Íconos, pocos y sólo donde repiten el de la acción que lleva a ese estado:
// el escudo de "Hacer admin" en los roles de admin y el círculo tachado de
// "Dar de baja" en una cuenta de baja. Los estados del evento no llevan: el
// chip aparece en cada tarjeta de la lista, y un ícono por tarjeta es ruido.
// El punto de "Abierto" y de "Pendiente" dice "esto está pasando ahora".

// h-fit: dentro de una fila flex que estira, el chip no crece al alto del botón
// de al lado.
const BASE =
  "inline-flex h-fit shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium";

const GRIS = "bg-white/10 text-tenue";

/** Mini (20/solid) a 16 px, corrido medio punto a la izquierda: sin eso el
 *  chip se ve con más aire del lado del ícono que del lado del texto. */
const ICONO = `${claseIconoChip} -ml-0.5`;

function Punto({ clase }: { clase: string }) {
  return <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${clase}`} />;
}

const EVENTO: Record<EstadoEvento, string> = {
  borrador: GRIS,
  activo: "bg-verde/15 text-verde",
  // Gris azulado: ya pasó, pero no es un error.
  cerrado: "bg-slate-400/15 text-slate-300",
};

/** borrador → "Sin publicar" · activo → "Abierto" (con punto verde) · cerrado → "Terminado" */
export function ChipEstado({ estado }: { estado: EstadoEvento }) {
  return (
    <span className={`${BASE} ${EVENTO[estado]}`}>
      {estado === "activo" && <Punto clase="bg-verde" />}
      {comun.estadosEvento[estado]}
    </span>
  );
}

export default ChipEstado;

const CUENTA: Record<EstadoCuenta, string> = {
  pendiente: "bg-naranja/15 text-naranja",
  activa: "bg-verde/15 text-verde",
  baja: GRIS,
};

/** pendiente → "Pendiente" (naranja, con punto: espera que alguien haga algo) ·
 *  activa → "Activa" · baja → "De baja" (con el ícono de "Dar de baja") */
export function ChipCuenta({ estado }: { estado: EstadoCuenta }) {
  return (
    <span className={`${BASE} ${CUENTA[estado]}`}>
      {estado === "pendiente" && <Punto clase="bg-naranja" />}
      {estado === "baja" && <NoSymbolIcon aria-hidden className={ICONO} />}
      {comun.estadosCuenta[estado]}
    </span>
  );
}

const ROL: Record<RolUsuario, string> = {
  // Relleno sólido: es la única cuenta así, y se distingue de un admin sin
  // sumar un color.
  superadmin: "bg-acento text-white",
  admin: "bg-acento/15 text-acento",
  organizador: GRIS,
};

/** superadmin → "Superadmin" (azul lleno) · admin → "Admin" (azul), los dos
 *  con el escudo de "Hacer admin" · organizador → "Organizador", sin ícono: es
 *  la cuenta común y la mayoría de la lista. */
export function ChipRol({ rol }: { rol: RolUsuario }) {
  return (
    <span className={`${BASE} ${ROL[rol]}`}>
      {rol !== "organizador" && <ShieldCheckIcon aria-hidden className={ICONO} />}
      {comun.roles[rol]}
    </span>
  );
}
