from cryptography.fernet import Fernet

from hinga.crypto import seal, unseal
from hinga.seed import HISTORY_DAYS


def test_fernet_round_trip():
    cipher = Fernet(Fernet.generate_key())
    plain = "zephyrquartz lantern on the desk"
    assert unseal(seal(plain, cipher), cipher) == plain
    assert plain.encode() not in seal(plain, cipher).encode()


def test_stored_journal_text_is_not_plaintext_and_delete_is_one_desk(client):
    phrase = "zephyrquartz lantern on the desk at noon"
    saved = client.post("/api/entries", json={"body": phrase, "mood": 3})
    assert saved.status_code == 200
    assert phrase in saved.json()["entry"]["body"]
    raw = client.db_path.read_bytes()
    assert phrase.encode() not in raw

    exported = client.get("/api/me/export").json()
    assert any(phrase in entry["body"] for entry in exported["entries"])
    assert exported["profile"]["values"]

    client.post("/api/session", json={"user_id": "jonah"})
    other = client.get("/api/me/export").json()
    assert all(phrase not in entry["body"] for entry in other["entries"])
    assert len(other["entries"]) == HISTORY_DAYS

    client.post("/api/session", json={"user_id": "maya"})
    deleted = client.post("/api/me/delete")
    assert deleted.status_code == 200
    assert client.get("/api/entries").json()["entries"] == []
    assert client.get("/api/me/export").json()["entries"] == []
    assert phrase.encode() not in client.db_path.read_bytes()

    client.post("/api/session", json={"user_id": "jonah"})
    assert len(client.get("/api/entries").json()["entries"]) == HISTORY_DAYS
