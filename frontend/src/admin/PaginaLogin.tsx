import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { ErrorApi, admin, tokenDeSesion } from "../api/client";
import Boton from "../comp/Boton";
import { Aviso, AvisoDeError, Campo, MarcoAcceso, PieAcceso } from "./PiezasAcceso";
import { acceso } from "./textos/acceso";
import { comun } from "./textos/comun";
import { olvidarSesion } from "./useSesion";

/**
 * Entrar al panel. Sin LayoutAdmin: quien llega acá todavía no tiene sesión.
 *
 * Los mensajes de error se muestran tal cual los manda el backend:
 * - 401: email o contraseña incorrectos, o una cuenta que todavía no
 *   habilitaron. Es UN solo mensaje para los dos casos, a propósito: si la
 *   pendiente tuviera uno propio, crear una cuenta y después probar entrar
 *   diría qué emails ya estaban registrados.
 * - 403: cuenta dada de baja (sólo con la contraseña correcta).
 * - 429: demasiados intentos seguidos.
 *
 * Debajo del botón, "¿Olvidaste tu contraseña?" lleva a /admin/olvide con el
 * email que ya estaba escrito, así no hay que escribirlo dos veces. Viaja en
 * el estado del historial y no en la dirección. De vuelta de Olvidé, llega
 * igual y el campo aparece completo.
 */
export default function PaginaLogin() {
  const navegar = useNavigate();
  const ubicacion = useLocation();
  const idTitulo = useId();
  const [email, setEmail] = useState(() => emailRecibido(ubicacion.state));
  const [password, setPassword] = useState("");
  const [faltanDatos, setFaltanDatos] = useState(false);
  const [error, setError] = useState<unknown>(null);
  // Cambia en cada fracaso para que el aviso se vuelva a montar: si el mensaje
  // es el mismo que el anterior, un lector de pantalla igual lo anuncia.
  const [intento, setIntento] = useState(0);
  const [enviando, setEnviando] = useState(false);
  const refEmail = useRef<HTMLInputElement>(null);
  const refPassword = useRef<HTMLInputElement>(null);
  const refAviso = useRef<HTMLParagraphElement>(null);
  // Cuando alguien ya tocó Entrar, la verificación de la sesión anterior (que
  // puede tardar si el servidor estaba dormido) llega tarde y no decide nada.
  const yaIntentoEntrar = useRef(false);

  useEffect(() => {
    document.title = comun.tituloPestana(acceso.entrar.tituloPestana);
  }, []);

  // Si ya hay una sesión que sirve, este formulario sobra. Se pregunta al
  // backend y no se mira sólo si hay token: uno vencido o de una cuenta dada
  // de baja mandaría a /admin, y de ahí useSesion lo devolvería acá.
  useEffect(() => {
    if (!tokenDeSesion()) return;
    let vivo = true;
    admin.yo().then(
      () => {
        if (vivo && !yaIntentoEntrar.current) navegar("/admin", { replace: true });
      },
      (e: unknown) => {
        // Un 401 es un token que ya no sirve: se tira. Sin red, no se sabe;
        // queda el formulario y el que entre pisa el token.
        if (vivo && !yaIntentoEntrar.current && e instanceof ErrorApi && e.esSinSesion) {
          olvidarSesion();
        }
      },
    );
    return () => {
      vivo = false;
    };
  }, [navegar]);

  // Al fallar, el teclado del celular tapa el aviso, que está abajo del
  // último campo. Se cierra el teclado y se lleva el aviso a la vista.
  useEffect(() => {
    if (error == null) return;
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    refAviso.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [error, intento]);

  async function entrar(evento: FormEvent) {
    evento.preventDefault();
    if (enviando) return;
    setError(null);

    const emailLimpio = email.trim();
    if (!emailLimpio || !password) {
      setFaltanDatos(true);
      (emailLimpio ? refPassword : refEmail).current?.focus();
      return;
    }

    setFaltanDatos(false);
    setEnviando(true);
    yaIntentoEntrar.current = true;
    // olvidarSesion() borra lo que useSesion recordaba de la cuenta anterior Y
    // el token. Por eso va ANTES del login: después borraría el token nuevo.
    olvidarSesion();
    try {
      await admin.login({ email: emailLimpio, password });
      navegar("/admin", { replace: true });
    } catch (e) {
      setError(e);
      setIntento((n) => n + 1);
      setEnviando(false);
    }
  }

  return (
    <MarcoAcceso>
      <form
        onSubmit={entrar}
        noValidate
        aria-labelledby={idTitulo}
        className="flex flex-col gap-4 rounded-3xl border border-borde bg-panel p-5 sm:p-6"
      >
        <header className="mb-1 flex flex-col gap-1 text-center">
          <h1 id={idTitulo} className="text-2xl font-semibold tracking-tight">
            {acceso.marca}
          </h1>
          <p className="text-base text-tenue">{acceso.entrar.subtitulo}</p>
        </header>

        <Campo
          etiqueta={acceso.campos.email}
          refCampo={refEmail}
          type="email"
          name="email"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            setFaltanDatos(false);
          }}
          autoComplete="username"
          inputMode="email"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          maxLength={254}
        />
        <Campo
          etiqueta={acceso.campos.password}
          refCampo={refPassword}
          type="password"
          name="password"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
            setFaltanDatos(false);
          }}
          autoComplete="current-password"
          enterKeyHint="go"
        />

        {faltanDatos && <Aviso>{acceso.entrar.faltanDatos}</Aviso>}
        {error != null && <AvisoDeError key={intento} error={error} refAviso={refAviso} />}

        <Boton type="submit" cargando={enviando} className="mt-1">
          {acceso.entrar.boton}
        </Boton>

        {/* El link mide 44 px pero la letra 24: el -my-2 le saca el aire de
            más para que no quede lejos del botón ni del borde. */}
        <PieAcceso
          a="/admin/olvide"
          estado={email.trim() ? { email: email.trim() } : undefined}
          texto={acceso.entrar.olvide}
          className="-my-2"
        />
      </form>

      <PieAcceso
        pregunta={acceso.entrar.sinCuenta}
        a="/admin/registro"
        texto={acceso.entrar.crearCuenta}
      />
    </MarcoAcceso>
  );
}

/** El email que manda Olvidé mi contraseña al volver, si mandó uno. */
function emailRecibido(estado: unknown): string {
  const email = (estado as { email?: unknown } | null)?.email;
  return typeof email === "string" ? email : "";
}
