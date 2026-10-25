"""The installed gate must propagate failures from configured Python tests."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
CLI=ROOT/'node_modules/@slop-lab/qg/dist/index.mjs'


class QualityGateTest(unittest.TestCase):
    def test_python_test_failure_blocks_the_gate_and_success_passes(self):
        # Keep fixture configuration out of concurrent workspace discovery.
        parent=ROOT/'.local/tmp/node_modules';parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temp:
            root=Path(temp)
            subprocess.run(['git','init','-q',str(root)],check=True)
            (root/'README.md').write_text('# Fixture\n')
            (root/'.gitattributes').write_text('* text=auto eol=lf\n')
            config={'hooks':{'preCommit':{'installation':'off'}},'checks':[{
                'name':'python-tests','command':sys.executable,
                'args':['-m','unittest','test_sample','-v']}]}
            (root/'.qg.yaml').write_text(json.dumps(config))
            suite=root/'test_sample.py'
            suite.write_text('import unittest\nclass Sample(unittest.TestCase):\n    def test_contract(self):\n        self.assertEqual(1, 2)\n')
            command=['node',str(CLI),'check','--full','--root',str(root)]
            environment={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
            failed=subprocess.run(command,capture_output=True,text=True,env=environment)
            self.assertEqual(failed.returncode,1,failed.stdout+failed.stderr)
            self.assertIn('test_contract',failed.stdout+failed.stderr)
            suite.write_text(suite.read_text().replace('assertEqual(1, 2)','assertEqual(2, 2)'))
            passed=subprocess.run(command,capture_output=True,text=True,env=environment)
            self.assertEqual(passed.returncode,0,passed.stdout+passed.stderr)
            self.assertIn('PASS',passed.stdout)
