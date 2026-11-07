from unittest.mock import MagicMock, patch

from app.main import ensure_macos_app_name


def test_ensure_macos_app_name_noop_on_non_darwin():
    with patch("sys.platform", "linux"):
        reexeced = ensure_macos_app_name()
        assert reexeced is False


def test_ensure_macos_app_name_noop_if_already_tekstitys():
    with patch("sys.platform", "darwin"), patch("sys.executable", "/path/to/Tekstitys"):
        reexeced = ensure_macos_app_name()
        assert reexeced is False


def test_ensure_macos_app_name_noop_if_reexec_flag_set(monkeypatch):
    monkeypatch.setenv("TEKSTITYS_REEXECED", "1")
    with patch("sys.platform", "darwin"), patch("sys.executable", "/path/to/python3"):
        reexeced = ensure_macos_app_name()
        assert reexeced is False


def test_ensure_macos_app_name_reexecs(monkeypatch, tmp_path):
    monkeypatch.delenv("TEKSTITYS_REEXECED", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    # Set when the suite is run without a re-exec; this test is about the re-exec.
    monkeypatch.delenv("TEKSTITYS_NO_REEXEC", raising=False)

    # Keep the MacOS/ link out of the real venv, where it would go stale.
    monkeypatch.setattr("sys.prefix", str(tmp_path / "venv"))

    fake_py = tmp_path / "python3"
    fake_py.write_text("#!/bin/sh\n")

    mock_execve = MagicMock()
    with (
        patch("sys.platform", "darwin"),
        patch("sys.executable", str(fake_py)),
        patch("os.execve", mock_execve),
    ):
        reexeced = ensure_macos_app_name()
        assert reexeced is True
        assert mock_execve.called
        called_binary, called_args, called_env = mock_execve.call_args[0]
        assert "Tekstitys" in called_binary
        assert called_env.get("TEKSTITYS_REEXECED") == "1"
