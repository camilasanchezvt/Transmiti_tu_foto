import { BrowserRouter, Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";

import PaginaInvitado from "./invitado/PaginaInvitado";
import PaginaPantalla from "./pantalla/PaginaPantalla";
import PantallaRaiz from "./pantalla/PantallaRaiz";
import PaginaLogin from "./admin/PaginaLogin";
import PaginaRegistro from "./admin/PaginaRegistro";
import PaginaEventos from "./admin/PaginaEventos";
import PaginaHistorial from "./admin/PaginaHistorial";
import PaginaCuentas from "./admin/PaginaCuentas";
import PaginaRevisar from "./admin/PaginaRevisar";
import PaginaAjustes from "./admin/PaginaAjustes";
import { textosBase } from "./comp/textos";

/**
 * Una sola SPA con tres zonas que no se cruzan:
 *   /e/:codigo   invitado, celular, salón oscuro
 *   /p           pantalla sin token: pide un código de seis dígitos. Es la ruta
 *                corta para cargar en una tele con el control remoto.
 *   /p/:token    pantalla, corre sola durante horas
 *   /admin/*     panel, notebook o celular, con apuro
 *
 * En el panel:
 *   /admin/login, /admin/registro       sin sesión
 *   /admin                              eventos vigentes
 *   /admin/historial                    terminados o con fecha pasada
 *   /admin/cuentas                      sólo admin
 *   /admin/eventos/:id/revisar          pantalla completa, sin la barra
 *   /admin/eventos/:id/ajustes
 */
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/e/:codigo" element={<PaginaInvitado />} />
        <Route path="/p" element={<PantallaRaiz />} />
        <Route path="/p/:token" element={<PaginaPantalla />} />

        <Route path="/admin/login" element={<PaginaLogin />} />
        <Route path="/admin/registro" element={<PaginaRegistro />} />
        <Route path="/admin" element={<PaginaEventos />} />
        <Route path="/admin/historial" element={<PaginaHistorial />} />
        <Route path="/admin/cuentas" element={<PaginaCuentas />} />
        <Route path="/admin/eventos/:id/revisar" element={<PaginaRevisar />} />
        <Route path="/admin/eventos/:id/ajustes" element={<PaginaAjustes />} />

        {/* Las rutas de antes del cambio de nombres. Hay links viejos guardados
            en favoritos y en pestañas abiertas: que sigan llevando al lugar. */}
        <Route path="/admin/eventos/:id/moderar" element={<RedirigirEvento a="revisar" />} />
        <Route path="/admin/eventos/:id/cierre" element={<RedirigirEvento a="ajustes" />} />

        <Route path="/" element={<Navigate to="/admin" replace />} />
        <Route path="*" element={<NoExiste />} />
      </Routes>
    </BrowserRouter>
  );
}

function RedirigirEvento({ a }: { a: "revisar" | "ajustes" }) {
  const { id = "" } = useParams();
  const { search, hash } = useLocation();
  return <Navigate to={`/admin/eventos/${encodeURIComponent(id)}/${a}${search}${hash}`} replace />;
}

function NoExiste() {
  return (
    <main className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
      <h1 className="text-2xl font-semibold">{textosBase.noExiste.titulo}</h1>
      <p className="text-tenue">{textosBase.noExiste.texto}</p>
    </main>
  );
}
