import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router-dom";
// Outline: el sobre relleno en azul se leía como un segundo ícono de app
// debajo del símbolo de la marca (MarcoAcceso). El trazo lo distingue.
import { EnvelopeIcon } from "@heroicons/react/24/outline";

import { cuentas } from "../api/client";
import Boton, { claseBoton } from "../comp/Boton";
import { AvisoDeError, Campo, MarcoAcceso, PieAcceso, TarjetaResultado } from "./PiezasAcceso";
import { acceso } from "./textos/acceso";
import { comun } from "./textos/comun";

/** El mismo patrón que valida el backend (EmailCuenta en schemas.py). */
const PATRON_EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function validar(email: string): string | null {
  const t = acceso.olvide.errores;
  if (!email) return t.emailVacio;
  if (email.length > 254 || !PATRON_EMAIL.test(email)) return t.emailInvalido;
  return null;
}

/** El email que traía Entrar, si ya estaba escrito. */
function emailRecibido(estado: unknown): string {
  const email = (estado as { email?: unknown } | null)?.email;
  return typeof email === "string" ? email : "";
}

/**
 * Olvidé mi contraseña (/admin/olvide). Sin LayoutAdmin: quien llega acá no
 * tiene sesión.
 *
 * cuentas.recuperar responde lo mismo exista o no la cuenta (así no se puede
 * averiguar quién está registrado), y por eso la confirmación tampoco promete
 * nada: "si hay una cuenta con ese email, te mandamos un link". Muestra el
 * email tal como se pidió, para que un error de tipeo se vea, y deja volver a
 * corregirlo sin borrar lo escrito.
 */
export default function PaginaOlvide() {
  const t = acceso.olvide;
  const ubicacion = useLocation();
  const idTitulo = useId();
  const [email, setEmail] = useState(() => emailRecibido(ubicacion.state));
  // Como en Crear cuenta: el error se muestra cuando la persona salió del
  // campo con algo escrito o tocó el botón, no mientras escribe.
  const [tocado, setTocado] = useState(false);
  const [intentoEnviar, setIntentoEnviar] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [intento, setIntento] = useState(0);
  const [enviadoA, setEnviadoA] = useState<string | null>(null);
  const refEmail = useRef<HTMLInputElement>(null);
  const refAviso = useRef<HTMLParagraphElement>(null);
  // Al volver de la confirmación con "Cambialo", el foco va al campo.
  const volverAlCampo = useRef(false);

  const emailLimpio = email.trim();
  const errorEmail = validar(emailLimpio);

  // Con la confirmación a la vista, el título lo pone TarjetaResultado.
  useEffect(() => {
    if (enviadoA !== null) return;
    document.title = comun.tituloPestana(t.tituloPestana);
    if (volverAlCampo.current) {
      volverAlCampo.current = false;
      refEmail.current?.focus();
      refEmail.current?.select();
    }
  }, [enviadoA, t.tituloPestana]);

  // Igual que en Entrar: el teclado del celular tapa el aviso de abajo.
  useEffect(() => {
    if (error == null) return;
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    refAviso.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [error, intento]);

  async function pedirLink(evento: FormEvent) {
    evento.preventDefault();
    if (enviando) return;
    setIntentoEnviar(true);
    setError(null);

    if (errorEmail) {
      refEmail.current?.focus();
      return;
    }

    setEnviando(true);
    try {
      await cuentas.recuperar(emailLimpio);
      setEnviadoA(emailLimpio.toLowerCase());
    } catch (e) {
      // DEMASIADOS_PEDIDOS y cualquier otro llegan con su mensaje: va tal cual.
      setError(e);
      setIntento((n) => n + 1);
    } finally {
      setEnviando(false);
    }
  }

  function cambiarEmail() {
    volverAlCampo.current = true;
    setIntentoEnviar(false);
    setTocado(false);
    setEnviadoA(null);
  }

  if (enviadoA !== null) {
    const c = t.enviado;
    return (
      <MarcoAcceso>
        <TarjetaResultado
          icono={EnvelopeIcon}
          colorIcono="text-acento"
          titulo={c.titulo}
          tituloPestana={c.tituloPestana}
        >
          <div className="flex flex-col gap-2">
            <p className="text-lg leading-snug">{c.mensaje}</p>
            <p className="text-base leading-snug">{c.noDeseado}</p>
          </div>
          {/* Un email largo sin espacios no puede empujar la tarjeta a lo ancho. */}
          <p className="w-full break-words text-sm text-tenue">{c.conEmail(enviadoA)}</p>
          {/* Ir a otra página es un link, con la forma del botón grande. */}
          <Link to="/admin/login" state={{ email: enviadoA }} className={`${claseBoton("principal")} mt-2`}>
            {c.volver}
          </Link>
        </TarjetaResultado>

        <PieAcceso pregunta={c.escribisteMal} onClick={cambiarEmail} texto={c.cambiar} />
      </MarcoAcceso>
    );
  }

  return (
    <MarcoAcceso>
      <form
        onSubmit={pedirLink}
        noValidate
        aria-labelledby={idTitulo}
        className="flex flex-col gap-4 rounded-3xl border border-borde bg-panel p-5 sm:p-6"
      >
        <header className="mb-1 flex flex-col gap-1 text-center">
          <h1 id={idTitulo} className="text-balance text-2xl font-semibold tracking-tight">
            {t.titulo}
          </h1>
          <p className="text-base text-tenue">{t.subtitulo}</p>
        </header>

        <Campo
          etiqueta={acceso.campos.email}
          refCampo={refEmail}
          type="email"
          name="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onBlur={() => {
            if (email !== "") setTocado(true);
          }}
          error={intentoEnviar || tocado ? errorEmail : null}
          autoComplete="email"
          inputMode="email"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          enterKeyHint="send"
          maxLength={254}
        />

        {error != null && <AvisoDeError key={intento} error={error} refAviso={refAviso} />}

        <Boton type="submit" cargando={enviando} className="mt-1">
          {t.boton}
        </Boton>
      </form>

      <PieAcceso
        a="/admin/login"
        estado={emailLimpio ? { email: emailLimpio } : undefined}
        texto={t.volver}
      />
    </MarcoAcceso>
  );
}
