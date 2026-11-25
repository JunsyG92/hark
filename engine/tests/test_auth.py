from __future__ import annotations

import keyring
from keyring.backends import fail

from hark_engine import auth


def test_file_fallback_is_private_and_stable(tmp_path, monkeypatch):
    monkeypatch.delenv("HARK_TOKEN", raising=False)
    monkeypatch.setattr(keyring, "get_keyring", lambda: fail.Keyring())
    t1 = auth.load_or_create_master_token(tmp_path)
    t2 = auth.load_or_create_master_token(tmp_path)
    assert t1 == t2 and len(t1) >= 40
    assert (tmp_path / ".token").stat().st_mode & 0o077 == 0


def test_keyring_used_when_available(tmp_path, monkeypatch):
    monkeypatch.delenv("HARK_TOKEN", raising=False)
    store: dict[tuple[str, str], str] = {}

    class Mem(keyring.backend.KeyringBackend):
        priority = 1  # type: ignore[assignment]

        def get_password(self, s, u):
            return store.get((s, u))

        def set_password(self, s, u, p):
            store[(s, u)] = p

        def delete_password(self, s, u):
            store.pop((s, u), None)

    monkeypatch.setattr(keyring, "get_keyring", lambda: Mem())
    monkeypatch.setattr(keyring, "get_password", Mem().get_password)
    monkeypatch.setattr(keyring, "set_password", Mem().set_password)
    t = auth.load_or_create_master_token(tmp_path)
    assert store[(auth.KEYRING_SERVICE, auth.KEYRING_USER)] == t
    assert not (tmp_path / ".token").exists()
