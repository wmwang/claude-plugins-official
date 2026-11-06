import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)


def run(script, *args):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args], capture_output=True, text=True)


def load(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def write(root, rel, text='x\n'):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text)


class ShardTests(unittest.TestCase):
    def test_tree_shards_by_directory_and_skips_vendored_code(self):
        with tempfile.TemporaryDirectory() as ws:
            for i in range(30):
                write(ws, f'legacy/erp/lib/pay/p{i}.pl', 'a\n' * 10)
            write(ws, 'legacy/erp/lib/tax/t.pl', 'a\n' * 400)
            write(ws, 'legacy/erp/node_modules/x/y.js', 'a\n')
            write(ws, 'legacy/erp/tests/t.pl', 'a\n')
            write(ws, 'legacy/erp/README.md', 'text\n')
            done = run('make_shards.py', 'erp', '--workspace', ws)
            self.assertEqual(done.returncode, 0, done.stderr)
            shards = load(os.path.join(ws, 'analysis/erp/extract-rules.modules.json'))
            names = [s['name'] for s in shards]
            self.assertEqual(names, ['lib/pay', 'lib/pay#2', 'lib/tax'])
            self.assertEqual(len(shards[0]['files']), 25)
            self.assertNotIn('node_modules', json.dumps(shards))
            self.assertNotIn('tests/t.pl', json.dumps(shards))
            self.assertTrue(all(not f.startswith('legacy/') for s in shards for f in s['files']))

    def test_a_symlinked_source_is_followed_and_files_stay_relative_to_it(self):
        with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as elsewhere:
            write(elsewhere, 'src/a.cbl', 'a\n' * 50)
            os.makedirs(os.path.join(ws, 'legacy'))
            os.symlink(elsewhere, os.path.join(ws, 'legacy', 'big'))
            done = run('make_shards.py', 'big', '--workspace', ws)
            self.assertEqual(done.returncode, 0, done.stderr)
            shards = load(os.path.join(ws, 'analysis/big/extract-rules.modules.json'))
            self.assertEqual(shards[0]['files'], ['src/a.cbl'])

    def test_topology_merges_small_modules_and_normalizes_paths(self):
        with tempfile.TemporaryDirectory() as ws:
            for name in ('A', 'B', 'C'):
                write(ws, f'legacy/s/{name}.cbl', 'a\n' * 50)
            topology = {'root': {'kind': 'system', 'id': 'sys', 'children': [{'kind': 'domain', 'name': 'D1', 'id': 'dom:d1', 'children': [
                {'kind': 'module', 'id': 'A', 'name': 'A', 'file': 'A.cbl', 'loc': 50},
                {'kind': 'module', 'id': 'B', 'name': 'B', 'file': 'legacy/s/B.cbl', 'loc': 50},
                {'kind': 'module', 'id': 'C', 'name': 'C', 'file': os.path.join(ws, 'legacy/s/C.cbl'), 'loc': 900}]}]}}
            write(ws, 'analysis/s/topology.json', json.dumps(topology))
            self.assertEqual(run('make_shards.py', 's', '--workspace', ws).returncode, 0)
            shards = load(os.path.join(ws, 'analysis/s/extract-rules.modules.json'))
            self.assertEqual([s['files'] for s in shards], [['A.cbl', 'B.cbl'], ['C.cbl']])
            self.assertEqual(run('make_shards.py', 's', 'C*', '--workspace', ws).returncode, 0)
            self.assertEqual(run('make_shards.py', 's', 'nothing*', '--workspace', ws).returncode, 1)

    def test_links_and_paths_that_leave_the_source_are_not_shards(self):
        with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as outside:
            write(ws, 'legacy/s/ok.pl', 'a\n' * 5)
            write(outside, 'secret.pl', 'not part of the system\n')
            os.symlink(os.path.join(outside, 'secret.pl'), os.path.join(ws, 'legacy/s/link.pl'))
            self.assertEqual(run('make_shards.py', 's', '--workspace', ws).returncode, 0)
            shards = load(os.path.join(ws, 'analysis/s/extract-rules.modules.json'))
            self.assertEqual([f for s in shards for f in s['files']], ['ok.pl'])
            topology = {'root': {'kind': 'system', 'id': 'sys', 'children': [{'kind': 'domain', 'name': 'D', 'id': 'd', 'children': [
                {'kind': 'module', 'id': 'A', 'name': 'A', 'file': 'ok.pl', 'loc': 500},
                {'kind': 'module', 'id': 'B', 'name': 'B', 'file': '../../../etc/hosts', 'loc': 500},
                {'kind': 'module', 'id': 'C', 'name': 'C', 'file': 'link.pl', 'loc': 500}]}]}}
            write(ws, 'analysis/s/topology.json', json.dumps(topology))
            done = run('make_shards.py', 's', '--workspace', ws)
            self.assertEqual(done.returncode, 0, done.stderr)
            shards = load(os.path.join(ws, 'analysis/s/extract-rules.modules.json'))
            self.assertEqual([f for s in shards for f in s['files']], ['ok.pl'])
            self.assertIn('outside the source directory', done.stdout)

    def test_a_link_to_the_home_directory_or_root_is_refused(self):
        with tempfile.TemporaryDirectory() as ws:
            os.makedirs(os.path.join(ws, 'legacy'))
            for broad in (os.path.expanduser('~'), '/', '/usr'):
                link = os.path.join(ws, 'legacy', 's')
                if os.path.islink(link):
                    os.unlink(link)
                os.symlink(broad, link)
                done = run('make_shards.py', 's', '--workspace', ws)
                self.assertEqual(done.returncode, 1, broad)
                self.assertIn('too broad', done.stderr)

    def test_a_plain_name_matches_what_lies_beneath_it(self):
        with tempfile.TemporaryDirectory() as ws:
            write(ws, 'legacy/s/jetty-util/src/A.java', 'a\n' * 5)
            write(ws, 'legacy/s/jetty-util-ajax/src/B.java', 'a\n' * 5)
            write(ws, 'legacy/s/other/C.java', 'a\n' * 5)
            self.assertEqual(run('make_shards.py', 's', 'jetty-util', '--workspace', ws).returncode, 0)
            shards = load(os.path.join(ws, 'analysis/s/extract-rules.modules.json'))
            self.assertEqual([f for sh in shards for f in sh['files']], ['jetty-util/src/A.java'])

    def test_a_map_whose_modules_share_one_directory_falls_back_to_the_tree(self):
        with tempfile.TemporaryDirectory() as ws:
            for name in ('a', 'b'):
                write(ws, f'legacy/s/pkg/{name}/X.java', 'a\n' * 50)
            children = [{'kind': 'module', 'id': f'pkg/{n}', 'name': f'pkg/{n}', 'file': 'pkg', 'loc': 900} for n in ('a', 'b')]
            topology = {'root': {'kind': 'system', 'id': 'sys', 'children': [{'kind': 'domain', 'name': 'D', 'id': 'd', 'children': children}]}}
            write(ws, 'analysis/s/topology.json', json.dumps(topology))
            done = run('make_shards.py', 's', '--workspace', ws)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn('cannot be sharded by module', done.stdout)
            shards = load(os.path.join(ws, 'analysis/s/extract-rules.modules.json'))
            self.assertEqual(sorted(f for sh in shards for f in sh['files']), ['pkg/a/X.java', 'pkg/b/X.java'])

    def test_missing_source_says_what_to_do(self):
        with tempfile.TemporaryDirectory() as ws:
            done = run('make_shards.py', 'nope', '--workspace', ws)
            self.assertEqual(done.returncode, 1)
            self.assertIn('preflight', done.stderr)

    def test_winforms_paired_files_never_split_across_shards(self):
        with tempfile.TemporaryDirectory() as ws:
            # 24 standalone files + a 3-file WinForms unit (Form.cs, Form.Designer.cs, Form.resx) = 27 files (> MAX_FILES=25)
            for i in range(24):
                write(ws, f'legacy/win/Forms/A{i:02d}.cs', 'a\n' * 10)
            write(ws, 'legacy/win/Forms/ZOrderForm.cs', 'a\n' * 20)
            write(ws, 'legacy/win/Forms/ZOrderForm.Designer.cs', 'a\n' * 30)
            write(ws, 'legacy/win/Forms/ZOrderForm.resx', '<root/>\n' * 5)
            done = run('make_shards.py', 'win', '--workspace', ws)
            self.assertEqual(done.returncode, 0, done.stderr)
            shards = load(os.path.join(ws, 'analysis/win/extract-rules.modules.json'))
            self.assertEqual(len(shards), 2)
            z_shards = [s['name'] for s in shards if any('ZOrderForm' in f for f in s['files'])]
            self.assertEqual(len(z_shards), 1, 'ZOrderForm.cs, .Designer.cs, and .resx must stay in the same shard')
            self.assertEqual(
                sorted(f for f in shards[1]['files'] if 'ZOrderForm' in f),
                ['Forms/ZOrderForm.Designer.cs', 'Forms/ZOrderForm.cs', 'Forms/ZOrderForm.resx'],
            )


class RenderTests(unittest.TestCase):
    def test_rules_render_with_rule_headings_and_hostile_text_stays_inert(self):
        result = {'confirmedRules': [
            {'name': 'Late fee', 'category': 'Calculation', 'priority': 'P0', 'source': 'a.cbl:10-20', 'plainEnglish': 'A fee.',
             'given': 'a late payment', 'when': 'month end', 'then': 'fee 5%', 'confidence': 'High'},
            {'name': 'Bad `name` | pipe\n# Heading', 'category': 'Validation', 'priority': 'P1', 'source': 'b.cbl:1-2', 'plainEnglish': 'x',
             'given': 'g\n# injected heading\n```', 'when': 'w', 'then': 't', 'confidence': 'Low', 'smeQuestion': 'Is it 5 or 6?'}],
            'dataObjects': [{'name': 'Account', 'source': 'a.cbl:1', 'fields': [{'name': 'id', 'type': 'int'}], 'consumedBy': ['Late fee']}],
            'injectionFlags': ['a.cbl:5'], 'rejectedRules': [{}], 'unverifiedRules': [], 'rerunModules': [],
            'stats': {'skippedModules': ['M9']}}
        with tempfile.TemporaryDirectory() as ws:
            write(ws, 'analysis/s/rules_result.json', json.dumps(result))
            done = run('render_rules.py', 's', '--workspace', ws)
            self.assertEqual(done.returncode, 0, done.stderr)
            text = open(os.path.join(ws, 'analysis/s/BUSINESS_RULES.md'), encoding='utf-8').read()
            self.assertIn('### RULE-001: Late fee', text)
            self.assertIn('### RULE-002: Bad', text)
            headings = [line for line in text.splitlines() if line.startswith('### ')]
            self.assertEqual(len(headings), 2, headings)
            self.assertNotIn('\n# injected heading', text)
            ids = [int(n) for n in re.findall(r'^### RULE-(\d+): ', text, re.M)]
            self.assertEqual(ids, list(range(1, len(ids) + 1)), 'rule numbers read in sequence down the document')
            self.assertIn('Rules requiring SME confirmation', text)
            self.assertIn('Is it 5 or 6?', text)
            self.assertIn('Coverage gaps', text)
            self.assertIn('Instruction-shaped content', text)
            dto = open(os.path.join(ws, 'analysis/s/DATA_OBJECTS.md'), encoding='utf-8').read()
            self.assertIn('## Account', dto)

    def test_a_rule_keeps_one_citation_and_the_rest_moves_to_also_cited(self):
        sources = ['wwwroot/a.pl:100-120 (aggregation); family table at lib/b.pm:31-40',
                   'lib/x.pm:966,1018,1238 (order lists)', 'no citation here', 'c.cbl:7']
        result = {'confirmedRules': [
            {'name': f'R{i}', 'category': 'Policy', 'priority': 'P1', 'source': src, 'plainEnglish': 'x',
             'given': 'g', 'when': 'w', 'then': 't', 'confidence': 'High'} for i, src in enumerate(sources)]}
        with tempfile.TemporaryDirectory() as ws:
            write(ws, 'analysis/s/rules_result.json', json.dumps(result))
            self.assertEqual(run('render_rules.py', 's', '--workspace', ws).returncode, 0)
            text = open(os.path.join(ws, 'analysis/s/BUSINESS_RULES.md'), encoding='utf-8').read()
            cites = re.findall(r'^\*\*Source:\*\* `([^`]*)`', text, re.M)
            self.assertEqual(sorted(cites), sorted(['wwwroot/a.pl:100-120', 'lib/x.pm:966', 'no citation here', 'c.cbl:7']))
            self.assertIn('**Also cited:** (aggregation); family table at lib/b.pm:31-40', text)
            self.assertEqual(text.count('**Also cited:**'), 2)

    def test_folded_rules_are_listed_so_nothing_disappears_untraceably(self):
        result = {'confirmedRules': [{'name': 'Twiddle table', 'category': 'Calculation', 'priority': 'P0', 'source': 'a.c:1-2 ; also b.c:3-4',
                                      'plainEnglish': 'x', 'given': 'g', 'when': 'w', 'then': 't', 'confidence': 'Low'}],
                  'foldedRules': [{'name': 'Twiddle factors', 'source': 'b.c:3-4', 'into': 'Twiddle table'}, 'junk', {'name': 'X\n# fake heading', 'source': 's', 'into': 'i'}]}
        with tempfile.TemporaryDirectory() as ws:
            write(ws, 'analysis/s/rules_result.json', json.dumps(result))
            self.assertEqual(run('render_rules.py', 's', '--workspace', ws).returncode, 0)
            text = open(os.path.join(ws, 'analysis/s/BUSINESS_RULES.md'), encoding='utf-8').read()
            self.assertIn('## Rules folded into another', text)
            self.assertIn('- Twiddle factors (b.c:3-4) into Twiddle table', text)
            self.assertIn('**Also cited:** b.c:3-4', text)
            self.assertNotIn('\n# fake heading', text)

    def test_unreadable_result_is_an_error(self):
        with tempfile.TemporaryDirectory() as ws:
            self.assertEqual(run('render_rules.py', 's', '--workspace', ws).returncode, 1)

    def test_gui_split_categories_and_verification_reach_proven(self):
        result = {'confirmedRules': [
            {'name': 'Foreign exchange discount calculation', 'category': 'Calculation', 'priority': 'P0',
             'targetLayer': 'Backend', 'uiMapping': 'OrderForm.btnSubmit_Click -> OrderPage -> POST /api/orders',
             'source': 'Forms/OrderForm.cs:40-65', 'plainEnglish': 'Calculates USD discount.',
             'given': 'USD order > 1000', 'when': 'submitted', 'then': '5% discount applied', 'confidence': 'High'},
            {'name': 'Currency selection enables exchange rate field', 'category': 'UI-State', 'priority': 'P0',
             'targetLayer': 'Frontend', 'uiMapping': 'OrderForm.cboCurrency_SelectedIndexChanged -> OrderForm.tsx (isFxEditable)',
             'source': 'Forms/OrderForm.Designer.cs:110-145', 'plainEnglish': 'Selecting USD unlocks exchange rate input.',
             'given': 'Currency is TWD', 'when': 'user selects USD', 'then': 'txtExchangeRate becomes editable', 'confidence': 'High'},
            {'name': 'High amount order confirmation dialog workflow', 'category': 'UI-Flow', 'priority': 'P0',
             'targetLayer': 'Full-Stack', 'uiMapping': 'OrderForm.btnSubmit_Click MessageBox -> ConfirmDialog.tsx -> POST /api/orders',
             'source': 'Forms/OrderForm.cs:70-98', 'plainEnglish': 'Orders above 10,000 require modal confirmation.',
             'given': 'Order total is 15000', 'when': 'operator clicks Submit', 'then': 'confirm modal opens before API call', 'confidence': 'High'}
        ]}
        with tempfile.TemporaryDirectory() as ws:
            write(ws, 'legacy/win/Forms/OrderForm.cs', '// legacy code\n')
            write(ws, 'analysis/win/PREFLIGHT.md', '# Preflight\n')
            write(ws, 'analysis/win/rules_result.json', json.dumps(result))
            self.assertEqual(run('render_rules.py', 'win', '--workspace', ws).returncode, 0)
            with open(os.path.join(ws, 'analysis/win/BUSINESS_RULES.md'), encoding='utf-8') as fh:
                rules_md = fh.read()
            self.assertIn('## UI-State', rules_md)
            self.assertIn('## UI-Flow', rules_md)
            self.assertIn('**Target layer:** Frontend', rules_md)
            self.assertIn('**UI mapping:** OrderForm.cboCurrency_SelectedIndexChanged', rules_md)

            # Build modernized GUI-split module (backend Spring Boot + frontend React)
            write(ws, 'modernized/win/order/backend/src/main/java/OrderService.java', '// RULE-001\nclass OrderService {}\n')
            write(ws, 'modernized/win/order/backend/src/test/java/OrderServiceTest.java', '// RULE-001\nclass OrderServiceTest {}\n')
            write(ws, 'modernized/win/order/frontend/src/components/OrderForm.tsx', '// RULE-002 RULE-003\nexport function OrderForm() {}\n')
            write(ws, 'modernized/win/order/frontend/src/__tests__/OrderForm.test.tsx', '// RULE-002 RULE-003\n')
            write(ws, 'modernized/win/order/TRANSFORMATION_NOTES.md',
                  '# Notes\n## GUI Workflow & Split Mapping\n| Legacy Form.Control | Rule | React | API |\n|---|---|---|---|\n'
                  '| OrderForm.Designer.cs cboCurrency_SelectedIndexChanged | RULE-002 | OrderForm.tsx | POST /api/orders |\n')

            # Backend JUnit XML (RULE-001 + 6 boundary/edge cases)
            be_cases = ['<testcase classname="com.acme.OrderServiceTest" name="rule001_fxDiscountCalculation" time="0.01"/>'] + [
                f'<testcase classname="com.acme.OrderServiceTest" name="rule001_boundary_case_{i}" time="0.01"/>' for i in range(6)
            ]
            write(ws, 'analysis/win/equivalence/junit-backend.xml',
                  f'<testsuite name="OrderServiceTest" tests="7" failures="0">{"".join(be_cases)}</testsuite>\n')

            # Frontend Vitest JUnit XML (RULE-002, RULE-003 + 6 UI-flow/state/dialog edge cases)
            fe_cases = [
                '<testcase classname="OrderForm.test.tsx" name="RULE-002: ui_state currency change unlocks rate input" time="0.02"/>',
                '<testcase classname="OrderForm.test.tsx" name="RULE-003: ui_flow confirm modal blocks API on cancel" time="0.02"/>',
            ] + [
                f'<testcase classname="OrderForm.test.tsx" name="ui_flow_dialog_edge_case_{i}" time="0.01"/>' for i in range(6)
            ]
            write(ws, 'analysis/win/equivalence/junit-frontend.xml',
                  f'<testsuite name="OrderForm.test.tsx" tests="8" failures="0">{"".join(fe_cases)}</testsuite>\n')

            # Canary XML (shows a failure when broken)
            write(ws, 'analysis/win/equivalence/canary-backend.xml',
                  '<testsuite name="OrderServiceTest" tests="1" failures="1">'
                  '<testcase classname="com.acme.OrderServiceTest" name="rule001_fxDiscountCalculation"><failure message="broken"/></testcase>'
                  '</testsuite>\n')

            test_runs = {
                'date': '2026-11-06',
                'guiSplit': True,
                'legacy': {'ran': False, 'how': '', 'why': 'WinForms desktop GUI (.exe)'},
                'suites': [
                    {'module': 'order', 'name': 'backend-junit', 'command': 'mvn test',
                     'junit': ['analysis/win/equivalence/junit-backend.xml'], 'log': []},
                    {'module': 'order', 'name': 'frontend-vitest', 'command': 'npx vitest run --reporter=junit',
                     'junit': ['analysis/win/equivalence/junit-frontend.xml'], 'log': []},
                ],
                'canaries': [
                    {'module': 'order', 'change': 'flipped discount rate in OrderService.java',
                     'junit': ['analysis/win/equivalence/canary-backend.xml'], 'log': []}
                ],
            }
            write(ws, 'analysis/win/equivalence/test-runs.json', json.dumps(test_runs))

            done = run('proof_pack.py', 'win', 'order', '--workspace', ws)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            ver = load(os.path.join(ws, 'analysis/win/VERIFICATION.json'))
            self.assertEqual(ver['overall']['verdict'], 'PROVEN')
            self.assertEqual(ver['modules'][0]['verdict'], 'PROVEN')
            self.assertEqual(ver['modules'][0]['evidence']['rules']['uiRulesTested'], 2)

            # Negative check: if GUI Workflow Mapping is missing from TRANSFORMATION_NOTES.md, Same behavior drops to gap (PARTLY PROVEN)
            write(ws, 'modernized/win/order/TRANSFORMATION_NOTES.md', '# Notes without GUI mapping\n')
            done_gap = run('proof_pack.py', 'win', 'order', '--workspace', ws)
            self.assertEqual(done_gap.returncode, 1)
            ver_gap = load(os.path.join(ws, 'analysis/win/VERIFICATION.json'))
            self.assertEqual(ver_gap['overall']['verdict'], 'PARTLY PROVEN')
            self.assertTrue(any('GUI Workflow & Split Mapping' in r for r in ver_gap['modules'][0]['reasons']))


if __name__ == '__main__':
    unittest.main()
