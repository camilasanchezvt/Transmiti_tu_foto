import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { ErrorApi, admin, salud } from "../api/client";
import Boton from "../comp/Boton";
import { Aviso, AvisoDeError, Campo, MarcoAcceso, PieAcceso } from "./PiezasAcceso";
import { acceso } from "./textos/acceso";
import { comun } from "./textos/comun";
import { comprobarSesion, olvidarSesion } from "./useSesion";

/** Desde cuándo una espera deja de ser normal. Despierta y con bcrypt de 10
 *  rondas, entrar tarda menos de un segundo; más de cinco es casi siempre la
 *  app dormida (Render gratuito) despertándose. */
const ESPERA_LARGA_MS = 5000;

/** Una vez por carga de la página alcanza para despertar la app: ir a Crear
 *  cuenta y volver no tiene que repetirlo. */
let yaSeDesperto = false;

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
 *
 * Que entrar se sienta rápido:
 * - Al abrir la página sin sesión, un pedido a /api/salud despierta la app
 *   mientras se escribe el email y la contraseña (en Render gratuito, el
 *   primer pedido después de un rato puede tardar cerca de un minuto). Nadie
 *   espera su respuesta.
 * - Con un token guardado, la pregunta "¿sigue sirviendo?" va por
 *   comprobarSesion, que deja la respuesta en el caché de useSesion: si sirve,
 *   el panel abre sin volver a preguntar lo mismo.
 * - Después del login se navega en el acto. El panel pide quién es y los
 *   eventos a la vez, no uno detrás del otro.
 * - El botón dice "Entrando…" con un círculo que gira, a color pleno: el
 *   gris de un botón deshabilitado parece que no pasa nada. Si pasan cinco
 *   segundos, un aviso debajo explica la demora.
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
  const [tarda, setTarda] = useState(false);
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
    const comprobacion = comprobarSesion();
    if (!comprobacion) {
      // Sin sesión: se despierta la app mientras se escribe. Si falla, no
      // importa; el login dirá lo que pase.
      if (!yaSeDesperto) {
        yaSeDesperto = true;
        salud().catch(() => {});
      }
      return;
    }
    let vivo = true;
    comprobacion.then(
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

  // Si la respuesta tarda, se avisa por qué (y que no hace falta tocar de
  // nuevo). Al llegar, el aviso se va.
  useEffect(() => {
    if (!enviando) {
      setTarda(false);
      return;
    }
    const reloj = window.setTimeout(() => setTarda(true), ESPERA_LARGA_MS);
    return () => window.clearTimeout(reloj);
  }, [enviando]);

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
    // La marca, arriba, es el título de la página: el nombre de la app en el
    // <h1> y "Panel para organizar tus eventos" debajo.
    <MarcoAcceso titulo={{ id: idTitulo, subtitulo: acceso.entrar.subtitulo }}>
      <form
        onSubmit={entrar}
        noValidate
        aria-labelledby={idTitulo}
        aria-busy={enviando || undefined}
        className="flex flex-col gap-4 rounded-3xl border border-borde bg-panel p-5 sm:p-6"
      >
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

        {/* Sin `cargando`: ese deshabilita y lo pone gris, y un botón gris
            parece que no hace nada. Éste queda a color, dice "Entrando…" y
            gira; un segundo toque no manda otro pedido (entrar() lo corta). */}
        <Boton type="submit" aria-disabled={enviando || undefined} className="mt-1">
          {enviando ? (
            <>
              <Girando />
              {acceso.entrar.entrando}
            </>
          ) : (
            acceso.entrar.boton
          )}
        </Boton>

        {/* Siempre montado, para que el lector de pantalla anuncie el aviso
            cuando aparece. Vacío va sr-only: es absolute y no suma el gap. */}
        <p
          aria-live="polite"
          className={tarda ? "text-balance text-center text-sm leading-snug text-tenue" : "sr-only"}
        >
          {tarda && acceso.entrar.tarda}
        </p>

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

/** El círculo que gira dentro del botón azul, del tamaño de un ícono de botón.
 *  Con "reducir movimiento" queda quieto: el texto ya dice que está entrando. */
function Girando() {
  return (
    <span
      aria-hidden
      className="-ml-1 h-5 w-5 shrink-0 rounded-full border-2 border-luz/35 border-t-luz motion-safe:animate-spin"
    />
  );
}
