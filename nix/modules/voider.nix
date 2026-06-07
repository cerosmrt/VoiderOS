# nix/modules/voider.nix
# VoiderOS desktop: greetd autologin → Hyprland → voider-shell → voider-py
{ config, pkgs, lib, ... }:

let
  voiderShell = pkgs.callPackage ../pkgs/voider-shell.nix { inherit pkgs lib; };
  voiderPy    = pkgs.callPackage ../pkgs/voider-py.nix    { inherit pkgs lib; };

  # ── Screen effects: shared shader system ─────────────────────────────────────
  # All visual effects (CRT, grain, B&W) share one /tmp shader file that is
  # regenerated on each toggle. State lives in /tmp/voider-fx as shell vars.
  # Hyprland only supports one screen_shader at a time, so this is the only
  # sane approach for independently-toggleable effects.

  # voider-fx-update: reads /tmp/voider-fx (shell-sourceable key=value pairs),
  # bakes all active effect parameters as GLSL constants, writes a combined
  # shader to /tmp/voider-active.glsl, and loads it via hyprctl.
  # Called by voider-open-panel (via Python subprocess) on every param change.
  fxUpdate = pkgs.writeShellScriptBin "voider-fx-update" ''
    STATE=/tmp/voider-fx
    SHADER=/tmp/voider-active.glsl
    HYPRCTL=${pkgs.hyprland}/bin/hyprctl

    # Propagate HYPRLAND_INSTANCE_SIGNATURE if the caller didn't inherit it
    if [ -z "$HYPRLAND_INSTANCE_SIGNATURE" ]; then
      for _d in /tmp/hypr/*/; do
        [ -d "$_d" ] && HYPRLAND_INSTANCE_SIGNATURE=$(basename "$_d") && break
      done
      export HYPRLAND_INSTANCE_SIGNATURE
    fi

    # Defaults — must match fx_panel.py PARAM_DEFS defaults
    crt=0;  crt_intensity=0.3000;  crt_thickness=2;    crt_vignette=0.7000
    grain=0; grain_intensity=0.2000; grain_speed=5.0000; grain_size=fine
    bw=0;   bw_blend=0.0000;       bw_contrast=1.0000

    [ -f "$STATE" ] && . "$STATE"

    if [ "$crt" = 0 ] && [ "$grain" = 0 ] && [ "$bw" = 0 ]; then
      "$HYPRCTL" keyword decoration:screen_shader "[[EMPTY]]"
      exit 0
    fi

    {
      printf 'precision highp float;\n'
      printf 'varying vec2 v_texcoord;\n'
      printf 'uniform sampler2D tex;\n'
      [ "$grain" = 1 ] && printf 'uniform float time;\n'
      printf '\n'

      # ── CRT constants ────────────────────────────────────────────────────────
      if [ "$crt" = 1 ]; then
        printf 'const float crt_intensity = %s;\n' "$crt_intensity"
        printf 'const int   crt_thickness = %s;\n' "$crt_thickness"
        printf 'const float crt_vignette  = %s;\n' "$crt_vignette"
        printf '\n'
      fi

      # ── Grain constants + hash helper ────────────────────────────────────────
      if [ "$grain" = 1 ]; then
        printf 'const float grain_intensity = %s;\n' "$grain_intensity"
        printf 'const float grain_speed     = %s;\n' "$grain_speed"
        case "$grain_size" in
          fine)   printf 'const float grain_scale = 1.00;\n' ;;
          medium) printf 'const float grain_scale = 0.50;\n' ;;
          coarse) printf 'const float grain_scale = 0.25;\n' ;;
          *)      printf 'const float grain_scale = 1.00;\n' ;;
        esac
        printf '\n'
        printf 'float hash(vec2 p) {\n'
        printf '    p = fract(p * vec2(443.897, 441.423));\n'
        printf '    p += dot(p, p.yx + 19.19);\n'
        printf '    return fract((p.x + p.y) * p.x);\n'
        printf '}\n\n'
      fi

      # ── B&W constants ────────────────────────────────────────────────────────
      if [ "$bw" = 1 ]; then
        printf 'const float bw_blend    = %s;\n' "$bw_blend"
        printf 'const float bw_contrast = %s;\n' "$bw_contrast"
        printf '\n'
      fi

      printf 'void main() {\n'
      printf '    vec4 color = texture2D(tex, v_texcoord);\n'

      if [ "$crt" = 1 ]; then
        printf '    float t    = float(crt_thickness);\n'
        printf '    float line = step(t, mod(floor(gl_FragCoord.y), 2.0 * t));\n'
        printf '    float dark = 1.0 - 0.18 * crt_intensity;\n'
        printf '    color.rgb *= mix(dark, 1.0, line);\n'
        printf '    vec2 vigUv = v_texcoord - 0.5;\n'
        printf '    float vig  = 1.0 - dot(vigUv, vigUv) * crt_vignette * 2.8;\n'
        printf '    color.rgb *= clamp(vig, 0.0, 1.0);\n'
      fi

      if [ "$grain" = 1 ]; then
        printf '    vec2  suv = v_texcoord * grain_scale;\n'
        printf '    float g   = hash(suv + vec2(fract(time * grain_speed * 0.37),\n'
        printf '                                fract(time * grain_speed * 0.19)));\n'
        printf '    color.rgb += (g - 0.5) * 0.26 * grain_intensity;\n'
      fi

      if [ "$bw" = 1 ]; then
        printf '    float gray = dot(color.rgb, vec3(0.299, 0.587, 0.114));\n'
        printf '    vec3  bw   = vec3(clamp((gray - 0.5) * bw_contrast + 0.5, 0.0, 1.0));\n'
        printf '    color.rgb  = mix(color.rgb, bw, bw_blend);\n'
      fi

      printf '    color.rgb = clamp(color.rgb, 0.0, 1.0);\n'
      printf '    gl_FragColor = color;\n'
      printf '}\n'
    } > "$SHADER"

    "$HYPRCTL" keyword decoration:screen_shader "$SHADER"
  '';

  # Single entry-point called by Hyprland keybinds: writes the effect name to
  # /tmp/voider-fx-panel. Voider polls this file every 100ms and opens or
  # closes the corresponding parameter panel.
  fxOpenPanel = pkgs.writeShellScriptBin "voider-open-panel" ''
    printf '%s' "$1" > /tmp/voider-fx-panel
  '';

  hyprlandConf = pkgs.writeText "hyprland.conf" ''
    # ── VoiderOS Hyprland config ─────────────────────────────────────────────
    # Hyprland is invisible infrastructure. Voider is what the user sees.

    monitor = ,preferred,auto,1

    # Launch the layer-shell host (which spawns voider-py)
    # Log output to /tmp so we can diagnose failures
    exec-once = bash -c 'voider-shell > /tmp/voider-shell.log 2>&1'

    # ── Voider window rules ───────────────────────────────────────────────────
    # voider-py tiles normally (fills workspace as sole tiled window).
    # nofullscreenrequest blocks the Qt showFullScreen() call so Hyprland
    # keeps it tiled rather than exclusive-fullscreen. Floating windows
    # (kitty, codium) are rendered above tiled windows by Hyprland.
    windowrulev2 = noborder,            class:voider-py
    windowrulev2 = noanim,              class:voider-py
    windowrulev2 = nofullscreenrequest, class:voider-py
    windowrulev2 = suppressevent maximize, class:voider-py

    # ── Apps that open on top of voider ──────────────────────────────────────
    windowrulev2 = float, class:kitty
    windowrulev2 = float, class:VSCodium

    # ── Open apps on top with Super shortcuts ─────────────────────────────────
    bind = SUPER, T, exec, kitty
    bind = SUPER, V, exec, codium
    bind = SUPER, C, exec, kitty --title claude -e claude
    bind = SUPER, Q, killactive,

    # ── Visual effect panels (Super+F5/F6/F7) ─────────────────────────────────
    bind = SUPER, F5, exec, voider-open-panel crt
    bind = SUPER, F6, exec, voider-open-panel grain
    bind = SUPER, F7, exec, voider-open-panel bw

    # ── Compositor settings ───────────────────────────────────────────────────
    general {
      border_size = 0
      gaps_in     = 0
      gaps_out    = 0
    }

    animations {
      enabled = no
    }

    decoration {
      rounding = 0

      shadow {
        enabled      = true
        range        = 30
        render_power = 3
        color        = rgba(00000099)
      }
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
    fxUpdate
    fxOpenPanel
    pkgs.kitty
    pkgs.vscodium
    pkgs.claude-code
    pkgs.git
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
