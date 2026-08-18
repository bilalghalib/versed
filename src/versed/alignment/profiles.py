"""Advisory local-compute profiles; alignment never downloads models implicitly."""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import subprocess
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class AlignmentCapabilities:
    system: str
    machine: str
    memory_gib: float | None
    semantic_runtime_installed: bool
    ollama_available: bool
    ollama_models: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProfileRecommendation:
    profile: str
    semantic_scope: str
    ollama_judge: str | None
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _memory_gib() -> float | None:
    total: int | None = None
    if platform.system() == "Darwin":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            total = int(result.stdout.strip())
        except (OSError, ValueError, subprocess.SubprocessError):
            total = None
    elif hasattr(os, "sysconf"):
        try:
            total = int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
        except (OSError, ValueError):
            total = None
    return round(total / (1024**3), 2) if total else None


def _ollama_models(base_url: str = "http://127.0.0.1:11434") -> tuple[bool, tuple[str, ...]]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/tags",
        headers={"User-Agent": "versed-pdf/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            body = response.read(2 * 1024 * 1024 + 1)
        if len(body) > 2 * 1024 * 1024:
            return True, ()
        payload = json.loads(body)
    except (OSError, ValueError, urllib.error.URLError):
        return False, ()
    listed = sorted(
        str(value["name"])
        for value in payload.get("models", [])
        if isinstance(value, dict) and value.get("name")
    )
    runnable: list[str] = []
    for name in listed:
        show = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/show",
            data=json.dumps({"model": name}).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "versed-pdf/1"},
        )
        try:
            with urllib.request.urlopen(show, timeout=2) as response:
                details = json.loads(response.read(2 * 1024 * 1024 + 1))
        except (OSError, ValueError, urllib.error.URLError):
            continue
        if "completion" in (details.get("capabilities") or []):
            runnable.append(name)
    return True, tuple(runnable)


def detect_alignment_capabilities() -> AlignmentCapabilities:
    ollama_available, models = _ollama_models()
    return AlignmentCapabilities(
        system=platform.system(),
        machine=platform.machine(),
        memory_gib=_memory_gib(),
        semantic_runtime_installed=(
            importlib.util.find_spec("torch") is not None
            and importlib.util.find_spec("transformers") is not None
        ),
        ollama_available=ollama_available,
        ollama_models=models,
    )


def recommend_alignment_profile(
    capabilities: AlignmentCapabilities | None = None,
) -> ProfileRecommendation:
    value = capabilities or detect_alignment_capabilities()
    memory = value.memory_gib or 0
    notes: list[str] = ["No model is downloaded or started automatically."]
    if not value.semantic_runtime_installed:
        profile = "basic"
        semantic_scope = "none"
        notes.append("Install the optional semantic extra for cross-language retrieval.")
    elif memory and memory < 8:
        profile = "balanced"
        semantic_scope = "paragraph"
        notes.append("Paragraph-only semantic retrieval limits memory use.")
    elif memory >= 12:
        profile = "thorough"
        semantic_scope = "paragraph_and_sentence"
    else:
        profile = "balanced"
        semantic_scope = "paragraph"

    generative = [
        name
        for name in value.ollama_models
        if "embed" not in name.lower() and any(token in name.lower() for token in ("gemma", "qwen", "llama"))
    ]
    judge = None
    if generative and memory >= 8:
        notes.append(
            "Runnable Ollama models were detected, but no judge is recommended without calibration gold."
        )
    elif value.ollama_available:
        notes.append("No suitable installed generative Ollama model was detected.")
    return ProfileRecommendation(profile, semantic_scope, judge, tuple(notes))
