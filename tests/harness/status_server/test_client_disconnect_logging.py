from __future__ import annotations

import importlib.util
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[3] / "harness" / "lib" / "symphony" / "status-server.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("solar_status_disconnect_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_transport_disconnect_does_not_emit_socketserver_traceback():
    module = _load_module()
    server = object.__new__(module.StatusThreadingHTTPServer)
    reset = ConnectionResetError(10054, "client closed the stream")

    with (
        mock.patch.object(sys, "exc_info", return_value=(ConnectionResetError, reset, None)),
        mock.patch.object(ThreadingHTTPServer, "handle_error") as default_handler,
    ):
        server.handle_error(object(), ("127.0.0.1", 12345))

    default_handler.assert_not_called()


def test_non_transport_server_error_remains_visible_to_default_handler():
    module = _load_module()
    server = object.__new__(module.StatusThreadingHTTPServer)
    failure = ValueError("real server defect")

    with (
        mock.patch.object(sys, "exc_info", return_value=(ValueError, failure, None)),
        mock.patch.object(ThreadingHTTPServer, "handle_error") as default_handler,
    ):
        server.handle_error(object(), ("127.0.0.1", 12345))

    default_handler.assert_called_once()
