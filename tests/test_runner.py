"""Check scientific output semantics and stale-source protection."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from gnss_project import runner


class RunnerTest(unittest.TestCase):
    def test_fixed_covariance_and_no_stale_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            obs = folder/'B.rnx'
            obs.write_text('> 2026 04 16 07 00 00.0000000  0  7\n'
                           '> 2026 04 16 07 00 01.0000000  0  7\n'
                           '> 2026 04 16 07 00 02.0000000  0  0\n')
            settings = dict(start_gpst='2026-04-16 07:00:00', end_gpst='2026-04-16 07:00:02',
                interval_s=1, dataset='test', datasets={'test':dict(rover_observation=str(obs))})
            tick = 252000000000
            eye = [[.01 if i==j else 0 for j in range(6)] for i in range(6)]
            row = dict(event='REL',tick=tick,stat=1,na=6,ratio=4.,nfix=1,
                fixed_x=[[1000],[2000],[3000],[.1],[.2],[.3]],fixed_P=eye,
                x=[[1010],[2010],[3010],[9],[9],[9]],P=[[100 if i==j else 0 for j in range(6)] for i in range(6)])
            epoch = dict(event='EPOCH',tick=tick,rc=1,stat=1,rel_error=0,rb=[[900],[1900],[2900],[0],[0],[0]],
                state_time=[1776322800,0],time=[1776322800,0],state_anchor=[[900],[1900],[2900]])
            stale = dict(epoch,tick=tick+10_000_000,stat=5)
            log = folder/'audit.jsonl'
            log.write_text('\n'.join(json.dumps(z) for z in [row,epoch,stale])+'\n')
            rows = runner.audit_baseline_csv(log,folder/'baseline.csv',settings,True)
            self.assertEqual(rows[0]['baseline_x_m'],100)
            self.assertEqual(rows[0]['relative_v_x_mps'],.1)
            self.assertEqual(rows[0]['Pbb_00'],.01)
            self.assertEqual(rows[0]['mean_source'],'xa/Pa')
            self.assertFalse(rows[1]['current_update'])
            self.assertNotIn('baseline_x_m',rows[1])
            self.assertEqual(rows[2]['status'],'ROVER_OBS_ABSENT')

    def test_changed_source_requires_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'bin').mkdir();(root/'src').mkdir()
            binary=root/'bin/solver';binary.write_bytes(b'test-binary')
            source=root/'src/example.c';source.write_text('int main(void){return 0;}')
            manifest=dict(binary='bin/solver',binary_sha256=runner.sha256(binary),source_root='src',
                source_files=[dict(path='example.c',sha256=runner.sha256(source))])
            (root/'bin/relative_cv.json').write_text(json.dumps(manifest))
            with patch.object(runner,'ROOT',root):
                runner.check_binary('relative_cv')
                source.write_text('int main(void){return 1;}')
                with self.assertRaisesRegex(RuntimeError,'源码已修改'):
                    runner.check_binary('relative_cv')


if __name__=='__main__':
    unittest.main()
