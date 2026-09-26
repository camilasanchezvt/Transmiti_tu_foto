import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { guardarPantalla } from "../api/client";
import Cargando from "../comp/Cargando";
import MensajeError from "../comp/MensajeError";
import QR from "./QR";
import { useCola } from "./useCola";

/** Fundido entre fotos. */
const FUNDIDO_MS = 700;

/**
 * La pantalla de proyección. Corre sola durante horas.
 *
 * Cinco estados: esperando, pasando fotos, llegó una nueva, sin conexión y
 * evento cerrado.
 */
interface Props {
  /** Cuando se llegó por `/p` y la tele ya estaba vinculada. */
  tokenVinculado?: string;
}

export default function PaginaPantalla({ tokenVinculado }: Props = {}) {
  const { token: enLaUrl = "" } = useParams();
  const token = tokenVinculado ?? enLaUrl;
  const { cargando, error, datos, foto, anterior, hayFotos, sinConexion, llegaron } =
    useCola(token);

  const [pantallaCompleta, setPantallaCompleta] = useState(false);
  const contenedor = useRef<HTMLDivElement>(null);

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
  useEffect(() => {
    if (pantallaCompleta) return;
    const alInteractuar = () => entrarAcompleta();
    window.addEventListener("keydown", alInteractuar);
    window.addEventListener("click", alInteractuar);
    return () => {
      window.removeEventListener("keydown", alInteractuar);
      window.removeEventListener("click", alInteractuar);
    };
  }, [pantallaCompleta, entrarAcompleta]);

  // El nombre del evento en el título: con dos pantallas vinculadas, es lo que
  // las distingue al ir a buscar cuál desvincular.
  useEffect(() => {
    if (datos) document.title = `${datos.evento.nombre} · Pantalla`;
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

  if (error) return <MensajeError error={error} />;
  if (cargando || !datos) return <Cargando texto="Preparando la pantalla…" />;

  const cerrado = datos.evento.estado === "cerrado";
  const urlDelQr = `${window.location.origin}/e/${datos.evento.codigo_publico}`;

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
          {anterior && <Capa key={anterior.id} url={anterior.url} />}
          <Capa key={foto.id} url={foto.url} apareciendo />
          {foto.nombre_invitado && (
            <p className="vidrio-oscuro absolute bottom-6 left-1/2 max-w-[80%] -translate-x-1/2 truncate rounded-full px-5 py-2 text-lg text-white sm:bottom-10 sm:px-6 sm:text-2xl">
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
          <p className="text-2xl font-semibold sm:text-4xl">Mandá tu foto y aparece acá</p>
        </div>
      )}

      {/* ── Evento cerrado sin fotos ──────────────────────── */}
      {!hayFotos && cerrado && (
        <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
          <h1 className="px-6 text-3xl font-semibold sm:text-5xl">{datos.evento.nombre}</h1>
          <p className="text-xl text-tenue sm:text-3xl">¡Gracias por las fotos!</p>
        </div>
      )}

      {/* ── QR chico, en una esquina fija. Desaparece al cerrar ── */}
      {hayFotos && !cerrado && (
        <div className="vidrio-oscuro absolute bottom-4 right-4 flex flex-col items-center gap-2 rounded-2xl p-2 sm:bottom-8 sm:right-8 sm:p-3">
          <QR url={urlDelQr} lado={220} className="w-[max(13vmin,64px)] p-2" />
          <p className="text-xs text-white/80 sm:text-sm">Mandá la tuya</p>
        </div>
      )}

      {hayFotos && cerrado && (
        <p className="vidrio-oscuro absolute bottom-4 right-4 rounded-full px-4 py-2 text-base text-white/90 sm:bottom-8 sm:right-8 sm:px-5 sm:text-xl">
          ¡Gracias por las fotos!
        </p>
      )}

      {/* ── Llegó una nueva: marca discreta y breve ───────── */}
      {llegaron > 0 && hayFotos && (
        <div className="pointer-events-none absolute left-4 top-4 animate-pulse rounded-full bg-acento px-4 py-2 text-base font-semibold text-white shadow-lg sm:left-8 sm:top-8 sm:px-5 sm:text-lg">
          {llegaron === 1 ? "Llegó una foto nueva" : `Llegaron ${llegaron} fotos nuevas`}
        </div>
      )}

      {/* ── Sin conexión: indicador mínimo, sin frenar el pase ── */}
      {sinConexion && (
        <div
          className="absolute right-8 top-8 h-3 w-3 rounded-full bg-naranja/80"
          title="Sin conexión con el servidor"
          aria-label="Sin conexión con el servidor"
        />
      )}

      {!pantallaCompleta && (
        <p className="vidrio-oscuro absolute left-1/2 top-4 max-w-[90%] -translate-x-1/2 rounded-full px-5 py-2 text-center text-sm text-white/70 sm:top-8">
          Tocá cualquier tecla para pantalla completa
        </p>
      )}

      {tokenVinculado && !pantallaCompleta && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            guardarPantalla(null);
            window.location.reload();
          }}
          className="vidrio-oscuro absolute bottom-4 left-4 rounded-full px-4 py-2 text-sm text-white/60 hover:text-white sm:bottom-8 sm:left-8"
        >
          Desvincular esta pantalla
        </button>
      )}
    </div>
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
