import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { admin } from "../api/client";
import Boton from "../comp/Boton";
import MensajeError from "../comp/MensajeError";

/** FASE 5: formulario mínimo. El panel completo llega en la Fase 8. */
export default function PaginaLogin() {
  const navegar = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [enviando, setEnviando] = useState(false);

  async function entrar(evento: FormEvent) {
    evento.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      await admin.login({ email, password });
      navegar("/admin");
    } catch (e) {
      setError(e);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-full max-w-sm flex-col justify-center gap-6 p-4 sm:p-8">
      <form onSubmit={entrar} className="flex flex-col gap-4 rounded-3xl border border-borde bg-panel p-6">
        <h1 className="mb-2 text-2xl font-semibold">Panel</h1>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email"
          autoComplete="username"
          required
          className="min-h-boton rounded-2xl border border-borde bg-hundido px-4 text-lg outline-none focus:border-acento"
        />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Contraseña"
          autoComplete="current-password"
          required
          className="min-h-boton rounded-2xl border border-borde bg-hundido px-4 text-lg outline-none focus:border-acento"
        />
        <Boton type="submit" cargando={enviando}>
          Entrar
        </Boton>
      </form>
      {error != null && <MensajeError error={error} />}
    </main>
  );
}
