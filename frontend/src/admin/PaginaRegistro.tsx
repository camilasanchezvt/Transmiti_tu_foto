import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { cuentas } from "../api/client";
import Boton from "../comp/Boton";
import { AvisoDeError, Campo, MarcoAcceso, PieAcceso } from "./PiezasAcceso";
import { MAXIMO_NOMBRE, MAXIMO_PASSWORD, MINIMO_PASSWORD, acceso } from "./textos/acceso";
import { comun } from "./textos/comun";

type NombreCampo = "nombre" | "email" | "password" | "repetir";
type Datos = Record<NombreCampo, string>;
type Errores = Partial<Record<NombreCampo, string>>;

/** En el orden en que aparecen: al fallar, el foco va al primero con error. */
const ORDEN: NombreCampo[] = ["nombre", "email", "password", "repetir"];

/** El mismo patrón que valida el backend (EmailCuenta en schemas.py): descarta
 *  lo que claramente no es un email, sin pretender más. */
const PATRON_EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** Largo como lo cuenta Python, por letras y no por unidades de UTF-16: una
 *  contraseña con emojis que acá mide 10 allá podría medir 8 y volver con un
 *  error que no dice qué pasó. */
function largo(texto: string): number {
  return [...texto].length;
}

function validar(datos: Datos): Errores {
  const t = acceso.registro.errores;
  const errores: Errores = {};

  const nombre = datos.nombre.trim();
  if (!nombre) errores.nombre = t.nombreVacio;
  else if (largo(nombre) > MAXIMO_NOMBRE) errores.nombre = t.nombreLargo;

  const email = datos.email.trim();
  if (!email) errores.email = t.emailVacio;
  else if (email.length > 254 || !PATRON_EMAIL.test(email)) errores.email = t.emailInvalido;

  // Corta: el mismo texto que la ayuda, en rojo. Dice cuántos faltan, que es
  // más útil que repetir el mínimo.
  const largoPassword = largo(datos.password);
  if (largoPassword < MINIMO_PASSWORD) errores.password = acceso.registro.ayudaPassword(largoPassword);
  else if (largoPassword > MAXIMO_PASSWORD) errores.password = t.passwordLarga;

  if (!datos.repetir) errores.repetir = t.repetirVacio;
  else if (datos.repetir !== datos.password) errores.repetir = t.noCoinciden;

  return errores;
}

/**
 * Crear cuenta. Público, sin LayoutAdmin: quien llega acá no tiene sesión.
 *
 * La cuenta nace pendiente y no puede entrar hasta que alguien que administra
 * la app la habilite. El backend responde lo mismo aunque el email ya exista
 * (así no se puede averiguar quién está registrado), y por eso la pantalla de
 * éxito tampoco promete nada distinto: dice qué va a pasar, no qué pasó.
 */
export default function PaginaRegistro() {
  const navegar = useNavigate();
  const idTitulo = useId();
  const [datos, setDatos] = useState<Datos>({ nombre: "", email: "", password: "", repetir: "" });
  // Los errores se calculan siempre, pero se muestran recién cuando la
  // persona terminó con el campo (salió de él con algo escrito) o tocó Crear.
  // Antes de eso, marcar en rojo un campo a medio escribir sólo apura.
  const [tocados, setTocados] = useState<Partial<Record<NombreCampo, boolean>>>({});
  const [intentoEnviar, setIntentoEnviar] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [intento, setIntento] = useState(0);
  const [emailPedido, setEmailPedido] = useState<string | null>(null);

  const refs = {
    nombre: useRef<HTMLInputElement>(null),
    email: useRef<HTMLInputElement>(null),
    password: useRef<HTMLInputElement>(null),
    repetir: useRef<HTMLInputElement>(null),
  };
  const refAviso = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    document.title = comun.tituloPestana(acceso.registro.tituloPestana);
  }, []);

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
    if (datos[campo] !== "") setTocados((t) => ({ ...t, [campo]: true }));
  }

  async function crear(evento: FormEvent) {
    evento.preventDefault();
    if (enviando) return;
    setIntentoEnviar(true);
    setError(null);

    const primero = ORDEN.find((campo) => errores[campo]);
    if (primero) {
      refs[primero].current?.focus();
      return;
    }

    setEnviando(true);
    const email = datos.email.trim().toLowerCase();
    try {
      await cuentas.registrar({ email, nombre: datos.nombre.trim(), password: datos.password });
      // La contraseña no tiene nada que hacer en memoria después de esto.
      setDatos((d) => ({ ...d, password: "", repetir: "" }));
      setEmailPedido(email);
    } catch (e) {
      // DEMASIADOS_PEDIDOS y cualquier otro llegan con su mensaje: va tal cual.
      setError(e);
      setIntento((n) => n + 1);
    } finally {
      setEnviando(false);
    }
  }

  if (emailPedido) {
    return <Listo email={emailPedido} onVolver={() => navegar("/admin/login")} />;
  }

  const largoPassword = largo(datos.password);
  const passwordCumple = largoPassword >= MINIMO_PASSWORD && largoPassword <= MAXIMO_PASSWORD;
  const coinciden = datos.repetir !== "" && datos.repetir === datos.password && passwordCumple;

  return (
    <MarcoAcceso>
      <form
        onSubmit={crear}
        noValidate
        aria-labelledby={idTitulo}
        className="flex flex-col gap-4 rounded-3xl border border-borde bg-panel p-5 sm:p-6"
      >
        <header className="mb-1 flex flex-col gap-1 text-center">
          <p className="text-sm font-medium text-tenue">{acceso.marca}</p>
          <h1 id={idTitulo} className="text-2xl font-semibold tracking-tight">
            {acceso.registro.titulo}
          </h1>
          <p className="text-base text-tenue">{acceso.registro.subtitulo}</p>
        </header>

        <Campo
          etiqueta={acceso.campos.nombre}
          refCampo={refs.nombre}
          name="name"
          value={datos.nombre}
          onChange={(e) => cambiar("nombre", e.target.value)}
          onBlur={() => salir("nombre")}
          error={mostrar("nombre")}
          autoComplete="name"
          autoCapitalize="words"
          maxLength={MAXIMO_NOMBRE}
        />
        <Campo
          etiqueta={acceso.campos.email}
          refCampo={refs.email}
          type="email"
          name="email"
          value={datos.email}
          onChange={(e) => cambiar("email", e.target.value)}
          onBlur={() => salir("email")}
          error={mostrar("email")}
          autoComplete="email"
          inputMode="email"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          maxLength={254}
        />
        <Campo
          etiqueta={acceso.campos.password}
          refCampo={refs.password}
          type="password"
          name="new-password"
          value={datos.password}
          onChange={(e) => cambiar("password", e.target.value)}
          onBlur={() => salir("password")}
          error={mostrar("password")}
          // Siempre a la vista, no sólo al equivocarse: el mínimo se sabe
          // antes de inventar la contraseña, no después.
          ayuda={acceso.registro.ayudaPassword(largoPassword)}
          ayudaCumplida={passwordCumple}
          autoComplete="new-password"
          minLength={MINIMO_PASSWORD}
          maxLength={MAXIMO_PASSWORD}
        />
        <Campo
          etiqueta={acceso.campos.repetirPassword}
          refCampo={refs.repetir}
          type="password"
          name="repetir-password"
          value={datos.repetir}
          onChange={(e) => cambiar("repetir", e.target.value)}
          onBlur={() => salir("repetir")}
          error={mostrar("repetir")}
          ayuda={coinciden ? acceso.registro.coinciden : null}
          ayudaCumplida={coinciden}
          autoComplete="new-password"
          maxLength={MAXIMO_PASSWORD}
        />

        {error != null && <AvisoDeError key={intento} error={error} refAviso={refAviso} />}

        <Boton type="submit" cargando={enviando} className="mt-1">
          {acceso.registro.boton}
        </Boton>
      </form>

      <PieAcceso pregunta={acceso.registro.conCuenta} a="/admin/login" texto={acceso.registro.irAEntrar} />
    </MarcoAcceso>
  );
}

/** Pantalla de éxito. El foco va al título para que un lector de pantalla
 *  anuncie el cambio: el formulario desapareció y no hay otra señal. */
function Listo({ email, onVolver }: { email: string; onVolver: () => void }) {
  const t = acceso.registro.exito;
  const refTitulo = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    document.title = comun.tituloPestana(t.tituloPestana);
    refTitulo.current?.focus();
  }, [t.tituloPestana]);

  return (
    <MarcoAcceso>
      <section className="flex flex-col items-center gap-4 rounded-3xl border border-borde bg-panel p-5 text-center sm:p-6">
        <span
          aria-hidden="true"
          className="flex h-14 w-14 items-center justify-center rounded-full bg-verde/15 text-verde"
        >
          <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none" stroke="currentColor" strokeWidth={2.5}>
            <path d="M5 12.5l4.5 4.5L19 7.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
        <h1 ref={refTitulo} tabIndex={-1} className="text-2xl font-semibold tracking-tight outline-none">
          {t.titulo}
        </h1>
        <p className="text-lg leading-snug">{t.mensaje}</p>
        {/* Un email largo sin espacios no puede empujar la tarjeta a lo ancho. */}
        <p className="w-full break-words text-sm text-tenue">{t.conEmail(email)}</p>
        <Boton onClick={onVolver} className="mt-2">
          {t.volver}
        </Boton>
      </section>
    </MarcoAcceso>
  );
}
