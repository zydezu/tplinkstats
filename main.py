"""
Flask web UI for TP-Link router stats.

Data is written to network.json by the separate poller.py process.
This file doesn't fetch data from the router, it just watches
network.json's mtime and serves that data.
"""

import atexit
import json
import os
import signal
import socket
import subprocess
import sys
import time
import webbrowser

from flask import Flask, jsonify, send_from_directory

from backend.getrouterstats import JSON_PATH, bytes_to_readable_format

app = Flask(__name__)

# JSON cache (reload only when file changes)
_cache: dict = {}
_cache_mtime: float = 0.0
_poller_pid: int | None = None


def _load_json_if_changed() -> dict:
    global _cache, _cache_mtime
    try:
        mtime = os.path.getmtime(JSON_PATH)
        if mtime != _cache_mtime:
            with open(JSON_PATH) as f:
                _cache = json.load(f)
            _cache_mtime = mtime
    except FileNotFoundError, json.JSONDecodeError:
        pass
    return _cache


def build_data() -> dict:
    data = _load_json_if_changed()
    if not data:
        return {
            "status": {},
            "devices": [],
            "mesh_data": [],
            "total_transferred_readable": "0 B",
            "errors": {},
            "file_mtime": 0,
        }

    devices = data.get("devices", [])
    total_traffic = sum(d.get("data_transferred", 0) for d in devices)
    data["total_transferred_readable"] = (
        bytes_to_readable_format(total_traffic) if devices else "0 B"
    )
    data["file_mtime"] = _cache_mtime  # detect new data and refresh on it
    return data


# Routes
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)


@app.route("/data")
def data():
    return jsonify(build_data())


@app.route("/trigger-poll", methods=["POST"])
def trigger_poll():
    # Wakes the poller immediately instead of waiting out its current sleep,
    if _poller_pid is not None:
        try:
            os.kill(_poller_pid, signal.SIGUSR1)
        except OSError:
            pass
    return ("", 204)


LOCK_PATH = os.path.join(os.path.dirname(__file__), ".main.pid")


def _stop_previous_instance() -> None:
    """Kill any previous main.py (and its poller) still running from an
    earlier launch, so relaunching (e.g. via a kiosk keybind) never stacks
    up duplicate pollers hammering the router at once.
    """
    try:
        with open(LOCK_PATH) as f:
            old_pid = int(f.read().strip())
    except FileNotFoundError, ValueError:
        return

    try:
        os.kill(old_pid, 0)
    except OSError:
        return  # not running

    print(f"[main] Stopping previous instance (pid {old_pid})")
    try:
        os.kill(old_pid, signal.SIGTERM)
    except OSError:
        return

    for _ in range(50):  # wait up to 5s for it (and its poller) to exit
        time.sleep(0.1)
        try:
            os.kill(old_pid, 0)
        except OSError:
            return
    print(f"[main] Previous instance (pid {old_pid}) didn't exit in time, killing it")
    try:
        os.kill(old_pid, signal.SIGKILL)
    except OSError:
        pass


def find_free_port(start: int = 8080) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        for port in range(start, start + 100):
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free port found")


if __name__ == "__main__":
    # Server mode - don't open a browser window
    headless = os.environ.get("TPLINKSTATS_SERVER") == "1"

    # Keep whatever data/network.json has from the last session so the page
    # shows last-known stats immediately instead of going blank on startup;
    # the poller overwrites it with fresh data once its first cycle completes.
    os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)

    _stop_previous_instance()
    with open(LOCK_PATH, "w") as f:
        f.write(str(os.getpid()))

    poller_path = os.path.join(os.path.dirname(__file__), "backend", "poller.py")
    poller = subprocess.Popen(
        [sys.executable, poller_path], cwd=os.path.dirname(__file__)
    )
    _poller_pid = poller.pid

    def _stop_poller() -> None:
        poller.terminate()
        try:
            poller.wait(timeout=5)
        except subprocess.TimeoutExpired:
            poller.kill()
        if os.path.exists(LOCK_PATH):
            os.remove(LOCK_PATH)

    atexit.register(_stop_poller)
    # SIGTERM (e.g. from `kill`/`pkill`) doesn't run atexit handlers by default
    # since Python only installs a Python-level handler for SIGINT; without this,
    # the poller subprocess is orphaned and keeps hammering the router forever.
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    print(f"[main] Poller started (pid {poller.pid})")

    if headless:
        host = "127.0.0.1"
        port = int(os.environ.get("PORT", 8090))
    else:
        host = "0.0.0.0"
        port = find_free_port()

    url = f"http://localhost:{port}"
    print(f"[main] Server starting on {url}")
    if not headless:
        webbrowser.open(f"{url}/?kiosk=1")
    app.run(host=host, port=port, threaded=True, debug=False)
