"""Emails de la app, por Brevo. Hoy hay uno solo: recuperar la contraseña.

Se usa la API HTTP de Brevo (POST https://api.brevo.com/v3/smtp/email, con la
cabecera `api-key`) con httpx, que ya está en el stack: ni SDK ni SMTP
(regla 10). Brevo responde 201 cuando acepta el envío.

La configuración es opcional (sección 9 de CONSTRUIR-APP.md): sin
BREVO_API_KEY o sin EMAIL_REMITENTE la app arranca igual, la recuperación
responde lo mismo que siempre, pero no sale ningún email. Eso queda en el log
UNA vez por proceso, como WARNING que empieza con "email:", igual que los de
`limpieza:` (el log de uvicorn no muestra el nombre del logger).

El envío corre en segundo plano (BackgroundTasks del endpoint): la respuesta
sale antes, así el tiempo de respuesta no delata si el email existe. Por eso
estas funciones nunca levantan una excepción: una falla de Brevo sólo va al
log, sin el email de la persona ni el link.
"""

from __future__ import annotations

import html
import logging
import threading

import httpx

from .config import obtener_config

config = obtener_config()

# Hijo del de uvicorn, que en Render sale en el log a nivel INFO.
log = logging.getLogger("uvicorn.error").getChild("email")

URL_BREVO = "https://api.brevo.com/v3/smtp/email"
TIMEOUT_S = 10.0

_aviso_dado = False
_candado = threading.Lock()


def configurado() -> bool:
    """¿Están la clave de Brevo y el remitente? Si no, avisa una vez en el log."""
    if config.email_configurado:
        return True
    global _aviso_dado
    with _candado:
        if _aviso_dado:
            return False
        _aviso_dado = True
    log.warning(
        "email: SIN CONFIGURAR, no se mandan los emails de recuperación de contraseña "
        "(faltan BREVO_API_KEY o EMAIL_REMITENTE)"
    )
    return False


def reiniciar_aviso() -> None:
    """Sólo para las pruebas."""
    global _aviso_dado
    with _candado:
        _aviso_dado = False


# ─────────────────────────────────────────────────────────────
# El email de recuperación
# ─────────────────────────────────────────────────────────────

ASUNTO_RECUPERACION = "Cambiá tu contraseña de Transmití tu foto"

_TEXTO_RECUPERACION = """Hola, {nombre}.

Pediste cambiar tu contraseña de Transmití tu foto. Abrí este link para elegir una nueva:

{enlace}

El link sirve una vez y vence en una hora. Si no fuiste vos, ignorá este email.
"""

# HTML simple, con estilos en línea (los clientes de email ignoran <style>) y
# en tablas, que es lo que respetan todos. Colores planos, sin degradés.
_HTML_RECUPERACION = """<!doctype html>
<html lang="es">
<body style="margin:0;padding:0;background:#F2F2F7;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F2F2F7;padding:24px 16px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background:#FFFFFF;border-radius:16px;">
<tr><td style="padding:28px 24px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:17px;line-height:1.5;color:#000000;">
<p style="margin:0 0 16px;">Hola, {nombre}.</p>
<p style="margin:0 0 24px;">Pediste cambiar tu contraseña de Transmití tu foto. Tocá el botón para elegir una nueva.</p>
<p style="margin:0 0 24px;"><a href="{enlace}" style="display:inline-block;background:#007AFF;color:#FFFFFF;text-decoration:none;font-weight:600;padding:14px 22px;border-radius:12px;">Elegir una contraseña nueva</a></p>
<p style="margin:0 0 8px;font-size:15px;color:#3C3C43;">El link sirve una vez y vence en una hora. Si no fuiste vos, ignorá este email.</p>
<p style="margin:0;font-size:13px;color:#8E8E93;word-break:break-all;">Si el botón no anda, copiá este link: {enlace}</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""


def email_de_recuperacion(nombre: str, enlace: str) -> tuple[str, str, str]:
    """Asunto, HTML y texto. El nombre lo elige la persona al registrarse:
    en el HTML va escapado, o un nombre con `<a href=...>` metería su propio
    link en un email que sale con nuestro remitente."""
    contenido_html = _HTML_RECUPERACION.format(
        nombre=html.escape(nombre, quote=True),
        enlace=html.escape(enlace, quote=True),
    )
    contenido_texto = _TEXTO_RECUPERACION.format(nombre=nombre, enlace=enlace)
    return ASUNTO_RECUPERACION, contenido_html, contenido_texto


def enlace_de_restablecer(token: str) -> str:
    """`{URL_PANEL}/admin/restablecer#token=...`.

    El token va en el fragmento (después de `#`): el navegador no lo manda en
    ningún pedido, así que no queda en los logs de Render, de Cloudflare ni de
    ningún proxy. Lo lee la página y lo manda en el cuerpo del POST.
    """
    return f"{config.url_panel}/admin/restablecer#token={token}"


def enviar(email: str, nombre: str, asunto: str, contenido_html: str, contenido_texto: str) -> bool:
    """Un email por Brevo. True si Brevo lo aceptó. Nunca levanta."""
    if not configurado():
        return False
    try:
        respuesta = httpx.post(
            URL_BREVO,
            headers={"api-key": config.BREVO_API_KEY.strip(), "accept": "application/json"},
            json={
                "sender": {
                    "name": config.EMAIL_REMITENTE_NOMBRE.strip() or "Transmití tu foto",
                    "email": config.EMAIL_REMITENTE.strip(),
                },
                "to": [{"email": email, "name": nombre}],
                "subject": asunto,
                "htmlContent": contenido_html,
                "textContent": contenido_texto,
            },
            timeout=TIMEOUT_S,
        )
    except httpx.HTTPError as e:
        log.error("email: sin respuesta de Brevo (%s)", type(e).__name__)
        return False
    if not 200 <= respuesta.status_code < 300:
        # El cuerpo de error de Brevo dice qué falló (remitente sin verificar,
        # clave inválida); no trae ni la clave ni el destinatario.
        log.error("email: Brevo respondió %s: %s", respuesta.status_code, respuesta.text[:300])
        return False
    return True


def enviar_recuperacion(email: str, nombre: str, token: str, usuario_id: int) -> bool:
    """La tarea de fondo de POST /api/cuentas/recuperar. Nunca levanta.

    Recibe datos sueltos y no la fila: corre después de la respuesta, cuando la
    sesión de base del pedido ya se cerró. En el log va el id de la cuenta,
    nunca el email ni el link (el link con el token sirve para entrar).
    """
    try:
        asunto, contenido_html, contenido_texto = email_de_recuperacion(
            nombre, enlace_de_restablecer(token)
        )
        enviado = enviar(email, nombre, asunto, contenido_html, contenido_texto)
    except Exception:
        log.exception("email: no se pudo mandar la recuperación de la cuenta %s", usuario_id)
        return False
    if enviado:
        log.info("email: recuperación de contraseña enviada a la cuenta %s", usuario_id)
    return enviado
