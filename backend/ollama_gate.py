# backend/ollama_gate.py
import os
import time
import logging
import threading
from contextlib import contextmanager

logger = logging.getLogger("OllamaGate")

OLLAMA_GENERATE_MAX_CONCURRENT = int(os.getenv("OLLAMA_GENERATE_MAX_CONCURRENT", "1"))
OLLAMA_EMBED_MAX_CONCURRENT = int(os.getenv("OLLAMA_EMBED_MAX_CONCURRENT", "2"))

_FAILURE_PAUSE_THRESHOLD = 4
_COOLDOWN_SECONDS = 60.0


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


_generate_gate = _OllamaGate("generate", OLLAMA_GENERATE_MAX_CONCURRENT)
_embed_gate = _OllamaGate("embed", OLLAMA_EMBED_MAX_CONCURRENT)


class OllamaPausedError(Exception):
    pass


@contextmanager
def generate_slot():
    if _generate_gate.is_paused():
        raise OllamaPausedError("LLM generation is temporarily paused after repeated failures. Please retry shortly.")
    with _generate_gate.slot():
        yield


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
