# Compilar el .exe de Windows (versión Python)

El primer `.exe` hecho con PyInstaller en Windows salió con la interfaz distinta a la de
NixOS. Revisando el spec y el código aparecieron tres causas, y las tres tienen arreglo
en este repo.

## Qué estaba mal

1. **Fuentes.** El default era `Consolas` (en NixOS no existe, así que Qt usaba otra
   monoespaciada; en Windows sí existe y las métricas cambian) y la fuente de lectura,
   `EB Garamond`, no está instalada en Windows. Todo lo que el layout calcula a partir de
   la fuente se movía. **Ahora las fuentes viajan con la app** (`fonts/`, con su licencia)
   y se registran en Qt al arrancar (`resources.py`, llamado desde `voider.py` antes de
   crear la ventana). El default pasó a ser `EB Garamond`.
2. **Rutas de Linux.** `/tmp/voider-fx`, `/tmp/voider-fx-panel` y `~/void/tts/*.onnx` no
   existen en Windows. Ahora el temporal sale de `tempfile.gettempdir()` y los modelos de
   voz de `<void>/tts/` (`platform_paths.py`). `tests/test_resources_and_paths.py` falla
   si alguien vuelve a escribir un `'/tmp/...'` en un `.py`.
3. **El spec.** Era mínimo: `upx=True` y `datas=[]`. UPX es una fuente conocida de `.exe`
   raros, y sin `datas` el build perdía en silencio las fuentes, los diccionarios de
   `pyphen` (hifenado) y los perfiles de `langdetect`. Los dos últimos fallan **sin
   avisar**: el código atrapa el error y devuelve el texto sin hifenar, así que el `.exe`
   "andaba" y solo se veía distinto.

## Cómo compilar

Desde esta carpeta, en Windows:

```
pip install pyinstaller PyQt6 numpy watchdog langdetect pyphen ebooklib pyaudio
pyinstaller voider.spec
```

O con Nuitka (recomendado en el plan: deja menos plugins de Qt afuera y no usa UPX):

```
pip install nuitka PyQt6 numpy watchdog langdetect pyphen ebooklib pyaudio
build_windows_nuitka.bat
```

`config.json`, `state.json` y `void/` **no** van adentro del `.exe`: se leen y escriben al
lado de él. Si querés una configuración inicial, copiálos junto a `voider.exe`.

## Qué no se pudo probar

Nada de esto se pudo compilar desde NixOS: PyInstaller y Nuitka necesitan correr en el
sistema de destino. Lo que **sí** está probado (`tests/`) es lo que se puede probar acá:
que el spec no use UPX y liste los datos, que el script de Nuitka pida lo mismo, que las
fuentes existan y se registren en Qt, y que ninguna ruta de Linux quede escrita a mano.
**El `.exe` resultante hay que mirarlo una vez en Windows** — en particular que las letras
sean EB Garamond y que el hifenado de F4 funcione.

## Alternativa

La versión Rust (`pkgs/voider-rs`) se compila a un `.exe` desde NixOS, sin Windows
(`pkgs/voider-rs/BUILD-WINDOWS.md`), y ya trae el mismo aspecto que esta.
