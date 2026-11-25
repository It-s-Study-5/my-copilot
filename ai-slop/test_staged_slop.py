import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from staged_slop import scan


class StagedSlopTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')

    def git(self, *args):
        subprocess.run(['git', *args], cwd=self.root, capture_output=True, check=True)

    def write(self, name, source):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding='utf-8')

    def test_scans_only_newly_staged_lines(self):
        name = 'frontend/src/한 글\t[0].jsx'
        old = 'console.log("old")\nexport const old = 3\n'
        self.write(name, old)
        self.git('add', '.')
        self.git('commit', '-qm', 'baseline')
        self.write(name, old + 'console.log("new"); // temporary\ndebugger;\n')
        self.git('add', '.')
        self.write(name, old + 'export const workingTree = true\n')
        self.assertEqual([(f['path'], f['line'], f['rule']) for f in scan(self.root)],
                         [(name, 3, 'console-log'), (name, 4, 'debugger')])

    def test_ignores_strings_comments_and_non_product_files(self):
        self.write('frontend/src/Example.tsx', '''/*
console.log("inside block comment")
*/
const sample = `example
console.log("inside template")
debugger;
`;
// debugger;
const message = 'console.log(3)';
console.error('keep user-visible error');
''')
        for name in ('frontend/src/Example.test.tsx', 'frontend/src/__tests__/example.js',
                     'backend/service.js', 'frontend/vite.config.js', 'frontend/src/style.css'):
            self.write(name, 'debugger;\n')
        self.git('add', '.')
        self.assertEqual(scan(self.root), [])

    def test_rename_does_not_reflag_existing_lines(self):
        before, after = 'frontend/src/a.js', 'frontend/src/b.js'
        self.write(before, 'debugger;\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'baseline')
        self.git('mv', before, after)
        self.assertEqual(scan(self.root), [])

    def test_git_failure_propagates(self):
        with TemporaryDirectory() as outside_git, self.assertRaises(subprocess.CalledProcessError):
            scan(Path(outside_git))


if __name__ == '__main__':
    unittest.main()
