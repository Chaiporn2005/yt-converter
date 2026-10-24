"""Offline checks for the instrumental pipeline and its failure/cancel paths."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import server


class KaraokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)
        self.patches = [patch.object(server, 'OUT_DIR', self.out),
                        patch.object(server, 'YTDLP', '/tools/yt-dlp'),
                        patch.object(server, 'FFMPEG', '/tools/ffmpeg'),
                        patch.object(server, 'vocal_command', return_value=['demucs'])]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        server.JOBS['test'] = {'state': 'starting', 'percent': 0}
        self.addCleanup(server.JOBS.clear)

    def fake_stage(self, job, cmd, on_line=None):
        if cmd[0] == '/tools/yt-dlp':
            source = Path(cmd[cmd.index('-P') + 1]) / 'Song [abcdefghijk] 192kbps.wav'
            source.write_bytes(b'original audio')
            on_line('FILE|' + str(source))
        elif cmd[0] == 'demucs':
            source = Path(cmd[-1])
            stem = Path(cmd[cmd.index('-o') + 1]) / 'htdemucs' / source.stem / 'no_vocals.wav'
            stem.parent.mkdir(parents=True)
            stem.write_bytes(b'instrumental')
        else:
            self.assertEqual(Path(cmd[cmd.index('-i') + 1]).read_bytes(), b'instrumental')
            Path(cmd[-1]).write_bytes(b'encoded instrumental')

    def test_only_instrumental_is_published_and_listed(self):
        with patch.object(server, 'run_stage', side_effect=self.fake_stage):
            server.run_karaoke('test', 'https://youtu.be/abcdefghijk', 192)
        job = server.JOBS['test']
        self.assertEqual(job['state'], 'done')
        self.assertEqual([p.name for p in self.out.iterdir()], [job['filename']])
        self.assertEqual(server.list_library()[0]['title'], 'Song (Instrumental)')
        self.assertEqual(server.list_library()[0]['quality'], '192k')

    def test_failed_separation_does_not_publish_original(self):
        def fail(job, cmd, on_line=None):
            if cmd[0] == 'demucs':
                raise RuntimeError('separation failed')
            self.fake_stage(job, cmd, on_line)
        with patch.object(server, 'run_stage', side_effect=fail):
            server.run_karaoke('test', 'https://youtu.be/abcdefghijk', 192)
        self.assertEqual(server.JOBS['test']['state'], 'error')
        self.assertEqual(list(self.out.iterdir()), [])

    def test_cancelled_stage_does_not_launch(self):
        job = server.JOBS['test']
        job['cancelled'] = True
        with patch.object(server.subprocess, 'Popen') as launch:
            with self.assertRaises(InterruptedError):
                server.run_stage(job, ['demucs'])
            launch.assert_not_called()

    def test_karaoke_settings_and_regular_library(self):
        self.assertEqual(server.clean_settings({'format': 'karaoke'})['format'], 'karaoke')
        (self.out / 'Song [abcdefghijk] 192kbps.mp3').write_bytes(b'mp3')
        self.assertEqual(server.list_library()[0]['title'], 'Song')


if __name__ == '__main__':
    unittest.main()
