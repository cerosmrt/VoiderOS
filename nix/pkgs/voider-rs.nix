# nix/pkgs/voider-rs.nix — voider-rs como paquete reproducible.
#
# Hasta ahora voider-rs se lanzaba con un script que hacía `cd` al checkout de
# desarrollo y ejecutaba un binario ya compilado a mano. Eso anda en la máquina
# donde se compiló y en ninguna otra, así que no puede viajar en una ISO. Acá se
# construye desde el fuente, con Nix, a partir del Cargo.lock del repo.
#
# El rustPlatform lo inyecta el flake desde nixpkgs-unstable: los dependientes de
# eframe piden rustc >= 1.88 y el nixpkgs estable del sistema trae 1.86. Es la
# única pieza que se toma de unstable — el resto del sistema sigue en 25.05.
{ lib
, rustPlatform
, pkg-config
, makeWrapper
, wayland
, libxkbcommon
, libGL
, vulkan-loader
}:

rustPlatform.buildRustPackage {
  pname = "voider-rs";
  version = "0.1.0";

  src = lib.cleanSourceWith {
    src = ../../pkgs/voider-rs;
    # target/ pesa cientos de megas y no aporta nada a la construcción.
    filter = path: type:
      let base = baseNameOf path;
      in base != "target" && base != "result";
  };

  cargoLock.lockFile = ../../pkgs/voider-rs/Cargo.lock;

  nativeBuildInputs = [ pkg-config makeWrapper ];
  buildInputs = [ wayland libxkbcommon libGL vulkan-loader ];

  # Los tests tocan sockets, procesos y el reloj; corren en el repo, no acá.
  doCheck = false;

  # winit carga wayland/libxkbcommon/libGL en runtime por dlopen, así que no
  # alcanza con enlazarlos: tienen que estar en LD_LIBRARY_PATH o falla al abrir
  # con NoWaylandLib.
  postInstall = ''
    wrapProgram $out/bin/voider-rs \
      --prefix LD_LIBRARY_PATH : ${lib.makeLibraryPath [ wayland libxkbcommon libGL vulkan-loader ]}
  '';

  meta = with lib; {
    description = "Voider — la máquina de escribir, en Rust/egui";
    platforms = platforms.linux;
    mainProgram = "voider-rs";
  };
}
