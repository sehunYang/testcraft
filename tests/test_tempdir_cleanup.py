import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from test_support import cleanup_tempdir


class FakeTempDir:
    def __init__(self, errors):
        self.errors = list(errors)
        self.calls = 0
        self.cleaned = False

    def cleanup(self):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        self.cleaned = True


def sharing_violation():
    error = PermissionError('file is temporarily in use')
    error.winerror = 32
    return error


class CleanupHelperTests(unittest.TestCase):
    def test_retries_winerror_32_until_cleanup_succeeds(self):
        tempdir = FakeTempDir([sharing_violation(), sharing_violation()])
        with patch('test_support.time.sleep') as sleep:
            cleanup_tempdir(tempdir)
        self.assertTrue(tempdir.cleaned)
        self.assertEqual(tempdir.calls, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_does_not_retry_other_permission_errors(self):
        error = PermissionError('access denied')
        error.winerror = 5
        tempdir = FakeTempDir([error])
        with patch('test_support.time.sleep') as sleep:
            with self.assertRaises(PermissionError) as caught:
                cleanup_tempdir(tempdir)
        self.assertIs(caught.exception, error)
        self.assertEqual(tempdir.calls, 1)
        sleep.assert_not_called()

    def test_timeout_reraises_last_sharing_violation(self):
        error = sharing_violation()
        tempdir = FakeTempDir([error] * 5)
        with patch('test_support.time.monotonic', side_effect=[0, 0, .5, 1, 1.5, 2.01]), patch('test_support.time.sleep') as sleep:
            with self.assertRaises(PermissionError) as caught:
                cleanup_tempdir(tempdir)
        self.assertIs(caught.exception, error)
        self.assertEqual(tempdir.calls, 5)
        self.assertEqual(sleep.call_count, 4)


if __name__ == '__main__':
    unittest.main(verbosity=2)
