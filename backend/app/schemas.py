"""Esquemas de entrada y salida de la API (Pydantic v2).

Son el contrato de la sección 5 de CONSTRUIR-APP.md traducido a tipos. Estos
esquemas son DEFINITIVOS desde la Fase 1: las tres interfaces se construyen
contra ellos. No agregar, sacar ni renombrar campos sin actualizar la sección 5.

Regla 1: el `id` interno de un evento no aparece en ninguna respuesta pública.
Fijate que ni EventoPublico ni PantallaEvento lo tienen. Los esquemas de
administración sí, porque van detrás del Bearer.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

EstadoEvento = Literal["borrador", "activo", "cerrado"]
EstadoFoto = Literal["pendiente", "aprobada", "rechazada"]
RolUsuario = Literal["superadmin", "admin", "organizador"]
EstadoCuenta = Literal["pendiente", "activa", "baja"]
TemaPanel = Literal["oscuro", "claro", "automatico"]
# Cómo se ve la pantalla del proyector. `desenfocado`: la misma foto, borrosa,
# detrás; `negro`: fondo negro liso. `fundido` o `corte` entre una foto y otra.
FondoPantalla = Literal["desenfocado", "negro"]
TransicionPantalla = Literal["fundido", "corte"]

# Los topes de los dos números de un evento, los mismos para el PATCH del
# evento y para los predeterminados de la cuenta: menos de 3 s por foto no se
# llega a ver en un proyector, y más de 50 fotos por invitado deja de ser un límite.
SegundosPorFoto = Annotated[int, Field(ge=3, le=30)]
MaxFotosPorDispositivo = Annotated[int, Field(ge=1, le=50)]

# El nombre de una cuenta, sin espacios de sobra. Se recorta ANTES de medir,
# así "   " cuenta como vacío y no como un nombre de tres caracteres.
NombreCuenta = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]

# Un email normalizado: sin espacios y en minúsculas, que es como se guarda y se
# compara. El formato se valida con un patrón simple a propósito: validar de
# verdad pide la librería email-validator, que no está en el stack (regla 10), y
# lo que importa acá es descartar lo que claramente no es un email.
EmailCuenta = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_lower=True, max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]


# ─────────────────────────────────────────────────────────────
# Error — la forma única de todos los errores del contrato
# ─────────────────────────────────────────────────────────────

class DetalleError(BaseModel):
    codigo: str = Field(examples=["EVENTO_CERRADO"])
    mensaje: str = Field(examples=["Este evento ya terminó"])


class RespuestaError(BaseModel):
    """{ "error": { "codigo": "...", "mensaje": "..." } }"""

    error: DetalleError


# ─────────────────────────────────────────────────────────────
# Públicos — los usa el celular del invitado
# ─────────────────────────────────────────────────────────────

class EventoPublico(BaseModel):
    """GET /api/e/{codigo_publico}

    Devuelve `estado` también cuando es `cerrado`, para que la app muestre la
    pantalla de cierre. Si es `borrador` el endpoint responde 404.
    """

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "nombre": "Casamiento Ana y Juan",
        "fecha_evento": "2026-09-12",
        "estado": "activo",
        "max_fotos_por_dispositivo": 10,
    }]})

    nombre: str
    fecha_evento: date
    estado: EstadoEvento
    max_fotos_por_dispositivo: int


class PedidoFirma(BaseModel):
    """Cuerpo de POST /api/e/{codigo_publico}/firma"""

    dispositivo_hash: str = Field(min_length=8, max_length=128, examples=["9f2c1a7b4e8d0c35"])


class Firma(BaseModel):
    """Respuesta de POST /api/e/{codigo_publico}/firma

    Se firman sólo `folder` y `timestamp`. La carpeta es siempre
    `eventos/{codigo_publico}`. El api_secret nunca sale del backend.
    """

    cloud_name: str
    api_key: str
    timestamp: int
    signature: str
    folder: str = Field(examples=["eventos/ab12cd34"])


class FotoNueva(BaseModel):
    """Cuerpo de POST /api/e/{codigo_publico}/fotos

    El `public_id` tiene que empezar con `eventos/{codigo_publico}/`. Sin esa
    verificación cualquiera podría registrar la URL de una imagen ajena.

    Los dos con largo máximo: los de Cloudinary miden unos 30 y 100 caracteres.
    El formato (carpeta, url exacta) lo miran verificar_public_id y
    verificar_url, que responden PUBLIC_ID_AJENO y ARCHIVO_INVALIDO; acá sólo
    se corta lo que no puede ser una foto de nadie.
    """

    public_id: str = Field(max_length=200, examples=["eventos/ab12cd34/k3j2h1"])
    url: str = Field(
        max_length=500,
        examples=["https://res.cloudinary.com/demo/image/upload/v1/eventos/ab12cd34/k3j2h1.jpg"],
    )
    ancho: int = Field(gt=0)
    alto: int = Field(gt=0)
    bytes: int = Field(gt=0)
    dispositivo_hash: str = Field(min_length=8, max_length=128)
    nombre_invitado: str | None = Field(default=None, max_length=80)


class FotoRegistrada(BaseModel):
    """Respuesta 201 de POST /api/e/{codigo_publico}/fotos"""

    id: int
    estado: EstadoFoto


# ─────────────────────────────────────────────────────────────
# Pantalla — la usa la notebook del proyector
# ─────────────────────────────────────────────────────────────

class PantallaEvento(BaseModel):
    nombre: str
    codigo_publico: str
    estado: EstadoEvento


class PantallaConfig(BaseModel):
    """`segundos_por_foto` y el estilo (`fondo`, `transicion`, `mostrar_nombre`,
    `mostrar_qr`) salen de la fila del evento: la pantalla los toma en su
    próxima pasada de polling, sin recargar. Los otros dos son del servidor."""

    segundos_por_foto: int
    intervalo_polling_ms: int
    maximo_buffer: int
    fondo: FondoPantalla
    transicion: TransicionPantalla
    mostrar_nombre: bool
    mostrar_qr: bool


class Pantalla(BaseModel):
    """GET /api/pantalla/{token_pantalla}"""

    evento: PantallaEvento
    config: PantallaConfig


class FotoPantalla(BaseModel):
    """Una foto tal como la ve la pantalla. Sin estado: son todas aprobadas."""

    id: int
    url: str
    ancho: int | None
    alto: int | None
    nombre_invitado: str | None


class ColaPantalla(BaseModel):
    """GET /api/pantalla/{token_pantalla}/fotos

    `desde=0` devuelve las últimas `limite` aprobadas, de la más vieja a la más
    nueva (arranque en frío). `desde=N` devuelve las aprobadas con id > N,
    ascendente (polling normal).

    `ultimo_id` es el mayor id devuelto, o el `desde` recibido si no vino nada.
    """

    fotos: list[FotoPantalla]
    ultimo_id: int


# ─────────────────────────────────────────────────────────────
# Administración — detrás de Authorization: Bearer
# ─────────────────────────────────────────────────────────────

class PedidoLogin(BaseModel):
    """Con largo máximo: el email es parte de la clave del tope de pedidos, y
    ninguno de los dos puede ser más largo que lo que acepta el registro de
    ninguna cuenta (254 y 128; se deja margen para las creadas a mano)."""

    email: str = Field(max_length=254, examples=["ana@transmitifoto.test"])
    password: str = Field(min_length=1, max_length=1024)


class Sesion(BaseModel):
    token: str
    expira_en: datetime


class EventoNuevo(BaseModel):
    """Cuerpo de POST /api/admin/eventos.

    `organizador_id` es opcional: sin él, el dueño es quien lo crea. Un admin
    puede crear un evento para otra cuenta activa; un organizador, sólo para sí.

    `fecha_evento` no puede ser de hace 30 días o más: sus fotos ya estarían
    vencidas (se borran a los 30 días de la fecha). Lo controla crear_evento y
    no un validador de acá, porque el error de validación sale con el mensaje
    genérico y éste tiene que decir "Revisá el año".
    """

    nombre: str = Field(min_length=1, max_length=120)
    fecha_evento: date = Field(description="No puede ser de hace 30 días o más (hoy de Argentina)")
    organizador_id: int | None = None


class CambioEstadoEvento(BaseModel):
    """Cuerpo de PATCH /api/admin/eventos/{id}. Cualquier combinación, al menos uno.

    Los topes cuidan la pantalla y el cupo: menos de 3 s por foto no se llega a
    ver en un proyector, y más de 50 fotos por invitado deja de ser un límite.

    Los cuatro `pantalla_*` son el estilo de la pantalla del proyector; le
    llegan en su próxima pasada de polling, sin recargarla.
    """

    estado: EstadoEvento | None = None
    segundos_por_foto: SegundosPorFoto | None = None
    max_fotos_por_dispositivo: MaxFotosPorDispositivo | None = None
    pantalla_fondo: FondoPantalla | None = None
    pantalla_transicion: TransicionPantalla | None = None
    pantalla_mostrar_nombre: bool | None = None
    pantalla_mostrar_qr: bool | None = None

    @model_validator(mode="after")
    def _algo_para_cambiar(self) -> "CambioEstadoEvento":
        if all(getattr(self, campo) is None for campo in type(self).model_fields):
            raise ValueError("Mandá al menos un campo para cambiar")
        return self


class EventoAdmin(BaseModel):
    """Un evento visto desde el panel: con sus dos claves, sus totales y su dueño.

    El dueño viaja siempre, también para un organizador que sólo ve los suyos:
    así el panel usa una sola forma y no tiene que preguntar el rol para leerla.

    A los 30 días de la fecha se borran de Cloudinary las fotos y los videos:
    `fotos_se_borran_el` dice cuándo (fecha_evento + 30), y `fotos_borradas_en`
    cuándo pasó, o null si todavía no. Las filas quedan, así que los totales
    siguen contando las fotos que hubo.

    `video_url_listo` es la URL del último video si está `listo` y los archivos
    no se borraron ni se están borrando (desde el día del borrado ya es null,
    aunque la limpieza todavía no haya pasado); si no, null. Es lo que el panel ofrece descargar sin tener
    que pedir el estado del video a cada evento de la lista.

    Los cuatro `pantalla_*` son el estilo de la pantalla del proyector. Al
    crear el evento se copian de los predeterminados del dueño, igual que
    `segundos_por_foto` y `max_fotos_por_dispositivo`.
    """

    id: int
    nombre: str
    fecha_evento: date
    estado: EstadoEvento
    codigo_publico: str
    token_pantalla: str
    segundos_por_foto: int
    max_fotos_por_dispositivo: int
    pendientes: int
    aprobadas: int
    rechazadas: int
    organizador_id: int
    organizador_nombre: str
    fotos_se_borran_el: date
    fotos_borradas_en: datetime | None
    video_url_listo: str | None
    pantalla_fondo: FondoPantalla
    pantalla_transicion: TransicionPantalla
    pantalla_mostrar_nombre: bool
    pantalla_mostrar_qr: bool


class VideoEvento(BaseModel):
    """GET y POST /api/admin/eventos/{id}/video

    `ninguno`: nunca se pidió. `procesando`: Cloudinary lo está armando.
    `listo`: `url` apunta al MP4. `fallo`: Cloudinary no lo aceptó o no lo
    terminó a tiempo; se puede volver a pedir.
    """

    estado: Literal["ninguno", "procesando", "listo", "fallo"]
    url: str | None
    fotos: int | None
    pedido_en: datetime | None


class FotoAdmin(BaseModel):
    """Una foto vista desde la bandeja de moderación."""

    id: int
    url: str
    ancho: int | None
    alto: int | None
    bytes: int | None
    estado: EstadoFoto
    nombre_invitado: str | None
    subida_en: datetime


class ListaFotosAdmin(BaseModel):
    """GET /api/admin/eventos/{id}/fotos"""

    fotos: list[FotoAdmin]
    ultimo_id: int


class Resumen(BaseModel):
    """GET /api/admin/eventos/{id}/resumen"""

    pendientes: int
    aprobadas: int
    rechazadas: int


class CambioEstadoFoto(BaseModel):
    """Cuerpo de PATCH /api/admin/fotos/{id}. Moderar es idempotente."""

    estado: EstadoFoto


class FotoModerada(BaseModel):
    """Respuesta de PATCH /api/admin/fotos/{id}"""

    id: int
    estado: EstadoFoto


class LoteModeracion(BaseModel):
    """Cuerpo de POST /api/admin/fotos/lote"""

    ids: list[int] = Field(min_length=1, examples=[[128, 129, 130]])
    estado: EstadoFoto


class ResultadoLote(BaseModel):
    afectadas: int


# ─────────────────────────────────────────────────────────────
# Cuentas y roles
# ─────────────────────────────────────────────────────────────

class PedidoRegistro(BaseModel):
    """Cuerpo de POST /api/cuentas/registro. Público, sin token.

    La contraseña tiene el mismo mínimo que pide crear_admin.py. El máximo es
    para que nadie mande un megabyte a que lo pase por bcrypt.
    """

    email: EmailCuenta = Field(examples=["bruno@transmitifoto.test"])
    nombre: NombreCuenta = Field(examples=["Bruno"])
    password: str = Field(min_length=10, max_length=128)


class RegistroRecibido(BaseModel):
    """Respuesta 201 del registro. Es SIEMPRE la misma, exista o no el email:
    una respuesta distinta serviría para averiguar qué emails están registrados."""

    estado: Literal["pendiente"]


class EstiloPantalla(BaseModel):
    """El estilo de la pantalla del proyector, dentro de los predeterminados."""

    fondo: FondoPantalla
    transicion: TransicionPantalla
    mostrar_nombre: bool
    mostrar_qr: bool


class Predeterminados(BaseModel):
    """Lo que se copia a cada evento nuevo de la cuenta. Cambiarlos no toca los
    eventos que ya existen."""

    segundos_por_foto: int
    max_fotos_por_dispositivo: int
    pantalla: EstiloPantalla


class UsuarioYo(BaseModel):
    """GET /api/admin/yo: quién tiene la sesión abierta, con lo de Mi cuenta.

    Lo devuelven también PATCH /api/admin/yo y los tres del avatar.
    """

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "id": 3,
        "email": "bruno@transmitifoto.test",
        "nombre": "Bruno",
        "rol": "organizador",
        "avatar_url": None,
        "tema": "automatico",
        "predeterminados": {
            "segundos_por_foto": 7,
            "max_fotos_por_dispositivo": 10,
            "pantalla": {"fondo": "desenfocado", "transicion": "fundido",
                         "mostrar_nombre": True, "mostrar_qr": True},
        },
    }]})

    id: int
    email: str
    nombre: str
    rol: RolUsuario
    avatar_url: str | None
    tema: TemaPanel
    predeterminados: Predeterminados


# Un cambio parcial: los campos que faltan (o vienen en null) no se tocan. Con
# `extra="forbid"`, un campo que no existe es 422 y no se ignora en silencio:
# así un `rol` o un `email` en el cuerpo no parecen haber cambiado algo.
_PARCIAL = ConfigDict(extra="forbid")


class CambioEstiloPantalla(BaseModel):
    model_config = _PARCIAL

    fondo: FondoPantalla | None = None
    transicion: TransicionPantalla | None = None
    mostrar_nombre: bool | None = None
    mostrar_qr: bool | None = None


class CambioPredeterminados(BaseModel):
    model_config = _PARCIAL

    segundos_por_foto: SegundosPorFoto | None = None
    max_fotos_por_dispositivo: MaxFotosPorDispositivo | None = None
    pantalla: CambioEstiloPantalla | None = None


class CambioYo(BaseModel):
    """Cuerpo de PATCH /api/admin/yo. Todo parcial, y al menos un valor en total.

    No cambia el email, el rol ni el estado: esos campos no existen acá y
    mandarlos es 422.
    """

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [
        {"tema": "claro"},
        {"predeterminados": {"segundos_por_foto": 9, "pantalla": {"fondo": "negro"}}},
    ]})

    nombre: NombreCuenta | None = None
    tema: TemaPanel | None = None
    predeterminados: CambioPredeterminados | None = None

    def valores(self) -> dict[str, object]:
        """Los valores mandados, aplanados: {"tema": ..., "pantalla.fondo": ...}."""
        planos: dict[str, object] = {}
        if self.nombre is not None:
            planos["nombre"] = self.nombre
        if self.tema is not None:
            planos["tema"] = self.tema
        pred = self.predeterminados
        if pred is not None:
            for campo in ("segundos_por_foto", "max_fotos_por_dispositivo"):
                if getattr(pred, campo) is not None:
                    planos[campo] = getattr(pred, campo)
            if pred.pantalla is not None:
                for campo in ("fondo", "transicion", "mostrar_nombre", "mostrar_qr"):
                    if getattr(pred.pantalla, campo) is not None:
                        planos[f"pantalla.{campo}"] = getattr(pred.pantalla, campo)
        return planos

    @model_validator(mode="after")
    def _algo_para_cambiar(self) -> "CambioYo":
        if not self.valores():
            raise ValueError("Mandá al menos un campo para cambiar")
        return self


class PedidoCambioContrasena(BaseModel):
    """Cuerpo de POST /api/admin/yo/contrasena. `nueva`, igual que en el registro."""

    actual: str = Field(min_length=1, max_length=1024)
    nueva: str = Field(min_length=10, max_length=128)


class AvatarNuevo(BaseModel):
    """Cuerpo de PUT /api/admin/yo/avatar: la imagen ya subida a Cloudinary.

    El `public_id` tiene que estar en `avatares/{id de la cuenta}/`, sin
    subcarpetas (si no, PUBLIC_ID_AJENO), y la `url` tiene que ser exactamente
    la de esa imagen en la cuenta de Cloudinary de la app (si no,
    ARCHIVO_INVALIDO). Mismos largos que una foto de invitado.
    """

    public_id: str = Field(max_length=200, examples=["avatares/3/k3j2h1"])
    url: str = Field(
        max_length=500,
        examples=["https://res.cloudinary.com/demo/image/upload/v1/avatares/3/k3j2h1.jpg"],
    )


class Cuenta(BaseModel):
    """Una cuenta vista por un admin, con un resumen de su historial.

    `ultimo_evento` es la fecha del evento más reciente de la cuenta, o null si
    todavía no tiene ninguno.
    """

    id: int
    email: str
    nombre: str
    rol: RolUsuario
    estado: EstadoCuenta
    creado_en: datetime
    eventos: int
    ultimo_evento: date | None
    avatar_url: str | None


class CambioCuenta(BaseModel):
    """Cuerpo de PATCH /api/admin/cuentas/{id}. Cualquier combinación, al menos uno.

    `pendiente` no es un valor aceptado: una cuenta se habilita o se da de baja,
    no vuelve a esperar. Dar de baja reemplaza a borrar: nada se borra.

    `rol: superadmin` pasa la validación sólo para que el endpoint responda con
    un mensaje claro ("El rol superadmin no se asigna desde el panel") en vez
    del genérico de datos inválidos. Nunca se aplica: el superadmin se nombra a
    mano en la base. Quién puede cambiar qué cuenta está en routers/cuentas.py.
    """

    estado: Literal["activa", "baja"] | None = None
    rol: RolUsuario | None = None
    nombre: NombreCuenta | None = None

    @model_validator(mode="after")
    def _algo_para_cambiar(self) -> "CambioCuenta":
        if self.estado is None and self.rol is None and self.nombre is None:
            raise ValueError("Mandá al menos un campo para cambiar")
        return self


class PedidoEliminarCuenta(BaseModel):
    """Cuerpo de DELETE /api/admin/cuentas/{id}. Sólo superadmin.

    `confirmar_email` es el email de la cuenta, escrito a mano: la confirmación
    se hace también del lado del servidor, no sólo en el diálogo del panel. Se
    compara sin mayúsculas y sin los espacios de alrededor. Va en el cuerpo y no
    en la URL, para que un email no quede en los logs de acceso.

    No se valida el formato: cualquier cosa que no sea el email de la cuenta
    responde "El email no coincide con el de la cuenta", también un texto vacío.
    """

    confirmar_email: str = Field(max_length=254, examples=["bruno@transmitifoto.test"])


class PedidoRecuperar(BaseModel):
    """Cuerpo de POST /api/cuentas/recuperar. Público, sin token."""

    email: EmailCuenta = Field(examples=["bruno@transmitifoto.test"])


class RecuperacionPedida(BaseModel):
    """Respuesta 200 de POST /api/cuentas/recuperar. Es SIEMPRE la misma, exista
    o no la cuenta: una respuesta distinta serviría para averiguar qué emails
    están registrados."""

    enviado: Literal[True]


class PedidoRestablecer(BaseModel):
    """Cuerpo de POST /api/cuentas/restablecer. Público, sin token de sesión.

    `token` es el del link del email (lo que sigue a `#token=`). Sin largo
    mínimo a propósito: cualquier token que no sirve, también uno vacío,
    responde "El link ya no sirve. Pedí uno nuevo."
    """

    token: str = Field(max_length=200)
    password: str = Field(min_length=10, max_length=128)


class ContrasenaRestablecida(BaseModel):
    """Respuesta 200 de POST /api/cuentas/restablecer. Después hay que entrar
    de nuevo: todas las sesiones de la cuenta se cerraron."""

    restablecida: Literal[True]


class CuentaEliminada(BaseModel):
    """Respuesta 200 de DELETE /api/admin/cuentas/{id}: cuántos eventos de la
    cuenta eliminada pasaron a la cuenta del superadmin que la eliminó."""

    eventos_transferidos: int = Field(examples=[3])


# ─────────────────────────────────────────────────────────────
# Vinculación de pantalla por código corto
# ─────────────────────────────────────────────────────────────

class CodigoVinculacion(BaseModel):
    """Respuesta de POST /api/admin/eventos/{id}/vincular

    Existe porque el link de la pantalla mide 68 caracteres y hay que poder
    cargarlo con el control remoto de una tele.
    """

    codigo: str = Field(examples=["394812"])
    expira_en: datetime


class PedidoCanje(BaseModel):
    """Cuerpo de POST /api/pantalla/canjear. Se aceptan espacios y guiones."""

    codigo: str = Field(min_length=6, max_length=16, examples=["394 812"])


class TokenDePantalla(BaseModel):
    """Respuesta del canje. Es la única vez que el token viaja sin estar en la URL."""

    token_pantalla: str


# ─────────────────────────────────────────────────────────────
# Salud
# ─────────────────────────────────────────────────────────────

class Salud(BaseModel):
    """GET /api/salud — sin auth."""

    estado: str = Field(examples=["ok"])
    base: str = Field(examples=["ok"])
