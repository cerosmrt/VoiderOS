# Cross-compile de voider-rs a Windows. Experimental: ver si egui/eframe cruza.
{ pkgs ? import (fetchTarball "https://nixos.org/channels/nixos-unstable/nixexprs.tar.xz") {} }:
pkgs.mkShell {
  nativeBuildInputs = with pkgs; [
    cargo rustc pkg-config
    pkgsCross.mingwW64.stdenv.cc
  ];
  CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER = "${pkgs.pkgsCross.mingwW64.stdenv.cc}/bin/x86_64-w64-mingw32-gcc";
}
