import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { pantalla } from "../api/client";
import type { Pantalla } from "../api/tipos";
import Cargando from "../comp/Cargando";
import MensajeError from "../comp/MensajeError";

/** FASE 5: pantalla mínima. La cola, el QR y la pantalla completa llegan en la Fase 7. */
export default function PaginaPantalla() {
  const { token = "" } = useParams();
  const [datos, setDatos] = useState<Pantalla | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let vigente = true;
    pantalla
      .config(token)
      .then((d) => vigente && setDatos(d))
      .catch((e) => vigente && setError(e));
    return () => {
      vigente = false;
    };
  }, [token]);

  if (error) return <MensajeError error={error} />;
  if (!datos) return <Cargando texto="Preparando la pantalla…" />;

  return (
    <main className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="text-5xl font-semibold leading-tight">{datos.evento.nombre}</h1>
      <p className="text-tenue">
        {datos.evento.estado === "cerrado" ? "El evento terminó" : "Esperando las primeras fotos"}
      </p>
    </main>
  );
}
