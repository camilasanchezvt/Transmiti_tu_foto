// Textos que comparten todas las páginas del panel: la barra, los estados, los
// verbos y los errores genéricos. Cada página tiene además su propio archivo en
// esta carpeta (eventos.ts, ajustes.ts, revisar.ts…).
//
// Los verbos viven acá y no en cada página para que no se desparramen: una
// página que dice "Bajar" y otra "Descargar" para lo mismo confunden más que
// cualquier ícono. Descargar (nunca Bajar), Crear (nunca Armar), Revisar fotos
// (nunca Moderar en lo que se ve; el código interno sí dice moderar).

import type { EstadoCuenta, EstadoEvento, RolUsuario } from "../../api/tipos";
import { textosBase } from "../../comp/textos";

export const comun = {
  marca: "Transmití tu foto",

  nav: {
    etiqueta: "Secciones del panel",
    eventos: "Eventos",
    historial: "Historial",
    cuentas: "Cuentas",
  },

  salir: "Salir",
  cancelar: "Cancelar",
  cerrar: "Cerrar",
  esperar: textosBase.esperar,
  cargando: textosBase.cargando,

  /** Para el título de la pestaña del navegador. */
  tituloPestana: (titulo: string) => `${titulo} · Transmití tu foto`,

  estadosEvento: {
    borrador: "Sin publicar",
    activo: "Abierto",
    cerrado: "Terminado",
  } satisfies Record<EstadoEvento, string>,

  estadosCuenta: {
    pendiente: "Pendiente",
    activa: "Activa",
    baja: "De baja",
  } satisfies Record<EstadoCuenta, string>,

  roles: {
    superadmin: "Superadmin",
    admin: "Admin",
    organizador: "Organizador",
  } satisfies Record<RolUsuario, string>,

  /** Quién organiza un evento. Sólo lo ve un admin, que ve los de todas las
   *  cuentas; un organizador ve sólo los suyos y ya sabe de quién son. Igual
   *  en Eventos, Historial y Ajustes. */
  organiza: (nombre: string) => `Organiza ${nombre}`,

  /** Para lectores de pantalla: el número rojo de la pestaña Cuentas. */
  pendientesCuentas: (n: number) =>
    n === 1 ? "1 cuenta esperando que la habilites" : `${n} cuentas esperando que las habilites`,

  verbos: {
    crear: "Crear",
    publicar: "Publicar",
    revisarFotos: "Revisar fotos",
    ajustes: "Ajustes",
    descargar: "Descargar",
    descargarQR: "Descargar QR para imprimir",
    /** Igual en Ajustes y en Historial. */
    descargarVideo: "Descargar video",
    copiar: "Copiar",
    copiado: "Copiado",
    deshacer: "Deshacer",
    guardar: "Guardar",
    guardado: "Guardado",
    terminarEvento: "Terminar el evento",
    volver: "Volver",
  },

  fotos: (n: number) => (n === 1 ? "1 foto" : `${n} fotos`),

  errores: {
    generico: textosBase.errorGenerico,
    sinRed: textosBase.sinRed,
    sinPermiso: "No tenés permiso para esto",
    reintentar: textosBase.probarDeNuevo,
  },
} as const;
