"""Ctrl+Shift+G — commit the whole /void by hand with a timestamp message."""
import subprocess
import types

from helpers import make_ring_app


def _git(void, *args):
    return subprocess.run(['git', '-C', str(void), *args],
                          capture_output=True, text=True)


def _void_repo(tmp_path):
    v = tmp_path / 'void'
    v.mkdir()
    subprocess.run(['git', 'init', '-q'], cwd=v, capture_output=True)
    _git(v, 'config', 'user.email', 't@t')
    _git(v, 'config', 'user.name', 'Tester')
    (v / '0.txt').write_text('inicial\n', encoding='utf-8')
    _git(v, 'add', '-A')
    _git(v, 'commit', '-q', '-m', 'base')
    return v


def _app(void):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    app.void_dir = str(void)
    app.commit_void = types.MethodType(FullscreenCircleApp.commit_void, app)
    return app


def test_commit_void_commits_changes(tmp_path):
    v = _void_repo(tmp_path)
    (v / 'I').mkdir()
    (v / 'I' / 'cap.txt').write_text('un texto nuevo\n', encoding='utf-8')
    _app(v).commit_void()
    log = _git(v, 'log', '--oneline').stdout
    assert 'snapshot' in log                       # the new commit exists
    assert 'cap.txt' in _git(v, 'show', '--name-only', 'HEAD').stdout


def test_commit_void_noop_when_clean(tmp_path):
    v = _void_repo(tmp_path)
    before = _git(v, 'rev-parse', 'HEAD').stdout.strip()
    _app(v).commit_void()                          # nothing changed
    after = _git(v, 'rev-parse', 'HEAD').stdout.strip()
    assert before == after                         # no empty commit created
