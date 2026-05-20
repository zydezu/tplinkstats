"""
Flask web UI for TP-Link router stats.

Data is written to network.json by the separate poller.py process.
This file doesn't fetch data from the router, it just watches
network.json's mtime and serves that data.

Static files live in static/
    index.html  — page structure
    app.js      — polling + DOM updates
    style.css   — styles
"""

import atexit
import json
import os
import socket
import subprocess
import sys
import webbrowser

from flask import Flask, jsonify, send_from_directory

from getrouterstats import JSON_PATH, bytes_to_readable_format

app = Flask(__name__)

# JSON cache (reload only when file changes)
_cache: dict = {}
_cache_mtime: float = 0.0


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
    # Clear stale data on startup so old data isn't shown
    with open(JSON_PATH, "w") as f:
        json.dump({}, f)

    poller_path = os.path.join(os.path.dirname(__file__), "poller.py")
    poller = subprocess.Popen([sys.executable, poller_path])
    atexit.register(poller.terminate)
    print(f"[main] Poller started (pid {poller.pid})")

    port = find_free_port()
    url = f"http://localhost:{port}"
    print(f"[main] Server starting on {url}")
    webbrowser.open(url)
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False)
