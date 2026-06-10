#!/bin/bash

echo "=== VoiderOS Test Suite ==="

# Audio
echo "Audio:"
systemctl --user is-active pipewire && echo "  ✓ PipeWire" || echo "  ✗ PipeWire"
systemctl --user is-active wireplumber && echo "  ✓ WirePlumber" || echo "  ✗ WirePlumber"

# Window Management
echo "Window Management:"
hyprctl binds | grep -q "SUPER.*B.*firefox" && echo "  ✓ Super+B firefox" || echo "  ✗ Super+B firefox"
hyprctl binds | grep -q "SUPER.*F.*togglefloating" && echo "  ✓ Super+F toggle" || echo "  ✗ Super+F toggle"
hyprctl binds | grep -q "SUPER.*T.*kitty" && echo "  ✓ Super+T kitty" || echo "  ✗ Super+T kitty"

# Cursor
echo "Cursor:"
[ "$XCURSOR_THEME" = "dot" ] && echo "  ✓ Theme=dot" || echo "  ✗ Theme=$XCURSOR_THEME"
[ "$XCURSOR_SIZE" = "12" ] && echo "  ✓ Size=12" || echo "  ✗ Size=$XCURSOR_SIZE"

# Scripts
echo "Scripts:"
which voider-nav >/dev/null && echo "  ✓ voider-nav" || echo "  ✗ voider-nav"
which voider-fx-update >/dev/null && echo "  ✓ voider-fx-update" || echo "  ✗ voider-fx-update"

# Apps
echo "Apps:"
which firefox >/dev/null && echo "  ✓ firefox" || echo "  ✗ firefox"
which kitty >/dev/null && echo "  ✓ kitty" || echo "  ✗ kitty"

echo "=== Done ==="