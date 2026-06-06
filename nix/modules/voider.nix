# nix/modules/voider.nix
# VoiderOS: autologin → sway → voider (layer-shell background)
# No display manager UI. No desktop environment. Voider IS the shell.
{ config, pkgs, lib, ... }:

let
  voider = pkgs.callPackage ../pkgs/voider.nix { inherit pkgs lib; };

  swayConfig = pkgs.writeText "sway-config" ''
    # ── VoiderOS sway config ─────────────────────────────────────────────────
    # Sway is a transparent substrate. Voider owns the screen.

    output * bg #000000 solid_color

    # No chrome on any window
    default_border           none
    default_floating_border  none
    hide_edge_borders        both
    gaps inner 0
    gaps outer 0
    # Cursor: hidden after 3 seconds of inactivity
    seat seat0 hide_cursor 3000
    seat seat0 xcursor_theme default 1

    # Keyboard layout (matches system.nix)
    input type:keyboard {
      xkb_layout gb
    }

    # Launch Voider as the background layer
    exec ${voider}/bin/voider

    # Emergency terminal (SUPER+Q)
    bindsym Mod4+q exec ${pkgs.kitty}/bin/kitty

    # Kill focused window (SUPER+W)
    bindsym Mod4+w kill

    # All other keybindings are handled by Voider itself via layer-shell keyboard interactivity
  '';

in
{
  # ── Sway ─────────────────────────────────────────────────────────────────────
  programs.sway = {
    enable      = true;
    wrapperFeatures.gtk = false;
    extraPackages  = [];  # no default sway packages (foot, dmenu, etc.)
    extraSessionCommands = ''
      export XDG_SESSION_TYPE=wayland
      export XDG_CURRENT_DESKTOP=sway
    '';
  };

  # ── Autologin: greetd → sway (no login UI, no password prompt) ───────────────
  services.greetd = {
    enable = true;
    settings.default_session = {
      command = "${pkgs.sway}/bin/sway --config ${swayConfig}";
      user    = "federico";
    };
  };

  # ── Voider + tools ────────────────────────────────────────────────────────────
  environment.systemPackages = [
    voider
    pkgs.kitty       # emergency terminal
    pkgs.pamixer     # volume queries (status overlay)
    pkgs.playerctl   # media info (status overlay)
  ];

  # ── Fonts ─────────────────────────────────────────────────────────────────────
  fonts.packages = with pkgs; [ jetbrains-mono ];

  # ── Wayland / environment ─────────────────────────────────────────────────────
  environment.sessionVariables = {
    XDG_SESSION_TYPE      = "wayland";
    XDG_CURRENT_DESKTOP   = "sway";
    MOZ_ENABLE_WAYLAND    = "1";   # firefox uses Wayland natively
    NIXOS_OZONE_WL        = "1";   # electron apps use Wayland
    WLR_NO_HARDWARE_CURSORS = "1"; # NVIDIA: disable hardware cursor
  };

  # ── Void directory created on first boot ─────────────────────────────────────
  systemd.user.tmpfiles.rules = [
    "d %h/void            0755 - - -"
    "d %h/.config/voideros 0755 - - -"
  ];

  # ── Security: polkit for privileged operations ───────────────────────────────
  security.polkit.enable = true;
}
