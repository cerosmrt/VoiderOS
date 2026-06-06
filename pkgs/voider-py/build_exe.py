# SOLUCIÓN 1: Script simplificado sin scipy problemático
import os
import datetime
import sys
import PyInstaller.__main__

def build_simple():
    """Versión simplificada que evita el problema con scipy"""
    timestamp = datetime.datetime.now().strftime('%y-%m-%d_%H-%M-%S')
    exe_name = f'voider-{timestamp}'
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    build_root = os.path.join(base_dir, 'builds')
    dist_dir = os.path.join(build_root, 'dist')
    work_dir = os.path.join(build_root, 'build')
    spec_dir = build_root
    main_script = os.path.join(base_dir, 'voider.py')
    icon_path = os.path.join(base_dir, 'voider.ico')
    
    os.makedirs(dist_dir, exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(spec_dir, exist_ok=True)
    
    # Argumentos mínimos - SIN scipy que está causando problemas
    args = [
        '--clean',
        '--onefile',  # Cambiar a onedir por ahora
        '--windowed',
        main_script,
        f'--name={exe_name}',
        f'--distpath={dist_dir}',
        f'--workpath={work_dir}',
        f'--specpath={spec_dir}',
        
        # Solo los imports esenciales
        '--hidden-import=PyQt6',
        '--hidden-import=PyQt6.QtCore',
        '--hidden-import=PyQt6.QtGui',
        '--hidden-import=PyQt6.QtWidgets',
        '--hidden-import=sounddevice',
        
        # Excluir scipy problemático
        '--exclude-module=scipy',
        '--exclude-module=numpy.distutils',
    ]
    
    if os.path.exists(icon_path):
        args.append(f'--icon={icon_path}')
    
    print(f"🔧 Construyendo versión simplificada: {exe_name}")
    try:
        PyInstaller.__main__.run(args)
        print("✅ ¡Versión simplificada completada!")
        return True
    except Exception as e:
        print(f"❌ Error en versión simplificada: {e}")
        return False

def build_with_spec_file():
    """SOLUCIÓN 2: Crear archivo .spec personalizado"""
    timestamp = datetime.datetime.now().strftime('%y-%m-%d_%H-%M-%S')
    exe_name = f'voider-{timestamp}'
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['voider.py'],
    pathex=['{base_dir.replace(chr(92), chr(92)+chr(92))}'],
    binaries=[],
    datas=[('voider.ico', '.')] if os.path.exists('voider.ico') else [],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui', 
        'PyQt6.QtWidgets',
        'sounddevice',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['scipy', 'matplotlib', 'tkinter', 'pygame', 'torch'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='{exe_name}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='voider.ico' if os.path.exists('voider.ico') else None,
)
'''
    
    spec_file = f'{exe_name}.spec'
    with open(spec_file, 'w') as f:
        f.write(spec_content)
    
    print(f"📝 Archivo .spec creado: {spec_file}")
    print("🔧 Ejecuta manualmente: pyinstaller --clean " + spec_file)
    return spec_file

def build_conda_fix():
    """SOLUCIÓN 3: Versión para entornos conda/problemas de dependencias"""
    timestamp = datetime.datetime.now().strftime('%y-%m-%d_%H-%M-%S')
    exe_name = f'voider-{timestamp}'
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    build_root = os.path.join(base_dir, 'builds')
    dist_dir = os.path.join(build_root, 'dist')
    work_dir = os.path.join(build_root, 'build')
    spec_dir = build_root
    main_script = os.path.join(base_dir, 'voider.py')
    
    os.makedirs(dist_dir, exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(spec_dir, exist_ok=True)
    
    args = [
        '--clean',
        '--onedir',
        '--console',  # Temporalmente para ver errores
        main_script,
        f'--name={exe_name}',
        f'--distpath={dist_dir}',
        f'--workpath={work_dir}',
        f'--specpath={spec_dir}',
        '--noupx',  # Desactivar UPX que a veces causa problemas
        '--debug=all',  # Más información de debug
    ]
    
    print(f"🔧 Construyendo versión debug: {exe_name}")
    try:
        PyInstaller.__main__.run(args)
        print("✅ ¡Versión debug completada!")
        return True
    except Exception as e:
        print(f"❌ Error en versión debug: {e}")
        return False

def main():
    print("🚀 Iniciando soluciones para PyInstaller...")
    print("=" * 50)
    
    # Información del sistema
    print("📊 Información del sistema:")
    print(f"   Python: {sys.version}")
    print(f"   Directorio: {os.getcwd()}")
    
    try:
        import PyInstaller
        print(f"   PyInstaller: {PyInstaller.__version__}")
    except:
        print("   PyInstaller: No disponible")
    
    try:
        import scipy
        print(f"   SciPy: {scipy.__version__}")
    except:
        print("   SciPy: No disponible")
    
    print("=" * 50)
    
    # Intentar soluciones en orden
    print("\n1️⃣ Intentando versión simplificada...")
    if build_simple():
        return
    
    print("\n2️⃣ Creando archivo .spec personalizado...")
    spec_file = build_with_spec_file()
    
    print("\n3️⃣ Intentando versión debug...")
    if build_conda_fix():
        return
    
    print("\n" + "=" * 50)
    print("🔧 INSTRUCCIONES MANUALES:")
    print("=" * 50)
    print("Si nada funcionó automáticamente, prueba estos comandos manuales:")
    print()
    print("OPCIÓN A - Sin scipy:")
    print("pyinstaller --onedir --windowed --clean voider.py --exclude-module=scipy")
    print()
    print("OPCIÓN B - Solo lo esencial:")
    print("pyinstaller --onedir --console voider.py")
    print()
    print("OPCIÓN C - Usar el .spec generado:")
    print(f"pyinstaller --clean {spec_file}")
    print()
    print("OPCIÓN D - Actualizar PyInstaller:")
    print("pip install --upgrade pyinstaller")
    print()
    print("OPCIÓN E - Crear entorno virtual limpio:")
    print("python -m venv venv_clean")
    print("venv_clean\\Scripts\\activate")
    print("pip install PyQt6 sounddevice pyinstaller")

if __name__ == "__main__":
    main()