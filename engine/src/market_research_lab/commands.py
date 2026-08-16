"""Top-level local development and production startup commands."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _npm_command() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def _wait_for_children(children: list[subprocess.Popen[object]]) -> None:
    try:
        while all(child.poll() is None for child in children):
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("Stopping local services.", file=sys.stderr)
        return
    finally:
        for child in children:
            if child.poll() is None:
                child.send_signal(signal.SIGTERM)


def dev() -> None:
    """Run the FastAPI engine and Vite interface for development."""
    repository_root = _repository_root()
    engine_root = repository_root / "engine"
    web_root = repository_root / "web"
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "market_research_lab.api:app",
            "--reload",
            "--port",
            "8000",
        ],
        cwd=engine_root,
    )
    interface = subprocess.Popen([_npm_command(), "run", "dev"], cwd=web_root)
    url = "http://localhost:5173"
    print(f"Market Research Lab is running at {url}")
    webbrowser.open(url)
    _wait_for_children([api, interface])


def serve() -> None:
    """Build the interface and serve it with FastAPI from one localhost origin."""
    repository_root = _repository_root()
    web_root = repository_root / "web"
    subprocess.run([_npm_command(), "run", "build"], cwd=web_root, check=True)
    url = "http://127.0.0.1:8000"
    print(f"Market Research Lab is running at {url}")
    webbrowser.open(url)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "market_research_lab.api:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=repository_root / "engine",
        check=True,
    )


def check() -> None:
    """Run the complete local validation suite without external services."""
    repository_root = _repository_root()
    engine_root = repository_root / "engine"
    web_root = repository_root / "web"
    subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=engine_root, check=True)
    subprocess.run([sys.executable, "-m", "ruff", "check", "."], cwd=engine_root, check=True)
    subprocess.run([_npm_command(), "run", "check"], cwd=web_root, check=True)


def build() -> None:
    """Generate the typed browser client and build the production interface."""
    subprocess.run([_npm_command(), "run", "build"], cwd=_repository_root() / "web", check=True)
