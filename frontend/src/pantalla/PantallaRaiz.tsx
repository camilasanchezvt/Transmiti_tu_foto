import { useState } from "react";

import { pantallaGuardada } from "../api/client";
import PaginaPantalla from "./PaginaPantalla";
import PaginaVincular from "./PaginaVincular";

/**
 * `/p` sin token: la ruta corta que se carga en una tele.
 *
 * Si ya se vinculó alguna vez, el token quedó guardado y la pantalla arranca
 * sola. Es lo que hace que reiniciar la tele no obligue a vincular de nuevo.
 */
export default function PantallaRaiz() {
  const [token, setToken] = useState<string | null>(() => pantallaGuardada());

  if (!token) return <PaginaVincular onVinculada={setToken} />;
  return <PaginaPantalla tokenVinculado={token} />;
}
