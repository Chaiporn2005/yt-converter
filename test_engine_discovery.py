"""Offline checks for vocal engine discovery from installed app bundles."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server


class EngineDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.resources = self.root / 'Applications' / 'Local Converter.app' / 'Contents' / 'Resources'
        self.resources.mkdir(parents=True)
        self.registry = self.root / 'support' / 'vocal-engine.json'
        self.registry.parent.mkdir()
        clean_env = {key: value for key, value in os.environ.items() if key != 'VOCAL_PYTHON'}
        patches = [patch.object(server, 'ROOT', self.resources),
                   patch.object(server, 'VOCAL_ENGINE_PATH', self.registry),
                   patch.object(server, 'find_tool', return_value=None),
                   patch.dict(os.environ, clean_env, clear=True)]
        for active_patch in patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)

    def engine(self, folder, ready=True, executable=True):
        python = folder / 'bin' / 'python'
        python.parent.mkdir(parents=True)
        python.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
        python.chmod(0o755 if executable else 0o644)
        if ready:
            (folder / '.ready').touch()
        return python

    def register(self, python):
        self.registry.write_text(json.dumps({'python': str(python)}), encoding='utf-8')

    def test_relocated_installed_app_uses_registered_engine(self):
        python = self.engine(self.root / 'project' / '.venv-vocals')
        self.register(python)
        self.assertEqual(server.vocal_command(), [str(python), '-m', 'demucs'])

    def test_malformed_registry_falls_back_to_local_engine(self):
        python = self.engine(self.resources / '.venv-vocals')
        self.registry.write_text('{broken json', encoding='utf-8')
        self.assertEqual(server.vocal_command(), [str(python), '-m', 'demucs'])

    def test_stale_registered_engine_falls_back_to_local_engine(self):
        python = self.engine(self.resources / '.venv-vocals')
        self.register(self.root / 'deleted-project' / '.venv-vocals' / 'bin' / 'python')
        self.assertEqual(server.vocal_command(), [str(python), '-m', 'demucs'])

    def test_registered_engine_requires_ready_marker(self):
        self.register(self.engine(self.root / 'unfinished-engine', ready=False))
        self.assertIsNone(server.vocal_command())

    def test_registered_engine_requires_executable_interpreter(self):
        self.register(self.engine(self.root / 'unusable-engine', executable=False))
        self.assertIsNone(server.vocal_command())

    def test_explicit_environment_override_takes_precedence(self):
        registered = self.engine(self.root / 'registered-engine')
        override = self.engine(self.root / 'override-engine')
        self.register(registered)
        with patch.dict(os.environ, {'VOCAL_PYTHON': str(override)}):
            self.assertEqual(server.vocal_command(), [str(override), '-m', 'demucs'])


if __name__ == '__main__':
    unittest.main()
