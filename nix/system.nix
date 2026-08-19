# nix/system.nix — base system settings (extracted from /etc/nixos/configuration.nix)
{ config, pkgs, lib, ... }:

{
  boot.loader.systemd-boot.enable   = true;
  boot.loader.efi.canTouchEfiVariables = true;

  # ── Arranque en silencio: pantalla negra hasta que aparece Voider ────────────
  # VoiderOS no tiene panel ni escritorio; tampoco debería tener un arranque que
  # se vea. Sin esto systemd escribe sus [ OK ] verdes sobre el negro, y lo
  # primero que ve el usuario no es el void sino un log.
  #
  # El menú del bootloader NO se pierde: con timeout 0 no aparece solo, pero
  # systemd-boot lo abre igual si mantenés ESPACIO durante el arranque. Esa es la
  # salida de emergencia para elegir una generación anterior.
  # mkDefault: en una máquina instalada el menú no aparece (VoiderOS arranca a
  # negro), pero la ISO live sí quiere mostrarlo — ahí conviene poder elegir.
  # Sin esto, la preferencia de una máquina instalada rompía la ISO.
  boot.loader.timeout = lib.mkDefault 0;

  # Esto ya agrega "loglevel=0" a los parámetros del kernel, así que no hace
  # falta ponerlo a mano abajo (iría antes y perdería igual).
  boot.consoleLogLevel = 0;      # los mensajes del kernel al framebuffer
  boot.initrd.verbose  = false;  # el initrd, que es lo primero que habla

  boot.kernelParams = [
    "quiet"                         # el kernel se calla
    "udev.log_priority=3"           # udev deja de narrar cada dispositivo
    "rd.udev.log_level=3"           # lo mismo, dentro del initrd
    "rd.systemd.show_status=false"  # los [ OK ] del initrd
    "systemd.show_status=false"     # los [ OK ] verdes del sistema
    "vt.global_cursor_default=0"    # ni el cursor titilando sobre el negro
  ];

  networking.hostName           = "nixos";
  networking.networkmanager.enable = true;

  time.timeZone = "America/Argentina/Buenos_Aires";

  i18n.defaultLocale = "en_US.UTF-8";
  i18n.extraLocaleSettings = {
    LC_ADDRESS        = "es_AR.UTF-8";
    LC_IDENTIFICATION = "es_AR.UTF-8";
    LC_MEASUREMENT    = "es_AR.UTF-8";
    LC_MONETARY       = "es_AR.UTF-8";
    LC_NAME           = "es_AR.UTF-8";
    LC_NUMERIC        = "es_AR.UTF-8";
    LC_PAPER          = "es_AR.UTF-8";
    LC_TELEPHONE      = "es_AR.UTF-8";
    LC_TIME           = "es_AR.UTF-8";
  };

  services.xserver.xkb = { layout = "gb"; variant = ""; };
  console.keyMap = "uk";

  users.users.federico = {
    isNormalUser  = true;
    description   = "Federico";
    extraGroups   = [ "networkmanager" "wheel" "video" "audio" ];
    packages      = with pkgs; [ git curl nodejs kitty firefox vscodium ntfs3g ladspaPlugins ];
  };

  nixpkgs.config.allowUnfree = true;

  system.stateVersion = "25.05";

  # Required for flake-based rebuilds (nixos-rebuild switch --flake .#voider)
  nix.settings.experimental-features = [ "nix-command" "flakes" ];

  programs.nix-ld.enable  = true;
  services.openssh.enable = true;

  # NVIDIA
  services.xserver.videoDrivers = [ "nvidia" ];
  hardware.nvidia = {
    modesetting.enable = true;
    open               = false;
    nvidiaSettings     = true;
    powerManagement.enable = true;   # preserve VRAM across suspend (fixes HDMI black on resume)
  };
  hardware.graphics.enable = true;

  # PipeWire
  services.pipewire = {
    enable      = true;
    alsa.enable = true;
    pulse.enable = true;
    jack.enable  = true;
    wireplumber.enable = true;
  };
  hardware.pulseaudio.enable = false;
  
  # Auto-start PipeWire user services  
  systemd.user.services.pipewire.wantedBy = [ "default.target" ];
  systemd.user.services.pipewire-pulse.wantedBy = [ "default.target" ];
  systemd.user.services.wireplumber.wantedBy = [ "default.target" ];
  
  # Ensure D-Bus is available for audio services
  services.dbus.enable = true;
  security.rtkit.enable      = true;
  # El disco de datos NTFS NO vive acá: es de una máquina concreta, no de
  # VoiderOS. Estaba en la base con un UUID fijo y sin nofail, así que en
  # cualquier otra computadora systemd esperaba un dispositivo inexistente y el
  # arranque se colgaba. Ahora lo declara el perfil de la máquina que lo tiene
  # (ver nix/profiles/tuf-data.nix, que importa el target `voider`).

  systemd.services."ModemManager".enable = false;
  powerManagement.cpuFreqGovernor = "performance";
}
