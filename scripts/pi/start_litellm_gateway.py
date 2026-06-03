"""Start the LiteLLM gateway with all required env vars.

This script sets env vars from known sources and starts LiteLLM in a subprocess.
Run once; keep the process running while using LiteLLM.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
CONFIG = Path(__file__).resolve().parents[2] / "configs" / "litellm" / "harnessci.yaml"


def load_kilo_key() -> str:
    models_path = HOME / ".pi" / "agent" / "models.json"
    if models_path.exists():
        data = json.loads(models_path.read_text(encoding="utf-8"))
        return data["providers"]["kilo-test"]["apiKey"]
    raise RuntimeError("Cannot find KILO_API_KEY in ~/.pi/agent/models.json")


def main() -> int:
    os.environ["KILO_API_KEY"] = load_kilo_key()
    os.environ["LITELLM_MASTER_KEY"] = os.environ.get("LITELLM_MASTER_KEY") or "Gusano2001@"
    os.environ["LANGFUSE_PUBLIC_KEY"] = (
        os.environ.get("LANGFUSE_PUBLIC_KEY") or input("LANGFUSE_PUBLIC_KEY (pk-lf-...): ").strip()
    )
    os.environ["LANGFUSE_SECRET_KEY"] = (
        os.environ.get("LANGFUSE_SECRET_KEY") or input("LANGFUSE_SECRET_KEY (sk-lf-...): ").strip()
    )
    os.environ["LANGFUSE_HOST"] = "https://cloud.langfuse.com"

    print(f"KILO_API_KEY: {os.environ['KILO_API_KEY'][:8]}... (loaded from models.json)")
    print(f"LITELLM_MASTER_KEY: {'***'}")
    print(f"LANGFUSE_PUBLIC_KEY: {os.environ['LANGFUSE_PUBLIC_KEY'][:12]}...")
    print(f"Config: {CONFIG}")
    print("Starting LiteLLM gateway on http://localhost:4000 ...")

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "litellm", "--config", str(CONFIG), "--port", "4000"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        text=True,
    )

    print(f"Process PID: {proc.pid}")
    print("Log output (Ctrl+C to stop):")
    print("-" * 40)

    try:
        for line in proc.stdout:  # type: ignore
            sys.stdout.write(line)
            sys.stdout.flush()
            if "Application startup complete" in line or "Uvicorn running on" in line:
                break
    except KeyboardInterrupt:
        print("\nStopping LiteLLM...")
        proc.terminate()
        proc.wait(timeout=10)
        print("Done.")
        return 0

    return proc.returncode if proc.poll() is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
