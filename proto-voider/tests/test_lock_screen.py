"""Tests for LockScreen logic (PAM auth, show/hide, field clearing)."""
import os
import sys
import types
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class _FakeLockScreen:
    """Thin wrapper that exercises LockScreen logic without real Qt widgets."""

    def __init__(self):
        # Simulate Qt widget state
        self._visible = False
        self._password_text = ''

        # Minimally stub _password_input
        pw = MagicMock()
        pw.text.side_effect = lambda: self._password_text
        pw.setText.side_effect = lambda v: setattr(self, '_password_text', v)
        pw.clear.side_effect = lambda: setattr(self, '_password_text', '')
        pw.setFocus = MagicMock()
        self._password_input = pw

        self._error_label = MagicMock()
        self._error_label.hide = MagicMock()
        self._error_label.show = MagicMock()
        self._error_label.setText = MagicMock()

    def show_lock(self):
        self._password_input.clear()
        self._error_label.hide()
        self._visible = True
        self._password_input.setFocus()

    def parentWidget(self):
        return None

    def hide(self):
        self._visible = False

    def isVisible(self):
        return self._visible

    def _try_unlock(self):
        """Delegate to the real implementation from lock_screen module."""
        from lock_screen import LockScreen
        LockScreen._try_unlock(self)


class TestLockScreenLogic:

    def test_initially_hidden(self):
        ls = _FakeLockScreen()
        assert not ls.isVisible()

    def test_show_lock_makes_visible(self):
        ls = _FakeLockScreen()
        ls.show_lock()
        assert ls.isVisible()

    def test_show_lock_clears_previous_input(self):
        ls = _FakeLockScreen()
        ls.show_lock()
        ls._password_text = 'leftover'
        ls.hide()
        ls.show_lock()
        assert ls._password_text == ''

    def test_correct_password_hides(self):
        ls = _FakeLockScreen()
        ls.show_lock()
        ls._password_text = 'correct'

        with patch('lock_screen.pam') as mock_pam_mod:
            mock_instance = MagicMock()
            mock_instance.authenticate.return_value = True
            mock_pam_mod.pam.return_value = mock_instance
            ls._try_unlock()

        assert not ls.isVisible()

    def test_wrong_password_stays_visible(self):
        ls = _FakeLockScreen()
        ls.show_lock()
        ls._password_text = 'bad'

        with patch('lock_screen.pam') as mock_pam_mod:
            mock_instance = MagicMock()
            mock_instance.authenticate.return_value = False
            mock_pam_mod.pam.return_value = mock_instance
            ls._try_unlock()

        assert ls.isVisible()

    def test_wrong_password_clears_field(self):
        ls = _FakeLockScreen()
        ls.show_lock()
        ls._password_text = 'bad'

        with patch('lock_screen.pam') as mock_pam_mod:
            mock_instance = MagicMock()
            mock_instance.authenticate.return_value = False
            mock_pam_mod.pam.return_value = mock_instance
            ls._try_unlock()

        assert ls._password_text == ''

    def test_pam_called_with_current_user(self):
        ls = _FakeLockScreen()
        ls.show_lock()
        ls._password_text = 'pw'

        with patch('lock_screen.pam') as mock_pam_mod, \
             patch('lock_screen.getpass') as mock_gp:
            mock_gp.getuser.return_value = 'federico'
            mock_instance = MagicMock()
            mock_instance.authenticate.return_value = True
            mock_pam_mod.pam.return_value = mock_instance

            ls._try_unlock()

            mock_instance.authenticate.assert_called_once_with('federico', 'pw')
