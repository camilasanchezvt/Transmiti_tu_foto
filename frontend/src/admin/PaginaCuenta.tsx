import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type MutableRefObject,
  type ReactNode,
} from "react";
import { Link } from "react-router-dom";
import {
  CheckIcon as GuardarReposo,
  ComputerDesktopIcon,
  LockClosedIcon as ContrasenaFila,
  MoonIcon,
  SunIcon,
  UserIcon,
} from "@heroicons/react/24/outline";
import { CheckIcon as GuardarPrincipal, LockClosedIcon as ContrasenaPrincipal } from "@heroicons/react/24/solid";
import {
  CameraIcon,
  CheckIcon as ListoMini,
  ExclamationTriangleIcon,
  MinusIcon as MenosMini,
  PlusIcon as MasMini,
  QrCodeIcon,
  TrashIcon,
} from "@heroicons/react/20/solid";

import { ErrorApi, admin } from "../api/client";
import type { EstiloPantalla, FondoPantalla, Tema, TransicionPantalla, UsuarioYo } from "../api/tipos";
import Avatar from "../comp/Avatar";
import Boton from "../comp/Boton";
import BotonChico from "../comp/BotonChico";
import Cargando from "../comp/Cargando";
import { ChipRol } from "../comp/ChipEstado";
import FilaDesplegable from "../comp/FilaDesplegable";
import { claseIconoChip, type Icono } from "../comp/icono";
import MensajeError from "../comp/MensajeError";
import { ArchivoInvalido, CALIDAD, comprimir } from "../lib/comprimir";
import { ErrorSubida, subirAcloudinary } from "../lib/subir";
import { aplicarTema, preferenciaTema, usePreferenciaTema } from "../lib/tema";
import LayoutAdmin from "./LayoutAdmin";
import { AvisoDeError, Campo } from "./PiezasAcceso";
import { MAXIMO_NOMBRE, MAXIMO_PASSWORD, MINIMO_PASSWORD } from "./textos/acceso";
import { comun } from "./textos/comun";
import { cuenta as t } from "./textos/cuenta";
import { actualizarUsuarioEnSesion, useAlPerderSesion, useSesion } from "./useSesion";

// Mi cuenta (/admin/cuenta), ordenada como los Ajustes de iOS: quién sos
// (foto y nombre), la contraseña, cómo se ve el panel y con qué arranca cada
// evento nuevo. Cada tarjeta guarda lo suyo por separado: cambiar el tema no
// puede esperar a que alguien toque un Guardar al pie de la página.
//
// El nombre y la contraseña son filas que se despliegan (FilaDesplegable):
// cerradas se ve lo de ahora; se abren para cambiarlo y, al guardar, se cierran
// solas y lo confirman en la fila misma. La página queda corta en el celular y
// los formularios no están abiertos cuando nadie los usa.
//
// Todo lo que el backend devuelve (la cuenta entera) pasa por
// actualizarUsuarioEnSesion: la barra de arriba cambia el nombre y la foto en
// el acto, sin volver a preguntar quién es.

const TARJETA = "rounded-3xl border border-borde bg-panel p-5";

/** La tarjeta de Perfil: la foto arriba y la fila del nombre al pie. Abajo,
 *  casi sin relleno: la fila (48 px, el texto al medio) ya deja su aire, y
 *  abierta suma el suyo. */
const TARJETA_PERFIL = "rounded-3xl border border-borde bg-panel px-5 pb-1 pt-5";

/** Una tarjeta que es sólo filas, como un grupo de Ajustes de iOS. */
const TARJETA_FILAS = "rounded-3xl border border-borde bg-panel px-5 py-1";

/** Cuánto se ve la confirmación en la fila. La de la contraseña es una frase
 *  entera que dice qué hacer en los otros dispositivos: más tiempo. */
const GUARDADO_MS = 2500;
const LISTO_CONTRASENA_MS = 6000;

/** Los botones grandes ocupan todo el ancho en el celular; en la compu, el de
 *  su texto. Lo mismo que en Ajustes. */
const ANCHO_BOTON = "sm:w-auto sm:min-w-56 sm:px-8";

/** Los topes del backend (SegundosPorFoto y MaxFotosPorDispositivo). */
const SEGUNDOS = { min: 3, max: 30 };
const CUPO = { min: 1, max: 50 };

/** El lado de la foto de perfil que se sube. En la pantalla más grande se ve
 *  de 80 px: 512 alcanza para cualquier celular y pesa unos 50 KB. */
const LADO_AVATAR = 512;

/** Cada cuánto cambia la foto en la vista previa de la pantalla. */
const VISTA_PREVIA_MS = 2600;

type Reflejar = (cuenta: UsuarioYo) => void;
type AlPerderSesion = (error: unknown) => boolean;

/** Largo como lo cuenta Python: por letras, no por unidades de UTF-16. */
function largo(texto: string): number {
  return [...texto].length;
}

function mensajeDe(error: unknown): string {
  return error instanceof ErrorApi ? error.message : comun.errores.generico;
}

export default function PaginaCuenta() {
  const { usuario, error, reintentar } = useSesion();
  const alPerderSesion = useAlPerderSesion();

  // El tema que se está guardando, si hay uno en camino. Si mientras tanto
  // vuelve otra respuesta (el nombre, la foto) con el tema de antes, no puede
  // pisar el que se acaba de elegir: el panel parpadearía al tema viejo.
  const temaEnCamino = useRef<Tema | null>(null);

  const reflejar = useCallback<Reflejar>((cuenta) => {
    const tema = temaEnCamino.current;
    actualizarUsuarioEnSesion(tema ? { ...cuenta, tema } : cuenta);
  }, []);

  useEffect(() => {
    document.title = comun.tituloPestana(t.tituloPestana);
  }, []);

  return (
    <LayoutAdmin titulo={t.titulo}>
      {error != null ? (
        <MensajeError error={error} onReintentar={reintentar} />
      ) : !usuario ? (
        <Cargando />
      ) : (
        <div className="flex flex-col gap-10">
          <Seccion titulo={t.perfil.titulo}>
            <div className={TARJETA_PERFIL}>
              <FotoDePerfil usuario={usuario} reflejar={reflejar} alPerderSesion={alPerderSesion} />
              <Nombre usuario={usuario} reflejar={reflejar} alPerderSesion={alPerderSesion} />
            </div>
          </Seccion>

          <Seccion titulo={t.seguridad.titulo}>
            <div className={TARJETA_FILAS}>
              <Contrasena email={usuario.email} alPerderSesion={alPerderSesion} />
            </div>
          </Seccion>

          <Seccion titulo={t.apariencia.titulo}>
            <Apariencia temaEnCamino={temaEnCamino} reflejar={reflejar} alPerderSesion={alPerderSesion} />
          </Seccion>

          <Seccion titulo={t.eventosNuevos.titulo}>
            {/* key: si cambia la cuenta (otra sesión en este navegador), el
                formulario arranca de nuevo con los suyos. */}
            <Predeterminados
              key={usuario.id}
              usuario={usuario}
              reflejar={reflejar}
              alPerderSesion={alPerderSesion}
            />
          </Seccion>
        </div>
      )}
    </LayoutAdmin>
  );
}

// ── Piezas comunes ───────────────────────────────────────────

/** El encabezado chico de los grupos de Ajustes de iOS, y su tarjeta debajo. */
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

/** Un error chico al lado de lo que falló. */
function ErrorEnLinea({ texto }: { texto: string }) {
  return (
    <p role="alert" className="mt-3 flex items-start gap-1.5 text-sm leading-snug text-rojo-tinta">
      <ExclamationTriangleIcon aria-hidden className={`mt-0.5 ${claseIconoChip}`} />
      <span className="min-w-0 break-words">{texto}</span>
    </p>
  );
}

/** "Guardado" con el tilde, un momento: `ms`, dos segundos y medio si no se
 *  dice otra cosa. */
function useGuardado(ms = GUARDADO_MS): [boolean, () => void, () => void] {
  const [visible, setVisible] = useState(false);
  const reloj = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(reloj.current), []);

  const mostrar = useCallback(() => {
    setVisible(true);
    window.clearTimeout(reloj.current);
    reloj.current = window.setTimeout(() => setVisible(false), ms);
  }, [ms]);
  const ocultar = useCallback(() => {
    window.clearTimeout(reloj.current);
    setVisible(false);
  }, []);

  return [visible, mostrar, ocultar];
}

/** Siempre en el DOM: una región viva que aparece de golpe no se anuncia en
 *  todos los lectores de pantalla. */
function Guardado({ visible, texto = comun.verbos.guardado }: { visible: boolean; texto?: string }) {
  return (
    <p role="status" className="flex items-center justify-center gap-1 text-sm text-verde-tinta sm:justify-start">
      {visible && (
        <>
          <ListoMini aria-hidden className={claseIconoChip} />
          {texto}
        </>
      )}
    </p>
  );
}

/** El botón de guardar de cada tarjeta: azul cuando hay algo para guardar,
 *  de vidrio y apagado cuando no. Con el "Guardado" al lado, salvo en una
 *  fila que se despliega: ahí lo dice la fila, ya cerrada. */
function FilaGuardar({
  listo,
  guardando,
  guardado,
}: {
  listo: boolean;
  guardando: boolean;
  guardado?: boolean;
}) {
  return (
    <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
      <Boton
        type="submit"
        className={ANCHO_BOTON}
        variante={listo ? "principal" : "secundario"}
        icono={listo ? GuardarPrincipal : GuardarReposo}
        cargando={guardando}
        disabled={!listo}
      >
        {comun.verbos.guardar}
      </Boton>
      {guardado !== undefined && <Guardado visible={guardado} />}
    </div>
  );
}

// ── Perfil: la foto ──────────────────────────────────────────

type Etapa = { tipo: "preparando" } | { tipo: "subiendo"; porcentaje: number } | { tipo: "guardando" };

/**
 * Recorta el cuadrado del medio y lo achica a `lado`. En una foto parada la
 * cara suele estar en el tercio de arriba: ahí el cuadrado sube, para no
 * dejar a nadie sin frente. Sin librerías: un canvas alcanza.
 *
 * Recibe lo que ya pasó por comprimir(): un JPEG derecho (la rotación de
 * iPhone ya está resuelta) o el original chico. from-image igual, por si es
 * el original y trae la rotación en el EXIF.
 */
async function recortarCuadrado(blob: Blob, lado: number): Promise<Blob> {
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(blob, { imageOrientation: "from-image" });
  } catch {
    throw new ArchivoInvalido();
  }
  try {
    const corte = Math.min(bitmap.width, bitmap.height);
    const x = (bitmap.width - corte) / 2;
    const y = (bitmap.height - corte) * (bitmap.height > bitmap.width ? 0.3 : 0.5);
    // Nunca agrandar: una foto de 300 px queda de 300.
    const final = Math.min(lado, corte);

    const lienzo = document.createElement("canvas");
    lienzo.width = final;
    lienzo.height = final;
    const contexto = lienzo.getContext("2d");
    if (!contexto) throw new ArchivoInvalido();
    contexto.imageSmoothingQuality = "high";
    contexto.drawImage(bitmap, x, y, corte, corte, 0, 0, final, final);

    return await new Promise<Blob>((resolver, rechazar) => {
      lienzo.toBlob((b) => (b ? resolver(b) : rechazar(new ArchivoInvalido())), "image/jpeg", CALIDAD);
    });
  } finally {
    bitmap.close();
  }
}

/**
 * La foto de perfil: se elige, se recorta cuadrada, se sube directo a
 * Cloudinary (con la firma de la carpeta avatares/{id} que da el backend) y
 * se registra. El mismo camino que una foto de invitado, con su progreso real.
 */
function FotoDePerfil({
  usuario,
  reflejar,
  alPerderSesion,
}: {
  usuario: UsuarioYo;
  reflejar: Reflejar;
  alPerderSesion: AlPerderSesion;
}) {
  const tp = t.perfil;
  const entrada = useRef<HTMLInputElement>(null);
  const controlador = useRef<AbortController | null>(null);
  const [etapa, setEtapa] = useState<Etapa | null>(null);
  const [quitando, setQuitando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  // La foto recortada, en este navegador. Mientras sube se ve ésa, y queda
  // hasta que la cuenta cambie de foto: así, al terminar, el círculo no se
  // vacía mientras baja la misma imagen de Cloudinary. `para` es la URL que
  // devolvió el backend; sin `para`, todavía está subiendo.
  const [local, setLocal] = useState<{ url: string; para?: string | null } | null>(null);
  const urlLocal = local?.url;
  useEffect(() => {
    if (!urlLocal) return;
    return () => URL.revokeObjectURL(urlLocal);
  }, [urlLocal]);

  // Si se sale de la página a mitad de una subida, se corta.
  useEffect(() => () => controlador.current?.abort(), []);

  const ocupado = etapa !== null || quitando;
  const tieneFoto = usuario.avatar_url !== null;
  const mostrada =
    local && (local.para === undefined || local.para === usuario.avatar_url) ? local.url : usuario.avatar_url;

  async function alElegir(e: ChangeEvent<HTMLInputElement>) {
    const archivo = e.target.files?.[0];
    // Vacío otra vez: elegir el mismo archivo después de un error tiene que
    // volver a disparar esto.
    e.target.value = "";
    if (!archivo || ocupado) return;

    const propio = new AbortController();
    controlador.current = propio;
    setError(null);
    setAviso(null);
    setEtapa({ tipo: "preparando" });

    try {
      const lista = await comprimir(archivo);
      URL.revokeObjectURL(lista.vistaPrevia);
      const blob = await recortarCuadrado(lista.blob, LADO_AVATAR);
      if (propio.signal.aborted) return;
      setLocal({ url: URL.createObjectURL(blob) });

      const firma = await admin.firmaAvatar();
      setEtapa({ tipo: "subiendo", porcentaje: 0 });
      const subida = await subirAcloudinary({
        firma,
        blob,
        senal: propio.signal,
        onProgreso: (porcentaje) => setEtapa({ tipo: "subiendo", porcentaje }),
      });

      setEtapa({ tipo: "guardando" });
      const nueva = await admin.guardarAvatar(subida.public_id, subida.url);
      if (propio.signal.aborted) return;
      setLocal((l) => (l ? { ...l, para: nueva.avatar_url } : l));
      reflejar(nueva);
      setAviso(tp.fotoLista);
    } catch (err) {
      if (propio.signal.aborted) return;
      setLocal(null);
      if (alPerderSesion(err)) return;
      setError(
        err instanceof ArchivoInvalido
          ? tp.noEsFoto
          : err instanceof ErrorSubida
            ? tp.noSeSubio
            : mensajeDe(err),
      );
    } finally {
      if (controlador.current === propio) {
        controlador.current = null;
        setEtapa(null);
      }
    }
  }

  async function quitar() {
    if (ocupado) return;
    setQuitando(true);
    setError(null);
    setAviso(null);
    try {
      reflejar(await admin.quitarAvatar());
      setLocal(null);
      setAviso(tp.fotoQuitada);
    } catch (err) {
      if (!alPerderSesion(err)) setError(mensajeDe(err));
    } finally {
      setQuitando(false);
    }
  }

  return (
    <div>
      <div className="flex items-center gap-4">
        <Avatar
          nombre={usuario.nombre}
          url={mostrada}
          tamano="perfil"
          className={etapa ? "opacity-60 transition-opacity" : "transition-opacity"}
        />
        <div className="min-w-0 flex-1">
          <p className="break-words text-lg font-semibold leading-snug">{usuario.nombre}</p>
          {/* Un email largo sin espacios no empuja la tarjeta a lo ancho. */}
          <p className="break-all text-sm text-tenue">{usuario.email}</p>
          <div className="mt-1.5">
            <ChipRol rol={usuario.rol} />
          </div>
        </div>
      </div>

      <p className="mt-4 text-sm text-tenue">{tp.fotoAyuda}</p>

      {/* En el celular, cada botón llena su mitad de la fila; en la compu, el
          ancho de su texto. */}
      <div className="mt-3 flex flex-wrap gap-2">
        <BotonChico
          icono={CameraIcon}
          className="grow whitespace-nowrap sm:grow-0"
          disabled={ocupado}
          onClick={() => entrada.current?.click()}
        >
          {tieneFoto ? tp.cambiarFoto : tp.elegirFoto}
        </BotonChico>
        {tieneFoto && (
          <BotonChico
            variante="peligro"
            icono={TrashIcon}
            className="grow whitespace-nowrap sm:grow-0"
            cargando={quitando}
            disabled={ocupado}
            onClick={quitar}
          >
            {tp.quitarFoto}
          </BotonChico>
        )}
      </div>
      {/* image/*, como en la página del invitado: así el celular ofrece la
          cámara y la galería, no un explorador de archivos. Lo que no sea una
          foto lo rechaza comprimir(). */}
      <input
        ref={entrada}
        type="file"
        accept="image/*"
        tabIndex={-1}
        aria-hidden
        className="hidden"
        onChange={alElegir}
      />

      {etapa && <Progreso etapa={etapa} />}

      <div role="status">
        {aviso && !etapa && (
          <p className="mt-3 flex items-center gap-1.5 text-sm text-verde-tinta">
            <ListoMini aria-hidden className={claseIconoChip} />
            {aviso}
          </p>
        )}
      </div>
      {error && <ErrorEnLinea texto={error} />}
    </div>
  );
}

/** La barra de la subida, con el porcentaje de verdad. Mientras se prepara la
 *  foto (recortar, comprimir) no hay porcentaje: la barra late. */
function Progreso({ etapa }: { etapa: Etapa }) {
  const tp = t.perfil;
  const porcentaje = etapa.tipo === "subiendo" ? etapa.porcentaje : etapa.tipo === "guardando" ? 100 : null;
  const texto =
    etapa.tipo === "preparando" ? tp.preparando : etapa.tipo === "subiendo" ? tp.subiendo(etapa.porcentaje) : tp.guardando;

  return (
    <div className="mt-3">
      <div
        role="progressbar"
        aria-label={tp.progreso}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={porcentaje ?? undefined}
        aria-valuetext={texto}
        className="h-1.5 overflow-hidden rounded-full bg-hundido"
      >
        <div
          className={
            "h-full rounded-full bg-acento transition-[width] duration-200 motion-reduce:transition-none " +
            (porcentaje === null ? "w-1/4 animate-pulse" : "")
          }
          style={porcentaje === null ? undefined : { width: `${porcentaje}%` }}
        />
      </div>
      <p className="mt-1.5 text-sm tabular-nums text-tenue">{texto}</p>
    </div>
  );
}

// ── Perfil: el nombre ────────────────────────────────────────

/**
 * La fila del nombre, al pie de la tarjeta de Perfil. Cerrada, el nombre de
 * ahora a la derecha. Al guardar se cierra sola y dice "Guardado" un momento;
 * si algo falla, queda abierta con el error.
 */
function Nombre({
  usuario,
  reflejar,
  alPerderSesion,
}: {
  usuario: UsuarioYo;
  reflejar: Reflejar;
  alPerderSesion: AlPerderSesion;
}) {
  const [abierto, setAbierto] = useState(false);
  const [guardado, mostrarGuardado, ocultarGuardado] = useGuardado();
  const guardando = useRef(false);

  return (
    <FilaDesplegable
      icono={UserIcon}
      titulo={t.perfil.filaNombre}
      resumen={usuario.nombre}
      confirmacion={guardado ? comun.verbos.guardado : null}
      abierto={abierto}
      onCambiar={(a) => {
        // Mientras guarda no se cierra: si el servidor fallara con el
        // formulario ya desmontado, el error no se vería.
        if (!a && guardando.current) return;
        setAbierto(a);
        ocultarGuardado();
      }}
      className="mt-4 border-t border-borde pt-1"
    >
      <FormularioNombre
        usuario={usuario}
        reflejar={reflejar}
        alPerderSesion={alPerderSesion}
        enCamino={guardando}
        alGuardar={() => {
          setAbierto(false);
          mostrarGuardado();
        }}
      />
    </FilaDesplegable>
  );
}

/** Se monta cada vez que se abre la fila: arranca con el nombre de ahora. */
function FormularioNombre({
  usuario,
  reflejar,
  alPerderSesion,
  enCamino,
  alGuardar,
}: {
  usuario: UsuarioYo;
  reflejar: Reflejar;
  alPerderSesion: AlPerderSesion;
  /** Lo lee la fila: mientras hay un pedido en camino, no se cierra. */
  enCamino: MutableRefObject<boolean>;
  alGuardar: () => void;
}) {
  const tp = t.perfil;
  const [nombre, setNombre] = useState(usuario.nombre);
  // El error se ve cuando salió del campo o tocó Guardar: no mientras borra
  // para escribir otro.
  const [mostrarError, setMostrarError] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const campo = useRef<HTMLInputElement>(null);

  const limpio = nombre.trim();
  const errorCampo = !limpio ? tp.nombreVacio : largo(limpio) > MAXIMO_NOMBRE ? tp.nombreLargo : null;
  const cambio = limpio !== usuario.nombre;

  async function guardar(e: FormEvent) {
    e.preventDefault();
    if (guardando || !cambio) return;
    if (errorCampo) {
      setMostrarError(true);
      campo.current?.focus();
      return;
    }
    setGuardando(true);
    enCamino.current = true;
    setError(null);
    try {
      const nueva = await admin.actualizarYo({ nombre: limpio });
      reflejar(nueva);
      setNombre(nueva.nombre);
      enCamino.current = false;
      alGuardar();
    } catch (err) {
      if (!alPerderSesion(err)) setError(err);
    } finally {
      enCamino.current = false;
      setGuardando(false);
    }
  }

  return (
    <form onSubmit={guardar} noValidate>
      <Campo
        etiqueta={tp.nombre}
        refCampo={campo}
        name="name"
        value={nombre}
        onChange={(e) => {
          setNombre(e.target.value);
          setError(null);
        }}
        onBlur={() => setMostrarError(true)}
        error={mostrarError ? errorCampo : null}
        ayuda={tp.nombreAyuda}
        autoComplete="name"
        autoCapitalize="words"
        maxLength={MAXIMO_NOMBRE}
      />
      <FilaGuardar listo={cambio} guardando={guardando} />
      {error != null && <ErrorEnLinea texto={mensajeDe(error)} />}
    </form>
  );
}

// ── Seguridad: la contraseña ─────────────────────────────────

type CampoContrasena = "actual" | "nueva" | "repetir";
type DatosContrasena = Record<CampoContrasena, string>;

/** En el orden en que aparecen: al fallar, el foco va al primero con error. */
const ORDEN_CONTRASENA: CampoContrasena[] = ["actual", "nueva", "repetir"];

function validarContrasena(d: DatosContrasena): Partial<Record<CampoContrasena, string>> {
  const ts = t.seguridad;
  const errores: Partial<Record<CampoContrasena, string>> = {};
  if (!d.actual) errores.actual = ts.actualVacia;
  const n = largo(d.nueva);
  if (n < MINIMO_PASSWORD) errores.nueva = ts.ayudaNueva(n);
  else if (n > MAXIMO_PASSWORD) errores.nueva = ts.nuevaLarga;
  if (!d.repetir) errores.repetir = ts.repetirVacia;
  else if (d.repetir !== d.nueva) errores.repetir = ts.noCoinciden;
  return errores;
}

/**
 * La fila de la contraseña, sola en la tarjeta de Seguridad. Al cambiarla se
 * cierra y dice "Listo, ya la cambiaste…" en la fila unos segundos; si algo
 * falla, queda abierta con el error.
 */
function Contrasena({ email, alPerderSesion }: { email: string; alPerderSesion: AlPerderSesion }) {
  const ts = t.seguridad;
  const [abierto, setAbierto] = useState(false);
  const [listo, mostrarListo, ocultarListo] = useGuardado(LISTO_CONTRASENA_MS);
  const enviando = useRef(false);

  return (
    <FilaDesplegable
      icono={ContrasenaFila}
      titulo={ts.fila}
      resumen={ts.resumen}
      resumenOculto
      confirmacion={listo ? ts.listo : null}
      abierto={abierto}
      onCambiar={(a) => {
        // Como el nombre: mientras se envía, no se cierra.
        if (!a && enviando.current) return;
        setAbierto(a);
        ocultarListo();
      }}
    >
      <FormularioContrasena
        email={email}
        alPerderSesion={alPerderSesion}
        enCamino={enviando}
        alCambiar={() => {
          setAbierto(false);
          mostrarListo();
        }}
      />
    </FilaDesplegable>
  );
}

/**
 * Cambiar la contraseña. El backend cierra todas las sesiones de la cuenta y
 * devuelve una nueva para ésta: admin.cambiarContrasena la guarda sola, y
 * quien la cambió sigue adentro sin darse cuenta.
 *
 * Se monta al abrir la fila y se desmonta al cerrarla: lo escrito no queda en
 * memoria con la fila cerrada, aunque no se haya enviado.
 */
function FormularioContrasena({
  email,
  alPerderSesion,
  enCamino,
  alCambiar,
}: {
  email: string;
  alPerderSesion: AlPerderSesion;
  /** Lo lee la fila: mientras hay un pedido en camino, no se cierra. */
  enCamino: MutableRefObject<boolean>;
  alCambiar: () => void;
}) {
  const ts = t.seguridad;
  const [datos, setDatos] = useState<DatosContrasena>({ actual: "", nueva: "", repetir: "" });
  const [tocados, setTocados] = useState<Partial<Record<CampoContrasena, boolean>>>({});
  const [intentoEnviar, setIntentoEnviar] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [vez, setVez] = useState(0);

  const refs = {
    actual: useRef<HTMLInputElement>(null),
    nueva: useRef<HTMLInputElement>(null),
    repetir: useRef<HTMLInputElement>(null),
  };

  const errores = validarContrasena(datos);
  const mostrar = (c: CampoContrasena) => (intentoEnviar || tocados[c] ? errores[c] : null);

  const largoNueva = largo(datos.nueva);
  const nuevaCumple = largoNueva >= MINIMO_PASSWORD && largoNueva <= MAXIMO_PASSWORD;
  const coinciden = datos.repetir !== "" && datos.repetir === datos.nueva && nuevaCumple;

  function cambiar(c: CampoContrasena, valor: string) {
    setDatos((d) => ({ ...d, [c]: valor }));
  }

  function salir(c: CampoContrasena) {
    if (datos[c] !== "") setTocados((x) => ({ ...x, [c]: true }));
  }

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (enviando) return;
    setIntentoEnviar(true);
    setError(null);

    const primero = ORDEN_CONTRASENA.find((c) => errores[c]);
    if (primero) {
      refs[primero].current?.focus();
      return;
    }

    setEnviando(true);
    enCamino.current = true;
    try {
      await admin.cambiarContrasena(datos.actual, datos.nueva);
      // Nada de contraseñas en memoria después de esto.
      setDatos({ actual: "", nueva: "", repetir: "" });
      setTocados({});
      setIntentoEnviar(false);
      // La fila se cierra y el foco vuelve a ella: el teclado del celular
      // baja y se lee el "Listo".
      enCamino.current = false;
      alCambiar();
    } catch (err) {
      // Un 401 es que esta sesión ya no sirve (la cambiaron desde otro lado):
      // al login. La actual incorrecta (422) y los muchos intentos (429)
      // llegan con su mensaje, tal cual.
      if (alPerderSesion(err)) return;
      setError(err);
      setVez((n) => n + 1);
    } finally {
      enCamino.current = false;
      setEnviando(false);
    }
  }

  return (
    <form onSubmit={enviar} noValidate aria-label={ts.cambiarTitulo}>
      <p className="text-sm text-tenue">{ts.cambiarDetalle}</p>

      {/* Para el gestor de contraseñas: sin el email, no sabe de qué cuenta
          es la contraseña nueva que ofrece guardar. */}
      <input type="email" name="username" autoComplete="username" value={email} readOnly hidden />

      <div className="mt-4 flex flex-col gap-4">
        <Campo
          etiqueta={ts.actual}
          refCampo={refs.actual}
          type="password"
          name="current-password"
          value={datos.actual}
          onChange={(e) => cambiar("actual", e.target.value)}
          onBlur={() => salir("actual")}
          error={mostrar("actual")}
          autoComplete="current-password"
          maxLength={MAXIMO_PASSWORD}
        />
        <Campo
          etiqueta={ts.nueva}
          refCampo={refs.nueva}
          type="password"
          name="new-password"
          value={datos.nueva}
          onChange={(e) => cambiar("nueva", e.target.value)}
          onBlur={() => salir("nueva")}
          error={mostrar("nueva")}
          ayuda={ts.ayudaNueva(largoNueva)}
          ayudaCumplida={nuevaCumple}
          autoComplete="new-password"
          minLength={MINIMO_PASSWORD}
          maxLength={MAXIMO_PASSWORD}
        />
        <Campo
          etiqueta={ts.repetir}
          refCampo={refs.repetir}
          type="password"
          name="repetir-password"
          value={datos.repetir}
          onChange={(e) => cambiar("repetir", e.target.value)}
          onBlur={() => salir("repetir")}
          error={mostrar("repetir")}
          ayuda={coinciden ? ts.coinciden : null}
          ayudaCumplida={coinciden}
          autoComplete="new-password"
          maxLength={MAXIMO_PASSWORD}
        />
      </div>

      {error != null && (
        <div className="mt-4">
          <AvisoDeError key={vez} error={error} />
        </div>
      )}

      <Boton type="submit" className={`mt-4 ${ANCHO_BOTON}`} icono={ContrasenaPrincipal} cargando={enviando}>
        {ts.boton}
      </Boton>

      {/* Olvidé mi contraseña funciona también con la sesión abierta: el link
          llega al email y, al usarlo, cierra todas las sesiones. */}
      <p className="mt-3 flex flex-wrap items-center gap-x-1 text-sm text-tenue">
        <span>{ts.olvidaste}</span>
        <Link
          to="/admin/olvide"
          className={
            "inline-flex min-h-11 items-center rounded-full px-1 font-medium text-acento-tinta " +
            "hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-acento"
          }
        >
          {ts.pedirLink}
        </Link>
      </p>
    </form>
  );
}

// ── Apariencia ───────────────────────────────────────────────

/** Automático usa ComputerDesktopIcon, el ícono de "sigue al sistema" de
 *  heroicons (CLAUDE.md: nada de SVG escritos a mano). */
const ICONO_TEMA: Record<Tema, Icono> = {
  oscuro: MoonIcon,
  claro: SunIcon,
  automatico: ComputerDesktopIcon,
};

const TEMAS: Tema[] = ["oscuro", "claro", "automatico"];

/**
 * Oscuro, claro o automático. Se ve en el acto y se guarda en la cuenta (así
 * vale también en el celular). Si no se pudo guardar, vuelve al que estaba.
 */
function Apariencia({
  temaEnCamino,
  reflejar,
  alPerderSesion,
}: {
  temaEnCamino: MutableRefObject<Tema | null>;
  reflejar: Reflejar;
  alPerderSesion: AlPerderSesion;
}) {
  const ta = t.apariencia;
  const preferencia = usePreferenciaTema();
  const [error, setError] = useState<unknown>(null);
  // Tres toques seguidos mandan tres pedidos: sólo vale lo que vuelve del
  // último, o una respuesta vieja devolvería el tema de antes.
  const ultimo = useRef(0);

  async function elegir(tema: Tema) {
    if (tema === preferenciaTema()) return;
    const anterior = preferenciaTema();
    const este = ++ultimo.current;
    setError(null);
    temaEnCamino.current = tema;
    aplicarTema(tema);
    try {
      const nueva = await admin.actualizarYo({ tema });
      if (este !== ultimo.current) return;
      temaEnCamino.current = null;
      reflejar(nueva);
    } catch (err) {
      if (este !== ultimo.current) return;
      temaEnCamino.current = null;
      if (alPerderSesion(err)) return;
      aplicarTema(anterior);
      setError(err);
    }
  }

  return (
    <div className={TARJETA}>
      <Segmentado
        etiqueta={ta.etiqueta}
        grande
        opciones={TEMAS.map((valor) => ({ valor, texto: ta.opciones[valor], icono: ICONO_TEMA[valor] }))}
        valor={preferencia}
        onCambiar={(v) => void elegir(v)}
      />
      <p className="mt-3 text-sm text-tenue">{ta.ayuda}</p>
      <p className="mt-1 text-sm text-tenue">{ta.siempreOscuro}</p>
      {error != null && <ErrorEnLinea texto={mensajeDe(error)} />}
    </div>
  );
}

/**
 * El control segmentado de iOS, hecho con radios de verdad: se elige con el
 * dedo, con Tab y las flechas, y el lector de pantalla dice "1 de 3". El radio
 * queda oculto (sr-only) y se pinta la cápsula de al lado.
 *
 * `grande`: con ícono arriba del texto, para Apariencia. Si no, sólo texto.
 */
function Segmentado<T extends string>({
  etiqueta,
  opciones,
  valor,
  onCambiar,
  grande = false,
}: {
  etiqueta: string;
  opciones: { valor: T; texto: string; icono?: Icono }[];
  valor: T;
  onCambiar: (v: T) => void;
  grande?: boolean;
}) {
  const nombre = useId();
  return (
    <fieldset>
      <legend className="text-base font-medium">{etiqueta}</legend>
      <div className={"flex gap-1 bg-hundido p-1 " + (grande ? "mt-3 rounded-2xl" : "mt-2 rounded-full")}>
        {opciones.map((o) => {
          const IconoOpcion = o.icono;
          return (
            <label key={o.valor} className="min-w-0 flex-1">
              <input
                type="radio"
                name={nombre}
                value={o.valor}
                checked={valor === o.valor}
                onChange={() => onCambiar(o.valor)}
                className="peer sr-only"
              />
              <span
                className={
                  "flex cursor-pointer items-center justify-center text-center text-sm font-medium text-tenue " +
                  "transition hover:text-texto peer-checked:bg-elegido peer-checked:text-texto " +
                  "peer-checked:shadow-sm peer-checked:shadow-sombra/10 " +
                  "peer-focus-visible:ring-2 peer-focus-visible:ring-acento " +
                  (grande ? "min-h-16 flex-col gap-1 rounded-xl px-1 py-2" : "min-h-11 rounded-full px-3")
                }
              >
                {IconoOpcion && <IconoOpcion aria-hidden className="h-6 w-6 shrink-0" />}
                {o.texto}
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

// ── Eventos nuevos: los predeterminados ──────────────────────

function aEntero(texto: string): number {
  return /^\d{1,3}$/.test(texto.trim()) ? Number(texto.trim()) : Number.NaN;
}

function enRango(n: number, rango: { min: number; max: number }): boolean {
  return Number.isInteger(n) && n >= rango.min && n <= rango.max;
}

const FONDOS: FondoPantalla[] = ["desenfocado", "negro"];
const TRANSICIONES: TransicionPantalla[] = ["fundido", "corte"];

/**
 * Con qué arranca cada evento nuevo: los mismos números que en los Ajustes de
 * un evento, y cómo se ve la pantalla. Cambiar esto no toca los eventos que ya
 * existen. Un solo Guardar para toda la tarjeta, como en Ajustes.
 */
function Predeterminados({
  usuario,
  reflejar,
  alPerderSesion,
}: {
  usuario: UsuarioYo;
  reflejar: Reflejar;
  alPerderSesion: AlPerderSesion;
}) {
  const te = t.eventosNuevos;
  const p = usuario.predeterminados;
  const [segundos, setSegundos] = useState(String(p.segundos_por_foto));
  const [cupo, setCupo] = useState(String(p.max_fotos_por_dispositivo));
  const [estilo, setEstilo] = useState<EstiloPantalla>({
    fondo: p.pantalla.fondo,
    transicion: p.pantalla.transicion,
    mostrar_nombre: p.pantalla.mostrar_nombre,
    mostrar_qr: p.pantalla.mostrar_qr,
  });
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [guardado, mostrarGuardado, ocultarGuardado] = useGuardado();

  const s = aEntero(segundos);
  const c = aEntero(cupo);
  const valido = enRango(s, SEGUNDOS) && enRango(c, CUPO);
  const cambio =
    s !== p.segundos_por_foto ||
    c !== p.max_fotos_por_dispositivo ||
    estilo.fondo !== p.pantalla.fondo ||
    estilo.transicion !== p.pantalla.transicion ||
    estilo.mostrar_nombre !== p.pantalla.mostrar_nombre ||
    estilo.mostrar_qr !== p.pantalla.mostrar_qr;

  function tocado() {
    ocultarGuardado();
    setError(null);
  }

  function cambiarEstilo<K extends keyof EstiloPantalla>(clave: K, v: EstiloPantalla[K]) {
    setEstilo((e) => ({ ...e, [clave]: v }));
    tocado();
  }

  async function guardar(e: FormEvent) {
    e.preventDefault();
    if (!valido || !cambio || guardando) return;
    setGuardando(true);
    setError(null);
    try {
      reflejar(
        await admin.actualizarYo({
          predeterminados: { segundos_por_foto: s, max_fotos_por_dispositivo: c, pantalla: estilo },
        }),
      );
      mostrarGuardado();
    } catch (err) {
      if (!alPerderSesion(err)) setError(err);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <form onSubmit={guardar} noValidate className={TARJETA}>
      <p className="text-sm text-tenue">{te.explicacion}</p>

      <div className="mt-1 divide-y divide-borde">
        <Numero
          etiqueta={te.segundos}
          ayuda={te.segundosAyuda}
          valor={segundos}
          onCambiar={(v) => {
            setSegundos(v);
            tocado();
          }}
          rango={SEGUNDOS}
          textoMenos={te.segundosMenos}
          textoMas={te.segundosMas}
        />
        <Numero
          etiqueta={te.cupo}
          ayuda={te.cupoAyuda}
          valor={cupo}
          onCambiar={(v) => {
            setCupo(v);
            tocado();
          }}
          rango={CUPO}
          textoMenos={te.cupoMenos}
          textoMas={te.cupoMas}
        />
      </div>

      <div className="border-t border-borde pt-5">
        <h3 className="text-lg font-semibold">{te.pantallaTitulo}</h3>

        {/* En la compu, la vista previa a la derecha y quieta mientras se
            baja por las opciones; en el celular, arriba de ellas. */}
        <div className="mt-3 flex flex-col gap-2 md:flex-row-reverse md:items-start md:gap-6">
          <figure className="md:sticky md:top-24 md:w-64 md:shrink-0">
            <figcaption className="mb-2 text-sm text-tenue">{te.vistaPrevia}</figcaption>
            <VistaPrevia estilo={estilo} />
          </figure>

          <div className="min-w-0 flex-1 divide-y divide-borde">
            <div className="py-4 md:pt-0">
              <Segmentado
                etiqueta={te.fondo}
                opciones={FONDOS.map((valor) => ({ valor, texto: te.fondoOpciones[valor] }))}
                valor={estilo.fondo}
                onCambiar={(v) => cambiarEstilo("fondo", v)}
              />
              <p className="mt-2 text-sm text-tenue">{te.fondoAyuda[estilo.fondo]}</p>
            </div>
            <div className="py-4">
              <Segmentado
                etiqueta={te.transicion}
                opciones={TRANSICIONES.map((valor) => ({ valor, texto: te.transicionOpciones[valor] }))}
                valor={estilo.transicion}
                onCambiar={(v) => cambiarEstilo("transicion", v)}
              />
              <p className="mt-2 text-sm text-tenue">{te.transicionAyuda[estilo.transicion]}</p>
            </div>
            <Interruptor
              etiqueta={te.mostrarNombre}
              ayuda={te.mostrarNombreAyuda}
              activo={estilo.mostrar_nombre}
              onCambiar={(v) => cambiarEstilo("mostrar_nombre", v)}
            />
            <Interruptor
              etiqueta={te.mostrarQr}
              ayuda={te.mostrarQrAyuda}
              activo={estilo.mostrar_qr}
              onCambiar={(v) => cambiarEstilo("mostrar_qr", v)}
            />
          </div>
        </div>
      </div>

      <FilaGuardar listo={cambio && valido} guardando={guardando} guardado={guardado} />
      {error != null && <ErrorEnLinea texto={mensajeDe(error)} />}
    </form>
  );
}

/**
 * Una fila con un número y su − y +, como el stepper de iOS. En el celular se
 * cambia con el dedo sin abrir el teclado; el campo igual se puede tipear,
 * para ir de 3 a 30 sin 27 toques. La misma pieza que en Ajustes.
 */
function Numero({
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
    "text-texto transition hover:bg-pulsado active:scale-[0.94] " +
    "disabled:cursor-not-allowed disabled:opacity-40 disabled:active:scale-100 " +
    "focus:outline-none focus-visible:ring-2 focus-visible:ring-acento";

  return (
    <div className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <div className="min-w-0">
        <label htmlFor={idCampo} className="text-base font-medium">
          {etiqueta}
        </label>
        <p id={idAyuda} className={`mt-0.5 text-sm ${valido ? "text-tenue" : "text-naranja-tinta"}`}>
          {valido ? ayuda : t.eventosNuevos.fueraDeRango(rango.min, rango.max)}
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
          <MenosMini aria-hidden className="h-5 w-5" />
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
            `text-texto outline-none focus:border-acento ${valido ? "border-borde" : "border-naranja"}`
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
          <MasMini aria-hidden className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
}

/**
 * El interruptor de iOS: verde prendido, gris apagado. Es un checkbox de
 * verdad con role="switch" (el lector dice "activado"); toda la fila es la
 * etiqueta, así se toca en cualquier parte y no sólo en la pastilla.
 */
function Interruptor({
  etiqueta,
  ayuda,
  activo,
  onCambiar,
}: {
  etiqueta: string;
  ayuda?: string;
  activo: boolean;
  onCambiar: (v: boolean) => void;
}) {
  const idAyuda = useId();
  return (
    <label className="flex min-h-11 cursor-pointer items-center justify-between gap-4 py-4">
      <span className="min-w-0">
        <span className="block text-base font-medium">{etiqueta}</span>
        {ayuda && (
          <span id={idAyuda} className="mt-0.5 block text-sm text-tenue">
            {ayuda}
          </span>
        )}
      </span>
      <input
        type="checkbox"
        role="switch"
        checked={activo}
        onChange={(e) => onCambiar(e.target.checked)}
        aria-describedby={ayuda ? idAyuda : undefined}
        className="peer sr-only"
      />
      {/* 51 × 31, como el de iOS. La perilla corre 20 px. */}
      <span
        aria-hidden
        className={
          "relative h-[31px] w-[51px] shrink-0 rounded-full bg-texto/20 transition-colors " +
          "peer-checked:bg-verde peer-focus-visible:ring-2 peer-focus-visible:ring-acento " +
          "after:absolute after:left-0.5 after:top-0.5 after:h-[27px] after:w-[27px] after:rounded-full " +
          "after:bg-luz after:shadow-md after:shadow-sombra/25 after:transition-transform " +
          "peer-checked:after:translate-x-5 motion-reduce:transition-none motion-reduce:after:transition-none"
        }
      />
    </label>
  );
}

// ── La vista previa de la pantalla ───────────────────────────

/**
 * Un proyector en miniatura: dos fotos paradas que se turnan con la
 * transición elegida, con el fondo, el nombre y el QR tal como van a salir.
 * Siempre oscuro, como la pantalla de verdad, sea cual sea el tema del panel.
 * Con "reducir movimiento" no se turnan: queda la primera, quieta.
 */
function VistaPrevia({ estilo }: { estilo: EstiloPantalla }) {
  const [cual, setCual] = useState(0);

  useEffect(() => {
    const reducir =
      typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reducir) return;
    const reloj = window.setInterval(() => {
      if (document.visibilityState === "visible") setCual((c) => 1 - c);
    }, VISTA_PREVIA_MS);
    return () => window.clearInterval(reloj);
  }, []);

  const fundido = estilo.transicion === "fundido";

  return (
    <div
      aria-hidden
      className="relative aspect-video w-full overflow-hidden rounded-2xl border border-borde bg-sombra"
    >
      {[0, 1].map((i) => (
        <div
          key={i}
          className={
            "absolute inset-0 " +
            (fundido ? "transition-opacity duration-700 ease-in-out motion-reduce:transition-none " : "") +
            (cual === i ? "opacity-100" : "opacity-0")
          }
        >
          {estilo.fondo === "desenfocado" && (
            <Dibujo n={i} cubrir className="absolute inset-0 h-full w-full scale-125 blur-md brightness-50" />
          )}
          {/* Alto completo y el ancho que pide 3:4, centrada: una foto parada
              en un proyector apaisado, con los costados libres. */}
          <div className="relative mx-auto aspect-[3/4] h-full">
            <Dibujo n={i} className="h-full w-full" />
          </div>
        </div>
      ))}

      {estilo.mostrar_nombre && (
        <p className="vidrio-oscuro absolute inset-x-0 bottom-2 mx-auto w-fit max-w-[60%] truncate rounded-full px-2.5 py-0.5 text-[10px] leading-4 text-luz">
          {t.eventosNuevos.nombreDeEjemplo}
        </p>
      )}
      {estilo.mostrar_qr && (
        <div className="vidrio-oscuro absolute bottom-1.5 right-1.5 rounded-md p-1">
          <div className="rounded-sm bg-luz p-0.5">
            <QrCodeIcon className="h-5 w-5 text-sombra" />
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Una "foto" de ejemplo, parada (3:4), hecha con formas lisas de los colores
 * del sistema: un paisaje de día y uno con globos. Sin imágenes que bajar.
 * `cubrir`: estirada para llenar el fondo desenfocado, como hace la pantalla.
 */
function Dibujo({ n, cubrir = false, className }: { n: number; cubrir?: boolean; className?: string }) {
  return (
    <svg
      viewBox="0 0 30 40"
      preserveAspectRatio={cubrir ? "xMidYMid slice" : "xMidYMid meet"}
      className={className}
    >
      {n === 0 ? (
        <>
          <rect width="30" height="40" className="fill-acento" />
          <circle cx="21" cy="11" r="5" className="fill-naranja" />
          <path d="M0 29 Q9 19 17 27 T30 25 V40 H0 Z" className="fill-verde" />
        </>
      ) : (
        <>
          <rect width="30" height="40" className="fill-naranja" />
          <circle cx="10" cy="13" r="5" className="fill-rojo" />
          <circle cx="20" cy="17" r="4" className="fill-acento" />
          <path d="M10 18 L11 30 M20 21 L19 30" className="stroke-luz" strokeWidth="0.4" fill="none" />
          <rect y="30" width="30" height="10" className="fill-sombra/60" />
        </>
      )}
    </svg>
  );
}
