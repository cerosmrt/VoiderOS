# nix/pkgs/voider-py.nix
# Wrapper that puts voider-py on PATH with the right Python + PyQt6 environment.
# Includes voider-layer (C++ extension) and layer-shell-qt plugin.
{ pkgs, lib }:

let
  voiderLayer = pkgs.callPackage ./voider-layer.nix { inherit pkgs lib; };

  python = pkgs.python3.withPackages (ps: with ps; [
    pyqt6
    numpy
    pyaudio
  ]);

  qtwayland    = pkgs.qt6.qtwayland;
  layerShellQt = pkgs.kdePackages.layer-shell-qt;
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

  # Qt Wayland platform + layer-shell-qt shell integration plugin
  export QT_PLUGIN_PATH=${qtwayland}/lib/qt-6/plugins''${QT_PLUGIN_PATH:+:$QT_PLUGIN_PATH}
  export QT_PLUGIN_PATH=${layerShellQt}/lib/qt-6/plugins:$QT_PLUGIN_PATH

  export QT_QPA_PLATFORM=wayland
  export VOIDER_CONFIG="$CONFIG_FILE"
  export VOIDER_VOID_DIR="$HOME/void"
  mkdir -p "$VOIDER_VOID_DIR"

  # voider_layer.so: C++ extension for layer-shell-qt configuration
  export PYTHONPATH=${voiderLayer}/lib''${PYTHONPATH:+:$PYTHONPATH}

  exec ${python}/bin/python3 ${src}/voider.py "$@"
''
