# flake.nix — VoiderOS system definition
# Real machine:  sudo nixos-rebuild switch --flake /home/federico/VoiderOS#<hostname>
# Test VM:       nixos-rebuild build-vm --flake .#voider-vm
#                QEMU_OPTS="-display vnc=0.0.0.0:0" ./result/bin/run-nixos-vm
#                Connect VNC viewer to <host>:5900
{
  description = "VoiderOS — a writing machine built on NixOS";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";

  # Sólo para construir voider-rs: los dependientes de eframe piden rustc >= 1.88
  # y el nixpkgs estable trae 1.86. Es la única pieza que se toma de unstable —
  # el resto del sistema sigue clavado en 25.05 a propósito.
  inputs.nixpkgs-unstable.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs, nixpkgs-unstable }:
  let
    system = "x86_64-linux";
    lib    = nixpkgs.lib;

    # voider-rs empaquetado desde el fuente. Es lo que va en la ISO: un binario
    # reproducible, no un script que apunta a un checkout como el de dev.nix.
    pkgsUnstable = nixpkgs-unstable.legacyPackages.${system};
    voiderRs = pkgsUnstable.callPackage ./nix/pkgs/voider-rs.nix { };


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
    #   hasMntData     : whether this machine has the extra /mnt/data disk (default true)
    #   extraModules   : any additional machine-specific modules
    mkVoiderSystem = { hardwareConfig, hasNvidia ? true, hasMntData ? true, extraModules ? [] }:
      lib.nixosSystem {
        inherit system;
        modules = baseModules
          ++ [ hardwareConfig ]
          ++ lib.optionals (!hasNvidia) [ noNvidiaOverrides ]
          ++ lib.optionals (!hasMntData) [
               ({ lib, ... }: {
                 fileSystems."/mnt/data" = lib.mkForce {
                   device  = "none";
                   fsType  = "tmpfs";
                   options = [ "defaults" "nofail" ];
                 };
               })
             ]
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


    # `nix build .#voider-iso` → result/iso/VoiderOS.iso
    packages.${system} = {
      voider-iso = self.nixosConfigurations.voider-iso.config.system.build.isoImage;
      voider-rs  = voiderRs;
    };
    nixosConfigurations = {

      # TUF (main machine, NVIDIA GPU, has Windows /mnt/data disk)
      voider = mkVoiderSystem {
        hardwareConfig = ./nix/hardware-configuration.nix;
        hasNvidia = true;
        hasMntData = true;
        extraModules = [ ./nix/profiles/dev.nix ./nix/profiles/tuf-data.nix ];
      };

      # Lenovo (writing laptop, no NVIDIA, single disk — no /mnt/data)
      #
      # OJO: hoy este target NO evalúa, y no es por los cambios de la ISO — el
      # archivo nix/hardware-configuration-lenovo.nix nunca existió en git. Es lo
      # único que hace fallar `nix flake check`.
      #
      # Para arreglarlo hay que generarlo EN el Lenovo (no se puede inventar
      # desde acá: lleva los UUID de sus discos, y un hardware-configuration
      # equivocado deja la máquina sin arrancar):
      #
      #     sudo nixos-generate-config --show-hardware-config \
      #       > nix/hardware-configuration-lenovo.nix
      #
      # Con la ISO andando esto además pasa a ser opcional: para probar VoiderOS
      # en el Lenovo alcanza con bootear el USB.
      voider-lenovo = mkVoiderSystem {
        hardwareConfig = ./nix/hardware-configuration-lenovo.nix;
        hasNvidia = false;
        hasMntData = false;
        extraModules = [ ./nix/profiles/dev.nix ];
      };

      # QEMU test VM
      voider-vm = lib.nixosSystem {
        inherit system;
        modules = baseModules ++ [ vmOverrides noNvidiaOverrides ./nix/profiles/dev.nix ];
      };

      # ── El producto ─────────────────────────────────────────────────────────
      # Los tres de arriba son perfiles de máquina, para desarrollar y probar
      # hardware concreto. Éste es lo que se distribuye: sin
      # hardware-configuration (arranca donde sea), sin dev.nix (no conoce
      # ningún checkout), sin el usuario federico y sin /mnt/data.
      voider-iso = lib.nixosSystem {
        inherit system;
        specialArgs = { inherit voiderRs; };
        modules = baseModules ++ [ noNvidiaOverrides ./nix/profiles/iso.nix ];
      };

    };
  };
}
