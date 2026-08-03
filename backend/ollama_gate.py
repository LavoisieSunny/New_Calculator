# backend/ollama_gate.py
import os
import time
import logging
import threading
from contextlib import contextmanager

logger = logging.getLogger("OllamaGate")

OLLAMA_MODEL_MAX_CONCURRENT = int(os.getenv("OLLAMA_MODEL_MAX_CONCURRENT", "3"))
OLLAMA_EMBED_MAX_CONCURRENT = int(os.getenv("OLLAMA_EMBED_MAX_CONCURRENT", "2"))

_FAILURE_PAUSE_THRESHOLD = 4
_COOLDOWN_SECONDS = 60.0


class _ModelAwareGenerateGate:
    """
    Lets up to OLLAMA_MODEL_MAX_CONCURRENT calls run concurrently as long as
    they all target the SAME already-resident model (cheap — just extra KV
    cache, no second model load). The moment a call for a DIFFERENT model
    arrives, it waits until the currently-active model's calls drain to zero
    before switching. This is what prevents two different 14B models (e.g.
    qwen2.5:14b + deepseek-r1:14b) from being loaded into the GPU at once —
    that was the actual crash cause under the old "parallelize independent
    LLM calls" change. Same-model concurrency is genuinely safe; cross-model
    concurrency is not.
    """
    def __init__(self, per_model_max_concurrent):
        self._cv = threading.Condition()
        self._active_model = None
        self._active_count = 0
        self._per_model_max = max(1, per_model_max_concurrent)
        self._consecutive_failures = 0
        self._paused_until = 0.0

    def is_paused(self):
        with self._cv:
            return time.time() < self._paused_until

    def record_result(self, success):
        with self._cv:
            if success:
                self._consecutive_failures = 0
                return
            self._consecutive_failures += 1
            if self._consecutive_failures >= _FAILURE_PAUSE_THRESHOLD:
                self._paused_until = time.time() + _COOLDOWN_SECONDS
                logger.error(f"Ollama generate gate paused for {_COOLDOWN_SECONDS:.0f}s after {self._consecutive_failures} consecutive failures.")

    @contextmanager
    def slot(self, model_name):
        with self._cv:
            while not (
                self._active_count == 0
                or (self._active_model == model_name and self._active_count < self._per_model_max)
            ):
                self._cv.wait(timeout=2.0)
            if self._active_count == 0:
                self._active_model = model_name
            self._active_count += 1
        try:
            yield
        finally:
            with self._cv:
                self._active_count -= 1
                if self._active_count <= 0:
                    self._active_count = 0
                    self._active_model = None
                self._cv.notify_all()


_generate_gate = _ModelAwareGenerateGate(OLLAMA_MODEL_MAX_CONCURRENT)


class OllamaPausedError(Exception):
    pass


@contextmanager
def generate_slot(model_name):
    if _generate_gate.is_paused():
        raise OllamaPausedError("LLM generation is temporarily paused after repeated failures. Please retry shortly.")
    with _generate_gate.slot(model_name):
        yield


# --- Keep the embed gate exactly as before ---
class _OllamaGate:
    def __init__(self, name, max_concurrent):
        self.name = name
        self._semaphore = threading.BoundedSemaphore(max(1, max_concurrent))
        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self._paused_until = 0.0

    def is_paused(self):
        with self._lock:
            return time.time() < self._paused_until

    def record_result(self, success):
        with self._lock:
            if success:
                self._consecutive_failures = 0
                return
            self._consecutive_failures += 1
            if self._consecutive_failures >= _FAILURE_PAUSE_THRESHOLD:
                self._paused_until = time.time() + _COOLDOWN_SECONDS
                logger.error(f"Ollama gate '{self.name}' paused for {_COOLDOWN_SECONDS:.0f}s after {self._consecutive_failures} consecutive failures.")

    @contextmanager
    def slot(self):
        self._semaphore.acquire()
        try:
            yield
        finally:
            self._semaphore.release()


_embed_gate = _OllamaGate("embed", OLLAMA_EMBED_MAX_CONCURRENT)


@contextmanager
def embed_slot():
    if _embed_gate.is_paused():
        raise OllamaPausedError("Embedding generation is temporarily paused after repeated failures. Please retry shortly.")
    with _embed_gate.slot():
        yield


def record_generate_result(success):
    _generate_gate.record_result(success)


def record_embed_result(success):
    _embed_gate.record_result(success)
