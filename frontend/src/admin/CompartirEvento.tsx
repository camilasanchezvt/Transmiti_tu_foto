import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { ComputerDesktopIcon, LinkIcon, QrCodeIcon, TvIcon } from "@heroicons/react/24/outline";
import {
  ArrowDownTrayIcon,
  ArrowTopRightOnSquareIcon,
  CheckIcon,
  ChevronRightIcon,
  ClipboardDocumentIcon,
  ExclamationTriangleIcon,
} from "@heroicons/react/20/solid";

import { ErrorApi, admin } from "../api/client";
import type { EventoAdmin } from "../api/tipos";
import BotonChico from "../comp/BotonChico";
import type { Icono } from "../comp/icono";
import { dibujarQR } from "../lib/qr";
import { textosCompartir as t } from "./textos/compartir";
import { useCopiar } from "./useCopiar";
import { useAlPerderSesion } from "./useSesion";

// "Compartir y pantalla": el QR para imprimir, el link para invitados y las
// tres formas de conectar la pantalla. Lo usan las tarjetas de Eventos. Por la
// regla de medianoche, una fiesta abierta que pasa las 00:00 sigue en Eventos
// hasta que la terminen, así que a esa hora el QR y "Conectar otra tele"
// siguen donde estaban. En el historial no hace falta: ahí no hay abiertos.

function mensajeDe(error: unknown, porDefecto: string): string {
  return error instanceof ErrorApi ? error.message : porDefecto;
}

/**
 * El bloque plegable, al pie de la tarjeta de un evento. Plegado por defecto:
 * se usa una vez por evento.
 */
export default function CompartirEvento({
  evento,
  abiertoAlInicio = false,
  qrGrande = false,
}: {
  evento: EventoAdmin;
  abiertoAlInicio?: boolean;
  qrGrande?: boolean;
}) {
  return (
    <Desplegable titulo={t.titulo} abiertoAlInicio={abiertoAlInicio}>
      <Compartir evento={evento} qrGrande={qrGrande} />
    </Desplegable>
  );
}

/** Una fila que se abre y se cierra, como las de Ajustes de iOS: el ícono del
 *  QR adelante, el título y la flecha que gira al abrir. El contenido sólo se
 *  monta abierto: cada QR se dibuja a 1024 px para imprimir, y con veinte
 *  eventos plegados serían veinte lienzos grandes de más. */
function Desplegable({
  titulo,
  abiertoAlInicio = false,
  children,
}: {
  titulo: string;
  abiertoAlInicio?: boolean;
  children: ReactNode;
}) {
  const [abierto, setAbierto] = useState(abiertoAlInicio);
  const id = useId();

  return (
    <div className="mt-4 border-t border-borde">
      <button
        type="button"
        aria-expanded={abierto}
        aria-controls={id}
        onClick={() => setAbierto((a) => !a)}
        className={
          "mt-1 flex min-h-12 w-full items-center justify-between gap-3 rounded-xl text-left text-base font-medium " +
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-acento"
        }
      >
        <span className="flex min-w-0 items-center gap-3">
          <QrCodeIcon aria-hidden className="h-6 w-6 shrink-0 text-acento" />
          {titulo}
        </span>
        <ChevronRightIcon
          aria-hidden
          className={`h-5 w-5 shrink-0 text-tenue transition-transform ${abierto ? "rotate-90" : ""}`}
        />
      </button>
      <div id={id} hidden={!abierto} className="pt-3">
        {abierto && children}
      </div>
    </div>
  );
}

function Compartir({ evento, qrGrande }: { evento: EventoAdmin; qrGrande: boolean }) {
  const urlInvitado = `${window.location.origin}/e/${evento.codigo_publico}`;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-start">
        <QrDescargable url={urlInvitado} nombre={evento.nombre} grande={qrGrande} />
        <div className="w-full min-w-0 flex-1">
          <Copiable etiqueta={t.linkInvitados} ayuda={t.linkInvitadosAyuda} valor={urlInvitado} />
        </div>
      </div>
      <ConectarPantalla evento={evento} />
    </div>
  );
}

function QrDescargable({ url, nombre, grande }: { url: string; nombre: string; grande: boolean }) {
  const lienzo = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!lienzo.current) return;
    // Se dibuja grande siempre y se muestra chico por CSS: el PNG que se
    // descarga tiene que servir para imprimir, no para la pantalla.
    dibujarQR(lienzo.current, url, 1024).catch(() => {});
  }, [url]);

  function descargar() {
    const png = lienzo.current?.toDataURL("image/png");
    if (!png) return;
    const a = document.createElement("a");
    a.href = png;
    a.download = t.archivoQR(nombre);
    a.click();
  }

  return (
    <div className="flex shrink-0 flex-col items-center gap-3">
      <canvas
        ref={lienzo}
        role="img"
        aria-label={t.qr(nombre)}
        className={`rounded-2xl bg-luz ${grande ? "h-[min(240px,65vw)] w-[min(240px,65vw)]" : "h-40 w-40"}`}
      />
      <BotonChico onClick={descargar} icono={ArrowDownTrayIcon}>
        {t.descargarQR}
      </BotonChico>
    </div>
  );
}

function Copiable({ etiqueta, ayuda, valor }: { etiqueta: string; ayuda: string; valor: string }) {
  const [copiado, copiar] = useCopiar();

  return (
    <div className="min-w-0">
      <p className="text-base font-medium">{etiqueta}</p>
      <p className="text-sm leading-snug text-tenue">{ayuda}</p>
      <div className="mt-2 flex items-center gap-2">
        {/* Sin "https://": ocupa lugar y no le dice nada a nadie. Lo que se
            copia es el link completo. Entero y en dos renglones si hace falta,
            no cortado con "…": en 375 px, al lado de "Copiar" no entra en uno,
            y quien lo dicta por teléfono necesita verlo todo. */}
        <code className="min-w-0 flex-1 break-all rounded-xl bg-hundido px-3 py-3 font-mono text-sm leading-snug">
          {valor.replace(/^https?:\/\//, "")}
        </code>
        <BotonChico
          onClick={() => copiar(valor, t.copiarAMano)}
          icono={copiado ? CheckIcon : ClipboardDocumentIcon}
          className="shrink-0"
          aria-live="polite"
        >
          {copiado ? t.copiado : t.copiar}
        </BotonChico>
      </div>
    </div>
  );
}

/**
 * Las tres formas de llevar las fotos a la pared, cada una con su ícono y
 * explicada en una línea: quien organiza no tiene por qué saber qué es un
 * "token de pantalla". Sin publicar, abrir y vincular no andan (el backend no
 * sirve la pantalla de un borrador); copiar el link sí, para dejarlo listo de
 * antemano. Las que no andan llevan el ícono apagado, además del botón.
 */
function ConectarPantalla({ evento }: { evento: EventoAdmin }) {
  const idTitulo = useId();
  const [copiado, copiar] = useCopiar();
  const sinPublicar = evento.estado === "borrador";
  const urlPantalla = `${window.location.origin}/p/${evento.token_pantalla}`;

  function abrir() {
    // Sin tele a mano, cualquier ventana hace de pantalla. Con nombre fijo,
    // un segundo toque reusa la misma ventana en vez de abrir otra.
    window.open(urlPantalla, `pantalla-${evento.token_pantalla}`, "popup,width=1280,height=720");
  }

  return (
    <section aria-labelledby={idTitulo}>
      <h3 id={idTitulo} className="text-base font-semibold">
        {t.pantalla.titulo}
      </h3>
      {sinPublicar ? (
        <p className="mt-0.5 flex items-start gap-2 text-sm leading-5 text-naranja-tinta">
          <ExclamationTriangleIcon aria-hidden className="h-5 w-5 shrink-0" />
          {t.pantalla.sinPublicar}
        </p>
      ) : (
        <p className="text-sm leading-snug text-tenue">{t.pantalla.ayuda}</p>
      )}

      <ul className="mt-3 divide-y divide-borde rounded-2xl border border-borde">
        <Opcion
          icono={ComputerDesktopIcon}
          apagada={sinPublicar}
          titulo={t.pantalla.estaCompu.titulo}
          ayuda={t.pantalla.estaCompu.ayuda}
          accion={
            <BotonChico onClick={abrir} disabled={sinPublicar} icono={ArrowTopRightOnSquareIcon}>
              {t.pantalla.estaCompu.boton}
            </BotonChico>
          }
        />
        <OpcionTele evento={evento} sinPublicar={sinPublicar} />
        <Opcion
          icono={LinkIcon}
          titulo={t.pantalla.otraCompu.titulo}
          ayuda={t.pantalla.otraCompu.ayuda}
          accion={
            <BotonChico
              onClick={() => copiar(urlPantalla, t.copiarAMano)}
              icono={copiado ? CheckIcon : ClipboardDocumentIcon}
              aria-live="polite"
            >
              {copiado ? t.copiado : t.pantalla.otraCompu.boton}
            </BotonChico>
          }
        />
      </ul>
    </section>
  );
}

/** Una fila de "Conectar la pantalla", como las de Ajustes de iOS: el ícono en
 *  su cuadradito, el nombre y una línea de ayuda. En el celular el botón va
 *  debajo y a todo el ancho (más fácil de acertar); desde sm, a la derecha. Lo
 *  de abajo (el código de la tele) también va a todo el ancho: seis dígitos
 *  grandes no entran corridos detrás del ícono en 375 px. */
function Opcion({
  icono: IconoOpcion,
  apagada = false,
  titulo,
  ayuda,
  accion,
  children,
}: {
  icono: Icono;
  /** Sin publicar no anda: el ícono gris en vez de azul. */
  apagada?: boolean;
  titulo: string;
  ayuda: string;
  accion: ReactNode;
  children?: ReactNode;
}) {
  return (
    <li className="p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className={
              "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl " +
              (apagada ? "bg-hundido text-tenue" : "bg-acento/15 text-acento-tinta")
            }
          >
            <IconoOpcion aria-hidden className="h-6 w-6" />
          </span>
          <div className="min-w-0">
            <p className="font-medium">{titulo}</p>
            <p className="text-sm leading-snug text-tenue">{ayuda}</p>
          </div>
        </div>
        {accion && <div className="flex shrink-0 flex-col sm:block">{accion}</div>}
      </div>
      {children}
    </li>
  );
}

/**
 * El código de seis dígitos para vincular una tele.
 *
 * El link de la pantalla mide 68 caracteres. Con una notebook se copia y pega;
 * con el control remoto de una tele es imposible. Esto lo reemplaza por seis
 * dígitos, que es lo único que un control hace bien.
 */
function OpcionTele({ evento, sinPublicar }: { evento: EventoAdmin; sinPublicar: boolean }) {
  const alPerderSesion = useAlPerderSesion();
  const [codigo, setCodigo] = useState<string | null>(null);
  // Cuándo vence, en ms. Se cuenta contra el reloj y no restando de a un
  // segundo: con la pestaña en segundo plano los temporizadores se frenan y
  // la cuenta mentiría.
  const [vence, setVence] = useState<number | null>(null);
  const [, setTic] = useState(0);
  const [vencido, setVencido] = useState(false);
  const [pidiendo, setPidiendo] = useState(false);
  const [falla, setFalla] = useState<string | null>(null);

  useEffect(() => {
    if (vence === null) return;
    const id = window.setInterval(() => {
      if (Date.now() >= vence) {
        setCodigo(null);
        setVence(null);
        setVencido(true);
      } else {
        setTic((n) => n + 1);
      }
    }, 1000);
    return () => window.clearInterval(id);
  }, [vence]);

  async function pedirCodigo() {
    setPidiendo(true);
    setFalla(null);
    setVencido(false);
    try {
      const respuesta = await admin.vincularPantalla(evento.id);
      setCodigo(respuesta.codigo);
      setVence(Date.parse(respuesta.expira_en));
    } catch (e) {
      if (alPerderSesion(e)) return;
      setFalla(mensajeDe(e, t.pantalla.tele.error));
    } finally {
      setPidiendo(false);
    }
  }

  const segundos = vence === null ? 0 : Math.max(0, Math.ceil((vence - Date.now()) / 1000));
  const restante = `${Math.floor(segundos / 60)}:${String(segundos % 60).padStart(2, "0")}`;

  return (
    <Opcion
      icono={TvIcon}
      apagada={sinPublicar}
      titulo={t.pantalla.tele.titulo}
      ayuda={t.pantalla.tele.ayuda}
      accion={
        codigo ? null : (
          <BotonChico onClick={pedirCodigo} cargando={pidiendo} disabled={sinPublicar}>
            {vencido ? t.pantalla.tele.otro : t.pantalla.tele.boton}
          </BotonChico>
        )
      }
    >
      {codigo && (
        <div className="mt-3 rounded-xl bg-hundido p-4 text-center">
          <p className="text-sm leading-snug">
            {t.pantalla.tele.abri}{" "}
            <strong className="break-all font-semibold text-texto">{window.location.host}/p</strong>{" "}
            {t.pantalla.tele.carga}
          </p>
          <p
            className="mt-2 font-mono text-3xl tabular-nums tracking-[0.2em] text-acento sm:text-4xl"
            aria-label={codigo.split("").join(" ")}
          >
            {codigo.slice(0, 3)} {codigo.slice(3)}
          </p>
          <p className="mt-1 text-sm tabular-nums text-tenue">{t.pantalla.tele.vence(restante)}</p>
        </div>
      )}
      {vencido && !codigo && <p className="mt-2 text-sm text-tenue">{t.pantalla.tele.vencido}</p>}
      {falla && (
        <p role="alert" className="mt-2 text-sm text-rojo-tinta">
          {falla}
        </p>
      )}
    </Opcion>
  );
}
