"""Find newly staged, standalone debug statements in Conduit's browser source."""

import os
from pathlib import Path, PurePosixPath
import re
import subprocess


# Mask complete comments and literals before inspecting individual source lines.
# A literal becomes a placeholder so it cannot join tokens on either side.
_NON_CODE = re.compile(
    r"//[^\n]*|/\*[\s\S]*?(?:\*/|\Z)|"
    r'''"(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*'|`(?:\\[\s\S]|[^`\\])*`'''
)
_RULES = (
    (re.compile(r"console\s*\.\s*log\s*\([^;]*\)\s*;?"), 'console-log',
     '브라우저 코드에 디버그 출력이 추가됐습니다. 배포 전에 이 로그를 정리하세요.'),
    (re.compile(r'debugger\s*;?'), 'debugger',
     '브라우저가 이 줄에서 멈출 수 있습니다. 디버그 중단점을 정리하세요.'),
)
_HUNK = re.compile(rb'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', re.MULTILINE)


def _git(root, *args):
    return subprocess.run(['git', *args], cwd=root, capture_output=True, check=True).stdout


def _is_browser_source(name):
    path = PurePosixPath(name)
    return (
        path.parts[:2] == ('frontend', 'src')
        and path.suffix in {'.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs'}
        and not { 'tests', 'test', '__tests__', '__mocks__', 'fixtures' }.intersection(path.parts)
        and not any(suffix in path.name.split('.')[1:-1] for suffix in ('test', 'spec', 'stories'))
    )


def _added_lines(root, old_oid, new_oid, line_count):
    if not old_oid.strip(b'0'):
        return range(1, line_count + 1)
    patch = _git(root, 'diff', '--no-ext-diff', '--no-textconv', '--no-color',
                 '--inter-hunk-context=0', '--unified=0', old_oid, new_oid)
    lines = []
    for match in _HUNK.finditer(patch):
        start = int(match[1])
        count = int(match[2] or b'1')
        lines.extend(range(start, start + count))
    return lines


def _mask(match):
    token = match[0]
    marker = ' ' if token.startswith('/') else '0'
    return marker + '\n' * token.count('\n')


def scan(root: Path) -> list[dict]:
    raw = _git(root, 'diff', '--cached', '--raw', '--no-abbrev', '--find-renames',
               '--diff-filter=AMRT', '-z', '--')
    fields = iter(raw.split(b'\0')[:-1])
    findings = []
    for header in fields:
        _, mode, old_oid, new_oid, status = header.split()
        name = os.fsdecode(next(fields))
        if status.startswith(b'R'):
            name = os.fsdecode(next(fields))
        if mode not in (b'100644', b'100755') or not _is_browser_source(name):
            continue
        source = _git(root, 'cat-file', 'blob', new_oid).decode('utf-8-sig')
        lines = _NON_CODE.sub(_mask, source).split('\n')
        for number in _added_lines(root, old_oid, new_oid, len(lines)):
            statement = lines[number - 1].strip()
            for pattern, rule, message in _RULES:
                if pattern.fullmatch(statement):
                    findings.append(dict(path=name, line=number, rule=rule, message=message))
    return findings
