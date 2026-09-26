"""Cuentas y roles: registro, habilitación, baja, y qué puede ver cada rol.

Las reglas que se prueban acá, en el orden del archivo:

- Registro público: nace organizador y pendiente, responde siempre igual
  aunque el email exista, y tiene límite de pedidos.
- Login: una cuenta pendiente o de baja no entra. La pendiente recibe lo mismo
  que una contraseña incorrecta, para que registro + login no delaten qué
  emails existen. Una baja corta también las sesiones abiertas.
- Cuentas: sólo un admin las ve y las cambia, y nadie cambia su propio rol ni
  su propio estado. La matriz completa con el superadmin está en
  test_superadmin.py.
- Eventos: un admin ve todos, un organizador sólo los suyos. Un evento ajeno
  responde 404, igual que uno inexistente. Vigentes e historial siguen la
  regla de medianoche: un evento abierto no se va al historial por su fecha.

Necesitan Postgres. Definí DATABASE_URL_TEST o se saltean solas.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models import Evento, Foto, Usuario
from app.routers import admin as rutas_admin
from app.routers import cuentas as rutas_cuentas
from app.routers.admin import hoy_en_argentina
from tests.conftest import (
    EMAIL_ADMIN,
    EMAIL_BAJA,
    EMAIL_ORGANIZADOR,
    EMAIL_PENDIENTE,
    PASSWORD_ADMIN,
    PASSWORD_CUENTA,
    iniciar_sesion,
    nueva_cuenta,
    sin_base,
    url_de,
)

pytestmark = sin_base

CLAVES_CUENTA = {"id", "email", "nombre", "rol", "estado", "creado_en", "eventos", "ultimo_evento"}


def afirmar_error(respuesta, codigo_esperado: str, http_esperado: int) -> None:
    assert respuesta.status_code == http_esperado, respuesta.text
    cuerpo = respuesta.json()
    assert set(cuerpo.keys()) == {"error"}
    assert cuerpo["error"]["codigo"] == codigo_esperado


def login(cliente, email: str, password: str):
    return cliente.post("/api/admin/login", json={"email": email, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def nuevo_evento(db, dueno: Usuario, nombre: str, codigo: str, *, estado: str = "activo",
                 fecha=None) -> Evento:
    evento = Evento(
        usuario_id=dueno.id,
        nombre=nombre,
        fecha_evento=fecha or hoy_en_argentina() + timedelta(days=7),
        codigo_publico=codigo,
        token_pantalla=(codigo * 4)[:32],
        estado=estado,
    )
    db.add(evento)
    db.commit()
    return evento


def con_fotos(db, evento: Evento) -> list[Foto]:
    """Dos pendientes y una aprobada, para tener qué moderar y qué descargar."""
    fotos = [
        Foto(evento_id=evento.id, public_id=f"eventos/{evento.codigo_publico}/f{i}",
             url=url_de(f"f{i}"), estado=estado)
        for i, estado in enumerate(["pendiente", "pendiente", "aprobada"])
    ]
    db.add_all(fotos)
    db.commit()
    return fotos


@pytest.fixture()
def evento_de_bruno(db, organizador):
    evento = nuevo_evento(db, organizador, "Cumple de Bruno", "br00no11")
    con_fotos(db, evento)
    return evento


@pytest.fixture()
def evento_de_diego(db, otro_organizador):
    evento = nuevo_evento(db, otro_organizador, "Casamiento de Diego", "di00eg22")
    con_fotos(db, evento)
    return evento


def fotos_de(db, evento: Evento, estado: str | None = None) -> list[int]:
    consulta = select(Foto.id).where(Foto.evento_id == evento.id)
    if estado:
        consulta = consulta.where(Foto.estado == estado)
    return list(db.scalars(consulta.order_by(Foto.id)))


def cantidad_de_cuentas(db) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(Usuario))


# ─────────────────────────────────────────────────────────────
# Registro público
# ─────────────────────────────────────────────────────────────

REGISTRO = {"email": "  Nueva@Transmitifoto.Test ", "nombre": "  Nueva Cuenta  ",
            "password": "una-clave-larga"}


def test_registro_crea_una_cuenta_pendiente_de_organizador(cliente_con_base, db):
    r = cliente_con_base.post("/api/cuentas/registro", json=REGISTRO)
    assert r.status_code == 201, r.text
    assert r.json() == {"estado": "pendiente"}

    db.expire_all()
    cuenta = db.scalar(select(Usuario).where(Usuario.email == "nueva@transmitifoto.test"))
    assert cuenta is not None, "el email se guarda sin espacios y en minúsculas"
    assert cuenta.nombre == "Nueva Cuenta"
    assert (cuenta.rol, cuenta.estado) == ("organizador", "pendiente")
    assert cuenta.password_hash != REGISTRO["password"], "nunca la contraseña en claro"
    assert cuenta.creado_en.tzinfo is not None


def test_registro_no_pide_sesion(cliente_con_base):
    """Es la única forma de conseguir una cuenta: tiene que andar sin token."""
    assert "Authorization" not in cliente_con_base.headers
    assert cliente_con_base.post("/api/cuentas/registro", json=REGISTRO).status_code == 201


def test_no_se_puede_registrar_como_admin_ni_activa(cliente_con_base, db):
    """Los campos de más se ignoran: rol y estado los decide un admin, no el formulario."""
    cuerpo = {**REGISTRO, "rol": "admin", "estado": "activa"}
    assert cliente_con_base.post("/api/cuentas/registro", json=cuerpo).status_code == 201
    db.expire_all()
    cuenta = db.scalar(select(Usuario).where(Usuario.email == "nueva@transmitifoto.test"))
    assert (cuenta.rol, cuenta.estado) == ("organizador", "pendiente")


def test_una_cuenta_recien_registrada_no_puede_entrar(cliente_con_base):
    cliente_con_base.post("/api/cuentas/registro", json=REGISTRO)
    r = login(cliente_con_base, "nueva@transmitifoto.test", REGISTRO["password"])
    afirmar_error(r, "NO_AUTORIZADO", 401)


def test_registro_mas_login_no_delatan_si_el_email_existia(cliente_con_base):
    """El registro deja elegir la contraseña de un email nuevo. Si después el
    login dijera "todavía no está habilitada" sólo para ése, y "contraseña
    incorrecta" para uno que ya existía, el par diría qué emails están
    registrados. Las dos respuestas tienen que ser idénticas."""
    sonda = {"nombre": "Sonda", "password": "clave-de-la-sonda"}
    for email in (EMAIL_ADMIN, "nadie-registrado@x.test"):
        r = cliente_con_base.post("/api/cuentas/registro", json={**sonda, "email": email})
        assert r.status_code == 201, r.text
    existia = login(cliente_con_base, EMAIL_ADMIN, sonda["password"])
    nuevo = login(cliente_con_base, "nadie-registrado@x.test", sonda["password"])
    afirmar_error(existia, "NO_AUTORIZADO", 401)
    assert (nuevo.status_code, nuevo.json()) == (existia.status_code, existia.json())


def test_registro_con_email_repetido_responde_igual_y_no_toca_nada(cliente_con_base, db):
    """Una respuesta distinta serviría para averiguar qué emails están registrados."""
    nuevo = cliente_con_base.post("/api/cuentas/registro", json=REGISTRO)

    ana_antes = db.scalar(select(Usuario).where(Usuario.email == EMAIL_ADMIN))
    hash_antes, nombre_antes = ana_antes.password_hash, ana_antes.nombre
    antes = cantidad_de_cuentas(db)

    repetido = cliente_con_base.post(
        "/api/cuentas/registro",
        json={"email": EMAIL_ADMIN.upper(), "nombre": "Impostora", "password": "otra-clave-larga"},
    )
    assert (repetido.status_code, repetido.json()) == (nuevo.status_code, nuevo.json())
    assert repetido.headers.get("content-length") == nuevo.headers.get("content-length")

    assert cantidad_de_cuentas(db) == antes, "no crea nada"
    ana = db.scalar(select(Usuario).where(Usuario.email == EMAIL_ADMIN))
    assert (ana.password_hash, ana.nombre, ana.rol, ana.estado) == (
        hash_antes, nombre_antes, "admin", "activa"
    ), "no cambia nada: ni la contraseña, ni el nombre, ni el estado"
    assert login(cliente_con_base, EMAIL_ADMIN, PASSWORD_ADMIN).status_code == 200
    assert login(cliente_con_base, EMAIL_ADMIN, "otra-clave-larga").status_code == 401


def test_registro_compara_el_email_sin_mayusculas(cliente_con_base, db):
    """El UNIQUE de la base distingue mayúsculas. Una cuenta vieja guardada como
    `Fede@X.Test` sólo se reconoce si la comparación ignora mayúsculas."""
    nueva_cuenta(db, "Fede@X.Test", "Fede")
    antes = cantidad_de_cuentas(db)
    r = cliente_con_base.post("/api/cuentas/registro",
                              json={**REGISTRO, "email": "fede@x.test"})
    assert r.json() == {"estado": "pendiente"}
    assert cantidad_de_cuentas(db) == antes


def test_registro_de_un_email_dado_de_baja_no_lo_reactiva(cliente_con_base, cuenta_baja, db):
    r = cliente_con_base.post(
        "/api/cuentas/registro",
        json={"email": EMAIL_BAJA, "nombre": "De nuevo", "password": "otra-clave-larga"},
    )
    assert r.json() == {"estado": "pendiente"}
    db.expire_all()
    assert db.get(Usuario, cuenta_baja.id).estado == "baja"


@pytest.mark.parametrize(
    "cambio",
    [
        {"email": "sin-arroba"},
        {"email": "dos@@arrobas.test"},
        {"email": "con espacio@x.test"},
        {"email": ""},
        {"nombre": "   "},
        {"nombre": "x" * 81},
        {"password": "corta"},
        {"password": "x" * 129},
    ],
)
def test_registro_con_datos_invalidos(cliente_con_base, db, cambio):
    antes = cantidad_de_cuentas(db)
    r = cliente_con_base.post("/api/cuentas/registro", json={**REGISTRO, **cambio})
    afirmar_error(r, "DATOS_INVALIDOS", 422)
    assert cantidad_de_cuentas(db) == antes


def test_registro_acepta_los_bordes(cliente_con_base):
    """Nombre de 80, contraseña de 10 y de 128: son los límites, no afuera de ellos."""
    for i, (nombre, password) in enumerate([("x" * 80, "x" * 10), ("y", "z" * 128)]):
        r = cliente_con_base.post(
            "/api/cuentas/registro",
            json={"email": f"borde{i}@x.test", "nombre": nombre, "password": password},
        )
        assert r.status_code == 201, r.text


def test_registro_tiene_limite_de_pedidos_por_ip(cliente_con_base, db):
    """Cinco por hora y por IP. El sexto no crea nada, aunque el email sea nuevo."""
    ip = {"X-Forwarded-For": "203.0.113.7"}
    for i in range(rutas_cuentas.MAXIMO_REGISTROS):
        r = cliente_con_base.post(
            "/api/cuentas/registro",
            json={**REGISTRO, "email": f"serie{i}@x.test"}, headers=ip,
        )
        assert r.status_code == 201, r.text

    antes = cantidad_de_cuentas(db)
    r = cliente_con_base.post(
        "/api/cuentas/registro", json={**REGISTRO, "email": "una-mas@x.test"}, headers=ip
    )
    afirmar_error(r, "DEMASIADOS_PEDIDOS", 429)
    assert cantidad_de_cuentas(db) == antes

    otra_ip = {"X-Forwarded-For": "198.51.100.9"}
    r = cliente_con_base.post(
        "/api/cuentas/registro", json={**REGISTRO, "email": "otra-ip@x.test"}, headers=otra_ip
    )
    assert r.status_code == 201, "el límite es por IP: otra persona no queda bloqueada"


def test_el_limite_de_registro_dura_una_hora_y_no_diez_minutos():
    """La limpieza periódica no puede reiniciar la cuenta del registro antes de tiempo."""
    from app import ratelimit

    clave = rutas_cuentas._CLAVE_REGISTRO
    for _ in range(rutas_cuentas.MAXIMO_REGISTROS):
        assert ratelimit.permitido("1.2.3.4", clave, ahora=0.0,
                                   maximo=rutas_cuentas.MAXIMO_REGISTROS,
                                   ventana=rutas_cuentas.VENTANA_REGISTROS)
    ratelimit.limpiar_vencidos(ahora=ratelimit.VENTANA_SEGUNDOS + 1)
    assert not ratelimit.permitido("1.2.3.4", clave, ahora=ratelimit.VENTANA_SEGUNDOS + 2,
                                   maximo=rutas_cuentas.MAXIMO_REGISTROS,
                                   ventana=rutas_cuentas.VENTANA_REGISTROS)
    assert ratelimit.permitido("1.2.3.4", clave, ahora=rutas_cuentas.VENTANA_REGISTROS + 1,
                               maximo=rutas_cuentas.MAXIMO_REGISTROS,
                               ventana=rutas_cuentas.VENTANA_REGISTROS)


# ─────────────────────────────────────────────────────────────
# Login y sesión
# ─────────────────────────────────────────────────────────────

def test_un_organizador_activo_entra(cliente_con_base, organizador):
    assert login(cliente_con_base, EMAIL_ORGANIZADOR, PASSWORD_CUENTA).status_code == 200


def test_una_cuenta_pendiente_no_puede_entrar(cliente_con_base, cuenta_pendiente):
    """Con la contraseña correcta, lo mismo que con una incorrecta: el mensaje
    cubre los dos casos sin decir cuál es."""
    r = login(cliente_con_base, EMAIL_PENDIENTE, PASSWORD_CUENTA)
    afirmar_error(r, "NO_AUTORIZADO", 401)
    assert r.json()["error"]["mensaje"] == (
        "Email o contraseña incorrectos. Si recién creaste tu cuenta, esperá a que la habiliten."
    )
    assert r.json() == login(cliente_con_base, EMAIL_PENDIENTE, "incorrecta").json()


def test_una_cuenta_de_baja_no_puede_entrar(cliente_con_base, cuenta_baja):
    r = login(cliente_con_base, EMAIL_BAJA, PASSWORD_CUENTA)
    afirmar_error(r, "NO_AUTORIZADO", 403)
    assert r.json()["error"]["mensaje"] == "Esta cuenta está dada de baja."


@pytest.mark.parametrize("email", [EMAIL_PENDIENTE, EMAIL_BAJA])
def test_con_clave_incorrecta_no_se_revela_el_estado(cliente_con_base, cuenta_pendiente,
                                                     cuenta_baja, email):
    """Sin la contraseña correcta, ni siquiera la baja se dice: es el mismo 401
    que un email que no existe."""
    mala = login(cliente_con_base, email, "incorrecta")
    no_existe = login(cliente_con_base, "nadie@x.test", "incorrecta")
    afirmar_error(mala, "NO_AUTORIZADO", 401)
    assert mala.json() == no_existe.json()


def test_la_baja_corta_la_sesion_abierta_en_el_acto(autorizado, organizador):
    """El token dura doce horas, pero la cuenta se relee en cada pedido."""
    token = iniciar_sesion(autorizado, EMAIL_ORGANIZADOR, PASSWORD_CUENTA)
    assert autorizado.get("/api/admin/eventos", headers=bearer(token)).status_code == 200

    autorizado.patch(f"/api/admin/cuentas/{organizador.id}", json={"estado": "baja"})
    for metodo, ruta in [("get", "/api/admin/eventos"), ("get", "/api/admin/yo")]:
        afirmar_error(getattr(autorizado, metodo)(ruta, headers=bearer(token)), "NO_AUTORIZADO", 401)
    r = autorizado.post("/api/admin/eventos", headers=bearer(token),
                        json={"nombre": "Después de la baja", "fecha_evento": "2026-12-01"})
    afirmar_error(r, "NO_AUTORIZADO", 401)

    autorizado.patch(f"/api/admin/cuentas/{organizador.id}", json={"estado": "activa"})
    assert autorizado.get("/api/admin/yo", headers=bearer(token)).status_code == 200, (
        "reactivada, vuelve a entrar"
    )


def test_un_cambio_de_rol_vale_desde_el_pedido_siguiente(autorizado, autorizado_superadmin,
                                                         organizador):
    """Lo hace admin un admin; quitárselo, ya siendo admin, sólo un superadmin."""
    token = iniciar_sesion(autorizado, EMAIL_ORGANIZADOR, PASSWORD_CUENTA)
    afirmar_error(autorizado.get("/api/admin/cuentas", headers=bearer(token)), "NO_AUTORIZADO", 403)

    autorizado.patch(f"/api/admin/cuentas/{organizador.id}", json={"rol": "admin"})
    assert autorizado.get("/api/admin/cuentas", headers=bearer(token)).status_code == 200

    autorizado_superadmin.patch(f"/api/admin/cuentas/{organizador.id}", json={"rol": "organizador"})
    afirmar_error(autorizado.get("/api/admin/cuentas", headers=bearer(token)), "NO_AUTORIZADO", 403)


# ─────────────────────────────────────────────────────────────
# /api/admin/yo
# ─────────────────────────────────────────────────────────────

def test_yo_de_un_admin(autorizado, db):
    ana = db.scalar(select(Usuario).where(Usuario.email == EMAIL_ADMIN))
    r = autorizado.get("/api/admin/yo")
    assert r.status_code == 200
    assert r.json() == {"id": ana.id, "email": EMAIL_ADMIN, "nombre": "Ana Moderadora", "rol": "admin"}


def test_yo_de_un_organizador(autorizado_organizador, organizador):
    assert autorizado_organizador.get("/api/admin/yo").json() == {
        "id": organizador.id, "email": EMAIL_ORGANIZADOR,
        "nombre": "Bruno Organizador", "rol": "organizador",
    }


# ─────────────────────────────────────────────────────────────
# Cuentas: sólo admins
# ─────────────────────────────────────────────────────────────

def test_un_organizador_no_ve_las_cuentas(autorizado_organizador):
    r = autorizado_organizador.get("/api/admin/cuentas")
    afirmar_error(r, "NO_AUTORIZADO", 403)
    assert r.json()["error"]["mensaje"] == "No tenés permiso para esto"


def test_un_organizador_no_cambia_cuentas(autorizado_organizador, cuenta_pendiente, db):
    r = autorizado_organizador.patch(
        f"/api/admin/cuentas/{cuenta_pendiente.id}", json={"estado": "activa"}
    )
    afirmar_error(r, "NO_AUTORIZADO", 403)
    db.expire_all()
    assert db.get(Usuario, cuenta_pendiente.id).estado == "pendiente"


def test_un_organizador_no_se_hace_admin_a_si_mismo(autorizado_organizador, organizador, db):
    r = autorizado_organizador.patch(f"/api/admin/cuentas/{organizador.id}", json={"rol": "admin"})
    afirmar_error(r, "NO_AUTORIZADO", 403)
    db.expire_all()
    assert db.get(Usuario, organizador.id).rol == "organizador"


def test_listado_de_cuentas_orden_y_forma(autorizado, db, organizador, otro_organizador,
                                          cuenta_pendiente, cuenta_baja):
    """Pendientes primero y las más nuevas arriba; después activas y al final
    las de baja, cada grupo por nombre."""
    ahora = datetime.now(timezone.utc)
    zoe = nueva_cuenta(db, "zoe@x.test", "Zoe Recién Llegada", estado="pendiente")
    zoe.creado_en = ahora - timedelta(hours=1)
    cuenta_pendiente.creado_en = ahora - timedelta(days=2)
    nueva_cuenta(db, "aaron@x.test", "Aarón Último en Llegar")
    db.commit()

    r = autorizado.get("/api/admin/cuentas")
    assert r.status_code == 200
    filas = r.json()
    assert all(set(f.keys()) == CLAVES_CUENTA for f in filas)
    assert [f["nombre"] for f in filas] == [
        "Zoe Recién Llegada",      # pendiente, hace una hora
        "Carla Pendiente",         # pendiente, hace dos días
        "Aarón Último en Llegar",  # activas por nombre, aunque se creó último
        "Ana Moderadora",
        "Bruno Organizador",
        "Diego Otro",
        "Ernesto de Baja",         # de baja, al final
    ]
    assert [f["estado"] for f in filas] == ["pendiente"] * 2 + ["activa"] * 4 + ["baja"]


def test_listado_de_cuentas_trae_el_historial(autorizado, db, organizador):
    hoy = hoy_en_argentina()
    nuevo_evento(db, organizador, "Viejo", "vi00ej00", fecha=hoy - timedelta(days=40))
    nuevo_evento(db, organizador, "Nuevo", "nu00ev00", fecha=hoy + timedelta(days=3))

    filas = {f["email"]: f for f in autorizado.get("/api/admin/cuentas").json()}
    assert filas[EMAIL_ORGANIZADOR]["eventos"] == 2
    assert filas[EMAIL_ORGANIZADOR]["ultimo_evento"] == (hoy + timedelta(days=3)).isoformat()
    assert filas[EMAIL_ADMIN]["eventos"] == 0
    assert filas[EMAIL_ADMIN]["ultimo_evento"] is None


def test_habilitar_una_cuenta_pendiente(autorizado, cuenta_pendiente):
    r = autorizado.patch(f"/api/admin/cuentas/{cuenta_pendiente.id}", json={"estado": "activa"})
    assert r.status_code == 200, r.text
    assert set(r.json().keys()) == CLAVES_CUENTA
    assert r.json()["estado"] == "activa"
    assert r.json()["rol"] == "organizador"
    assert login(autorizado, EMAIL_PENDIENTE, PASSWORD_CUENTA).status_code == 200, "ya puede entrar"


def test_dar_de_baja_no_borra_nada_y_se_puede_reactivar(autorizado, organizador,
                                                        evento_de_bruno, db):
    fotos_antes = fotos_de(db, evento_de_bruno)

    r = autorizado.patch(f"/api/admin/cuentas/{organizador.id}", json={"estado": "baja"})
    assert r.json()["estado"] == "baja"
    assert r.json()["eventos"] == 1, "la cuenta sigue teniendo su evento"

    db.expire_all()
    assert db.get(Usuario, organizador.id) is not None, "baja es un estado, no un DELETE"
    assert fotos_de(db, evento_de_bruno) == fotos_antes
    visibles = [e["id"] for e in autorizado.get("/api/admin/eventos").json()]
    assert evento_de_bruno.id in visibles, "los admins siguen viendo sus eventos"
    assert autorizado.get(f"/api/admin/eventos/{evento_de_bruno.id}/fotos").status_code == 200

    r = autorizado.patch(f"/api/admin/cuentas/{organizador.id}", json={"estado": "activa"})
    assert r.json()["estado"] == "activa"


def test_dar_y_quitar_el_rol_de_admin(autorizado, autorizado_superadmin, organizador):
    """Un admin puede hacer admin a un organizador, pero no deshacerlo: una vez
    admin, esa cuenta la gestiona sólo un superadmin."""
    r = autorizado.patch(f"/api/admin/cuentas/{organizador.id}", json={"rol": "admin"})
    assert r.json()["rol"] == "admin"
    r = autorizado.patch(f"/api/admin/cuentas/{organizador.id}", json={"rol": "organizador"})
    afirmar_error(r, "NO_AUTORIZADO", 403)
    r = autorizado_superadmin.patch(f"/api/admin/cuentas/{organizador.id}",
                                    json={"rol": "organizador"})
    assert r.json()["rol"] == "organizador"


def test_cambiar_el_nombre_de_una_cuenta(autorizado, organizador):
    r = autorizado.patch(f"/api/admin/cuentas/{organizador.id}", json={"nombre": "  Bruno B.  "})
    assert r.json()["nombre"] == "Bruno B."


def test_cambiar_una_cuenta_es_idempotente(autorizado, organizador, db):
    primera = autorizado.patch(f"/api/admin/cuentas/{organizador.id}",
                               json={"estado": "baja", "nombre": "Bruno B."})
    segunda = autorizado.patch(f"/api/admin/cuentas/{organizador.id}",
                               json={"estado": "baja", "nombre": "Bruno B."})
    assert primera.status_code == segunda.status_code == 200
    assert primera.json() == segunda.json()
    db.expire_all()
    assert cantidad_de_cuentas(db) == 2


def test_cambiar_a_un_admin_es_idempotente_para_un_superadmin(autorizado_superadmin,
                                                              organizador, db):
    cambio = {"estado": "baja", "rol": "admin"}
    primera = autorizado_superadmin.patch(f"/api/admin/cuentas/{organizador.id}", json=cambio)
    segunda = autorizado_superadmin.patch(f"/api/admin/cuentas/{organizador.id}", json=cambio)
    assert primera.status_code == segunda.status_code == 200, segunda.text
    assert primera.json() == segunda.json()
    assert (segunda.json()["rol"], segunda.json()["estado"]) == ("admin", "baja")
    db.expire_all()
    assert cantidad_de_cuentas(db) == 3


@pytest.mark.parametrize("cambio", [{"rol": "organizador"}, {"estado": "baja"},
                                    {"rol": "admin"}, {"estado": "activa"},
                                    {"rol": "organizador", "nombre": "Ana"}])
def test_un_admin_no_cambia_su_propio_rol_ni_su_estado(autorizado, db, cambio):
    """Así el sistema nunca se queda sin admins y nadie se bloquea solo. Vale
    también si el valor mandado es el mismo que ya tiene."""
    ana = db.scalar(select(Usuario).where(Usuario.email == EMAIL_ADMIN))
    r = autorizado.patch(f"/api/admin/cuentas/{ana.id}", json=cambio)
    afirmar_error(r, "DATOS_INVALIDOS", 422)
    assert r.json()["error"]["mensaje"] == "No podés cambiar tu propio rol ni tu estado"
    db.expire_all()
    ana = db.get(Usuario, ana.id)
    assert (ana.rol, ana.estado, ana.nombre) == ("admin", "activa", "Ana Moderadora")


def test_un_admin_si_puede_cambiar_su_propio_nombre(autorizado, db):
    ana = db.scalar(select(Usuario).where(Usuario.email == EMAIL_ADMIN))
    r = autorizado.patch(f"/api/admin/cuentas/{ana.id}", json={"nombre": "Ana M."})
    assert r.status_code == 200
    assert r.json()["nombre"] == "Ana M."


@pytest.mark.parametrize(
    "cambio",
    [{}, {"estado": "pendiente"}, {"estado": "cualquiera"}, {"rol": "dueño"},
     {"nombre": "   "}, {"nombre": "x" * 81}],
)
def test_cambios_de_cuenta_invalidos(autorizado, organizador, cambio):
    """Vacío no sirve, y `pendiente` no es un estado al que se pueda volver."""
    r = autorizado.patch(f"/api/admin/cuentas/{organizador.id}", json=cambio)
    afirmar_error(r, "DATOS_INVALIDOS", 422)


def test_cuenta_inexistente(autorizado):
    r = autorizado.patch("/api/admin/cuentas/999999", json={"estado": "activa"})
    afirmar_error(r, "DATOS_INVALIDOS", 404)
    assert r.json()["error"]["mensaje"] == "No encontramos esa cuenta"


# ─────────────────────────────────────────────────────────────
# Eventos: qué ve cada rol
# ─────────────────────────────────────────────────────────────

def test_un_admin_ve_todos_los_eventos_con_su_dueno(autorizado, evento_de_bruno,
                                                    evento_de_diego, organizador,
                                                    otro_organizador):
    filas = {e["nombre"]: e for e in autorizado.get("/api/admin/eventos").json()}
    assert set(filas) == {"Cumple de Bruno", "Casamiento de Diego"}
    assert filas["Cumple de Bruno"]["organizador_id"] == organizador.id
    assert filas["Cumple de Bruno"]["organizador_nombre"] == "Bruno Organizador"
    assert filas["Casamiento de Diego"]["organizador_id"] == otro_organizador.id
    assert filas["Casamiento de Diego"]["organizador_nombre"] == "Diego Otro"


def test_un_organizador_ve_solo_los_suyos(autorizado_organizador, evento_de_bruno,
                                          evento_de_diego):
    filas = autorizado_organizador.get("/api/admin/eventos").json()
    assert [e["nombre"] for e in filas] == ["Cumple de Bruno"]
    assert filas[0]["organizador_nombre"] == "Bruno Organizador"


def test_el_filtro_por_organizador_es_para_admins(autorizado, autorizado_organizador,
                                                  evento_de_bruno, evento_de_diego,
                                                  otro_organizador):
    de_diego = autorizado.get(f"/api/admin/eventos?organizador={otro_organizador.id}").json()
    assert [e["nombre"] for e in de_diego] == ["Casamiento de Diego"]

    # Un organizador que pide los de otro sigue viendo sólo los suyos.
    pedido = autorizado_organizador.get(f"/api/admin/eventos?organizador={otro_organizador.id}")
    assert [e["nombre"] for e in pedido.json()] == ["Cumple de Bruno"]


def nombres_de(cliente, consulta: str) -> list[str]:
    r = cliente.get(f"/api/admin/eventos{consulta}")
    assert r.status_code == 200, r.text
    return [e["nombre"] for e in r.json()]


def test_vigentes_e_historial(autorizado, organizador, db):
    """La regla de medianoche. Vigentes: abiertos de cualquier fecha y sin
    publicar de hoy en adelante, lo más cercano primero. Historial: terminados
    de cualquier fecha y sin publicar de fecha pasada, lo más reciente primero."""
    hoy = hoy_en_argentina()
    dia = timedelta(days=1)
    nuevo_evento(db, organizador, "Hoy", "ho00yy00", fecha=hoy)
    nuevo_evento(db, organizador, "En diez días", "di00ez00", fecha=hoy + 10 * dia, estado="borrador")
    nuevo_evento(db, organizador, "En tres días", "tr00es00", fecha=hoy + 3 * dia)
    nuevo_evento(db, organizador, "Terminado antes de tiempo", "te00rm00", fecha=hoy + 5 * dia,
                 estado="cerrado")
    nuevo_evento(db, organizador, "Ayer sin cerrar", "ay00er00", fecha=hoy - dia)
    nuevo_evento(db, organizador, "Hace un mes", "me00ss00", fecha=hoy - 30 * dia, estado="cerrado")
    nuevo_evento(db, organizador, "Sin publicar de hoy", "sp00ho00", fecha=hoy, estado="borrador")
    nuevo_evento(db, organizador, "Sin publicar de ayer", "sp00ay00", fecha=hoy - dia,
                 estado="borrador")

    assert nombres_de(autorizado, "?alcance=vigentes") == [
        "Ayer sin cerrar", "Hoy", "Sin publicar de hoy", "En tres días", "En diez días"
    ]
    assert nombres_de(autorizado, "?alcance=historial") == [
        "Terminado antes de tiempo", "Sin publicar de ayer", "Hace un mes"
    ]
    assert nombres_de(autorizado, "") == [
        "En diez días", "Terminado antes de tiempo", "En tres días", "Sin publicar de hoy",
        "Hoy", "Sin publicar de ayer", "Ayer sin cerrar", "Hace un mes",
    ], "sin alcance, todos y como siempre: por fecha, lo más nuevo primero (y el último creado)"


def test_un_evento_abierto_de_fecha_pasada_sigue_en_vigentes(autorizado, organizador, db):
    """Una fiesta que pasa la medianoche no se va al historial en plena pista, y
    uno abierto hace una semana que nadie terminó tampoco: sigue esperando que
    alguien lo termine, y es en vigentes donde se lo busca."""
    hoy = hoy_en_argentina()
    for dias, codigo in [(1, "pa00s100"), (7, "pa00s700"), (400, "pa04s000")]:
        nuevo_evento(db, organizador, f"Abierto hace {dias} días", codigo,
                     fecha=hoy - timedelta(days=dias))
    assert nombres_de(autorizado, "?alcance=vigentes") == [
        "Abierto hace 400 días", "Abierto hace 7 días", "Abierto hace 1 días"
    ]
    assert nombres_de(autorizado, "?alcance=historial") == []


def test_uno_sin_publicar_de_fecha_pasada_va_al_historial(autorizado, organizador, db):
    """Si su fecha ya pasó y nunca se publicó, ya no se va a hacer."""
    hoy = hoy_en_argentina()
    nuevo_evento(db, organizador, "Sin publicar de ayer", "sp00ay00",
                 fecha=hoy - timedelta(days=1), estado="borrador")
    nuevo_evento(db, organizador, "Sin publicar del año pasado", "sp00aa00",
                 fecha=hoy - timedelta(days=365), estado="borrador")
    assert nombres_de(autorizado, "?alcance=vigentes") == []
    assert nombres_de(autorizado, "?alcance=historial") == [
        "Sin publicar de ayer", "Sin publicar del año pasado"
    ]


def test_uno_terminado_va_al_historial_aunque_su_fecha_no_haya_llegado(autorizado,
                                                                       organizador, db):
    nuevo_evento(db, organizador, "Terminado el mes que viene", "te00mv00",
                 fecha=hoy_en_argentina() + timedelta(days=30), estado="cerrado")
    assert nombres_de(autorizado, "?alcance=vigentes") == []
    assert nombres_de(autorizado, "?alcance=historial") == ["Terminado el mes que viene"]


def test_la_regla_de_medianoche_vale_para_un_organizador(autorizado_organizador,
                                                         organizador, db):
    hoy = hoy_en_argentina()
    nuevo_evento(db, organizador, "Abierto de ayer", "ab00ay00", fecha=hoy - timedelta(days=1))
    nuevo_evento(db, organizador, "Sin publicar de ayer", "sp00ay00",
                 fecha=hoy - timedelta(days=1), estado="borrador")
    assert nombres_de(autorizado_organizador, "?alcance=vigentes") == ["Abierto de ayer"]
    assert nombres_de(autorizado_organizador, "?alcance=historial") == ["Sin publicar de ayer"]


def test_el_alcance_se_combina_con_el_filtro_por_organizador(autorizado, organizador,
                                                              otro_organizador, db):
    hoy = hoy_en_argentina()
    nuevo_evento(db, organizador, "De Bruno", "bb00bb00", fecha=hoy + timedelta(days=2))
    nuevo_evento(db, otro_organizador, "De Diego", "dd00dd00", fecha=hoy + timedelta(days=2))
    r = autorizado.get(f"/api/admin/eventos?alcance=vigentes&organizador={organizador.id}")
    assert [e["nombre"] for e in r.json()] == ["De Bruno"]


def test_alcance_invalido(autorizado):
    afirmar_error(autorizado.get("/api/admin/eventos?alcance=todos"), "DATOS_INVALIDOS", 422)


def test_hoy_es_el_de_argentina():
    """El servidor está en UTC. A las 22 h de Buenos Aires ya es mañana en UTC."""
    esperado = (datetime.now(timezone.utc) - timedelta(hours=3)).date()
    assert hoy_en_argentina() == esperado


def test_el_listado_decide_con_el_hoy_de_argentina(autorizado, organizador, db, monkeypatch):
    """El listado pregunta la fecha a hoy_en_argentina y no al reloj del
    servidor. Cuando allá cambia el día, el de hoy sin publicar pasa al
    historial; el de hoy abierto, no: la fiesta sigue."""
    nuevo_evento(db, organizador, "Esta noche, abierto", "no00ch00", fecha=hoy_en_argentina())
    nuevo_evento(db, organizador, "Esta noche, sin publicar", "no00sp00",
                 fecha=hoy_en_argentina(), estado="borrador")
    assert nombres_de(autorizado, "?alcance=vigentes") == [
        "Esta noche, abierto", "Esta noche, sin publicar"
    ]

    manana = hoy_en_argentina() + timedelta(days=1)
    monkeypatch.setattr(rutas_admin, "hoy_en_argentina", lambda: manana)
    assert nombres_de(autorizado, "?alcance=vigentes") == ["Esta noche, abierto"]
    assert nombres_de(autorizado, "?alcance=historial") == ["Esta noche, sin publicar"]


def test_a_la_medianoche_la_fiesta_sigue_en_vigentes_hasta_que_la_terminen(
    autorizado, organizador, evento_de_bruno, db, monkeypatch
):
    """El recorrido completo: abierta a la noche, pasa la medianoche, sigue en
    vigentes; recién cuando alguien la termina pasa al historial."""
    db.get(Evento, evento_de_bruno.id).fecha_evento = hoy_en_argentina()
    db.commit()
    manana = hoy_en_argentina() + timedelta(days=1)
    monkeypatch.setattr(rutas_admin, "hoy_en_argentina", lambda: manana)

    assert nombres_de(autorizado, "?alcance=vigentes") == ["Cumple de Bruno"]
    r = autorizado.patch(f"/api/admin/eventos/{evento_de_bruno.id}", json={"estado": "cerrado"})
    assert r.status_code == 200, r.text
    assert nombres_de(autorizado, "?alcance=vigentes") == []
    assert nombres_de(autorizado, "?alcance=historial") == ["Cumple de Bruno"]


# ─────────────────────────────────────────────────────────────
# Crear eventos a nombre de otra cuenta
# ─────────────────────────────────────────────────────────────

def test_un_admin_crea_un_evento_para_un_organizador(autorizado, autorizado_organizador,
                                                     organizador):
    r = autorizado.post("/api/admin/eventos", json={
        "nombre": "Para Bruno", "fecha_evento": "2026-12-01", "organizador_id": organizador.id,
    })
    assert r.status_code == 201, r.text
    assert r.json()["organizador_id"] == organizador.id
    assert r.json()["organizador_nombre"] == "Bruno Organizador"

    suyos = autorizado_organizador.get("/api/admin/eventos").json()
    assert [e["nombre"] for e in suyos] == ["Para Bruno"], "Bruno lo ve como propio"


def test_sin_organizador_el_dueno_es_quien_lo_crea(autorizado, autorizado_organizador,
                                                   organizador, db):
    ana = db.scalar(select(Usuario).where(Usuario.email == EMAIL_ADMIN))
    de_ana = autorizado.post("/api/admin/eventos",
                             json={"nombre": "De Ana", "fecha_evento": "2026-12-01"})
    de_bruno = autorizado_organizador.post("/api/admin/eventos",
                                           json={"nombre": "De Bruno", "fecha_evento": "2026-12-01"})
    assert (de_ana.json()["organizador_id"], de_ana.json()["organizador_nombre"]) == (
        ana.id, "Ana Moderadora"
    )
    assert de_bruno.json()["organizador_id"] == organizador.id


def test_un_organizador_puede_mandar_su_propio_id(autorizado_organizador, organizador):
    r = autorizado_organizador.post("/api/admin/eventos", json={
        "nombre": "Mío", "fecha_evento": "2026-12-01", "organizador_id": organizador.id,
    })
    assert r.status_code == 201, r.text
    assert r.json()["organizador_id"] == organizador.id


def test_un_organizador_no_crea_eventos_para_otro(autorizado_organizador, otro_organizador, db):
    r = autorizado_organizador.post("/api/admin/eventos", json={
        "nombre": "Para Diego", "fecha_evento": "2026-12-01",
        "organizador_id": otro_organizador.id,
    })
    afirmar_error(r, "NO_AUTORIZADO", 403)
    assert r.json()["error"]["mensaje"] == "No tenés permiso para esto"
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Evento)) == 0


@pytest.mark.parametrize("cuenta", ["pendiente", "baja", "inexistente"])
def test_no_se_crean_eventos_para_una_cuenta_que_no_esta_activa(autorizado, cuenta_pendiente,
                                                                cuenta_baja, db, cuenta):
    ids = {"pendiente": cuenta_pendiente.id, "baja": cuenta_baja.id, "inexistente": 999999}
    r = autorizado.post("/api/admin/eventos", json={
        "nombre": "No va", "fecha_evento": "2026-12-01", "organizador_id": ids[cuenta],
    })
    afirmar_error(r, "DATOS_INVALIDOS", 422)
    assert r.json()["error"]["mensaje"] == "Esa cuenta no está activa"
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Evento)) == 0


def test_cambiar_un_evento_devuelve_su_dueno(autorizado, evento_de_bruno, organizador):
    r = autorizado.patch(f"/api/admin/eventos/{evento_de_bruno.id}", json={"segundos_por_foto": 9})
    assert r.status_code == 200
    assert r.json()["organizador_id"] == organizador.id
    assert r.json()["organizador_nombre"] == "Bruno Organizador"


# ─────────────────────────────────────────────────────────────
# Eventos ajenos: 404, igual que uno que no existe
# ─────────────────────────────────────────────────────────────

# Todo lo que se hace sobre un evento por su id. El evento es de Diego y el que
# pide es Bruno: para él tiene que ser como si no existiera.
SOBRE_UN_EVENTO = [
    ("listar fotos", "get", "/api/admin/eventos/{id}/fotos", None),
    ("resumen", "get", "/api/admin/eventos/{id}/resumen", None),
    ("cambiar estado", "patch", "/api/admin/eventos/{id}", {"estado": "cerrado"}),
    ("configurar", "patch", "/api/admin/eventos/{id}", {"segundos_por_foto": 12}),
    ("ver video", "get", "/api/admin/eventos/{id}/video", None),
    ("armar video", "post", "/api/admin/eventos/{id}/video", None),
    ("descarga", "get", "/api/admin/eventos/{id}/descarga", None),
    ("vincular pantalla", "post", "/api/admin/eventos/{id}/vincular", None),
]


def pedir(cliente, metodo: str, ruta: str, cuerpo):
    if cuerpo is None:
        return getattr(cliente, metodo)(ruta)
    return getattr(cliente, metodo)(ruta, json=cuerpo)


@pytest.fixture()
def sin_descargas(monkeypatch):
    """Las URLs de estas fotos no existen: el ZIP de verdad se prueba en
    test_fase4.py. Acá sólo importa si el pedido llega o no al evento."""
    monkeypatch.setattr(rutas_admin, "armar_zip", lambda fotos: iter([b"zip"]))


@pytest.mark.parametrize("accion,metodo,ruta,cuerpo", SOBRE_UN_EVENTO,
                         ids=[x[0] for x in SOBRE_UN_EVENTO])
def test_un_organizador_no_llega_a_un_evento_ajeno(autorizado_organizador, evento_de_diego,
                                                   db, accion, metodo, ruta, cuerpo):
    ajeno = pedir(autorizado_organizador, metodo, ruta.format(id=evento_de_diego.id), cuerpo)
    afirmar_error(ajeno, "EVENTO_NO_ENCONTRADO", 404)

    inexistente = pedir(autorizado_organizador, metodo, ruta.format(id=999999), cuerpo)
    assert ajeno.json() == inexistente.json(), "no se distingue ajeno de inexistente"

    db.expire_all()
    evento = db.get(Evento, evento_de_diego.id)
    assert (evento.estado, evento.segundos_por_foto, evento.video_estado) == ("activo", 7, None), (
        "y no se tocó nada"
    )


@pytest.mark.parametrize("accion,metodo,ruta,cuerpo",
                         [x for x in SOBRE_UN_EVENTO if x[0] != "armar video"],
                         ids=[x[0] for x in SOBRE_UN_EVENTO if x[0] != "armar video"])
def test_un_organizador_si_llega_a_los_suyos(autorizado_organizador, evento_de_bruno,
                                             sin_descargas, accion, metodo, ruta, cuerpo):
    """La contracara: las mismas acciones sobre su propio evento andan. El video
    se arma en test_video.py, porque le pide a Cloudinary."""
    r = pedir(autorizado_organizador, metodo, ruta.format(id=evento_de_bruno.id), cuerpo)
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("accion,metodo,ruta,cuerpo",
                         [x for x in SOBRE_UN_EVENTO if x[0] != "armar video"],
                         ids=[x[0] for x in SOBRE_UN_EVENTO if x[0] != "armar video"])
def test_un_admin_llega_a_cualquier_evento(autorizado, evento_de_diego, sin_descargas,
                                           accion, metodo, ruta, cuerpo):
    r = pedir(autorizado, metodo, ruta.format(id=evento_de_diego.id), cuerpo)
    assert r.status_code == 200, r.text


def test_un_organizador_no_modera_una_foto_ajena(autorizado_organizador, evento_de_diego, db):
    id_foto = fotos_de(db, evento_de_diego, "pendiente")[0]
    ajena = autorizado_organizador.patch(f"/api/admin/fotos/{id_foto}", json={"estado": "aprobada"})
    afirmar_error(ajena, "FOTO_NO_ENCONTRADA", 404)
    inexistente = autorizado_organizador.patch("/api/admin/fotos/999999", json={"estado": "aprobada"})
    assert ajena.json() == inexistente.json()
    db.expire_all()
    assert db.get(Foto, id_foto).estado == "pendiente"


def test_el_lote_de_un_organizador_ignora_las_fotos_ajenas(autorizado_organizador,
                                                           evento_de_bruno, evento_de_diego, db):
    propias = fotos_de(db, evento_de_bruno, "pendiente")
    ajenas = fotos_de(db, evento_de_diego, "pendiente")

    r = autorizado_organizador.post("/api/admin/fotos/lote",
                                    json={"ids": ajenas, "estado": "aprobada"})
    assert r.json() == {"afectadas": 0}, "sólo ajenas: no cambia nada"

    r = autorizado_organizador.post("/api/admin/fotos/lote",
                                    json={"ids": ajenas + propias, "estado": "rechazada"})
    assert r.json() == {"afectadas": len(propias)}

    db.expire_all()
    assert fotos_de(db, evento_de_diego, "pendiente") == ajenas, "las ajenas siguen igual"
    assert fotos_de(db, evento_de_bruno, "rechazada") == propias


def test_un_organizador_modera_las_suyas_y_queda_registrado(autorizado_organizador,
                                                            organizador, evento_de_bruno, db):
    id_foto = fotos_de(db, evento_de_bruno, "pendiente")[0]
    r = autorizado_organizador.patch(f"/api/admin/fotos/{id_foto}", json={"estado": "aprobada"})
    assert r.json() == {"id": id_foto, "estado": "aprobada"}
    db.expire_all()
    assert db.get(Foto, id_foto).moderada_por == organizador.id


def test_un_admin_modera_fotos_de_cualquier_evento(autorizado, evento_de_diego, db):
    ana = db.scalar(select(Usuario).where(Usuario.email == EMAIL_ADMIN))
    pendientes = fotos_de(db, evento_de_diego, "pendiente")

    r = autorizado.patch(f"/api/admin/fotos/{pendientes[0]}", json={"estado": "aprobada"})
    assert r.status_code == 200
    r = autorizado.post("/api/admin/fotos/lote", json={"ids": pendientes, "estado": "aprobada"})
    assert r.json() == {"afectadas": 1}, "la primera ya estaba aprobada: idempotente"

    db.expire_all()
    assert {db.get(Foto, i).moderada_por for i in pendientes} == {ana.id}
