#!/usr/bin/env bash
# VoiderOS launcher — called by Hyprland on startup
export QT_QPA_PLATFORM=xcb
export PYTHONPATH=/mnt/data/programming/VoiderOS/src

exec nix-shell \
    -p python3 python3Packages.pyqt6 python3Packages.python-pam \
    --run "python3 /mnt/data/programming/VoiderOS/src/voider.py"
