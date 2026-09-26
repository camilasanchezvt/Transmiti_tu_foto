import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { ErrorApi, publico } from "../api/client";
import type { EventoPublico } from "../api/tipos";
import Cargando from "../comp/Cargando";
import Boton from "../comp/Boton";
import { ArchivoInvalido, comprimir, type FotoLista } from "../lib/comprimir";
import { hashDelDispositivo } from "../lib/dispositivo";
import { subirAcloudinary } from "../lib/subir";
import { textos } from "./textos";

/**
 * Qué botón ofrece un error. `reintentar` vuelve a mandar la misma foto (se
 * cortó la señal); `elegir`, otra (la que eligió no sirve); `ninguno` es para
 * cuando no hay nada que hacer (ya mandó todas las que podía): un botón ahí
 * sólo lleva a fallar otra vez después de comprimir.
 */
type AccionDeError = "reintentar" | "elegir" | "ninguno";

type Estado =
  | { paso: "cargando" }
  | { paso: "bienvenida" }
  | { paso: "preparando" }
  | { paso: "subiendo"; porcentaje: number }
  | { paso: "listo" }
  | { paso: "error"; mensaje: string; accion: AccionDeError };

/**
 * Los cuatro estados de la sección 6, en una sola pantalla y sin scroll.
 *
 * El invitado está en un salón oscuro, con una copa en la otra mano y el brillo
 * del celular bajo. Todo el recorrido tiene que salir de dos toques.
 */
export default function PaginaInvitado() {
  const { codigo = "" } = useParams();

  const [evento, setEvento] = useState<EventoPublico | null>(null);
  const [errorEvento, setErrorEvento] = useState<unknown>(null);
  const [intentoCarga, setIntentoCarga] = useState(0);
  const [estado, setEstado] = useState<Estado>({ paso: "cargando" });
  const [nombre, setNombre] = useState("");

  // La foto elegida se guarda para que un error de red no la pierda: el brief
  // pide poder reintentar "sin perder la foto elegida".
  const [foto, setFoto] = useState<FotoLista | null>(null);
  const entrada = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let vigente = true;
    setErrorEvento(null);
    publico
      .evento(codigo)
      .then((e) => {
        if (!vigente) return;
        setEvento(e);
        setEstado({ paso: "bienvenida" });
      })
      .catch((e) => vigente && setErrorEvento(e));
    return () => {
      vigente = false;
    };
  }, [codigo, intentoCarga]);

  // Las vistas previas son URLs de objeto: si no se revocan, mandar diez fotos
  // seguidas deja diez blobs retenidos.
  useEffect(() => {
    return () => {
      if (foto) URL.revokeObjectURL(foto.vistaPrevia);
    };
  }, [foto]);

  async function alElegirArchivo(evento_: React.ChangeEvent<HTMLInputElement>) {
    const archivo = evento_.target.files?.[0];
    // Se limpia el input para que elegir la misma foto dos veces vuelva a
    // disparar el change.
    evento_.target.value = "";
    if (!archivo) return;

    setEstado({ paso: "preparando" });
    try {
      const lista = await comprimir(archivo);
      setFoto(lista);
      await enviar(lista);
    } catch (error) {
      if (error instanceof ArchivoInvalido) {
        setEstado({ paso: "error", mensaje: textos.errorArchivo, accion: "elegir" });
        return;
      }
      setEstado({ paso: "error", mensaje: textos.errorRed, accion: "reintentar" });
    }
  }

  async function enviar(lista: FotoLista) {
    if (!evento) return;
    const dispositivo_hash = hashDelDispositivo();
    setEstado({ paso: "subiendo", porcentaje: 0 });

    try {
      const firma = await publico.firma(codigo, dispositivo_hash);

      const subida = await subirAcloudinary({
        firma,
        blob: lista.blob,
        onProgreso: (porcentaje) => setEstado({ paso: "subiendo", porcentaje }),
      });

      await publico.registrarFoto(codigo, {
        public_id: subida.public_id,
        url: subida.url,
        ancho: subida.ancho,
        alto: subida.alto,
        bytes: subida.bytes,
        dispositivo_hash,
        nombre_invitado: nombre.trim() || null,
      });

      URL.revokeObjectURL(lista.vistaPrevia);
      setFoto(null);
      setEstado({ paso: "listo" });
    } catch (error) {
      // El evento terminó mientras elegía la foto: la pantalla de cierre, con
      // el nombre del evento, en vez de un error con un botón que no sirve.
      if (error instanceof ErrorApi && error.codigo === "EVENTO_CERRADO") {
        setFoto(null);
        setEvento({ ...evento, estado: "cerrado" });
        return;
      }
      setEstado(errorDeEnvio(error, evento));
    }
  }

  function errorDeEnvio(error: unknown, evento_: EventoPublico): Estado {
    if (error instanceof ErrorApi) {
      switch (error.codigo) {
        case "LIMITE_ALCANZADO":
          return {
            paso: "error",
            mensaje: textos.errorLimite(evento_.max_fotos_por_dispositivo),
            accion: "ninguno",
          };
        case "DEMASIADOS_PEDIDOS":
          return { paso: "error", mensaje: textos.errorMuchas, accion: "reintentar" };
        case "ARCHIVO_INVALIDO":
        case "PUBLIC_ID_AJENO":
          return { paso: "error", mensaje: textos.errorArchivo, accion: "elegir" };
        default:
          return { paso: "error", mensaje: textos.errorRed, accion: "reintentar" };
      }
    }
    return { paso: "error", mensaje: textos.errorRed, accion: "reintentar" };
  }

  if (errorEvento) {
    // Sin red o con el evento todavía sin publicar (responde igual que uno que
    // no existe), probar de nuevo en un rato es lo que sirve: sin tener que
    // volver a escanear el QR.
    return (
      <Pantalla>
        <p className="text-2xl leading-snug">{mensajeDeCarga(errorEvento)}</p>
        <Boton variante="secundario" onClick={() => setIntentoCarga((n) => n + 1)}>
          {textos.botonReintentar}
        </Boton>
      </Pantalla>
    );
  }

  if (!evento || estado.paso === "cargando") return <Cargando />;

  if (evento.estado === "cerrado") {
    return (
      <Pantalla>
        <h1 className="text-3xl font-semibold leading-tight">{evento.nombre}</h1>
        <p className="text-xl text-tenue">{textos.eventoCerrado}</p>
      </Pantalla>
    );
  }

  return (
    <Pantalla>
      <input
        ref={entrada}
        type="file"
        accept="image/*"
        // Sin `capture`: así el sistema operativo ofrece cámara Y galería. Con
        // capture fuerza la cámara, y si el invitado no dio permiso se queda sin
        // poder mandar nada.
        onChange={alElegirArchivo}
        className="hidden"
      />

      {estado.paso === "bienvenida" && (
        <>
          <p className="text-tenue">{evento.nombre}</p>
          <h1 className="text-3xl font-semibold leading-tight">{textos.bienvenida}</h1>
          <label className="mt-2 w-full text-left text-sm text-tenue">
            {textos.etiquetaNombre}
            <input
              type="text"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder={textos.ejemploNombre}
              maxLength={80}
              className="mt-1 min-h-boton w-full rounded-2xl border border-borde bg-hundido px-4 text-lg text-white outline-none focus:border-acento"
            />
          </label>
          <Boton onClick={() => entrada.current?.click()}>{textos.botonPrincipal}</Boton>
        </>
      )}

      {estado.paso === "preparando" && (
        <>
          <VistaPrevia foto={foto} />
          <p className="text-xl">{textos.preparando}</p>
        </>
      )}

      {estado.paso === "subiendo" && (
        <>
          <VistaPrevia foto={foto} />
          <p className="text-xl tabular-nums">{textos.subiendo(estado.porcentaje)}</p>
          <div
            className="h-3 w-full overflow-hidden rounded-full bg-hundido"
            role="progressbar"
            aria-valuenow={estado.porcentaje}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div
              className="h-full rounded-full bg-acento transition-[width] duration-200"
              style={{ width: `${estado.porcentaje}%` }}
            />
          </div>
        </>
      )}

      {estado.paso === "listo" && (
        <>
          <Tilde />
          <h1 className="text-3xl font-semibold">{textos.listoTitulo}</h1>
          <p className="text-xl text-tenue">{textos.listoDetalle}</p>
          <Boton onClick={() => entrada.current?.click()}>{textos.botonOtra}</Boton>
        </>
      )}

      {estado.paso === "error" && (
        <>
          <VistaPrevia foto={foto} />
          <p className="text-xl leading-snug">{estado.mensaje}</p>
          {estado.accion === "reintentar" && foto ? (
            <Boton onClick={() => enviar(foto)}>{textos.botonReintentar}</Boton>
          ) : estado.accion !== "ninguno" ? (
            <Boton variante="secundario" onClick={() => entrada.current?.click()}>
              {textos.botonPrincipal}
            </Boton>
          ) : null}
        </>
      )}
    </Pantalla>
  );
}

/** Centrado, en una tarjeta de vidrio, y el botón siempre al alcance del
 *  pulgar. Si la pantalla es muy baja (celular acostado) scrollea en vez de
 *  cortar el botón. */
function Pantalla({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto flex min-h-full max-w-md flex-col items-center justify-center p-4 sm:p-6">
      <div className="flex w-full flex-col items-center gap-5 rounded-3xl border border-borde bg-panel p-6 text-center">
        {children}
      </div>
    </main>
  );
}

/** Si el evento no abre. */
function mensajeDeCarga(error: unknown): string {
  if (!(error instanceof ErrorApi) || error.esDeRed) return textos.errorCarga;
  if (error.codigo === "EVENTO_NO_ENCONTRADO") return textos.eventoNoEncontrado;
  return error.message;
}

/** El tilde verde de iOS y no un emoji: los emojis se ven distinto en cada
 *  celular, y unas chispitas dicen poco de que la foto llegó. */
function Tilde() {
  return (
    <svg viewBox="0 0 24 24" className="h-16 w-16 text-verde" aria-hidden>
      <circle cx="12" cy="12" r="12" fill="currentColor" />
      <path
        d="M7 12.4l3.3 3.3L17 9"
        fill="none"
        stroke="white"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function VistaPrevia({ foto }: { foto: FotoLista | null }) {
  if (!foto) return null;
  return (
    <img
      src={foto.vistaPrevia}
      alt=""
      className="max-h-[40vh] w-auto rounded-2xl object-contain"
    />
  );
}
