import json
import os
import tempfile

from bot_auth import can_write, record, role_of, session_alive, stamp_session, viewer_refused


class _Bag(dict):
    permanent = False


def test_bot_writes_and_leonardobot_only_looks():
    assert role_of("bot") == "write"
    assert role_of("leonardobot") == "view"
    assert role_of("nobody") == ""
    view = _Bag()
    stamp_session(view, "leonardobot")
    assert session_alive(view)
    assert view["user"] == "leonardobot"
    assert not can_write(view)
    writer = _Bag()
    stamp_session(writer, "bot")
    assert can_write(writer)


def test_a_session_without_a_user_is_not_alive():
    assert not session_alive(_Bag(auth=1))


def test_a_viewer_cannot_post_a_change_and_can_sign_out():
    assert viewer_refused("view", "POST", "buy")
    assert viewer_refused("view", "POST", "save_prefs")
    assert viewer_refused("view", "POST", "sell")
    assert viewer_refused("view", "POST", "refresh")
    assert not viewer_refused("view", "POST", "logout")
    assert not viewer_refused("view", "GET", "buy")
    assert not viewer_refused("write", "POST", "buy")


def test_the_access_log_keeps_the_operation_and_drops_a_password():
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, "access.log")
    record("leonardobot", "127.0.0.1", "login", "ok", path=path)
    record("leonardobot", "127.0.0.1", "buy", "refused", "password=secret qty=1", path=path)
    lines = open(path, encoding="utf-8").read().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["user"] == "leonardobot" and first["action"] == "login" and first["result"] == "ok"
    assert second["result"] == "refused" and second["detail"] == ""
    assert "secret" not in open(path, encoding="utf-8").read()
    assert os.stat(path).st_mode & 0o777 == 0o600
