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
  ]);

  qtwayland = pkgs.qt6.qtwayland;
  # The system voider now builds from proto-voider — the improved/canonical
  # version (portal, split, shuffle, all the data-safety fixes). proto honors
  # VOIDER_CONFIG / VOIDER_VOID_DIR (set below) so it runs from the read-only
  # store with config in $HOME. The old pkgs/voider-py/ is kept for reference.
  src = ../../proto-voider;
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
