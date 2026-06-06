# nix/modules/voider.nix
# VoiderOS desktop: greetd autologin → Hyprland → voider-shell → voider-py
{ config, pkgs, lib, ... }:

let
  voiderShell = pkgs.callPackage ../pkgs/voider-shell.nix { inherit pkgs lib; };
  voiderPy    = pkgs.callPackage ../pkgs/voider-py.nix    { inherit pkgs lib; };

  hyprlandConf = pkgs.writeText "hyprland.conf" ''
    # ── VoiderOS Hyprland config ─────────────────────────────────────────────
    # Hyprland is invisible infrastructure. Voider is what the user sees.

    monitor = ,preferred,auto,1

    # Launch the layer-shell host (which spawns voider-py)
    exec-once = voider-shell

    # ── Voider window rules ───────────────────────────────────────────────────
    windowrulev2 = fullscreen,          class:voider-py
    windowrulev2 = noborder,            class:voider-py
    windowrulev2 = noanim,              class:voider-py
    windowrulev2 = nofullscreenrequest, class:voider-py
    windowrulev2 = suppressevent maximize, class:voider-py

    # ── Open apps on top with Super shortcuts ─────────────────────────────────
    bind = SUPER, T, exec, kitty
    bind = SUPER, Q, killactive,

    # ── Compositor settings ───────────────────────────────────────────────────
    general {
      border_size = 0
      gaps_in     = 0
      gaps_out    = 0
    }

    animations {
      enabled = no
    }

    misc {
      disable_hyprland_logo  = true
      disable_splash_rendering = true
    }

    # ── Input ─────────────────────────────────────────────────────────────────
    input {
      kb_layout = gb
    }
  '';
in
{
  # ── Hyprland ─────────────────────────────────────────────────────────────────
  programs.hyprland = {
    enable = true;
    xwayland.enable = false;
  };

  # ── Autologin: greetd → Hyprland (no login UI) ───────────────────────────────
  services.greetd = {
    enable = true;
    settings.default_session = {
      command = "${pkgs.hyprland}/bin/Hyprland --config ${hyprlandConf}";
      user    = "federico";
    };
  };

  # ── Packages ──────────────────────────────────────────────────────────────────
  environment.systemPackages = [
    voiderShell
    voiderPy
    pkgs.kitty
  ];

  # ── Wayland / environment ─────────────────────────────────────────────────────
  environment.sessionVariables = {
    XDG_SESSION_TYPE    = "wayland";
    XDG_CURRENT_DESKTOP = "Hyprland";
    QT_QPA_PLATFORM     = "wayland";
    MOZ_ENABLE_WAYLAND  = "1";
    NIXOS_OZONE_WL      = "1";
    VOIDER_CMD          = "voider-py";
  };

  # ── Void directory created on first boot ──────────────────────────────────────
  systemd.user.tmpfiles.rules = [
    "d %h/void             0755 - - -"
    "d %h/.config/voideros 0755 - - -"
  ];

  # ── Security: polkit for privileged operations ───────────────────────────────
  security.polkit.enable = true;
}
