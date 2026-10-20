"""Run the Researcher's calculation programs in a sandbox and capture their printed tables.

In CI (CALC_SANDBOX=strict) each program runs as the unprivileged 'nobody' user inside a new
network namespace, with an empty environment, so code written by a model can neither reach
the network nor read the runner's secrets.
"""
import os
import shutil
import subprocess
import tempfile

from . import config


def _cmd(script):
    py = shutil.which("python3") or "python3"
    if config.CALC_SANDBOX == "strict":
        return ["sudo", "-n", "unshare", "--net", "--", "sudo", "-n", "-u", "nobody", py, "-I", "-S", script]
    if config.CALC_SANDBOX == "auto" and shutil.which("unshare") and shutil.which("sudo"):
        probe = subprocess.run(["sudo", "-n", "true"], capture_output=True)
        if probe.returncode == 0:
            return ["sudo", "-n", "unshare", "--net", "--", "sudo", "-n", "-u", "nobody", py, "-I", "-S", script]
    return [py, "-I", "-S", script]


def run_all(calculations):
    outputs, errors = [], []
    for i, c in enumerate(calculations or [], start=1):
        cid = f"C{i}"
        with tempfile.TemporaryDirectory() as d:
            os.chmod(d, 0o755)
            script = os.path.join(d, "calc.py")
            with open(script, "w", encoding="utf-8") as fh:
                fh.write(c.get("python", ""))
            os.chmod(script, 0o644)
            try:
                p = subprocess.run(_cmd(script), capture_output=True, text=True, timeout=30,
                                   cwd=d, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
            except subprocess.TimeoutExpired:
                errors.append({"id": cid, "name": c.get("name"), "error": "timed out after 30s"})
                continue
            if p.returncode != 0 or not p.stdout.strip():
                errors.append({"id": cid, "name": c.get("name"), "error": (p.stderr or "no output")[-1500:]})
                continue
            outputs.append({"id": cid, "name": c.get("name"), "fact_inputs": c.get("fact_inputs", []),
                            "output": p.stdout.strip()[:6000]})
    return outputs, errors
