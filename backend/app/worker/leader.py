"""Leader election with a PostgreSQL session-level advisory lock (SADD ADR-07).

The lock lives on one dedicated connection. If the worker process dies or loses
that connection, PostgreSQL releases the lock and a waiting worker takes over.
"""

from sqlalchemy import Connection, Engine, text

# Any constant bigint works, as long as nothing else uses it: "CAFW" in ASCII.
WORKER_LOCK_KEY = 0x43414657


class LeaderLock:
    def __init__(self, engine: Engine, key: int = WORKER_LOCK_KEY) -> None:
        self._engine = engine
        self._key = key
        self._connection: Connection | None = None

    @property
    def held(self) -> bool:
        return self._connection is not None

    def try_acquire(self) -> bool:
        """Take the lock without waiting; True if this worker is now the leader."""
        if self._connection is not None:
            return True
        # Autocommit, so the lock connection never holds a transaction open.
        connection = self._engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        acquired = connection.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": self._key}
        ).scalar_one()
        if acquired:
            self._connection = connection
        else:
            connection.close()
        return bool(acquired)

    def is_alive(self) -> bool:
        """Whether the lock connection still works; if not, the lock is already gone."""
        if self._connection is None:
            return False
        try:
            self._connection.execute(text("SELECT 1"))
        except Exception:
            return False
        return True

    def release(self) -> None:
        if self._connection is None:
            return
        try:
            self._connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": self._key})
        except Exception:
            pass  # a dead connection has released the lock already
        finally:
            self._connection.close()
            self._connection = None
