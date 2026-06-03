# nix/pkgs/voider.nix
# Builds the Voider Wayland layer-shell app from pkgs/voider/ (Rust crate).
{ pkgs, lib }:

pkgs.rustPlatform.buildRustPackage {
  pname   = "voider";
  version = "0.1.0";

  src = ../../pkgs/voider;

  # After first `cargo update` in pkgs/voider/, commit Cargo.lock then:
  #   nix build .#packages.x86_64-linux.voider 2>&1 | grep "got:"
  # Paste the sha256 here.
  cargoLock.lockFile = ../../pkgs/voider/Cargo.lock;

  nativeBuildInputs = with pkgs; [
    pkg-config
    rustPlatform.bindgenHook
  ];

  buildInputs = with pkgs; [
    wayland      # libwayland-client
    libxkbcommon # keyboard layout handling
  ];

  postFixup = ''
    patchelf --add-rpath "${pkgs.lib.makeLibraryPath [
      pkgs.wayland pkgs.libxkbcommon
    ]}" $out/bin/voider
  '';

  meta = {
    description = "VoiderOS shell — Wayland layer-shell writing environment";
    mainProgram  = "voider";
  };
}
