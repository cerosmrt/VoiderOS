# Compilar voider.exe desde NixOS

Sí se puede, y con Python no se podía. Salió un ejecutable de 4,9 MB que en
Windows no necesita nada instalado.

```bash
# 1. Un rustc con la librería estándar de Windows (el de nixpkgs sólo trae la
#    de Linux). Fuera del store a propósito, es una herramienta, no una entrada.
export RUSTUP_HOME=~/.local/share/voider-rs-win/rustup
export CARGO_HOME=~/.local/share/voider-rs-win/cargo
nix-shell -p rustup --run "rustup toolchain install stable --profile minimal \
  && rustup target add x86_64-pc-windows-gnu"

# 2. Compilar
cd pkgs/voider-rs
nix-shell -p pkgsCross.mingwW64.stdenv.cc pkgsCross.mingwW64.windows.pthreads pkg-config --run '
  export PATH="$RUSTUP_HOME/toolchains/stable-x86_64-unknown-linux-gnu/bin:$PATH"
  export CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER=$(which x86_64-w64-mingw32-gcc)
  PT=$(find /nix/store -maxdepth 4 -name libpthread.a -path "*pthreads-w32*" | head -1)
  export RUSTFLAGS="-L native=$(dirname $PT)"
  cargo build --release --target x86_64-pc-windows-gnu --no-default-features
'
# → target/x86_64-pc-windows-gnu/release/voider-rs.exe
```

## Los cuatro obstáculos, y por qué ninguno era de egui

Vale dejarlo escrito porque la intuición dice "una app gráfica no cruza", y
resultó al revés: **eframe, egui-winit y egui_glow cruzaron sin tocar nada.**
Lo que costó fue todo lo de alrededor.

1. **Falta la std de Windows.** El `rustc` de nixpkgs sólo trae la del sistema
   anfitrión. Se resuelve con rustup (paso 1).

2. **`rust-fontconfig` no linkea.** Viene de `printpdf`, no de la interfaz. Por
   eso el PDF es una característica opcional: `--no-default-features` saca la
   exportación y el resto compila. En Linux sigue incluida.

3. **`std::os::unix` no existe en Windows.** Es el IPC entre instancias, sobre
   sockets de dominio Unix. En `ipc.rs` hay un stub inerte con la misma interfaz
   para `#[cfg(not(unix))]`. Consecuencia real: **en Windows dos ventanas sobre
   el mismo texto se pisan.** Habría que rehacerlo sobre named pipes.

4. **`cannot find -l:libpthread.a`.** Rust lo pide por ese nombre; mingw de
   nixpkgs no lo trae ahí. `pkgsCross.mingwW64.windows.pthreads` sí, y alcanza
   con ponerlo en el camino del enlazador.

## Lo que la versión Windows no tiene

- Exportar PDF (Ctrl+S en F4) — sacado para poder cruzar
- La voz (Ctrl+T) — necesita `piper` instalado en Windows
- Sincronización entre instancias — ver el punto 3

Y el void es otro: crea su propio `~/void` en la carpeta de usuario de Windows.
No ve el de esta máquina. Llevar el texto y reconciliarlo sigue siendo manual —
es el ítem "PORTABLE BACKUP" de `roadmap/pending.txt`, todavía abierto.
