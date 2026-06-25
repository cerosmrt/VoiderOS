# nix/pkgs/voider-py.nix
# Wrapper that puts voider-py on PATH with the right Python + PyQt6 environment.
# voider-shell spawns this by name ("voider-py").
{ pkgs, lib }:

let
  python = pkgs.python3.withPackages (ps: with ps; [
    pyqt6
    numpy
    pyaudio
    watchdog
    python-pam
  ]);

  qtwayland = pkgs.qt6.qtwayland;
  # System voider builds from pkgs/voider-py — its own copy of the good code
  # ported from proto-voider (portal, split, shuffle, data-safety fixes) plus the
  # VOIDER_CONFIG / VOIDER_VOID_DIR packaging adaptation. proto-voider/ stays the
  # untouched dev sandbox; promote by re-copying proto → voider-py when ready.
  src = ../../pkgs/voider-py;
in
pkgs.writeShellScriptBin "voider-py" ''
  # Config lives in the user's home so it's writable
  CONFIG_DIR="$HOME/.config/voideros"
  CONFIG_FILE="$CONFIG_DIR/config.json"
  mkdir -p "$CONFIG_DIR"

  # Seed default config on first run
  if [ ! -f "$CONFIG_FILE" ]; then
    cp ${src}/config.json "$CONFIG_FILE"
    chmod 644 "$CONFIG_FILE"
  fi

  export WAYLAND_DISPLAY=''${WAYLAND_DISPLAY:-wayland-1}
  export QT_PLUGIN_PATH=${qtwayland}/lib/qt-6/plugins''${QT_PLUGIN_PATH:+:$QT_PLUGIN_PATH}
  export QT_QPA_PLATFORM=wayland
  export VOIDER_CONFIG="$CONFIG_FILE"
  export VOIDER_VOID_DIR="$HOME/void"
  mkdir -p "$VOIDER_VOID_DIR"

  exec ${python}/bin/python3 ${src}/voider.py "$@"
''
