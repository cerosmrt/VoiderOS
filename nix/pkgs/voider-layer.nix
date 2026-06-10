# nix/pkgs/voider-layer.nix
# Python C++ extension that configures voider-py's QMainWindow as a
# Layer::Bottom wlr-layer-shell surface using layer-shell-qt.
{ pkgs, lib }:

pkgs.stdenv.mkDerivation {
  pname   = "voider-layer";
  version = "0.1.0";
  src     = ../../pkgs/voider-layer;

  nativeBuildInputs = with pkgs; [
    cmake
    pkg-config
    qt6.wrapQtAppsHook
  ];

  buildInputs = with pkgs; [
    python3
    qt6.qtbase
    qt6.qtwayland
    kdePackages.layer-shell-qt
    kdePackages.layer-shell-qt.dev
  ];

  dontWrapQtApps = true;
}
