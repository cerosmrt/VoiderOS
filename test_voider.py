#!/usr/bin/env python3

import subprocess
import os
import sys
from pathlib import Path

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

class VoiderTest:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        
    def test(self, name: str, condition: bool):
        if condition:
            print(f"{Colors.GREEN}✓{Colors.END} {name}")
            self.passed += 1
        else:
            print(f"{Colors.RED}✗{Colors.END} {name}")
            self.failed += 1
            
    def run_cmd(self, cmd: str) -> tuple[int, str]:
        """Run command and return (exit_code, output)"""
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return result.returncode, result.stdout.strip()
        except Exception:
            return 1, ""
            
    def service_active(self, service: str) -> bool:
        code, _ = self.run_cmd(f"systemctl --user is-active {service}")
        return code == 0
        
    def command_exists(self, cmd: str) -> bool:
        code, _ = self.run_cmd(f"which {cmd}")
        return code == 0
        
    def keybind_exists(self, pattern: str) -> bool:
        code, output = self.run_cmd("hyprctl binds")
        return code == 0 and pattern in output
        
    def env_var_equals(self, var: str, value: str) -> bool:
        return os.environ.get(var) == value
        
    def file_exists(self, path: str) -> bool:
        return Path(path).exists()
        
    def run_all_tests(self):
        print(f"{Colors.BLUE}=== VoiderOS Test Suite ==={Colors.END}\n")
        
        # Audio System
        print(f"{Colors.YELLOW}Audio System:{Colors.END}")
        self.test("PipeWire service active", self.service_active("pipewire"))
        self.test("WirePlumber service active", self.service_active("wireplumber"))
        print()
        
        # Window Management
        print(f"{Colors.YELLOW}Window Management:{Colors.END}")
        self.test("Super+B → firefox bind", self.keybind_exists("SUPER, B, exec, firefox"))
        self.test("Super+F → togglefloating bind", self.keybind_exists("SUPER, F, togglefloating"))
        self.test("Super+T → kitty bind", self.keybind_exists("SUPER, T, exec, kitty"))
        self.test("Super+Q → killactive bind", self.keybind_exists("SUPER, Q, killactive"))
        self.test("Super+A → pavucontrol bind", self.keybind_exists("SUPER, A, exec, pavucontrol"))
        print()
        
        # Cursor System  
        print(f"{Colors.YELLOW}Cursor System:{Colors.END}")
        self.test("XCURSOR_THEME=dot", self.env_var_equals("XCURSOR_THEME", "dot"))
        self.test("XCURSOR_SIZE=12", self.env_var_equals("XCURSOR_SIZE", "12"))
        print()
        
        # Navigation Scripts
        print(f"{Colors.YELLOW}Navigation Scripts:{Colors.END}")
        self.test("voider-nav available", self.command_exists("voider-nav"))
        self.test("voider-move available", self.command_exists("voider-move"))
        self.test("Super+arrows → voider-nav", self.keybind_exists("SUPER, left, exec, voider-nav"))
        self.test("Super+Shift+arrows → voider-move", self.keybind_exists("SUPER SHIFT, left, exec, voider-move"))
        print()
        
        # Effect System
        print(f"{Colors.YELLOW}Effect System:{Colors.END}")
        self.test("voider-fx-update available", self.command_exists("voider-fx-update"))
        self.test("voider-open-panel available", self.command_exists("voider-open-panel"))
        self.test("Super+F5 → crt panel", self.keybind_exists("SUPER, F5, exec, voider-open-panel crt"))
        self.test("Super+F6 → grain panel", self.keybind_exists("SUPER, F6, exec, voider-open-panel grain"))
        self.test("Super+F7 → bw panel", self.keybind_exists("SUPER, F7, exec, voider-open-panel bw"))
        print()
        
        # File Management
        print(f"{Colors.YELLOW}File Management:{Colors.END}")
        self.test("voider-sort available", self.command_exists("voider-sort"))
        self.test("~/incoming directory exists", self.file_exists(f"{os.path.expanduser('~')}/incoming"))
        self.test("voider-inbox-watch service", self.service_active("voider-inbox-watch"))
        print()
        
        # Audio Routing
        print(f"{Colors.YELLOW}Audio Routing:{Colors.END}")
        self.test("voider-audio-route service", self.service_active("voider-audio-route"))
        code, output = self.run_cmd("pw-cli ls | grep voider_virtual_mic")
        self.test("Virtual microphone created", code == 0)
        code, output = self.run_cmd("pw-cli ls | grep voider_speaker_monitor") 
        self.test("Speaker monitor created", code == 0)
        print()
        
        # System Packages
        print(f"{Colors.YELLOW}System Packages:{Colors.END}")
        self.test("firefox available", self.command_exists("firefox"))
        self.test("kitty available", self.command_exists("kitty"))
        self.test("codium available", self.command_exists("codium"))
        self.test("claude-code available", self.command_exists("claude-code"))
        self.test("mpv available", self.command_exists("mpv"))
        self.test("voider-radio available", self.command_exists("voider-radio"))
        print()
        
        # Animation & Circle
        print(f"{Colors.YELLOW}Circle Animation:{Colors.END}")
        # Check if the circle parameters were updated for better visibility
        code, output = self.run_cmd("grep '_BREATH_AMPLITUDE.*0\\.15' /nix/store/*/pkgs/voider-py/views.py")
        self.test("Breathing amplitude increased (15%)", code == 0)
        code, output = self.run_cmd("grep 'circle_radius.*- 100' /nix/store/*/pkgs/voider-py/circular_view.py")
        self.test("Circle radius adjusted for screen fit", code == 0)
        print()
        
        # Configuration Files
        print(f"{Colors.YELLOW}Configuration:{Colors.END}")
        self.test("Effect state file exists", self.file_exists("/tmp/voider-fx"))
        print()
        
        # Summary
        print(f"{Colors.BLUE}=== Test Summary ==={Colors.END}")
        print(f"Passed: {Colors.GREEN}{self.passed}{Colors.END}")
        print(f"Failed: {Colors.RED}{self.failed}{Colors.END}")
        
        if self.failed == 0:
            print(f"{Colors.GREEN}All tests passed!{Colors.END}")
            return True
        else:
            print(f"{Colors.RED}{self.failed} tests failed{Colors.END}")
            return False

if __name__ == "__main__":
    tester = VoiderTest()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)