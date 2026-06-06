# nix/pkgs/voider-shell.nix
# Thin Rust layer-shell host. Creates a transparent Layer::Bottom Wayland
# surface and spawns voider-py. Never changes — all logic is in Python.
{ pkgs, lib }:

pkgs.rustPlatform.buildRustPackage {
  pname   = "voider-shell";
  version = "0.1.0";

  src = ../../pkgs/voider-shell;

  cargoLock.lockFile = ../../pkgs/voider-shell/Cargo.lock;

  nativeBuildInputs = with pkgs; [ pkg-config ];
  buildInputs       = with pkgs; [ wayland ];

  meta.mainProgram = "voider-shell";
}
