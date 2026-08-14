# Dev shell for voider-rs (the Rust/egui mirror).
#   cd pkgs/voider-rs && nix-shell --run "cargo test"
#
# Pinned to nixos-unstable because the system nixpkgs ships rustc 1.86, which is
# below the MSRV (1.88) of some transitive deps of eframe.
{ pkgs ? import (fetchTarball "https://nixos.org/channels/nixos-unstable/nixexprs.tar.xz") {} }:

pkgs.mkShell {
  nativeBuildInputs = with pkgs; [ cargo rustc pkg-config ];
  buildInputs = with pkgs; [ wayland libxkbcommon libGL ];
  # winit/eframe dlopen these at runtime.
  LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath (with pkgs; [ wayland libxkbcommon libGL ]);
}
