import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { ErrorApi, guardarPantalla } from "../api/client";
import Boton from "../comp/Boton";
import Cargando from "../comp/Cargando";
import Confirmar from "../comp/Confirmar";
import QR from "./QR";
import { textos } from "./textos";
import { FUNDIDO_MS, useCola } from "./useCola";

/** Cada cuánto vuelve a probar sola una pantalla que no pudo arrancar. */
const REINTENTO_SOLO_S = 30;

interface Props {
  /** Cuando se llegó por `/p` y la tele ya estaba vinculada. */
  tokenVinculado?: string;
}

/**
 * La pantalla de proyección. Corre sola durante horas.
 *
 * Reintentar es volver a montar la proyección entera, con una cola nueva, y no
 * recargar la página: si lo que falló es la red, un reload deja la tele en la
 * página de error del navegador, que ya no se recupera sola.
 */
export default function PaginaPantalla(props: Props = {}) {
  const [intento, setIntento] = useState(0);
  const reintentar = useCallback(() => setIntento((n) => n + 1), []);
  return <Proyeccion key={intento} {...props} onReintentar={reintentar} />;
}

/**
 * Cinco estados: esperando, pasando fotos, llegó una nueva, sin conexión y
 * evento cerrado. Y uno más antes de todos: no pudo arrancar.
 */
function Proyeccion({ tokenVinculado, onReintentar }: Props & { onReintentar: () => void }) {
  const { token: enLaUrl = "" } = useParams();
  const token = tokenVinculado ?? enLaUrl;
  const { cargando, error, datos, foto, anterior, hayFotos, sinConexion, llegaron } =
    useCola(token);

  // Arranca con lo que ya está: al reintentar se vuelve a montar, y la ventana
  // puede seguir en pantalla completa desde antes.
  const [pantallaCompleta, setPantallaCompleta] = useState(() =>
    Boolean(document.fullscreenElement),
  );
  const [confirmando, setConfirmando] = useState(false);
  const contenedor = useRef<HTMLDivElement>(null);

  // Si el navegador no sabe ponerse en pantalla completa (el iPhone, muchas
  // teles), no se promete: el aviso se quedaría arriba toda la noche.
  const sePuedeCompleta = document.fullscreenEnabled === true;

  const entrarAcompleta = useCallback(() => {
    const nodo = contenedor.current ?? document.documentElement;
    nodo.requestFullscreen?.().catch(() => {
      /* el navegador puede negarlo si no vino de un gesto */
    });
  }, []);

  useEffect(() => {
    const alCambiar = () => setPantallaCompleta(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", alCambiar);
    return () => document.removeEventListener("fullscreenchange", alCambiar);
  }, []);

  // Si alguien sale con Escape, se vuelve a entrar con cualquier tecla o click.
  // Con la pregunta de desconectar abierta, no: el diálogo vive fuera del
  // contenedor y quedaría escondido detrás de la pantalla completa.
  useEffect(() => {
    if (pantallaCompleta || confirmando) return;
    const alInteractuar = () => entrarAcompleta();
    window.addEventListener("keydown", alInteractuar);
    window.addEventListener("click", alInteractuar);
    return () => {
      window.removeEventListener("keydown", alInteractuar);
      window.removeEventListener("click", alInteractuar);
    };
  }, [pantallaCompleta, confirmando, entrarAcompleta]);

  // El nombre del evento en el título: con dos pantallas vinculadas, es lo que
  // las distingue al ir a buscar cuál desvincular.
  useEffect(() => {
    if (datos) document.title = textos.pestana(datos.evento.nombre);
  }, [datos]);

  // Que la notebook no se suspenda a mitad del evento.
  useEffect(() => {
    let bloqueo: WakeLockSentinel | null = null;
    let cancelado = false;

    const pedir = async () => {
      try {
        bloqueo = await navigator.wakeLock?.request("screen");
      } catch {
        /* no está en todos los navegadores, y no es motivo para no andar */
      }
    };
    pedir();

    // El bloqueo se pierde si la pestaña pasa a segundo plano. Se vuelve a pedir.
    const alVolver = () => {
      if (!cancelado && document.visibilityState === "visible") pedir();
    };
    document.addEventListener("visibilitychange", alVolver);

    return () => {
      cancelado = true;
      document.removeEventListener("visibilitychange", alVolver);
      bloqueo?.release().catch(() => {});
    };
  }, []);

  if (error) {
    return (
      <NoArranca error={error} conectada={Boolean(tokenVinculado)} onReintentar={onReintentar} />
    );
  }
  if (cargando || !datos) return <Cargando texto={textos.preparando} />;

  const cerrado = datos.evento.estado === "cerrado";
  const urlDelQr = `${window.location.origin}/e/${datos.evento.codigo_publico}`;
  const mostrarAviso = !pantallaCompleta && sePuedeCompleta;

  return (
    <div
      ref={contenedor}
      className="relative h-full w-full overflow-hidden bg-fondo"
      // Corre sola: el mouse no tiene nada que hacer acá.
      style={{ cursor: pantallaCompleta ? "none" : "pointer" }}
    >
      {/* ── Pasando fotos ─────────────────────────────────── */}
      {hayFotos && foto && (
        <>
          {/* La key es la foto: la que sale sigue siendo la misma capa que
              estaba en pantalla, sin volver a cargar la imagen. useCola la
              retira al terminar el fundido, así la que entra siempre se monta
              nueva, transparente, aunque sea la que acaba de salir. */}
          {anterior && <Capa key={anterior.id} url={anterior.url} />}
          <Capa key={foto.id} url={foto.url} apareciendo />
          {/* Centrado con inset-x-0 + mx-auto + w-fit y no con left-1/2: un
              absoluto que arranca en la mitad sólo tiene la otra mitad para
              crecer, y el max-w nunca llegaba a aplicarse. En un celular va
              más arriba: abajo no entra al lado del QR y de Desconectar. */}
          {foto.nombre_invitado && (
            <p className="vidrio-oscuro absolute inset-x-0 bottom-36 mx-auto w-fit max-w-[80%] truncate rounded-full px-5 py-2 text-lg text-white sm:bottom-10 sm:px-6 sm:text-2xl">
              {foto.nombre_invitado}
            </p>
          )}
        </>
      )}

      {/* ── Esperando: QR enorme en el centro ─────────────── */}
      {!hayFotos && !cerrado && (
        <div className="flex h-full flex-col items-center justify-center gap-6 px-6 text-center sm:gap-10">
          <div className="rounded-[2rem] border border-borde bg-panel p-4 sm:p-6">
            <QR url={urlDelQr} lado={520} className="w-[min(38vmin,70vw)] max-w-none p-4" />
          </div>
          <p className="text-2xl font-semibold sm:text-4xl">{textos.esperando}</p>
        </div>
      )}

      {/* ── Evento cerrado sin fotos ──────────────────────── */}
      {!hayFotos && cerrado && (
        <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
          <h1 className="px-6 text-3xl font-semibold sm:text-5xl">{datos.evento.nombre}</h1>
          <p className="text-xl text-tenue sm:text-3xl">{textos.gracias}</p>
        </div>
      )}

      {/* ── QR chico, en una esquina fija. Desaparece al cerrar ── */}
      {hayFotos && !cerrado && (
        <div className="vidrio-oscuro absolute bottom-4 right-4 flex flex-col items-center gap-2 rounded-2xl p-2 sm:bottom-8 sm:right-8 sm:p-3">
          <QR url={urlDelQr} lado={220} className="w-[max(13vmin,64px)] p-2" />
          <p className="text-xs text-white/80 sm:text-sm">{textos.mandaLaTuya}</p>
        </div>
      )}

      {hayFotos && cerrado && (
        <p className="vidrio-oscuro absolute bottom-4 right-4 rounded-full px-4 py-2 text-base text-white/90 sm:bottom-8 sm:right-8 sm:px-5 sm:text-xl">
          {textos.gracias}
        </p>
      )}

      {/* ── Llegó una nueva: marca discreta y breve ─────────
          Con el aviso de pantalla completa arriba, baja: en un celular o una
          ventana chica se pisarían. */}
      {llegaron > 0 && hayFotos && (
        <div
          className={
            "pointer-events-none absolute left-4 animate-pulse rounded-full bg-acento px-4 py-2 text-base font-semibold text-white shadow-lg sm:left-8 sm:px-5 sm:text-lg " +
            (mostrarAviso ? "top-20 sm:top-24" : "top-4 sm:top-8")
          }
        >
          {textos.llegaron(llegaron)}
        </div>
      )}

      {/* ── Sin conexión: indicador mínimo, sin frenar el pase ── */}
      {sinConexion && (
        <div
          role="img"
          className="absolute right-3 top-3 h-3 w-3 rounded-full bg-naranja/80 sm:right-8 sm:top-8"
          title={textos.sinConexion}
          aria-label={textos.sinConexion}
        />
      )}

      {mostrarAviso && (
        <p className="vidrio-oscuro absolute inset-x-0 top-4 mx-auto w-fit max-w-[90%] rounded-3xl px-5 py-2 text-center text-sm text-white/70 sm:top-8">
          {textos.pantallaCompleta}
        </p>
      )}

      {/* Mientras no está en pantalla completa se ve, y en una tele el control
          puede caer encima sin querer: por eso pregunta antes. Volver a
          conectarla pide un código nuevo del panel. */}
      {tokenVinculado && !pantallaCompleta && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setConfirmando(true);
          }}
          className="vidrio-oscuro absolute bottom-4 left-4 inline-flex min-h-11 items-center rounded-full px-4 text-sm text-white/60 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-acento sm:bottom-8 sm:left-8"
        >
          {textos.desconectar}
        </button>
      )}

      <Confirmar
        abierto={confirmando}
        titulo={textos.confirmarDesconectar.titulo}
        mensaje={textos.confirmarDesconectar.mensaje}
        textoConfirmar={textos.confirmarDesconectar.confirmar}
        peligro
        onConfirmar={desconectar}
        onCancelar={() => setConfirmando(false)}
      />
    </div>
  );
}

/** Se olvida el token guardado y la tele vuelve a pedir el código. */
function desconectar() {
  guardarPantalla(null);
  window.location.reload();
}

type Falla = "borrador" | "sinRed" | "noEncontrado" | "otra";

function queFallo(error: unknown): Falla {
  if (!(error instanceof ErrorApi)) return "otra";
  if (error.codigo === "EVENTO_BORRADOR") return "borrador";
  if (error.codigo === "EVENTO_NO_ENCONTRADO") return "noEncontrado";
  if (error.esDeRed || error.http >= 500) return "sinRed";
  return "otra";
}

/**
 * La pantalla no pudo arrancar. Lo ve casi siempre quien la está preparando,
 * así que cada caso dice qué hacer.
 *
 * Sin red y sin publicar se reintenta solo: la notebook del proyector suele
 * quedar armada antes de que alguien publique el evento o de que el wifi del
 * salón ande, y nadie vuelve a tocarla. Un evento que no existe no se arregla
 * esperando: ahí no insiste.
 */
function NoArranca({
  error,
  conectada,
  onReintentar,
}: {
  error: unknown;
  conectada: boolean;
  onReintentar: () => void;
}) {
  const falla = queFallo(error);
  const reintentaSola = falla === "sinRed" || falla === "borrador";
  const e = textos.errores;

  useEffect(() => {
    if (!reintentaSola) return;
    const id = window.setTimeout(onReintentar, REINTENTO_SOLO_S * 1000);
    return () => window.clearTimeout(id);
  }, [reintentaSola, onReintentar]);

  let titulo: string;
  let detalle: string | null = null;
  switch (falla) {
    case "borrador":
      titulo = e.borradorTitulo;
      detalle = e.borradorDetalle;
      break;
    case "sinRed":
      titulo = e.sinRedTitulo;
      detalle = e.sinRedDetalle(REINTENTO_SOLO_S);
      break;
    case "noEncontrado":
      titulo = e.noEncontradoTitulo;
      detalle = conectada ? e.noEncontradoConectada : e.noEncontradoLink;
      break;
    default:
      titulo = error instanceof ErrorApi ? error.message : e.generico;
  }

  return (
    <main className="flex min-h-full flex-col items-center justify-center gap-4 p-6 text-center sm:gap-6 sm:p-10">
      <h1 className="max-w-3xl text-2xl font-semibold leading-tight sm:text-5xl">{titulo}</h1>
      {detalle && (
        <p className="max-w-2xl text-lg leading-snug text-tenue sm:text-2xl">{detalle}</p>
      )}
      <div className="mt-2 w-full max-w-xs">
        {falla === "noEncontrado" && conectada ? (
          <Boton onClick={desconectar}>{textos.desconectar}</Boton>
        ) : (
          <Boton variante="secundario" onClick={onReintentar}>
            {reintentaSola ? e.probarAhora : e.probarDeNuevo}
          </Boton>
        )}
      </div>
    </main>
  );
}

/**
 * Una foto a pantalla completa. Nunca se deforma: entra completa y centrada, y
 * el espacio que sobra se llena con la misma imagen ampliada y desenfocada.
 */
function Capa({ url, apareciendo = false }: { url: string; apareciendo?: boolean }) {
  const [visible, setVisible] = useState(!apareciendo);

  useEffect(() => {
    if (!apareciendo) return;
    // Un cuadro de retraso para que el navegador registre la opacidad inicial y
    // la transición se vea. Sin esto aparece de golpe.
    const id = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(id);
  }, [apareciendo]);

  return (
    <div
      className="absolute inset-0 transition-opacity ease-in-out"
      style={{ opacity: visible ? 1 : 0, transitionDuration: `${FUNDIDO_MS}ms` }}
    >
      <div
        aria-hidden
        className="absolute inset-0 scale-110 bg-cover bg-center blur-3xl brightness-[0.35]"
        style={{ backgroundImage: `url(${JSON.stringify(url)})` }}
      />
      <img src={url} alt="" className="relative h-full w-full object-contain" />
    </div>
  );
}
