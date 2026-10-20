"""Tiny JSON store under automation/data. Every file is committed to git, so history is the audit trail."""
import json
from pathlib import Path

from . import config


def path(name):
    return config.DATA / name


def load(name, default=None):
    p = path(name)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def save(name, obj):
    p = path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class Run:
    """Per-run folder: every agent's input and output is written here."""

    def __init__(self, run_id):
        self.id = run_id
        self.dir = config.RUNS / run_id
        self.dir.mkdir(parents=True, exist_ok=True)

    def write(self, name, obj):
        p = self.dir / name
        if isinstance(obj, str):
            p.write_text(obj, encoding="utf-8")
        else:
            p.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return p

    def read(self, name, default=None):
        p = self.dir / name
        if not p.exists():
            return default
        txt = p.read_text(encoding="utf-8")
        return json.loads(txt) if name.endswith(".json") else txt

    @property
    def state(self):
        return self.read("state.json", {}) or {}

    def set_state(self, **kw):
        s = self.state
        s.update(kw)
        self.write("state.json", s)
        return s


def latest_run_dir():
    if not config.RUNS.exists():
        return None
    runs = sorted([p for p in config.RUNS.iterdir() if p.is_dir()])
    return runs[-1] if runs else None
