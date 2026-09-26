import { Outlet } from "react-router-dom";

import { useSiempreOscuro } from "../lib/tema";

/**
 * Ruta de diseño para las zonas que no siguen el tema del panel: el invitado
 * y la pantalla. Todo lo que cuelga de ella se ve en oscuro, elija lo que
 * elija quien organiza (App.tsx):
 *
 *   <Route element={<SiempreOscuro />}>
 *     <Route path="/e/:codigo" element={<PaginaInvitado />} />
 *   </Route>
 *
 * Si se agrega una ruta de esas zonas, va adentro. El script de index.html
 * tiene la misma lista para el primer cuadro (/e/… y /p/…).
 */
export default function SiempreOscuro() {
  useSiempreOscuro();
  return <Outlet />;
}
