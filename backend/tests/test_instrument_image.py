"""Foto del pasaporte, QR descargable y etiqueta imprimible (RF-DOC-01 / T9).

La imagen es evidencia visual del activo: se guarda en el volumen de ficheros
con el `public_id` como nombre y no requiere migraciones del modelo canónico.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import instruments as instruments_api
from app.database.session import engine, get_db
from app.main import app
from app.models.calibration import AuditLog
from app.models.instrument import InstrumentType, InstrumentUnit

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"passporttwin-image-test"
JPG_BYTES = b"\xff\xd8\xff\xe0" + b"passporttwin-image-test"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("INSTRUMENT_IMAGE_DIR", str(tmp_path / "images"))

    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")

    family = InstrumentType(name=f"imagen-{uuid4()}", magnitude="Pressure", unit="bar")
    db.add(family)
    db.flush()

    instrument = InstrumentUnit(
        instrument_type_id=family.id,
        serial_number=f"IMG-{uuid4().hex[:8].upper()}",
        manufacturer="TEST",
        model="TEST",
    )
    db.add(instrument)
    db.flush()

    def override():
        yield db

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override

    try:
        yield TestClient(app), db, instrument, tmp_path / "images"
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        db.close()
        transaction.rollback()
        connection.close()


def upload(client, instrument, data=PNG_BYTES, content_type="image/png", filename="foto.png"):
    return client.post(
        f"/api/v1/instruments/{instrument.id}/image",
        files={"file": (filename, data, content_type)},
    )


def test_upload_and_serve_instrument_image(setup):
    client, db, instrument, _ = setup

    response = upload(client, instrument)

    assert response.status_code == 200
    data = response.json()
    assert data["public_id"] == str(instrument.public_id)
    assert data["size_bytes"] == len(PNG_BYTES)
    assert data["image_url"].endswith(f"/instruments/{instrument.public_id}/image")

    image = client.get(f"/api/v1/instruments/{instrument.public_id}/image")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content == PNG_BYTES

    event = db.query(AuditLog).filter(
        AuditLog.action == "INSTRUMENT_IMAGE_UPDATED",
        AuditLog.entity_id == instrument.id,
    ).one()
    assert event.details["metadata"]["size_bytes"] == len(PNG_BYTES)


def test_replacing_image_removes_previous_file(setup):
    client, _, instrument, image_dir = setup

    assert upload(client, instrument).status_code == 200
    assert upload(client, instrument, data=JPG_BYTES, content_type="image/jpeg", filename="foto.jpg").status_code == 200

    image = client.get(f"/api/v1/instruments/{instrument.public_id}/image")
    assert image.headers["content-type"] == "image/jpeg"
    assert image.content == JPG_BYTES
    assert [path.suffix for path in image_dir.iterdir()] == [".jpg"]


def test_image_is_404_when_instrument_has_no_photo(setup):
    client, _, instrument, _ = setup

    response = client.get(f"/api/v1/instruments/{instrument.public_id}/image")

    assert response.status_code == 404
    assert "no tiene fotografía" in response.json()["detail"]


def test_upload_rejects_unsupported_empty_and_oversized_files(setup, monkeypatch):
    client, _, instrument, _ = setup

    unsupported = upload(client, instrument, content_type="application/pdf", filename="foto.pdf")
    assert unsupported.status_code == 415
    assert "JPEG, PNG o WebP" in unsupported.json()["detail"]

    empty = upload(client, instrument, data=b"")
    assert empty.status_code == 400

    monkeypatch.setattr(instruments_api, "MAX_IMAGE_BYTES", 8)
    oversized = upload(client, instrument)
    assert oversized.status_code == 413


def test_qr_and_label_downloads_use_attachment_filenames(setup):
    client, _, instrument, _ = setup

    qr_download = client.get(f"/api/v1/instruments/{instrument.public_id}/qr?download=true")
    assert qr_download.status_code == 200
    assert qr_download.headers["content-type"] == "image/png"
    assert qr_download.headers["content-disposition"] == (
        f'attachment; filename="qr-{instrument.serial_number}.png"'
    )

    qr_inline = client.get(f"/api/v1/instruments/{instrument.public_id}/qr")
    assert "content-disposition" not in qr_inline.headers

    label = client.get(f"/api/v1/instruments/{instrument.public_id}/label.pdf")
    assert label.status_code == 200
    assert label.headers["content-disposition"] == (
        f'attachment; filename="etiqueta-{instrument.serial_number}.pdf"'
    )

    label_inline = client.get(f"/api/v1/instruments/{instrument.public_id}/label.pdf?download=false")
    assert label_inline.headers["content-disposition"].startswith("inline;")
