"""In-memory TTL cache used by the GitHub client.

Repository trees and file contents are cached so repeated analyses of the
same repository don't burn API quota. Thread-safe.
"""
import threading
import time


class TTLCache:
    def __init__(self, ttl_seconds=900, maxsize=512):
        self.ttl = ttl_seconds
        self.maxsize = maxsize
        self._store = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            stamped, value = entry
            if time.time() - stamped > self.ttl:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key, value):
        with self._lock:
            if len(self._store) >= self.maxsize:
                # drop the oldest entry
                oldest = min(self._store, key=lambda k: self._store[k][0])
                self._store.pop(oldest, None)
            self._store[key] = (time.time(), value)

    def get_or_load(self, key, loader):
        value = self.get(key)
        if value is not None:
            return value
        value = loader()
        self.set(key, value)
        return value


# Shared caches: trees and file contents, 15-minute TTL.
tree_cache = TTLCache(ttl_seconds=900)
content_cache = TTLCache(ttl_seconds=900)
meta_cache = TTLCache(ttl_seconds=900)
