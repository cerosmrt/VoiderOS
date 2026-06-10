# nix/modules/voider.nix
# VoiderOS desktop: greetd autologin → Hyprland → voider-shell → voider-py
{ config, pkgs, lib, ... }:

let
  voiderShell = pkgs.callPackage ../pkgs/voider-shell.nix { inherit pkgs lib; };
  voiderPy    = pkgs.callPackage ../pkgs/voider-py.nix    { inherit pkgs lib; };

  # Shared Python env — used by both voider-py and voider-proto
  voiderPython = pkgs.python3.withPackages (ps: with ps; [
    pyqt6 numpy pyaudio watchdog
  ]);

  # Voider ring cursor — white circle with black fill, matches the app logo
  voiderCursor = pkgs.stdenv.mkDerivation {
    name = "voider-cursor";
    src = pkgs.writeTextDir "dummy" "";
    buildInputs = [ pkgs.imagemagick pkgs.xorg.xcursorgen ];
    buildCommand = ''
      mkdir -p $out/share/icons/voider/cursors

      # White ring, black fill, transparent outside — 4 sizes
      for spec in "16 7 7 2" "24 11 11 2" "32 15 15 3" "48 23 23 4"; do
        read sz cx cy sw <<< "$spec"
        r=$((sz / 2 - 1))
        ${pkgs.imagemagick}/bin/magick \
          -size ''${sz}x''${sz} xc:transparent \
          -fill black -stroke white -strokewidth ''${sw} \
          -draw "circle ''${cx},''${cy} ''${cx},$((cy - r + sw))" \
          cursor''${sz}.png
        echo "''${sz} ''${cx} ''${cy} cursor''${sz}.png" >> cursor.cfg
      done

      ${pkgs.xorg.xcursorgen}/bin/xcursorgen cursor.cfg \
        $out/share/icons/voider/cursors/default

      # Symlink every common name so all apps pick it up
      cd $out/share/icons/voider/cursors
      for name in \
        left_ptr arrow top_left_arrow \
        pointer hand hand1 hand2 \
        text xterm ibeam \
        crosshair cross tcross \
        move fleur all-scroll \
        watch wait progress \
        not-allowed forbidden no-drop \
        ns-resize ew-resize \
        nw-resize ne-resize sw-resize se-resize \
        n-resize s-resize e-resize w-resize \
        col-resize row-resize \
        zoom-in zoom-out copy; do
        ln -sf default "$name"
      done

      cat > $out/share/icons/voider/index.theme <<'THEME'
[Icon Theme]
Name=voider
Comment=Voider ring cursor
THEME
    '';
  };

  # ── Monitor configuration: clock positions ────────────────────────────────────
  # Clock positions relative to primary monitor:
  #     12
  #  11    1
  # 9       3  
  #  10    2
  #     6
  # 
  # Change clockPosition below to move your external monitor:
  monitorConfig = {
    primary = {
      name = "eDP-1";              # laptop screen
      resolution = "1920x1080@120";
      position = "0x0";            # always center
    };
    secondary = {
      name = "HDMI-A-1";           # external monitor  
      resolution = "1920x1080@60"; 
      clockPosition = 9;           # ← CHANGE THIS: 9=left, 3=right, 12=top, 6=bottom
    };
  };

  # Calculate secondary monitor position based on clock position
  getMonitorPosition = clockPos: 
    let primaryWidth = 1920; primaryHeight = 1080; in
    if clockPos == 12 then "0x-${toString primaryHeight}"      # top
    else if clockPos == 3 then "${toString primaryWidth}x0"    # right  
    else if clockPos == 6 then "0x${toString primaryHeight}"   # bottom
    else if clockPos == 9 then "-${toString primaryWidth}x0"   # left
    else if clockPos == 1 then "${toString (primaryWidth / 2)}x-${toString (primaryHeight / 2)}"  # top-right
    else if clockPos == 2 then "${toString (primaryWidth / 2)}x-${toString primaryHeight}"        # bottom-right  
    else if clockPos == 10 then "-${toString (primaryWidth / 2)}x-${toString (primaryHeight / 2)}" # top-left
    else if clockPos == 11 then "-${toString (primaryWidth / 2)}x${toString primaryHeight}"       # bottom-left
    else "0x0"; # fallback

  # ── Screen effects: shared shader system ─────────────────────────────────────
  # All visual effects (CRT, grain, B&W) share one /tmp shader file that is
  # regenerated on each toggle. State lives in /tmp/voider-fx as shell vars.
  # Hyprland only supports one screen_shader at a time, so this is the only
  # sane approach for independently-toggleable effects.

  # voider-proto: dev sandbox — runs proto-voider/watch.py with auto-reload.
  # Edit any .py in proto-voider/, save, app restarts instantly.
  voiderProto = pkgs.writeShellScriptBin "proto-voider" ''
    cd /home/federico/VoiderOS/proto-voider
    export QT_QPA_PLATFORM=wayland
    export QT_PLUGIN_PATH=${pkgs.qt6.qtwayland}/lib/qt-6/plugins''${QT_PLUGIN_PATH:+:$QT_PLUGIN_PATH}
    export WAYLAND_DISPLAY=''${WAYLAND_DISPLAY:-wayland-1}
    exec ${voiderPython}/bin/python3 watch.py
  '';

  # voider-radio: plays random internet radio (jazz, ambient, classical)
  # First call starts playback, second call stops it.
  voiderRadio = pkgs.writeShellScriptBin "voider-radio" ''
    PIDFILE=/tmp/voider-radio.pid
    
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      # Radio is running, stop it
      kill "$(cat "$PIDFILE")" 2>/dev/null
      rm -f "$PIDFILE"
      exit 0
    fi
    
    # Radio is not running, start it
    STATIONS=(
      "http://audio-edge-es7t4.fra.h.radiomast.io/3c8e82f8-2aa4-4ce3-8e62-9b5b96b38021"  # Jazz FM
      "http://streamer-dtc-aa05.dtc.arn.net/ambient_low.mp3"                              # Ambient
      "http://stream.radioparadise.com/aac-320"                                           # Radio Paradise
      "http://radio.stereoscenic.com/asp-h"                                               # Ambient Sleeping Pill
      "http://uk2.internet-radio.com:8024/stream"                                         # Ambient Radio
      "https://classical-high.streamguys1.com/classical"                                  # WQED Classical
    )
    
    STATION_COUNT=''${#STATIONS[@]}
    RANDOM_INDEX=$((RANDOM % STATION_COUNT))
    STATION="''${STATIONS[$RANDOM_INDEX]}"
    
    # Start mpv in background with no UI
    ${pkgs.mpv}/bin/mpv --no-video --no-terminal --volume=30 "$STATION" &
    echo $! > "$PIDFILE"
  '';

  # ── File organiser ───────────────────────────────────────────────────────────
  # voider-sort [src]: moves every file in <src> (default ~/incoming) into
  # a ~/folder organised by extension. Text files go into ~/void (the vault).
  # The operation is idempotent: files with the same name AND size are skipped.

  sortScript = pkgs.writeText "voider-sort.py" ''
    import os, sys, shutil
    from pathlib import Path

    DEST = {
        "txt":"void", "md":"void", "rst":"void", "org":"void",
        "pdf":"documents", "epub":"documents", "mobi":"documents",
        "doc":"documents", "docx":"documents", "odt":"documents",
        "jpg":"images", "jpeg":"images", "png":"images", "gif":"images",
        "webp":"images", "bmp":"images", "svg":"images", "tiff":"images",
        "tif":"images", "heic":"images", "raw":"images", "cr2":"images",
        "mp3":"music", "flac":"music", "ogg":"music", "wav":"music",
        "aac":"music", "m4a":"music", "opus":"music", "wma":"music",
        "mp4":"videos", "mkv":"videos", "avi":"videos", "mov":"videos",
        "webm":"videos", "m4v":"videos", "flv":"videos",
        "py":"code", "js":"code", "ts":"code", "rs":"code",
        "c":"code", "cpp":"code", "h":"code", "go":"code",
        "rb":"code", "sh":"code", "lua":"code", "nix":"code",
        "zip":"archives", "tar":"archives", "gz":"archives",
        "7z":"archives", "rar":"archives", "bz2":"archives",
        "xz":"archives", "zst":"archives",
    }

    def sort_dir(src):
        home = Path.home()
        moved = skipped = 0
        for file in sorted(src.rglob("*")):
            if not file.is_file() or file.name.startswith("."):
                continue
            ext  = file.suffix.lstrip(".").lower()
            dest = home / DEST.get(ext, "other")
            dest.mkdir(parents=True, exist_ok=True)
            target = dest / file.name
            if target.exists():
                if target.stat().st_size == file.stat().st_size:
                    skipped += 1
                    continue
                stem, suf = file.stem, file.suffix
                n = 1
                while target.exists():
                    target = dest / f"{stem}_{n}{suf}"
                    n += 1
            shutil.move(str(file), str(target))
            print(f"  -> {dest.name}/{target.name}")
            moved += 1
        print(f"voider-sort: {moved} moved, {skipped} skipped ({src})")

    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "incoming"
    if not src.is_dir():
        print(f"voider-sort: not a directory: {src}")
        sys.exit(1)
    sort_dir(src)
  '';

  voiderSort = pkgs.writeShellScriptBin "voider-sort" ''
    exec ${pkgs.python3}/bin/python3 ${sortScript} "$@"
  '';

  # voider-usb-sort: called by the systemd path unit when /run/media/federico
  # changes (USB mounted). Sorts everything in all currently-mounted volumes.
  voiderUsbSort = pkgs.writeShellScriptBin "voider-usb-sort" ''
    for d in /run/media/federico/*/; do
      [ -d "$d" ] && voider-sort "$d"
    done
  '';

  # voider-inbox-watch: inotify loop; runs voider-sort whenever files land in
  # ~/incoming. Runs as a systemd user service so it restarts on failure.
  voiderInboxWatch = pkgs.writeShellScriptBin "voider-inbox-watch" ''
    mkdir -p "$HOME/incoming"
    ${pkgs.inotify-tools}/bin/inotifywait \
      -m -q -e close_write -e moved_to "$HOME/incoming" \
      --format '%f' |
    while IFS= read -r _f; do
      voider-sort "$HOME/incoming"
    done
  '';

  # voider-fx-update: reads /tmp/voider-fx (shell-sourceable key=value pairs),
  # bakes all active effect parameters as GLSL constants, writes a combined
  # shader to /tmp/voider-active.glsl, and loads it via hyprctl.
  # Called by voider-open-panel (via Python subprocess) on every param change.
  fxUpdate = pkgs.writeShellScriptBin "voider-fx-update" ''
    STATE=/tmp/voider-fx
    SHADER=/tmp/voider-active.glsl
    HYPRCTL=${pkgs.hyprland}/bin/hyprctl

    # Propagate HYPRLAND_INSTANCE_SIGNATURE if the caller didn't inherit it.
    # Hyprland 0.34+ places the socket under $XDG_RUNTIME_DIR/hypr/ (not /tmp/hypr/).
    if [ -z "$HYPRLAND_INSTANCE_SIGNATURE" ]; then
      _rt="''${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
      for _d in "$_rt/hypr/"*/; do
        [ -d "$_d" ] && HYPRLAND_INSTANCE_SIGNATURE=$(basename "$_d") && break
      done
      export HYPRLAND_INSTANCE_SIGNATURE
    fi

    # Defaults — must match fx_panel.py PARAM_DEFS defaults
    crt=1;  crt_intensity=0.6000;  crt_thickness=2;    crt_vignette=0.7000
    grain=1; grain_intensity=0.4000; grain_speed=5.0000; grain_size=fine
    bw=1;   bw_blend=1.0000;       bw_contrast=1.2000

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

  # voider-nav: navigation with hidden cursor
  # Usage: voider-nav <direction>  where direction = l|r|u|d
  voiderNav = pkgs.writeShellScriptBin "voider-nav" ''
    HYPRCTL=${pkgs.hyprland}/bin/hyprctl
    
    # Hide cursor
    $HYPRCTL setcursor "blank" 1 2>/dev/null || $HYPRCTL dispatch exec "sleep 0.1 && $HYPRCTL setcursor blank 1"
    
    # Move focus
    $HYPRCTL dispatch movefocus "$1"
    
    # Auto-show cursor after 3 seconds if no more nav
    (
      sleep 3
      if [ -f "/tmp/voider-nav-active" ]; then
        rm /tmp/voider-nav-active
        $HYPRCTL setcursor "voider" 32 2>/dev/null || true
      fi
    ) &
    
    # Mark navigation as active
    touch /tmp/voider-nav-active
  '';

  # voider-move: move windows with hidden cursor  
  voiderMove = pkgs.writeShellScriptBin "voider-move" ''
    HYPRCTL=${pkgs.hyprland}/bin/hyprctl
    
    # Hide cursor
    $HYPRCTL setcursor "blank" 1 2>/dev/null || true
    
    # Move window
    $HYPRCTL dispatch movewindow "$1"
    
    # Auto-show cursor after 2 seconds
    (
      sleep 2
      $HYPRCTL setcursor "Adwaita" 4 2>/dev/null || true
    ) &
  '';

  # voider-launch-split: launch app in splitscreen mode
  voiderLaunchSplit = pkgs.writeShellScriptBin "voider-launch-split" ''
    HYPRCTL=${pkgs.hyprland}/bin/hyprctl
    
    # Launch the application
    "$@" &
    
    # Wait a moment for window to appear
    sleep 0.5
    
    # Ensure splitscreen layout
    $HYPRCTL dispatch splitratio 0.5
    
    # Focus the new window
    $HYPRCTL dispatch focuscurrentorlast
  '';

  hyprlandConf = pkgs.writeText "hyprland.conf" ''
    # ── VoiderOS Hyprland config ─────────────────────────────────────────────
    # Hyprland is invisible infrastructure. Voider is what the user sees.

    monitor = ,preferred,auto,1
    monitor = ${monitorConfig.primary.name}, ${monitorConfig.primary.resolution}, ${monitorConfig.primary.position}, 1
    monitor = ${monitorConfig.secondary.name}, ${monitorConfig.secondary.resolution}, ${getMonitorPosition monitorConfig.secondary.clockPosition}, 1

    # ── Workspaces ────────────────────────────────────────────────────────────
    # Workspace 1 = laptop screen (main), workspace 2 = external HDMI
    workspace = 1, monitor:eDP-1, default:true
    workspace = 2, monitor:HDMI-A-1, default:true

    # ── Layout: split side-by-side ────────────────────────────────────────────
    general {
        layout = dwindle
        resize_on_border = true
    }
    
    dwindle {
        pseudotile = false
    }

    # ── Cursor: minimal dot ───────────────────────────────────────────────────
    cursor {
        no_hardware_cursors = false
        zoom_factor = 1.0
        zoom_rigid = false
        enable_hyprcursor = false
        hide_on_key_press = true
        hide_on_touch = false
    }
    
    env = XCURSOR_SIZE, 32
    env = XCURSOR_THEME, voider

    # Launch the layer-shell host (which spawns voider-py)
    # Log output to /tmp so we can diagnose failures
    exec-once = bash -c 'voider-shell > /tmp/voider-shell.log 2>&1'
    exec-once = ${pkgs.mako}/bin/mako
    # Apply default shaders (B&W on by default) as soon as Hyprland is ready
    exec-once = voider-fx-update
    # USB automount (connects to udisks2 over D-Bus)
    exec-once = ${pkgs.udiskie}/bin/udiskie --automount --no-notify

    # ── Voider window rules ───────────────────────────────────────────────────
    windowrulev2 = noborder,              class:voider-py
    windowrulev2 = noanim,               class:voider-py
    windowrulev2 = nofullscreenrequest,  class:voider-py
    windowrulev2 = suppressevent maximize, class:voider-py
    windowrulev2 = workspace 1,          class:voider-py

    # ── Force all apps to workspace 1 (tiles with voider) ────────────────────
    windowrulev2 = workspace 1, class:firefox
    windowrulev2 = workspace 1, class:kitty
    windowrulev2 = workspace 1, class:VSCodium

    # ── App window rules ──────────────────────────────────────────────────────
    # Default: TILED (side by side with voider)  
    # Super+F: toggles to FLOAT fullscreen (these rules apply when floating)
    
    windowrulev2 = size 100% 100%, floating:1, class:kitty
    windowrulev2 = move 0 0, floating:1, class:kitty
    windowrulev2 = center, floating:1, class:kitty
    
    windowrulev2 = size 100% 100%, floating:1, class:VSCodium  
    windowrulev2 = move 0 0, floating:1, class:VSCodium
    windowrulev2 = center, floating:1, class:VSCodium
    
    windowrulev2 = size 100% 100%, floating:1, class:firefox
    windowrulev2 = move 0 0, floating:1, class:firefox  
    windowrulev2 = center, floating:1, class:firefox

    # ── Launch apps ───────────────────────────────────────────────────────────
    bind = SUPER, T, exec, kitty
    bind = SUPER, V, exec, codium
    bind = SUPER, C, exec, kitty --title claude -e claude
    bind = SUPER, R, exec, voider-radio
    bind = SUPER, I, exec, kitty --working-directory ~/incoming
    bind = SUPER, B, exec, firefox
    bind = SUPER, A, exec, pavucontrol
    bind = SUPER, P, exec, kitty --title proto-voider -e proto-voider
    bind = SUPER, Q, killactive,
    bind = SUPER, F, togglefloating, active
    bind = SUPER, TAB, cyclenext,
    bind = SUPER, 1, workspace, 1
    bind = SUPER, 2, workspace, 2
    bind = SUPER SHIFT, 1, movetoworkspace, 1
    bind = SUPER SHIFT, 2, movetoworkspace, 2

    # ── Focus navigation (with hidden cursor) ────────────────────────────────
    bind = SUPER, left,  exec, voider-nav l
    bind = SUPER, right, exec, voider-nav r
    bind = SUPER, up,    exec, voider-nav u
    bind = SUPER, down,  exec, voider-nav d

    # ── Move windows (with hidden cursor) ─────────────────────────────────────
    bind = SUPER SHIFT, left,  exec, voider-move l
    bind = SUPER SHIFT, right, exec, voider-move r
    bind = SUPER SHIFT, up,    exec, voider-move u
    bind = SUPER SHIFT, down,  exec, voider-move d

    # ── Mouse: move/resize floating windows (Super + drag) ────────────────────
    bindm = SUPER, mouse:272, movewindow
    bindm = SUPER, mouse:273, resizewindow

    # ── Visual effect panels (Super+F5/F6/F7) ─────────────────────────────────
    bind = SUPER, F5, exec, voider-open-panel crt
    bind = SUPER, F6, exec, voider-open-panel grain
    bind = SUPER, F7, exec, voider-open-panel bw

    # ── Screenshot to clipboard ───────────────────────────────────────────────
    bind = SUPER, S, exec, grim - | wl-copy

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

    debug {
      damage_tracking = false
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

  # ── USB automount (udisks2 is the daemon; udiskie is the session client) ──────
  services.udisks2.enable = true;

  # Ensure /run/media/federico exists so the systemd path unit can watch it
  # before the first USB is ever inserted.
  systemd.tmpfiles.rules = [
    "d /run/media/federico 0755 federico users -"
  ];

  # ── Packages ──────────────────────────────────────────────────────────────────
  environment.systemPackages = [
    voiderShell
    voiderPy
    voiderProto
    voiderCursor
    fxUpdate
    fxOpenPanel
    voiderNav
    voiderMove
    voiderLaunchSplit
    voiderRadio
    voiderSort
    voiderUsbSort
    voiderInboxWatch
    pkgs.kitty
    pkgs.vscodium
    pkgs.claude-code
    pkgs.git
    pkgs.mpv
    pkgs.ffmpeg
    pkgs.udiskie
    pkgs.inotify-tools
    pkgs.wl-clipboard
    pkgs.mako
    pkgs.grim
    pkgs.slurp
    pkgs.xdg-utils
    pkgs.zathura
    pkgs.imv
    pkgs.pavucontrol
    pkgs.brightnessctl
    pkgs.btop
    pkgs.yt-dlp
    pkgs.hyprlock
    pkgs.grim
    pkgs.wl-clipboard
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
    "d %h/incoming         0755 - - -"
  ];

  # ── PipeWire configuration for speaker → mic routing ──────────────────────────
  systemd.user.services.voider-audio-route = {
    description = "Route speaker output to virtual microphone for voider";
    after = [ "pipewire.service" ];
    wants = [ "pipewire.service" ];
    wantedBy = [ "graphical-session.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      ExecStart = pkgs.writeShellScript "setup-audio-route" ''
        # Wait for PipeWire to be ready
        sleep 2
        
        # Create null sink for speaker monitoring
        ${pkgs.pipewire}/bin/pw-cli create-node adapter '{
          factory.name=support.null-audio-sink
          node.name="voider_speaker_monitor"
          node.description="VoiderOS Speaker Monitor"
          media.class=Audio/Sink
          audio.format=F32
          audio.rate=44100
          audio.channels=2
          audio.position=[FL FR]
        }' || true
        
        # Create virtual microphone from the monitor
        ${pkgs.pipewire}/bin/pw-cli create-node adapter '{
          factory.name=adapter
          node.name="voider_virtual_mic"  
          node.description="VoiderOS Virtual Microphone"
          media.class=Audio/Source
          audio.format=F32
          audio.rate=44100
          audio.channels=2
          audio.position=[FL FR]
          target.object="voider_speaker_monitor"
        }' || true
        
        # Link default sink monitor to our virtual mic
        sleep 1
        ${pkgs.pipewire}/bin/pw-link @DEFAULT_AUDIO_SINK@:monitor_FL voider_virtual_mic:input_FL || true
        ${pkgs.pipewire}/bin/pw-link @DEFAULT_AUDIO_SINK@:monitor_FR voider_virtual_mic:input_FR || true
      '';
    };
  };

  # ── Inbox watcher: auto-sorts ~/incoming when files land there ────────────────
  systemd.user.services.voider-inbox = {
    description = "VoiderOS ~/incoming auto-sort";
    after    = [ "graphical-session.target" ];
    wantedBy = [ "graphical-session.target" ];
    serviceConfig = {
      ExecStart = "${voiderInboxWatch}/bin/voider-inbox-watch";
      Restart    = "on-failure";
      RestartSec = "5";
    };
  };

  # ── USB watcher: sort file when a USB is mounted ──────────────────────────────
  systemd.user.paths.voider-usb = {
    description = "Watch for USB mounts under /run/media/federico";
    pathConfig.PathChanged = "/run/media/federico";
    wantedBy = [ "default.target" ];
  };

  systemd.user.services.voider-usb = {
    description = "Sort files from newly mounted USB";
    serviceConfig = {
      Type      = "oneshot";
      ExecStart = "${voiderUsbSort}/bin/voider-usb-sort";
    };
  };

  # ── Security: polkit for privileged operations ───────────────────────────────
  security.polkit.enable = true;
}
