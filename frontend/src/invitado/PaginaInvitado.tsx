import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { publico } from "../api/client";
import type { EventoPublico } from "../api/tipos";
import Cargando from "../comp/Cargando";
import MensajeError from "../comp/MensajeError";

/** FASE 5: pantalla mínima. Los cuatro estados y la subida llegan en la Fase 6. */
export default function PaginaInvitado() {
  const { codigo = "" } = useParams();
  const [evento, setEvento] = useState<EventoPublico | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [intento, setIntento] = useState(0);

  useEffect(() => {
    let vigente = true;
    setError(null);
    setEvento(null);
    publico
      .evento(codigo)
      .then((e) => vigente && setEvento(e))
      .catch((e) => vigente && setError(e));
    return () => {
      vigente = false;
    };
  }, [codigo, intento]);

  if (error) return <MensajeError error={error} onReintentar={() => setIntento((n) => n + 1)} />;
  if (!evento) return <Cargando />;

  return (
    <main className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
      <p className="text-tenue">{evento.estado === "cerrado" ? "Este evento ya terminó" : "Estás en"}</p>
      <h1 className="text-3xl font-semibold leading-tight">{evento.nombre}</h1>
    </main>
  );
}
