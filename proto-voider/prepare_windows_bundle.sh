#!/usr/bin/env bash
# prepare_windows_bundle.sh — arma la caché offline que usa Ctrl+B cuando se
# marca "Incluir el programa". Se corre UNA vez (necesita internet acá); después
# Ctrl+B sólo copia de la caché, y INSTALAR.bat compila en Windows sin red.
#
#   nix-shell -p "python3.withPackages(ps: with ps; [pip setuptools wheel])" \
#     --run "bash prepare_windows_bundle.sh"
#
# Volver a correrlo actualiza las dependencias (borrar la caché antes si se
# quiere empezar de cero).
set -euo pipefail

CACHE="${1:-$HOME/.cache/voider/windows-bundle}"
PY_INSTALLER="${PY_INSTALLER:-/mnt/data/Downloads/python-3.10.11-amd64.exe}"

mkdir -p "$CACHE/wheels"

# El instalador de Python que INSTALAR.bat usa si la compu no tiene Python 3.10.
if [ ! -f "$CACHE/$(basename "$PY_INSTALLER")" ]; then
    cp "$PY_INSTALLER" "$CACHE/"
fi

# 1) Paquetes ya compilados para Windows 64 bits / Python 3.10 (con sus
#    dependencias). pyaudio es opcional en el .bat, pero si está, viaja.
#    OJO: pip evalúa los marcadores (sys_platform == "win32") con ESTA máquina,
#    así que las dependencias que sólo pide Windows van nombradas a mano:
#    pefile y pywin32-ctypes (las pide pyinstaller).
python3 -m pip download --dest "$CACHE/wheels" \
    --only-binary=:all: --platform win_amd64 --python-version 3.10 \
    --implementation cp \
    PyQt6 numpy watchdog pyphen pyinstaller pyaudio lxml six \
    pefile pywin32-ctypes

# 2) Los que sólo existen como código fuente (son Python puro): se arman acá
#    como wheel, porque en Windows no habrá red para bajar con qué armarlos.
python3 -m pip wheel --no-deps --wheel-dir "$CACHE/wheels" langdetect ebooklib

echo
echo "Caché lista: $CACHE"
du -sh "$CACHE"
