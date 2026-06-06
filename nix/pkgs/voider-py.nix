# nix/pkgs/voider-py.nix
# Wrapper that puts voider-py on PATH with the right Python + PyQt6 environment.
# voider-shell spawns this by name ("voider-py").
{ pkgs, lib }:

let
  python = pkgs.python3.withPackages (ps: with ps; [
    pyqt6
  ]);

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

  export QT_QPA_PLATFORM=wayland
  export VOIDER_CONFIG="$CONFIG_FILE"

  exec ${python}/bin/python3 ${src}/voider.py "$@"
''
