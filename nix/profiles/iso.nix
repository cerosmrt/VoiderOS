# nix/profiles/iso.nix — VoiderOS como producto: la ISO booteable.
#
# Es el perfil que NO conoce esta máquina. Sin hardware-configuration.nix (la
# ISO arranca en hardware que no vio nunca), sin el usuario federico, sin
# /mnt/data, sin el checkout del repositorio y sin corpus personal.
#
# El void nace vacío: es una máquina de escribir nueva, no una copia del libro
# de nadie.
#
# Arranca con Rust: voider-rs empaquetado desde el fuente (nix/pkgs/voider-rs.nix),
# no el Python. Un binario contra los ~150 MB de intérprete + PyQt6 que arrastra
# el otro, que en una ISO se nota.
{ config, pkgs, lib, modulesPath, voiderRs, ... }:

{
  imports = [
    # Trae kernel genérico, detección de hardware, y el arranque híbrido
    # UEFI/BIOS. Es lo que hace que la misma ISO sirva en varias PCs.
    "${modulesPath}/installer/cd-dvd/installation-cd-minimal.nix"
  ];

  isoImage.isoName = lib.mkForce "VoiderOS.iso";
  isoImage.volumeID = lib.mkForce "VOIDEROS";
  # El instalador de NixOS y su documentación no pintan nada en una máquina de
  # escribir; sacarlos también achica la imagen.
  isoImage.includeSystemBuildDependencies = false;

  # ── El usuario ──────────────────────────────────────────────────────────────
  # Fijo, sin contraseña: la ISO es live y arranca directo en Voider. No hay
  # login que pasar porque no hay nada que proteger todavía.
  users.users.voider = {
    isNormalUser = true;
    description  = "Voider";
    extraGroups  = [ "wheel" "video" "audio" "input" ];
    password     = "";
  };
  users.users.root.password = lib.mkForce "";
  services.getty.autologinUser = lib.mkForce null;

  # ── La sesión ───────────────────────────────────────────────────────────────
  # greetd entra solo como `voider` y lanza Hyprland, que hospeda a voider-rs.
  # Hyprland sigue siendo infraestructura invisible: el usuario ve Voider.
  services.greetd.settings.default_session = lib.mkForce {
    command = "${pkgs.hyprland}/bin/Hyprland --config ${config.environment.etc."voider/hyprland-iso.conf".source}";
    user    = "voider";
  };

  # Config mínima de Hyprland para la ISO: sin atajos de desarrollo, sin
  # monitores nombrados a mano (la ISO no sabe qué pantallas hay), y con Voider
  # arrancando como único cliente.
  environment.etc."voider/hyprland-iso.conf".text = ''
    monitor = ,preferred,auto,1

    general {
      border_size = 0
      gaps_in = 0
      gaps_out = 0
    }
    decoration { rounding = 0 }
    animations { enabled = false }
    misc {
      disable_hyprland_logo = true
      disable_splash_rendering = true
      force_default_wallpaper = 0
    }

    # Voider ES el escritorio.
    exec-once = ${voiderRs}/bin/voider-rs

    # Lo mínimo para no quedar encerrado sin poder salir.
    bind = SUPER, Q, killactive,
    bind = SUPER SHIFT, E, exit,
    bind = SUPER, T, exec, ${pkgs.kitty}/bin/kitty
  '';

  environment.systemPackages = [ voiderRs pkgs.kitty ];

  # ── El void ─────────────────────────────────────────────────────────────────
  # Vacío. voider-rs lo crea solo en ~/void la primera vez que escribís.
  # Nada de /mnt/data ni de corpus: el void es personal y no viaja en una ISO.

  # Sin disco propio, el estado vive en RAM mientras dure la sesión live.
  # Es a propósito: esta ISO es para probar, y todavía no instala nada.
  networking.hostName = lib.mkForce "voideros";
  networking.wireless.enable = lib.mkForce false;
  networking.networkmanager.enable = lib.mkForce true;
}
