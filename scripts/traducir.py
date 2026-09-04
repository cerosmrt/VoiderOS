#!/usr/bin/env python3
"""Traducir un archivo del void al castellano, sin salir de la maquina.

    traducir.py entrada.txt salida.txt [--from en] [--to es]

Usa argos-translate: modelos neuronales que corren aca, sin mandar el texto a
ningun servidor. La primera vez baja el modelo (~100 MB) y queda cacheado.

Respeta el formato de Voider: traduce LINEA POR LINEA y deja los separadores
'.' intactos. Eso importa — si juntara las lineas en parrafos, el archivo
traducido dejaria de servir en F2, que trabaja una linea a la vez. Asi sale
listo para leer, cortar y reciclar como cualquier otro texto del void.
"""
import argparse
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("entrada")
    ap.add_argument("salida")
    ap.add_argument("--from", dest="desde", default="en")
    ap.add_argument("--to", dest="hasta", default="es")
    a = ap.parse_args()

    from argostranslate import package, translate

    # Bajar el modelo si no esta.
    instalados = {(p.from_code, p.to_code) for p in package.get_installed_packages()}
    if (a.desde, a.hasta) not in instalados:
        print(f"Bajando el modelo {a.desde}->{a.hasta} (una sola vez)...", flush=True)
        package.update_package_index()
        disponibles = package.get_available_packages()
        try:
            elegido = next(p for p in disponibles
                           if p.from_code == a.desde and p.to_code == a.hasta)
        except StopIteration:
            sys.exit(f"No hay modelo {a.desde}->{a.hasta}")
        package.install_from_path(elegido.download())

    idiomas = {l.code: l for l in translate.get_installed_languages()}
    traductor = idiomas[a.desde].get_translation(idiomas[a.hasta])

    lineas = open(a.entrada, encoding="utf-8", errors="replace").read().splitlines()
    total = len(lineas)
    salida = []
    for i, linea in enumerate(lineas, 1):
        limpia = linea.strip()
        # Los separadores y las lineas vacias pasan tal cual: son estructura del
        # void, no texto. Traducirlos los rompe.
        if not limpia or limpia == "." or all(c == "." for c in limpia):
            salida.append(linea)
        else:
            try:
                salida.append(traductor.translate(limpia))
            except Exception as e:
                # Una linea que falla no puede tumbar 7000: se deja el original.
                print(f"  linea {i}: sin traducir ({e})", file=sys.stderr)
                salida.append(linea)
        if i % 100 == 0 or i == total:
            print(f"  {i}/{total}", end="\r", flush=True)

    with open(a.salida, "w", encoding="utf-8") as f:
        f.write("\n".join(salida) + "\n")
    print(f"\nListo: {a.salida} ({total} lineas)")


if __name__ == "__main__":
    main()
