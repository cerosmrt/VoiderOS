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
    extraConfig.pipewire."91-bitcrush" = {
      "context.modules" = [{
        name = "libpipewire-module-filter-chain";
        args = {
          "node.description" = "Bitcrusher";
          "filter.graph" = {
            nodes = [{
              type    = "ladspa";
              name    = "bitcrush";
              plugin  = "${pkgs.ladspaPlugins}/lib/ladspa/bitcrush_1413.so";
              label   = "bitcrush";
              control = { "Bit depth" = 6; "Sample rate decimation" = 3; };
            }];
          };
          "capture.props" = {
            "node.name"          = "effect_input.bitcrush";
            "media.class"        = "Audio/Sink";
            "priority.session"   = 1000;
            "node.default-sink"  = true;
          };
          "playback.props" = {
            "node.name"    = "effect_output.bitcrush";
            "node.passive" = true;
          };
        };
      }];
    };
  };
  hardware.pulseaudio.enable = false;
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
