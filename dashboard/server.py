#!/usr/bin/env python3
"""OpenClaw Dashboard API Server — port 8888"""

import json
import os
import platform
import subprocess
import time
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

BASE = Path(__file__).resolve().parent.parent  # ~/OpenClaw
LOGS = BASE / "logs"


def _read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _read_jsonl_tail(path, n=5):
    try:
        lines = Path(path).read_text().strip().splitlines()
        out = []
        for line in lines[-n:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return out
    except Exception:
        return []


def _read_log_tail(path, n=20):
    try:
        lines = Path(path).read_text().strip().splitlines()
        return lines[-n:]
    except Exception:
        return []


def _http_get_json(url, timeout=3):
    try:
        req = Request(url)
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


# ── system info ──────────────────────────────────────────────────────────────

def _system_info():
    info = {"hostname": platform.node(), "platform": platform.platform()}

    # uptime
    try:
        raw = subprocess.check_output(["uptime"], text=True).strip()
        info["uptime"] = raw.split(",")[0].replace("  ", " ").strip()
    except Exception:
        info["uptime"] = "unknown"

    # CPU usage (macOS: top snapshot)
    try:
        raw = subprocess.check_output(
            ["top", "-l", "1", "-n", "0", "-stats", "cpu"],
            text=True, timeout=5
        )
        for line in raw.splitlines():
            if "CPU usage" in line:
                info["cpu"] = line.strip()
                break
    except Exception:
        info["cpu"] = "unknown"

    # Memory via vm_stat
    try:
        raw = subprocess.check_output(["vm_stat"], text=True)
        pages = {}
        for line in raw.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                val = val.strip().rstrip(".")
                try:
                    pages[key.strip()] = int(val)
                except ValueError:
                    pass
        page_size = 16384  # Apple Silicon default
        free = pages.get("Pages free", 0) * page_size
        active = pages.get("Pages active", 0) * page_size
        inactive = pages.get("Pages inactive", 0) * page_size
        wired = pages.get("Pages wired down", 0) * page_size
        compressed = pages.get("Pages occupied by compressor", 0) * page_size
        used = active + wired + compressed
        total = used + free + inactive
        info["memory"] = {
            "used_gb": round(used / 1e9, 1),
            "total_gb": round(total / 1e9, 1),
            "percent": round(used / max(total, 1) * 100, 1),
        }
    except Exception:
        info["memory"] = {"used_gb": 0, "total_gb": 0, "percent": 0}

    # Total physical RAM via sysctl
    try:
        raw = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
        info["memory"]["total_gb"] = round(int(raw) / 1e9, 1)
    except Exception:
        pass

    return info


# ── process checks ───────────────────────────────────────────────────────────

def _check_process(pattern):
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", pattern], text=True
        ).strip()
        pids = [int(p) for p in out.splitlines() if p]
        return {"running": True, "pids": pids}
    except subprocess.CalledProcessError:
        return {"running": False, "pids": []}


def _processes():
    return {
        "orchestrator": _check_process("orchestrator.py"),
        "telegram_bot": _check_process("telegram_bot"),
        "design_cycle": _check_process("design_cycle"),
    }


# ── ollama ───────────────────────────────────────────────────────────────────

def _ollama():
    running_data = _http_get_json("http://localhost:11434/api/ps")
    tags_data = _http_get_json("http://localhost:11434/api/tags")

    if running_data is None and tags_data is None:
        return {"status": "stopped", "running_models": [], "installed_models": []}

    running_models = []
    if running_data and "models" in running_data:
        for m in running_data["models"]:
            running_models.append({
                "name": m.get("name", "?"),
                "size": m.get("size", 0),
                "size_gb": round(m.get("size", 0) / 1e9, 2),
            })

    installed_models = []
    if tags_data and "models" in tags_data:
        for m in tags_data["models"]:
            installed_models.append({
                "name": m.get("name", "?"),
                "size": m.get("size", 0),
                "size_gb": round(m.get("size", 0) / 1e9, 2),
                "modified_at": m.get("modified_at", ""),
            })

    return {
        "status": "running",
        "running_models": running_models,
        "installed_models": installed_models,
    }


# ── aggregate ────────────────────────────────────────────────────────────────

def build_status():
    return {
        "generated_at": datetime.now().isoformat(),
        "system": _system_info(),
        "ollama": _ollama(),
        "processes": _processes(),
        "orchestrator_state": _read_json(BASE / "state.json"),
        "phase_state": _read_json(LOGS / "phase_state.json"),
        "action_plan": _read_json(LOGS / "action_plan.json"),
        "trend_report": _read_json(LOGS / "trend_report.json"),
        "farcaster_posts": (_read_json(LOGS / "farcaster_log.json") or [])[-5:],
        "recent_decisions": _read_jsonl_tail(LOGS / "decisions_log.jsonl", 5),
        "log_tail": _read_log_tail(LOGS / "orchestrator.log", 20),
    }


# ── HTTP handler ─────────────────────────────────────────────────────────────

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).resolve().parent), **kwargs)

    def do_GET(self):
        if self.path == "/api/status":
            data = build_status()
            payload = json.dumps(data, default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload)
        elif self.path == "/" or self.path == "/index.html":
            self.path = "/index.html"
            super().do_GET()
        else:
            super().do_GET()

    def log_message(self, fmt, *args):
        # quieter logs
        pass


if __name__ == "__main__":
    port = 8888
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"OpenClaw Dashboard running on http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()
