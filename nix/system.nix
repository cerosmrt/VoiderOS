# nix/system.nix — base system settings (extracted from /etc/nixos/configuration.nix)
{ config, pkgs, lib, ... }:

{
  boot.loader.systemd-boot.enable   = true;
  boot.loader.efi.canTouchEfiVariables = true;

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

  # NTFS data disk
  fileSystems."/mnt/data" = {
    device  = "/dev/disk/by-uuid/F29420EE9420B6CF";
    fsType  = "ntfs3";
    options = [ "uid=1000" "gid=1000" "umask=0022" ];
  };

  systemd.services."ModemManager".enable = false;
  powerManagement.cpuFreqGovernor = "performance";
}
