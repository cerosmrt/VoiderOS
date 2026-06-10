# VoiderOS Test Suite & Documentation

## Current System State Tests

### Audio System
- [ ] `systemctl --user status pipewire` → should be ACTIVE
- [ ] `systemctl --user status wireplumber` → should be ACTIVE  
- [ ] Super+A → opens pavucontrol without "connecting to pulseaudio" error
- [ ] Audio devices visible in pavucontrol

### Window Management
- [ ] Super+T (kitty) → opens TILED beside voider (not floating)
- [ ] Super+B (firefox) → opens TILED beside voider (not floating)
- [ ] Super+V (vscodium) → opens TILED beside voider (not floating)
- [ ] Focus on firefox, Super+F → toggles firefox to FULLSCREEN float
- [ ] Super+F again → toggles firefox back to TILED
- [ ] Super+Q → kills focused window

### Cursor & Navigation
- [ ] Cursor is DOT theme (not default Hyprland arrow)
- [ ] Cursor size appropriate (not huge)
- [ ] Super+arrows → hides cursor, changes focus
- [ ] Moving mouse → shows cursor again
- [ ] Super+Shift+arrows → moves windows with hidden cursor

### Monitor Setup
- [ ] External monitor (HDMI-A-1) positioned LEFT of laptop (position 9 o'clock)
- [ ] Mouse moves left to reach external monitor
- [ ] Both monitors working with correct resolution

### Visual Effects
- [ ] Screen has B&W + grain + CRT effects applied globally
- [ ] Effects apply to ALL windows (firefox, kitty, voider)
- [ ] Super+F5/F6/F7 → open effect panels

### Voider Application
- [ ] Voider circle size NORMAL (not zoomed/huge)
- [ ] Voider responds to keyboard input
- [ ] F1/F2/F3/F4/F5/F6 → different voider views work
- [ ] Text input works in voider

## Known Issues to Fix
1. **Cursor reverted to Hyprland default** (should be dot theme)
2. **Voider circle appears zoomed/large** 
3. **Display scaling seems wrong** (cursor large on both monitors)

## Configuration Files
- `/home/federico/VoiderOS/nix/modules/voider.nix` → Hyprland config + window rules
- `/home/federico/VoiderOS/nix/system.nix` → PipeWire + system services
- `/home/federico/VoiderOS/pkgs/voider-py/` → Voider application code

## Test Commands
```bash
# Check services
systemctl --user status pipewire pipewire-pulse wireplumber

# Check Hyprland config
export HYPRLAND_INSTANCE_SIGNATURE=$(ls /run/user/1000/hypr/ | tail -1)
hyprctl monitors  # Check monitor setup
hyprctl binds | grep -i super  # Check keybinds

# Test audio
pavucontrol  # Should open without errors

# Test cursor theme
echo $XCURSOR_THEME $XCURSOR_SIZE  # Should show dot theme

# Check voider logs
tail -f /tmp/voider-shell.log
tail -f /tmp/voider-py.log
```

## How to Test Changes
1. Make configuration change
2. Run `hyprctl reload` (for Hyprland changes) or rebuild (for system changes)
3. Run through checklist above
4. If anything breaks, document what changed
5. Commit only when ALL tests pass

## Documentation of Current Keybinds

### System Apps
- Super+T → kitty terminal (tiled)
- Super+B → firefox browser (tiled) 
- Super+V → vscodium editor (tiled)
- Super+C → claude code terminal (tiled)
- Super+A → pavucontrol audio mixer (tiled)
- Super+R → voider-radio background music
- Super+I → terminal in ~/incoming directory

### Window Management
- Super+F → toggle focused window float/tiled
- Super+Q → kill focused window
- Super+Tab → cycle between windows

### Navigation
- Super+arrows → focus navigation (hides cursor)
- Super+Shift+arrows → move windows (hides cursor)
- Mouse movement → shows cursor again

### Voider Views
- F1 → Write mode (center entry, active file)
- F2 → Circular doc (edit/reorder lines)
- F3 → Book browser (manage chapters)  
- F4 → Vault browser (shuffled vault lines)
- F5 → Oracle (one random vault line)
- F6 → Metronome (BPM pulses)
- F8 → Help overlay

### Visual Effects
- Super+F5 → CRT scanlines panel
- Super+F6 → Film grain panel  
- Super+F7 → Black & white panel

### Recording (if working)
- Ctrl+M → toggle mic recording
- Ctrl+K → toggle camera recording

## Expected Behavior Summary
1. **Boot**: Voider starts fullscreen with normal-sized circle
2. **Apps**: Launch tiled beside voider, focus on new app
3. **Toggle**: Super+F makes focused app fullscreen float, Super+F again returns to tiled
4. **Audio**: Works without connection errors
5. **Cursor**: Small dot that hides during keyboard nav
6. **Monitors**: External monitor correctly positioned left
7. **Effects**: Global B&W+grain+CRT on everything