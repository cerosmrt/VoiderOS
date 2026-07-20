"""commit_void (Ctrl+Shift+G) should echo git's own change summary again —
the 'N file(s) changed, X insertions(+), Y deletions(-)' line — so you see how
much was committed. _commit_stat_line() extracts it from git's output."""
import pytest

pytest.importorskip("PyQt6")
from io_mixin import IoMixin


def test_extracts_the_summary_line():
    out = ("[archive 1a2b3c4] snapshot 2026-07-20 11:44:29\n"
           " 1 file changed, 142 insertions(+), 123 deletions(-)\n")
    assert IoMixin._commit_stat_line(out) == \
        "1 file changed, 142 insertions(+), 123 deletions(-)"


def test_multiple_files():
    out = " 3 files changed, 10 insertions(+), 2 deletions(-)"
    line = IoMixin._commit_stat_line(out)
    assert 'insertions' in line and 'deletions' in line


def test_insertions_only():
    out = "[main abc] x\n 2 files changed, 5 insertions(+)\n"
    assert IoMixin._commit_stat_line(out) == "2 files changed, 5 insertions(+)"


def test_no_summary_returns_empty():
    assert IoMixin._commit_stat_line("nothing to commit, working tree clean") == ''
    assert IoMixin._commit_stat_line("") == ''
