import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import { CheckCircleIcon, LinkSlashIcon } from "@heroicons/react/24/solid";

import { ErrorApi, cuentas } from "../api/client";
import Boton, { claseBoton } from "../comp/Boton";
import { AvisoDeError, Campo, MarcoAcceso, PieAcceso, TarjetaResultado } from "./PiezasAcceso";
import { MAXIMO_PASSWORD, MINIMO_PASSWORD, acceso } from "./textos/acceso";
import { comun } from "./textos/comun";

type NombreCampo = "password" | "repetir";
type Datos = Record<NombreCampo, string>;
type Errores = Partial<Record<NombreCampo, string>>;

/** En el orden en que aparecen: al fallar, el foco va al primero con error. */
const ORDEN: NombreCampo[] = ["password", "repetir"];

/** El backend no acepta un token más largo (PedidoRestablecer en schemas.py):
 *  uno así no puede ser un link bueno. */
const LARGO_MAXIMO_TOKEN = 200;

/** El token del link del email: /admin/restablecer#token=…. Va en el
 *  fragmento (#), que el navegador no manda a ningún servidor. */
function leerToken(): string | null {
  const fragmento = window.location.hash.replace(/^#/, "");
  if (!fragmento) return null;
  const token = new URLSearchParams(fragmento).get("token")?.trim() ?? "";
  return token && token.length <= LARGO_MAXIMO_TOKEN ? token : null;
}

/** Largo como lo cuenta Python, por letras y no por unidades de UTF-16 (igual
 *  que en Crear cuenta). */
function largo(texto: string): number {
  return [...texto].length;
}

function validar(datos: Datos): Errores {
  const t = acceso.restablecer;
  const errores: Errores = {};

  const largoPassword = largo(datos.password);
  if (largoPassword < MINIMO_PASSWORD) errores.password = t.ayudaPassword(largoPassword);
  else if (largoPassword > MAXIMO_PASSWORD) errores.password = t.errores.passwordLarga;

  if (!datos.repetir) errores.repetir = t.errores.repetirVacio;
  else if (datos.repetir !== datos.password) errores.repetir = t.errores.noCoinciden;

  return errores;
}

/**
 * Contraseña nueva (/admin/restablecer#token=…), el link del email. Sin
 * LayoutAdmin: quien llega acá no tiene sesión.
 *
 * El token se lee una vez y se borra de la barra de direcciones: así no queda
 * en el historial ni se comparte copiando la dirección. Si se recarga la
 * página, ya no está, y se ve lo mismo que con un link vencido: el del email
 * sigue sirviendo hasta que se use.
 *
 * Tres caras:
 * - el formulario (contraseña nueva y repetirla);
 * - "Listo", con el botón a Entrar. No abre sesión: el backend cierra todas
 *   las de la cuenta y hay que entrar con la contraseña nueva;
 * - "El link ya no sirve", si falta el token o el backend lo rechaza (vencido,
 *   usado, reemplazado por uno más nuevo). El mensaje del backend va tal cual,
 *   con "Pedir otro link".
 */
export default function PaginaRestablecer() {
  // Un link nuevo pegado en esta misma pestaña cambia sólo el fragmento: el
  // navegador no recarga y React Router no vuelve a montar la página, que
  // seguía con el token de antes (o con "El link ya no sirve") y dejaba el
  // nuevo a la vista en la barra. Con la key, arranca de cero con el nuevo.
  // Borrar el fragmento con history.replaceState no cambia la key: React
  // Router no se entera.
  const { hash } = useLocation();
  return <Restablecer key={hash} />;
}

function Restablecer() {
  const t = acceso.restablecer;
  const idTitulo = useId();
  // Con useState y no en un efecto: el efecto de abajo borra el fragmento, y
  // en desarrollo React monta dos veces; leído en un efecto, el segundo
  // montaje ya no lo encontraría.
  const [token] = useState(leerToken);
  const [linkInvalido, setLinkInvalido] = useState<string | null>(token ? null : t.invalido.mensaje);
  const [listo, setListo] = useState(false);

  const [datos, setDatos] = useState<Datos>({ password: "", repetir: "" });
  const [tocados, setTocados] = useState<Partial<Record<NombreCampo, boolean>>>({});
  const [intentoEnviar, setIntentoEnviar] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [intento, setIntento] = useState(0);

  const refs = {
    password: useRef<HTMLInputElement>(null),
    repetir: useRef<HTMLInputElement>(null),
  };
  const refAviso = useRef<HTMLParagraphElement>(null);

  // history.replaceState y no navegar(): es la misma página, sólo cambia lo
  // que se ve en la barra. Se conserva el estado del historial, que es de
  // React Router.
  useEffect(() => {
    const { pathname, search, hash } = window.location;
    if (hash) window.history.replaceState(window.history.state, "", pathname + search);
  }, []);

  // Con "Listo" o "El link ya no sirve" a la vista, el título lo pone
  // TarjetaResultado.
  const conFormulario = !listo && linkInvalido === null;
  useEffect(() => {
    if (conFormulario) document.title = comun.tituloPestana(t.tituloPestana);
  }, [conFormulario, t.tituloPestana]);

  // Igual que en Entrar: el teclado del celular tapa el aviso de abajo.
  useEffect(() => {
    if (error == null) return;
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    refAviso.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [error, intento]);

  const errores = validar(datos);
  const mostrar = (campo: NombreCampo) => (intentoEnviar || tocados[campo] ? errores[campo] : null);

  function cambiar(campo: NombreCampo, valor: string) {
    setDatos((d) => ({ ...d, [campo]: valor }));
  }

  function salir(campo: NombreCampo) {
    if (datos[campo] !== "") setTocados((tc) => ({ ...tc, [campo]: true }));
  }

  async function guardar(evento: FormEvent) {
    evento.preventDefault();
    if (enviando || !token) return;
    setIntentoEnviar(true);
    setError(null);

    const primero = ORDEN.find((campo) => errores[campo]);
    if (primero) {
      refs[primero].current?.focus();
      return;
    }

    // Cuando el formulario desaparece, la contraseña no tiene nada que hacer
    // en memoria.
    const vaciar = () => setDatos({ password: "", repetir: "" });

    setEnviando(true);
    try {
      await cuentas.restablecer(token, datos.password);
      vaciar();
      setListo(true);
    } catch (e) {
      // La contraseña ya se validó acá con las mismas reglas que el backend:
      // un 422 es el link (vencido, usado, reemplazado). Se muestra tal cual
      // y el formulario deja de tener sentido.
      if (e instanceof ErrorApi && e.codigo === "DATOS_INVALIDOS") {
        vaciar();
        setLinkInvalido(e.message);
      } else {
        // DEMASIADOS_PEDIDOS o sin red: el link puede seguir sirviendo y lo
        // escrito queda para probar de nuevo.
        setError(e);
        setIntento((n) => n + 1);
      }
    } finally {
      setEnviando(false);
    }
  }

  if (listo) {
    const c = t.listo;
    return (
      <MarcoAcceso>
        <TarjetaResultado
          icono={CheckCircleIcon}
          colorIcono="text-verde"
          titulo={c.titulo}
          tituloPestana={c.tituloPestana}
        >
          <p className="text-lg leading-snug">{c.mensaje}</p>
          <p className="text-sm leading-snug text-tenue">{c.otrosLados}</p>
          <Link to="/admin/login" replace className={`${claseBoton("principal")} mt-2`}>
            {c.entrar}
          </Link>
        </TarjetaResultado>
      </MarcoAcceso>
    );
  }

  if (linkInvalido !== null) {
    const c = t.invalido;
    return (
      <MarcoAcceso>
        <TarjetaResultado
          icono={LinkSlashIcon}
          colorIcono="text-naranja"
          titulo={linkInvalido}
          tituloPestana={c.tituloPestana}
        >
          <p className="text-base leading-snug text-tenue">{c.porQue}</p>
          <Link to="/admin/olvide" className={`${claseBoton("principal")} mt-2`}>
            {c.pedirOtro}
          </Link>
        </TarjetaResultado>

        <PieAcceso a="/admin/login" texto={c.volver} />
      </MarcoAcceso>
    );
  }

  const largoPassword = largo(datos.password);
  const passwordCumple = largoPassword >= MINIMO_PASSWORD && largoPassword <= MAXIMO_PASSWORD;
  const coinciden = datos.repetir !== "" && datos.repetir === datos.password && passwordCumple;

  return (
    <MarcoAcceso>
      <form
        onSubmit={guardar}
        noValidate
        aria-labelledby={idTitulo}
        className="flex flex-col gap-4 rounded-3xl border border-borde bg-panel p-5 sm:p-6"
      >
        <header className="mb-1 flex flex-col gap-1 text-center">
          <p className="text-sm font-medium text-tenue">{acceso.marca}</p>
          <h1 id={idTitulo} className="text-balance text-2xl font-semibold tracking-tight">
            {t.titulo}
          </h1>
          <p className="text-base text-tenue">{t.subtitulo}</p>
        </header>

        <Campo
          etiqueta={t.campos.password}
          refCampo={refs.password}
          type="password"
          name="new-password"
          value={datos.password}
          onChange={(e) => cambiar("password", e.target.value)}
          onBlur={() => salir("password")}
          error={mostrar("password")}
          // Siempre a la vista: el mínimo se sabe antes de inventarla.
          ayuda={t.ayudaPassword(largoPassword)}
          ayudaCumplida={passwordCumple}
          autoComplete="new-password"
          minLength={MINIMO_PASSWORD}
          maxLength={MAXIMO_PASSWORD}
        />
        <Campo
          etiqueta={t.campos.repetir}
          refCampo={refs.repetir}
          type="password"
          name="repetir-password"
          value={datos.repetir}
          onChange={(e) => cambiar("repetir", e.target.value)}
          onBlur={() => salir("repetir")}
          error={mostrar("repetir")}
          ayuda={coinciden ? t.coinciden : null}
          ayudaCumplida={coinciden}
          autoComplete="new-password"
          enterKeyHint="done"
          maxLength={MAXIMO_PASSWORD}
        />

        {error != null && <AvisoDeError key={intento} error={error} refAviso={refAviso} />}

        <Boton type="submit" cargando={enviando} className="mt-1">
          {t.boton}
        </Boton>
      </form>

      <PieAcceso a="/admin/login" texto={t.volver} />
    </MarcoAcceso>
  );
}
