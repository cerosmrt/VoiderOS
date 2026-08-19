# nix/profiles/tuf-data.nix — el disco NTFS de la TUF.
#
# Vivía en nix/system.nix, que es la base compartida, con un UUID fijo y sin
# nofail: en cualquier otra máquina systemd esperaba un dispositivo que no
# existe y el arranque quedaba colgado. Un disco concreto de una computadora
# concreta no pertenece a la definición de VoiderOS.
{ ... }:
{
  fileSystems."/mnt/data" = {
    device  = "/dev/disk/by-uuid/F29420EE9420B6CF";
    fsType  = "ntfs3";
    options = [ "uid=1000" "gid=1000" "umask=0022" "nofail" ];
  };
}
