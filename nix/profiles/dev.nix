# nix/profiles/dev.nix — el banco de trabajo, no el producto.
#
# Todo lo que sirve para DESARROLLAR Voider y que por definición no puede viajar
# en una ISO: los atajos que abren el sandbox de Python y el binario de Rust
# compilado a mano, y que apuntan al checkout del repositorio.
#
# Lo importan los perfiles de máquina (voider, voider-lenovo, voider-vm). La ISO
# no lo importa, y por eso la ISO no sabe nada de /home/federico ni de ~/VoiderOS.
{ config, pkgs, lib, voiderRs, ... }:

let
  repo = "/home/federico/VoiderOS";

  voiderPython = pkgs.python3.withPackages (ps: with ps; [
    pyqt6 numpy pyaudio watchdog langdetect pyphen
  ]);

  # proto-voider: el sandbox de Python. Corre la app directamente, sin watcher —
  # el watcher reiniciaba la app con cada cambio en un .py y se llevaba puesto el
  # texto que se estaba editando. Para tomar cambios de código, reiniciar a mano.
  voiderProto = pkgs.writeShellScriptBin "proto-voider" ''
    cd ${repo}/proto-voider
    export QT_QPA_PLATFORM=wayland
    export QT_PLUGIN_PATH=${pkgs.qt6.qtwayland}/lib/qt-6/plugins''${QT_PLUGIN_PATH:+:$QT_PLUGIN_PATH}
    export WAYLAND_DISPLAY=''${WAYLAND_DISPLAY:-wayland-1}
    exec ${voiderPython}/bin/python3 voider.py
  '';

  # voider-rs recién compilado, desde el checkout. Es a propósito distinto del
  # paquete de nix/pkgs/voider-rs.nix: éste corre lo que acabás de compilar con
  # cargo, sin pasar por Nix, que es lo que uno quiere mientras desarrolla.
  # El del producto se construye desde el fuente y vive en la ISO.
  voiderRsDev = pkgs.writeShellScriptBin "voider-rs-dev" ''
    cd ${repo}/pkgs/voider-rs
    export LD_LIBRARY_PATH=${lib.makeLibraryPath [ pkgs.wayland pkgs.libxkbcommon pkgs.libGL ]}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
    export WAYLAND_DISPLAY=''${WAYLAND_DISPLAY:-wayland-1}
    BIN=target/release/voider-rs
    [ -x "$BIN" ] || BIN=target/debug/voider-rs
    if [ ! -x "$BIN" ]; then
      echo "voider-rs no está compilado todavía. Compilalo con:"
      echo "  cd ~/VoiderOS/pkgs/voider-rs && nix-shell --run 'cargo build --release'"
      read -r -p "Enter para cerrar..." _
      exit 1
    fi
    exec ./"$BIN" "$@"
  '';
in
{
  # Las dos versiones conviven a propósito en una máquina de desarrollo:
  # `voider-rs` es el paquete reproducible (el mismo que viaja en la ISO), y
  # `voider-rs-dev` corre lo que acabás de compilar con cargo. Comparar una con
  # otra es justamente lo que uno quiere poder hacer acá.
  environment.systemPackages = [ voiderProto voiderRsDev voiderRs ];

  # Los dos atajos de desarrollo, por el punto de extensión que expone
  # nix/modules/voider.nix. Super+O corre el binario recién compilado con cargo;
  # el voider-rs empaquetado (el del producto) también está en el PATH.
  voider.extraHyprlandBinds = ''
    bind = SUPER, P, exec, kitty --title proto-voider -e proto-voider
    bind = SUPER, O, exec, kitty --title voider-rs-dev -e voider-rs-dev
  '';
}
