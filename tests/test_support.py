"""Small helpers shared by isolated tests."""
import time


def cleanup_tempdir(tempdir, timeout=2.0, retry_interval=0.05):
    """Retry only transient Windows sharing violations during test cleanup."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            tempdir.cleanup()
            return
        except PermissionError as exc:
            if getattr(exc, 'winerror', None) != 32:
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(retry_interval, remaining))
