#!/usr/bin/env python3
"""Run offline tests; never use a real account, Keychain, or network."""
import argparse
import contextlib
import importlib.util
import hashlib
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--upstream', type=Path, help='Optional reviewed nara.py for helper compatibility tests')
    args = parser.parse_args()
    root = args.root.resolve()
    for name in ('keychain-credentials', 'nara-baby'):
        sys.path.insert(0, str(root / name / 'scripts'))
    if args.upstream and hashlib.sha256(args.upstream.read_bytes()).hexdigest() != "fc8358a285544de343f008b80e9056cb31c7833cd1d7d5c9a1e3b3d4fca3e8a0":
        parser.error("Upstream source does not match the reviewed SHA-256")
    import nara_config
    import skill_credentials
    with tempfile.TemporaryDirectory() as temporary, contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(nara_config, 'config_path', return_value=Path(temporary) / 'preferences.json'))
        stack.enter_context(patch.object(skill_credentials, '_backend', side_effect=AssertionError('Real Keychain forbidden during tests')))
        stack.enter_context(patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden during tests')))
        stack.enter_context(patch.object(socket, 'create_connection', side_effect=AssertionError('Network forbidden during tests')))
        stack.enter_context(patch.dict(os.environ, {'NARA_SOURCE_FILE': str(args.upstream.resolve()) if args.upstream else ''}))
        suite = unittest.TestSuite()
        for path in sorted(root.glob('*/tests/test_*.py')):
            spec = importlib.util.spec_from_file_location(path.stem, path)
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except unittest.SkipTest as exc:
                def skipped(reason=str(exc)):
                    raise unittest.SkipTest(reason)
                suite.addTest(unittest.FunctionTestCase(skipped, description=path.name))
            else:
                suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        if not suite.countTestCases():
            parser.error('No tests found under --root')
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1

if __name__ == '__main__':
    sys.exit(main())
