# controls.py - Controles de navegación y líneas aleatorias
import random
import os

def setup_controls(app):
    """Configura los controles de la aplicación."""
    print("Configurando controles...")
    app.first_up_after_submission = False

def show_random_line_from_current_file(app, event=None):
    """
    COPIA una línea aleatoria del archivo activo al entry,
    excluyendo la línea actual y las líneas que son solo puntos.
    """
    try:
        if os.path.exists(app.current_file_path):
            with open(app.current_file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if line.strip() and line.strip() != '.']
            
            if not lines:
                print(f"El archivo {os.path.basename(app.current_file_path)} no tiene líneas válidas.")
                return
            
            # Exclude current line if exists and there are other options
            current_line = app.entry.text().strip() if app.entry.text() else None
            available_lines = [line for line in lines if line != current_line] if current_line and len(lines) > 1 else lines
            
            if available_lines:
                random_line = random.choice(available_lines)
                app.entry.setText(random_line)
                app.entry.setCursorPosition(0)
                print(f"📋 Ctrl+. | Línea copiada del archivo activo: '{random_line}'")
            else:
                app.entry.setText(lines[0])
                app.entry.setCursorPosition(0)
        else:
            print(f"El archivo {os.path.basename(app.current_file_path)} no existe.")
            app.entry.clear()
    except Exception as e:
        print(f"Error al copiar línea aleatoria del archivo activo: {e}")
        app.entry.clear()


def show_random_line_from_random_file(app, event=None):
    """
    COPIA una línea aleatoria de un archivo .txt aleatorio (EXCLUYENDO 0.txt),
    incluyendo subcarpetas. La línea se copia al entry para editar.
    """
    try:
        # Escanear todos los .txt en void_dir incluyendo subcarpetas
        all_txt_files = []
        for root, dirs, files in os.walk(app.void_dir):
            for file in files:
                if file.lower().endswith('.txt'):
                    full_path = os.path.join(root, file)
                    # Excluir 0.txt
                    if os.path.basename(full_path) != '0.txt':
                        all_txt_files.append(full_path)
        
        if not all_txt_files:
            print("❌ No hay archivos .txt disponibles (excluyendo 0.txt).")
            return
        
        # Elegir archivo random
        random_file = random.choice(all_txt_files)
        
        # Leer líneas válidas (excluir puntos)
        with open(random_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines() if line.strip() and line.strip() != '.']
        
        if lines:
            random_line = random.choice(lines)
            app.entry.setText(random_line)
            app.entry.setCursorPosition(0)
            rel_path = os.path.relpath(random_file, app.void_dir)
            print(f"📋 Ctrl+0 | Línea copiada de '{rel_path}': '{random_line}'")
        else:
            print(f"El archivo {os.path.basename(random_file)} no tiene líneas válidas.")
            
    except Exception as e:
        print(f"Error al copiar línea aleatoria de archivo random: {e}")


def recycle_line_to_zero_txt(app, event=None):
    """
    RECICLADO (*): Muestra línea random de cualquier archivo (excluir archivo activo)
    para pegar manualmente en el archivo activo actual. Cut-up technique.
    
    - NO cambia el archivo activo
    - Solo muestra la línea en el entry
    - El usuario decide si la pega (Enter) o descarta (Esc/borrar)
    - Se pega en el current index del archivo activo cuando el usuario presione Enter
    """
    try:
        # Escanear todos los .txt en void_dir incluyendo subcarpetas
        all_txt_files = []
        for root, dirs, files in os.walk(app.void_dir):
            for file in files:
                if file.lower().endswith('.txt'):
                    full_path = os.path.join(root, file)
                    # Excluir el archivo activo actual
                    if full_path != app.current_file_path:
                        all_txt_files.append(full_path)
        
        if not all_txt_files:
            print("❌ No hay otros archivos .txt disponibles para reciclar.")
            return
        
        # Elegir archivo random
        random_file = random.choice(all_txt_files)
        
        # Leer líneas válidas (excluir puntos)
        with open(random_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines() if line.strip() and line.strip() != '.']
        
        if lines:
            random_line = random.choice(lines)
            
            # Mostrar la línea en el entry (el usuario decide si la pega)
            app.entry.setText(random_line)
            app.entry.setCursorPosition(0)
            
            rel_path_from = os.path.relpath(random_file, app.void_dir)
            current_file = os.path.basename(app.current_file_path)
            print(f"♻️ * | Reciclado de '{rel_path_from}' → {current_file}")
            print(f"   Línea: '{random_line}'")
            print(f"   (Enter para pegar, Esc para descartar)")
        else:
            print(f"El archivo {os.path.basename(random_file)} no tiene líneas válidas.")
            
    except Exception as e:
        print(f"Error al reciclar línea: {e}")


def show_previous_current_file_line(app, event=None):
    """Muestra la línea anterior en el archivo activo, con navegación circular."""
    try:
        if os.path.exists(app.current_file_path):
            with open(app.current_file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if not lines:
                print(f"El archivo {os.path.basename(app.current_file_path)} está vacío.")
                app.current_active_line = None
                app.current_active_line_index = None
                app.first_up_after_submission = False
                app.entry.clear()
                return
            
            # If first Up press after submission, show last inserted line
            if app.first_up_after_submission and hasattr(app, 'last_inserted_index') and app.last_inserted_index is not None:
                if app.last_inserted_index < len(lines) and lines[app.last_inserted_index].strip():
                    app.current_active_line = lines[app.last_inserted_index].strip()
                    app.current_active_line_index = app.last_inserted_index
                    app.entry.setText(app.current_active_line)
                    app.entry.setCursorPosition(0)
                    app.first_up_after_submission = False
                    print(f"Primera flecha arriba: Mostrando última línea enviada: {app.current_active_line}")
                    return
            
            # Normal navigation: Find previous non-empty line (skip dots)
            current_index = app.current_active_line_index if app.current_active_line_index is not None else len(lines)
            new_index = current_index - 1
            
            # Loop if at start
            if new_index < 0:
                new_index = len(lines) - 1
                while new_index >= 0:
                    if lines[new_index].strip() and lines[new_index].strip() != '.':
                        app.current_active_line_index = new_index
                        app.current_active_line = lines[new_index].strip()
                        app.entry.setText(app.current_active_line)
                        app.entry.setCursorPosition(0)
                        app.first_up_after_submission = False
                        print(f"Loop a última línea: {app.current_active_line}")
                        return
                    new_index -= 1
            
            # Find previous non-empty line (skip dots)
            while new_index >= 0:
                if lines[new_index].strip() and lines[new_index].strip() != '.':
                    app.current_active_line_index = new_index
                    app.current_active_line = lines[new_index].strip()
                    app.entry.setText(app.current_active_line)
                    app.entry.setCursorPosition(0)
                    app.first_up_after_submission = False
                    print(f"Línea anterior mostrada: {app.current_active_line}")
                    return
                new_index -= 1
            
            print("No hay líneas válidas en el archivo.")
            app.current_active_line = None
            app.current_active_line_index = None
            app.first_up_after_submission = False
            app.entry.clear()
        else:
            print(f"El archivo {os.path.basename(app.current_file_path)} no existe.")
            app.current_active_line = None
            app.current_active_line_index = None
            app.first_up_after_submission = False
            app.entry.clear()
    except Exception as e:
        print(f"Error al mostrar línea anterior: {e}")
        app.current_active_line = None
        app.current_active_line_index = None
        app.first_up_after_submission = False
        app.entry.clear()


def show_next_current_file_line(app, event=None):
    """Muestra la línea siguiente en el archivo activo, con navegación circular."""
    try:
        if os.path.exists(app.current_file_path):
            with open(app.current_file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if not lines:
                print(f"El archivo {os.path.basename(app.current_file_path)} está vacío.")
                app.current_active_line = None
                app.current_active_line_index = None
                app.first_up_after_submission = False
                app.entry.clear()
                return
            
            # If index is None, start from last_inserted_index
            current_index = (app.last_inserted_index if hasattr(app, 'last_inserted_index') and app.last_inserted_index is not None else -1) if app.current_active_line_index is None else app.current_active_line_index
            new_index = current_index + 1
            
            # Loop if past end
            if new_index >= len(lines):
                new_index = 0
                while new_index < len(lines):
                    if lines[new_index].strip() and lines[new_index].strip() != '.':
                        app.current_active_line_index = new_index
                        app.current_active_line = lines[new_index].strip()
                        app.entry.setText(app.current_active_line)
                        app.entry.setCursorPosition(0)
                        app.first_up_after_submission = False
                        print(f"Loop a primera línea: {app.current_active_line}")
                        return
                    new_index += 1
            
            # Find next non-empty line (skip dots)
            while new_index < len(lines):
                if lines[new_index].strip() and lines[new_index].strip() != '.':
                    app.current_active_line_index = new_index
                    app.current_active_line = lines[new_index].strip()
                    app.entry.setText(app.current_active_line)
                    app.entry.setCursorPosition(0)
                    app.first_up_after_submission = False
                    print(f"Línea siguiente mostrada: {app.current_active_line}")
                    return
                new_index += 1
            
            print("No hay líneas válidas en el archivo.")
            app.current_active_line = None
            app.current_active_line_index = None
            app.first_up_after_submission = False
            app.entry.clear()
        else:
            print(f"El archivo {os.path.basename(app.current_file_path)} no existe.")
            app.current_active_line = None
            app.current_active_line_index = None
            app.first_up_after_submission = False
            app.entry.clear()
    except Exception as e:
        print(f"Error al mostrar línea siguiente: {e}")
        app.current_active_line = None
        app.current_active_line_index = None
        app.first_up_after_submission = False
        app.entry.clear()