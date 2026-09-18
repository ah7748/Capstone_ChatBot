import io

import pytest

from tests.conftest import login

pytestmark = pytest.mark.asyncio


async def test_document_upload_list_edit_delete(client, seed):
    headers, _ = await login(client, "max@wellq.co.uk")
    content = ("Guia de examenes medicos WellQ. Los examenes pueden subirse en PDF, JPG o PNG "
               "con un maximo de 20 MB. El error 415 indica formato no compatible. "
               "Para subir un examen entra a Salud, Examenes, Subir archivo.").encode()
    files = {"file": ("guia_examenes.txt", io.BytesIO(content), "text/plain")}
    r = await client.post("/api/v1/company/documents", files=files,
                          data={"chat_type": "technical"}, headers=headers)
    assert r.status_code == 201, r.text
    doc_id = r.json()["document_id"]

    # duplicado por hash
    files = {"file": ("guia_examenes.txt", io.BytesIO(content), "text/plain")}
    r2 = await client.post("/api/v1/company/documents", files=files,
                           data={"chat_type": "technical"}, headers=headers)
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "DOCUMENT_DUPLICATE"

    # tipo no soportado
    files = {"file": ("virus.exe", io.BytesIO(b"x"), "application/octet-stream")}
    r3 = await client.post("/api/v1/company/documents", files=files,
                           data={"chat_type": "technical"}, headers=headers)
    assert r3.status_code == 415

    lst = await client.get("/api/v1/company/documents?chat_type=technical", headers=headers)
    assert lst.status_code == 200
    doc = [d for d in lst.json()["items"] if d["document_id"] == doc_id][0]
    assert doc["status"] == "indexed"
    assert doc["chunks"] >= 1

    got = await client.get(f"/api/v1/company/documents/{doc_id}/content", headers=headers)
    assert got.status_code == 200
    version = got.json()["version"]

    put = await client.put(f"/api/v1/company/documents/{doc_id}/content",
                           json={"content": "Contenido corregido del manual. Error 415: formato.",
                                 "version": version}, headers=headers)
    assert put.status_code == 200

    stale = await client.put(f"/api/v1/company/documents/{doc_id}/content",
                             json={"content": "x", "version": version}, headers=headers)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "DOCUMENT_VERSION_CONFLICT"

    dele = await client.delete(f"/api/v1/company/documents/{doc_id}", headers=headers)
    assert dele.status_code == 204


async def test_faq_crud_and_export(client, seed):
    headers, _ = await login(client, "max@wellq.co.uk")
    r = await client.post("/api/v1/company/faqs", headers=headers, json={
        "question": "¿Cómo recupero mi contraseña?",
        "answer": "Desde la pantalla de inicio pulsa Olvidé mi contraseña.",
        "chat_type": "technical"})
    assert r.status_code == 201, r.text
    faq_id = r.json()["faq_id"]

    dup = await client.post("/api/v1/company/faqs", headers=headers, json={
        "question": "¿Cómo recupero mi contraseña?",
        "answer": "Otra respuesta.", "chat_type": "technical"})
    assert dup.status_code == 409

    exp = await client.get("/api/v1/company/faqs/export?format=json", headers=headers)
    assert exp.status_code == 200
    assert "FAQ_wellq.json" in exp.headers["content-disposition"]

    expw = await client.get("/api/v1/company/faqs/export?format=docx", headers=headers)
    assert expw.status_code == 200

    bad = await client.get("/api/v1/company/faqs/export?format=xls", headers=headers)
    assert bad.status_code == 422

    upd = await client.patch(f"/api/v1/company/faqs/{faq_id}", headers=headers,
                             json={"answer": "Respuesta actualizada con más detalle."})
    assert upd.status_code == 200


async def test_faq_import_csv(client, seed):
    headers, _ = await login(client, "max@wellq.co.uk")
    csv_data = ("question,answer,chat_type\n"
                "¿Hay descuentos para equipos?,Sí desde 10 usuarios.,commercial\n"
                "mala,x,desconocido\n").encode()
    files = {"file": ("faqs.csv", io.BytesIO(csv_data), "text/csv")}
    r = await client.post("/api/v1/company/faqs/import", files=files, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["inserted"] == 1
    assert body["rejected"][0]["reason_code"] == "INVALID_ROW"
