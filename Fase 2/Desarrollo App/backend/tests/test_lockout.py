"""Bloqueo de la cuenta tras 6 intentos fallidos y desbloqueo al restablecer la contraseña."""
import re

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User
from app.services import email as mail

URL = "/api/v1/auth"


async def _usuario(email: str) -> None:
    async with SessionLocal() as db:
        db.add(User(name="Lola", email=email, role="platform_admin", status="active",
                    password_hash=hash_password("Password123!"), lang="es"))
        await db.commit()


async def _login(client, email, password):
    return await client.post(f"{URL}/login", json={"email": email, "password": password})


async def _estado(email):
    async with SessionLocal() as db:
        u = (await db.execute(select(User).where(User.email == email))).scalar_one()
        return u.failed_logins, u.locked_at


async def test_seis_fallos_bloquean_la_cuenta_y_la_clave_correcta_ya_no_sirve(client, seed):
    email = "bloqueo1@test.com"
    await _usuario(email)
    n = settings.LOGIN_MAX_ATTEMPTS
    assert n == 6
    for _ in range(n - 1):
        r = await _login(client, email, "incorrecta1")
        assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"
    ultimo = await _login(client, email, "incorrecta1")                 # el 6.º fallo bloquea
    assert ultimo.status_code == 423
    assert ultimo.json()["error"]["code"] == "AUTH_ACCOUNT_LOCKED"
    assert (await _estado(email))[1] is not None
    ok = await _login(client, email, "Password123!")                    # ni la clave correcta entra
    assert ok.status_code == 423 and ok.json()["error"]["code"] == "AUTH_ACCOUNT_LOCKED"


async def test_un_login_correcto_reinicia_el_contador(client, seed):
    email = "bloqueo2@test.com"
    await _usuario(email)
    for _ in range(5):
        assert (await _login(client, email, "incorrecta1")).status_code == 401
    assert (await _estado(email))[0] == 5
    assert (await _login(client, email, "Password123!")).status_code == 200
    assert await _estado(email) == (0, None)
    for _ in range(5):                                                  # otros 5 fallos no bloquean
        assert (await _login(client, email, "incorrecta1")).status_code == 401
    assert (await _login(client, email, "Password123!")).status_code == 200


async def test_restablecer_la_contrasena_desbloquea(client, seed):
    email = "bloqueo3@test.com"
    await _usuario(email)
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        await _login(client, email, "incorrecta1")
    assert (await _login(client, email, "Password123!")).status_code == 423

    mail.outbox.clear()
    rq = await client.post(f"{URL}/password/reset-request", json={"email": email})
    assert rq.status_code == 200 and len(mail.outbox) == 1
    token = re.search(r"token=([\w\-]+)", mail.outbox[0]["text"]).group(1)
    ok = await client.post(f"{URL}/password/reset-confirm",
                           json={"reset_token": token, "new_password": "NuevaClave123!"})
    assert ok.status_code == 200, ok.text
    assert await _estado(email) == (0, None)
    assert (await _login(client, email, "Password123!")).status_code == 401      # la anterior ya no vale
    assert (await _login(client, email, "NuevaClave123!")).status_code == 200


async def test_un_email_inexistente_no_bloquea_nada(client, seed):
    r = await _login(client, "nadie-existe@test.com", "incorrecta1")
    assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"
