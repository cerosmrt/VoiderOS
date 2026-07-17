# flake.nix — VoiderOS system definition
# Real machine:  sudo nixos-rebuild switch --flake /home/federico/VoiderOS#<hostname>
# Test VM:       nixos-rebuild build-vm --flake .#voider-vm
#                QEMU_OPTS="-display vnc=0.0.0.0:0" ./result/bin/run-nixos-vm
#                Connect VNC viewer to <host>:5900
{
  description = "VoiderOS — a writing machine built on NixOS";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";

  outputs = { self, nixpkgs }:
  let
    system = "x86_64-linux";
    lib    = nixpkgs.lib;

    baseModules = [
      ./nix/system.nix
      ./nix/modules/voider.nix
    ];

    # Disables NVIDIA-specific config for machines without that GPU
    noNvidiaOverrides = { lib, ... }: {
      hardware.nvidia.modesetting.enable     = lib.mkForce false;
      hardware.nvidia.open                   = lib.mkForce false;
      hardware.nvidia.nvidiaSettings         = lib.mkForce false;
      hardware.nvidia.powerManagement.enable = lib.mkForce false;
      services.xserver.videoDrivers          = lib.mkForce [ "modesetting" ];
    };

    # VM overrides — no NVIDIA, no physical disk, no EFI
    # Hyprland uses wlroots, same env vars as Sway for software rendering
    vmOverrides = { pkgs, ... }: {
      fileSystems."/" = {
        device = "/dev/disk/by-label/nixos";
        fsType = "ext4";
      };

      fileSystems."/mnt/data" = lib.mkForce {
        device  = "none";
        fsType  = "tmpfs";
        options = [ "defaults" "nofail" ];
      };

      boot.loader.systemd-boot.enable      = lib.mkForce false;
      boot.loader.efi.canTouchEfiVariables = lib.mkForce false;
      boot.loader.grub = {
        enable     = true;
        device     = "nodev";
        efiSupport = false;
      };

      # Hyprland / wlroots software rendering in QEMU
      environment.sessionVariables.WLR_RENDERER             = lib.mkForce "pixman";
      environment.sessionVariables.WLR_NO_HARDWARE_CURSORS  = lib.mkForce "1";
      environment.sessionVariables.LIBGL_ALWAYS_SOFTWARE    = lib.mkForce "1";
      environment.sessionVariables.WLR_RENDERER_ALLOW_SOFTWARE = lib.mkForce "1";
    };

    # Reusable builder for any physical VoiderOS machine.
    #   hardwareConfig : path to that machine's hardware-configuration.nix
    #   hasNvidia      : whether to keep the NVIDIA driver config (default true)
    #   extraModules   : any additional machine-specific modules
    mkVoiderSystem = { hardwareConfig, hasNvidia ? true, extraModules ? [] }:
      lib.nixosSystem {
        inherit system;
        modules = baseModules
          ++ [ hardwareConfig ]
          ++ lib.optionals (!hasNvidia) [ noNvidiaOverrides ]
          ++ extraModules;
      };

  in {
    # Dev shell: `nix develop` then `cd pkgs/voider-shell && cargo check`
    devShells.${system}.default = let
      pkgs = nixpkgs.legacyPackages.${system};
    in pkgs.mkShell {
      buildInputs = with pkgs; [
        cargo rustc gcc pkg-config git
        wayland libxkbcommon wayland-protocols
      ];
    };

    nixosConfigurations = {

      # TUF (main machine, NVIDIA GPU)
      voider = mkVoiderSystem {
        hardwareConfig = ./nix/hardware-configuration.nix;
        hasNvidia = true;
      };

      # Lenovo (writing laptop, no NVIDIA)
      voider-lenovo = mkVoiderSystem {
        hardwareConfig = ./nix/hardware-configuration-lenovo.nix;
        hasNvidia = false;
      };

      # QEMU test VM
      voider-vm = lib.nixosSystem {
        inherit system;
        modules = baseModules ++ [ vmOverrides noNvidiaOverrides ];
      };

    };
  };
}        fsType  = "tmpfs";
        options = [ "defaults" "nofail" ];
      };

      boot.loader.systemd-boot.enable      = lib.mkForce false;
      boot.loader.efi.canTouchEfiVariables = lib.mkForce false;
      boot.loader.grub = {
        enable     = true;
        device     = "nodev";
        efiSupport = false;
      };

      # Hyprland / wlroots software rendering in QEMU
      environment.sessionVariables.WLR_RENDERER             = lib.mkForce "pixman";
      environment.sessionVariables.WLR_NO_HARDWARE_CURSORS  = lib.mkForce "1";
      environment.sessionVariables.LIBGL_ALWAYS_SOFTWARE    = lib.mkForce "1";
      environment.sessionVariables.WLR_RENDERER_ALLOW_SOFTWARE = lib.mkForce "1";
    };

  in {
    # Dev shell: `nix develop` then `cd pkgs/voider-shell && cargo check`
    devShells.${system}.default = let
      pkgs = nixpkgs.legacyPackages.${system};
    in pkgs.mkShell {
      buildInputs = with pkgs; [
        cargo rustc gcc pkg-config git
        wayland libxkbcommon wayland-protocols
      ];
    };

    nixosConfigurations = {

      # Real machine
      voider = lib.nixosSystem {
        inherit system;
        modules = baseModules ++ [ ./nix/hardware-configuration.nix ];
      };

      # QEMU test VM
      voider-vm = lib.nixosSystem {
        inherit system;
        modules = baseModules ++ [ vmOverrides ];
      };

    };
  };
}
