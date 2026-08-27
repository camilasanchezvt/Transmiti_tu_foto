import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import PaginaInvitado from "./invitado/PaginaInvitado";
import PaginaPantalla from "./pantalla/PaginaPantalla";
import PaginaLogin from "./admin/PaginaLogin";
import PaginaEventos from "./admin/PaginaEventos";
import PaginaModerar from "./admin/PaginaModerar";
import PaginaCierre from "./admin/PaginaCierre";

/**
 * Una sola SPA con tres zonas que no se cruzan:
 *   /e/:codigo   invitado, celular, salón oscuro
 *   /p/:token    pantalla, corre sola durante horas
 *   /admin/*     panel, notebook, con apuro
 */
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/e/:codigo" element={<PaginaInvitado />} />
        <Route path="/p/:token" element={<PaginaPantalla />} />

        <Route path="/admin/login" element={<PaginaLogin />} />
        <Route path="/admin" element={<PaginaEventos />} />
        <Route path="/admin/eventos/:id/moderar" element={<PaginaModerar />} />
        <Route path="/admin/eventos/:id/cierre" element={<PaginaCierre />} />

        <Route path="/" element={<Navigate to="/admin" replace />} />
        <Route path="*" element={<NoExiste />} />
      </Routes>
    </BrowserRouter>
  );
}

function NoExiste() {
  return (
    <main className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
      <h1 className="text-2xl font-semibold">No encontramos esta página</h1>
      <p className="text-tenue">Revisá el link o escaneá el código otra vez.</p>
    </main>
  );
}
