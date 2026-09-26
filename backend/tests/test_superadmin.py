"""Superadmin: la matriz de quién cambia qué cuenta, y que ve todo como un admin.

La matriz de PATCH /api/admin/cuentas/{id} (sección 5 de CONSTRUIR-APP.md),
con actor = quien pide y objetivo = la cuenta:

| objetivo                              | admin | superadmin |
|---------------------------------------|-------|------------|
| organizador (activa, pendiente, baja) |  200  |    200     |
| admin                                 |  403  |    200     |
| otro superadmin                       |  403  |    403     |
| la propia: rol o estado               |  422  |    422     |
| la propia: nombre                     |  200  |    200     |
| cualquiera con `rol: superadmin`      |  422  |    422     |

Cada celda se prueba con los tres campos: rol, estado y nombre.

Necesitan Postgres. Definí DATABASE_URL_TEST o se saltean solas.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text

import crear_admin
from app.deps import es_admin, es_superadmin, solo_admin
from app.errores import ErrorApp
from app.models import Evento, Usuario
from app.security import crear_token, verificar_password
from tests.conftest import (
    EMAIL_ADMIN,
    EMAIL_PENDIENTE,
    EMAIL_SUPERADMIN,
    PASSWORD_CUENTA,
    nueva_cuenta,
    sin_base,
)
from tests.test_cuentas import (
    SOBRE_UN_EVENTO,
    YO_POR_DEFECTO,
    afirmar_error,
    con_fotos,
    fotos_de,
    login,
    nuevo_evento,
    pedir,
)

pytestmark = sin_base

SIN_PERMISO = "No tenés permiso para esto"
PROPIO = "No podés cambiar tu propio rol ni tu estado"
NO_SE_ASIGNA = "El rol superadmin no se asigna desde el panel"


# ─────────────────────────────────────────────────────────────
# Las cuentas de la matriz
# ─────────────────────────────────────────────────────────────

@pytest.fixture()
def cuentas(limpiar, superadmin, organizador, cuenta_pendiente, cuenta_baja) -> dict[str, Usuario]:
    """Una cuenta por cada tipo de objetivo. Ana, la admin de `limpiar`, es la
    `admin`; Sofía, la `superadmin`. Cada una tiene un par del mismo rol, para
    que "otro admin" y "otro superadmin" no sean la propia cuenta.

    Usa los fixtures de conftest para las que ya existen: así convive con
    `autorizado_superadmin`, que necesita a la misma Sofía."""
    db = limpiar
    return {
        "superadmin": superadmin,
        "otro_superadmin": nueva_cuenta(db, "tomas@transmitifoto.test", "Tomás Superadmin",
                                        rol="superadmin"),
        "admin": db.scalar(select(Usuario).where(Usuario.email == EMAIL_ADMIN)),
        "otro_admin": nueva_cuenta(db, "gabi@transmitifoto.test", "Gabi Admin", rol="admin"),
        "admin_de_baja": nueva_cuenta(db, "hugo@transmitifoto.test", "Hugo Admin de Baja",
                                      rol="admin", estado="baja"),
        "organizador": organizador,
        "pendiente": cuenta_pendiente,
        "baja": cuenta_baja,
    }


def bearer_de(cuenta: Usuario) -> dict[str, str]:
    """Un token de verdad, firmado igual que el del login, sin pasar por bcrypt:
    la matriz son decenas de casos y el login ya tiene sus propias pruebas."""
    token, _ = crear_token(cuenta.id, cuenta.email)
    return {"Authorization": f"Bearer {token}"}


def cambio_natural(campo: str, objetivo: Usuario) -> dict:
    """El cambio que tiene sentido pedir sobre esa cuenta para ese campo."""
    if campo == "rol":
        return {"rol": "organizador" if objetivo.rol in ("admin", "superadmin") else "admin"}
    if campo == "estado":
        return {"estado": "baja" if objetivo.estado == "activa" else "activa"}
    return {"nombre": f"{objetivo.nombre} (renombrada)"}


def como_quedo(db, cuenta: Usuario) -> tuple[str, str, str]:
    db.expire_all()
    fila = db.get(Usuario, cuenta.id)
    return (fila.rol, fila.estado, fila.nombre)


# ─────────────────────────────────────────────────────────────
# La matriz de PATCH /api/admin/cuentas/{id}
# ─────────────────────────────────────────────────────────────

# (actor, objetivo) → HTTP esperado para rol, estado y nombre.
MATRIZ = {
    ("superadmin", "otro_superadmin"): (403, 403, 403),
    ("superadmin", "admin"): (200, 200, 200),
    ("superadmin", "admin_de_baja"): (200, 200, 200),
    ("superadmin", "organizador"): (200, 200, 200),
    ("superadmin", "pendiente"): (200, 200, 200),
    ("superadmin", "baja"): (200, 200, 200),
    ("superadmin", "superadmin"): (422, 422, 200),
    ("admin", "superadmin"): (403, 403, 403),
    ("admin", "otro_admin"): (403, 403, 403),
    ("admin", "admin_de_baja"): (403, 403, 403),
    ("admin", "organizador"): (200, 200, 200),
    ("admin", "pendiente"): (200, 200, 200),
    ("admin", "baja"): (200, 200, 200),
    ("admin", "admin"): (422, 422, 200),
}

CASOS = [
    (actor, objetivo, campo, esperado[i])
    for (actor, objetivo), esperado in MATRIZ.items()
    for i, campo in enumerate(("rol", "estado", "nombre"))
]


@pytest.mark.parametrize(
    "actor,objetivo,campo,http", CASOS, ids=[f"{a}-{o}-{c}" for a, o, c, _ in CASOS]
)
def test_matriz_de_cambios_de_cuenta(cliente_con_base, cuentas, db, actor, objetivo, campo, http):
    cuenta = cuentas[objetivo]
    cambio = cambio_natural(campo, cuenta)
    antes = como_quedo(db, cuenta)

    r = cliente_con_base.patch(f"/api/admin/cuentas/{cuenta.id}", json=cambio,
                               headers=bearer_de(cuentas[actor]))

    if http == 200:
        assert r.status_code == 200, r.text
        assert r.json()[campo] == cambio[campo]
        assert como_quedo(db, cuenta) != antes, "y quedó guardado"
        return
    if http == 403:
        afirmar_error(r, "NO_AUTORIZADO", 403)
        assert r.json()["error"]["mensaje"] == SIN_PERMISO
    else:
        afirmar_error(r, "DATOS_INVALIDOS", 422)
        assert r.json()["error"]["mensaje"] == PROPIO
    assert como_quedo(db, cuenta) == antes, "y no se tocó nada"


@pytest.mark.parametrize("actor", ["superadmin", "admin"])
@pytest.mark.parametrize(
    "objetivo",
    ["superadmin", "otro_superadmin", "admin", "otro_admin", "organizador", "pendiente", "baja"],
)
def test_el_rol_superadmin_no_se_asigna_desde_el_panel(cliente_con_base, cuentas, db,
                                                       actor, objetivo):
    """Ni a una cuenta ajena ni a la propia, ni siquiera a quien ya lo es."""
    cuenta = cuentas[objetivo]
    antes = como_quedo(db, cuenta)
    r = cliente_con_base.patch(f"/api/admin/cuentas/{cuenta.id}", json={"rol": "superadmin"},
                               headers=bearer_de(cuentas[actor]))
    afirmar_error(r, "DATOS_INVALIDOS", 422)
    assert r.json()["error"]["mensaje"] == NO_SE_ASIGNA
    assert como_quedo(db, cuenta) == antes


def test_el_rol_superadmin_se_rechaza_aunque_venga_con_otros_cambios(cliente_con_base,
                                                                     cuentas, db):
    cuenta = cuentas["pendiente"]
    r = cliente_con_base.patch(
        f"/api/admin/cuentas/{cuenta.id}",
        json={"estado": "activa", "rol": "superadmin", "nombre": "Carla"},
        headers=bearer_de(cuentas["superadmin"]),
    )
    afirmar_error(r, "DATOS_INVALIDOS", 422)
    assert como_quedo(db, cuenta) == ("organizador", "pendiente", "Carla Pendiente"), (
        "no se aplica ni una parte del cambio"
    )


@pytest.mark.parametrize("actor", ["superadmin", "admin"])
def test_habilitar_como_admin(cliente_con_base, cuentas, db, actor):
    """'Habilitar como admin' es estado activa + rol admin en un solo pedido.
    Lo pueden hacer los dos: los admins también crean admins."""
    cuenta = cuentas["pendiente"]
    r = cliente_con_base.patch(f"/api/admin/cuentas/{cuenta.id}",
                               json={"estado": "activa", "rol": "admin"},
                               headers=bearer_de(cuentas[actor]))
    assert r.status_code == 200, r.text
    assert (r.json()["rol"], r.json()["estado"]) == ("admin", "activa")
    assert login(cliente_con_base, EMAIL_PENDIENTE, PASSWORD_CUENTA).status_code == 200


def test_el_admin_recien_nombrado_ya_no_lo_toca_otro_admin(cliente_con_base, cuentas, db):
    """Un admin hace admin a Bruno; desde ese momento, a Bruno lo gestiona sólo un superadmin."""
    bruno = cuentas["organizador"]
    como_admin = bearer_de(cuentas["admin"])
    r = cliente_con_base.patch(f"/api/admin/cuentas/{bruno.id}", json={"rol": "admin"},
                               headers=como_admin)
    assert r.status_code == 200
    for cambio in ({"rol": "organizador"}, {"estado": "baja"}, {"nombre": "Bruno B."}):
        r = cliente_con_base.patch(f"/api/admin/cuentas/{bruno.id}", json=cambio,
                                   headers=como_admin)
        afirmar_error(r, "NO_AUTORIZADO", 403)
    assert como_quedo(db, bruno) == ("admin", "activa", "Bruno Organizador")


def test_un_superadmin_da_de_baja_y_reactiva_a_un_admin(cliente_con_base, cuentas, db):
    gabi = cuentas["otro_admin"]
    como_superadmin = bearer_de(cuentas["superadmin"])
    for estado in ("baja", "activa"):
        r = cliente_con_base.patch(f"/api/admin/cuentas/{gabi.id}", json={"estado": estado},
                                   headers=como_superadmin)
        assert r.json()["estado"] == estado
    assert como_quedo(db, gabi) == ("admin", "activa", "Gabi Admin")


def test_un_admin_no_toca_a_otro_admin_ni_con_un_cambio_que_no_cambia_nada(cliente_con_base,
                                                                          cuentas):
    """El permiso depende de la cuenta, no de si el cambio termina tocando algo."""
    gabi = cuentas["otro_admin"]
    r = cliente_con_base.patch(f"/api/admin/cuentas/{gabi.id}",
                               json={"rol": "admin", "nombre": "Gabi Admin"},
                               headers=bearer_de(cuentas["admin"]))
    afirmar_error(r, "NO_AUTORIZADO", 403)


def test_un_superadmin_no_cambia_su_propio_rol_ni_su_estado_aunque_no_cambie_nada(
    cliente_con_base, cuentas, db
):
    sofia = cuentas["superadmin"]
    for cambio in ({"estado": "activa"}, {"rol": "admin"}, {"estado": "baja", "nombre": "Sofi"}):
        r = cliente_con_base.patch(f"/api/admin/cuentas/{sofia.id}", json=cambio,
                                   headers=bearer_de(sofia))
        afirmar_error(r, "DATOS_INVALIDOS", 422)
        assert r.json()["error"]["mensaje"] == PROPIO
    assert como_quedo(db, sofia) == ("superadmin", "activa", "Sofía Superadmin")


def test_un_superadmin_cambia_su_propio_nombre(cliente_con_base, cuentas):
    sofia = cuentas["superadmin"]
    r = cliente_con_base.patch(f"/api/admin/cuentas/{sofia.id}", json={"nombre": "Sofi"},
                               headers=bearer_de(sofia))
    assert r.status_code == 200, r.text
    assert (r.json()["nombre"], r.json()["rol"]) == ("Sofi", "superadmin")


def test_un_organizador_no_toca_ninguna_cuenta(cliente_con_base, cuentas, db):
    """solo_admin corta antes de la matriz: 403 para cualquier objetivo."""
    como_organizador = bearer_de(cuentas["organizador"])
    for objetivo in ("superadmin", "admin", "pendiente", "baja"):
        cuenta = cuentas[objetivo]
        antes = como_quedo(db, cuenta)
        r = cliente_con_base.patch(f"/api/admin/cuentas/{cuenta.id}",
                                   json={"nombre": "Otro nombre"}, headers=como_organizador)
        afirmar_error(r, "NO_AUTORIZADO", 403)
        assert como_quedo(db, cuenta) == antes


def test_cuenta_inexistente_para_un_superadmin(cliente_con_base, cuentas):
    r = cliente_con_base.patch("/api/admin/cuentas/999999", json={"estado": "activa"},
                               headers=bearer_de(cuentas["superadmin"]))
    afirmar_error(r, "DATOS_INVALIDOS", 404)


# ─────────────────────────────────────────────────────────────
# El superadmin en el resto del panel: es un admin más
# ─────────────────────────────────────────────────────────────

def test_es_admin_y_solo_admin_aceptan_al_superadmin():
    superadmin = Usuario(id=1, email="s@x.test", nombre="S", rol="superadmin", estado="activa")
    admin = Usuario(id=2, email="a@x.test", nombre="A", rol="admin", estado="activa")
    organizador = Usuario(id=3, email="o@x.test", nombre="O", rol="organizador",
                          estado="activa")

    assert (es_admin(superadmin), es_admin(admin), es_admin(organizador)) == (True, True, False)
    assert (es_superadmin(superadmin), es_superadmin(admin)) == (True, False)
    assert solo_admin(superadmin) is superadmin
    assert solo_admin(admin) is admin
    with pytest.raises(ErrorApp) as error:
        solo_admin(organizador)
    assert error.value.http == 403


def test_un_superadmin_entra_y_yo_dice_su_rol(autorizado_superadmin, superadmin):
    r = autorizado_superadmin.get("/api/admin/yo")
    assert r.status_code == 200
    assert r.json() == {"id": superadmin.id, "email": EMAIL_SUPERADMIN,
                        "nombre": "Sofía Superadmin", "rol": "superadmin", **YO_POR_DEFECTO}


def test_un_superadmin_ve_las_cuentas_y_los_superadmins_figuran(autorizado,
                                                               autorizado_superadmin, cuentas):
    """El listado incluye a los superadmins, para un admin y para un superadmin."""
    for cliente in (autorizado, autorizado_superadmin):
        r = cliente.get("/api/admin/cuentas")
        assert r.status_code == 200, r.text
        roles = {f["email"]: f["rol"] for f in r.json()}
        assert roles[EMAIL_SUPERADMIN] == "superadmin"
        assert roles["tomas@transmitifoto.test"] == "superadmin"
        assert roles[EMAIL_ADMIN] == "admin"


@pytest.fixture()
def eventos_ajenos(db, cuentas) -> dict[str, Evento]:
    """Un evento de Bruno y uno de Ana: para Sofía, los dos son ajenos."""
    de_bruno = nuevo_evento(db, cuentas["organizador"], "Cumple de Bruno", "br00no11")
    de_ana = nuevo_evento(db, cuentas["admin"], "Casamiento de Ana", "an00aa22")
    con_fotos(db, de_bruno)
    con_fotos(db, de_ana)
    return {"de_bruno": de_bruno, "de_ana": de_ana}


def test_un_superadmin_ve_todos_los_eventos(autorizado_superadmin, cuentas, eventos_ajenos):
    filas = {e["nombre"]: e for e in autorizado_superadmin.get("/api/admin/eventos").json()}
    assert set(filas) == {"Cumple de Bruno", "Casamiento de Ana"}
    assert filas["Cumple de Bruno"]["organizador_nombre"] == "Bruno Organizador"

    bruno = cuentas["organizador"]
    r = autorizado_superadmin.get(f"/api/admin/eventos?organizador={bruno.id}&alcance=vigentes")
    assert [e["nombre"] for e in r.json()] == ["Cumple de Bruno"], "el filtro se respeta"


@pytest.fixture()
def sin_descargas(monkeypatch):
    from app.routers import admin as rutas_admin

    monkeypatch.setattr(rutas_admin, "armar_zip", lambda fotos: iter([b"zip"]))


@pytest.mark.parametrize("accion,metodo,ruta,cuerpo",
                         [x for x in SOBRE_UN_EVENTO if x[0] != "armar video"],
                         ids=[x[0] for x in SOBRE_UN_EVENTO if x[0] != "armar video"])
def test_un_superadmin_llega_a_cualquier_evento(autorizado_superadmin, eventos_ajenos,
                                                sin_descargas, accion, metodo, ruta, cuerpo):
    r = pedir(autorizado_superadmin, metodo, ruta.format(id=eventos_ajenos["de_bruno"].id), cuerpo)
    assert r.status_code == 200, r.text


def test_un_superadmin_modera_y_crea_eventos_para_otros(autorizado_superadmin, cuentas,
                                                        eventos_ajenos, db):
    sofia = cuentas["superadmin"]
    de_bruno = eventos_ajenos["de_bruno"]
    pendientes = fotos_de(db, de_bruno, "pendiente")
    r = autorizado_superadmin.post("/api/admin/fotos/lote",
                                   json={"ids": pendientes, "estado": "aprobada"})
    assert r.json() == {"afectadas": len(pendientes)}
    db.expire_all()
    assert set(fotos_de(db, de_bruno, "aprobada")) >= set(pendientes)

    r = autorizado_superadmin.post("/api/admin/eventos", json={
        "nombre": "Para Bruno", "fecha_evento": "2026-12-01",
        "organizador_id": cuentas["organizador"].id,
    })
    assert r.status_code == 201, r.text
    assert r.json()["organizador_id"] == cuentas["organizador"].id
    assert sofia.id not in {e.usuario_id for e in db.scalars(select(Evento))}


# ─────────────────────────────────────────────────────────────
# crear_admin.py
# ─────────────────────────────────────────────────────────────

def correr_crear_admin(monkeypatch, capsys, respuestas: list[str]) -> str:
    """Contesta las preguntas del script y devuelve lo que imprimió."""
    entradas = iter(respuestas)
    monkeypatch.setattr("builtins.input", lambda _: next(entradas))
    monkeypatch.setattr(crear_admin, "getpass", lambda _: "clave-de-diez-o-mas")
    crear_admin.main()
    return capsys.readouterr().out


@pytest.mark.parametrize("respuesta,rol", [("", "superadmin"), ("superadmin", "superadmin"),
                                           ("  Admin ", "admin")])
def test_crear_admin_pregunta_el_rol(monkeypatch, capsys, limpiar, respuesta, rol):
    """Por defecto superadmin. El INSERT que imprime entra tal cual en la base,
    con el rol elegido, la cuenta activa y la contraseña hasheada."""
    salida = correr_crear_admin(monkeypatch, capsys,
                                ["Duena@Ejemplo.Test ", "Dueña de la App", respuesta])
    insert = salida[salida.index("INSERT"):]
    assert "clave-de-diez-o-mas" not in salida, "nunca la contraseña en claro"

    limpiar.execute(text(insert))
    limpiar.commit()
    cuenta = limpiar.scalar(select(Usuario).where(Usuario.email == "duena@ejemplo.test"))
    assert (cuenta.nombre, cuenta.rol, cuenta.estado) == ("Dueña de la App", rol, "activa")
    assert verificar_password("clave-de-diez-o-mas", cuenta.password_hash)


@pytest.mark.parametrize("respuesta", ["organizador", "dueña", "super"])
def test_crear_admin_no_acepta_otro_rol(monkeypatch, capsys, respuesta):
    with pytest.raises(SystemExit):
        correr_crear_admin(monkeypatch, capsys, ["x@ejemplo.test", "X", respuesta])
    assert "INSERT" not in capsys.readouterr().out


def test_crear_admin_escapa_las_comillas():
    assert "'O''Brien'" in crear_admin.insert("o@x.test", "O'Brien", "hash", "admin")
    with pytest.raises(ValueError):
        crear_admin.insert("o@x.test", "O", "hash", "organizador")
