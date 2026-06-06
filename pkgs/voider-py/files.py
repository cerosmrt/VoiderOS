# --- files.py ---
import os
import random
import re
import datetime
import sys

def setup_file_handling(app):
    """Initializes file handling for the active file and ensures void_dir exists."""
    # Ensure void_dir exists
    if not os.path.exists(app.void_dir):
        os.makedirs(app.void_dir)
    
    # Ensure the active file (current_file_path) exists
    if not os.path.exists(app.current_file_path):
        with open(app.current_file_path, 'w', encoding='utf-8') as f:
            f.write('')
        print(f"Created active file: {app.current_file_path}")
    
    # Ensure 0.txt exists (as a fallback or for commands like //)
    if not os.path.exists(app.void_file_path):
        with open(app.void_file_path, 'w', encoding='utf-8') as f:
            f.write('')
        print(f"Created 0.txt: {app.void_file_path}")
    
    # Initialize navigation state
    app.current_active_line = None
    app.current_active_line_index = None
    app.last_inserted_index = None
    print(f"File handling initialized. Active file: {app.current_file_path}")

def void_line(app, event=None):
    """Procesa la línea ingresada, formateándola y guardándola en el archivo activo,
       o ejecutando un comando de archivo (cambiar o mover bloques/líneas)."""
    try:
        line = app.entry.text().strip()
        app.entry.clear()
        app.entry.setFocus()

        if not line:
            app.current_active_line_index = None 
            app.current_active_line = None
            
            # --- MODIFICACIÓN AQUÍ: Mover al final del archivo si la entrada está vacía ---
            lines_in_file = []
            if os.path.exists(app.current_file_path):
                with open(app.current_file_path, 'r', encoding='utf-8') as f:
                    lines_in_file = f.readlines()
            
            # Establecer last_inserted_index al índice de la última línea (o -1 si está vacío)
            # Esto asegura que la próxima inserción se haga al final del archivo.
            app.last_inserted_index = len(lines_in_file) - 1 

            print(f"Input vacío: Reiniciando índice de línea activa y estableciendo last_inserted_index a {app.last_inserted_index} (final del archivo).")
            return # No hacer nada más si la línea está vacía
        # --- FIN MODIFICACIÓN ---

        # Prevent consecutive dots (dots are paragraph separators)
        if line == '.':
            try:
                with open(app.current_file_path, 'r', encoding='utf-8') as f:
                    last = next((l.strip() for l in reversed(f.readlines()) if l.strip()), None)
                if last == '.':
                    print("Consecutive dots not allowed.")
                    return
            except Exception:
                pass

        # --- 1. Manejo de comandos de cambio de archivo (//) ---
        if line.startswith("//"):
            target_filename = line[2:].strip()
            if not target_filename: # Si solo se escribe "//", ir a 0.txt
                target_filename = "0" 
            
            # Normalizar el nombre del archivo
            if not target_filename.lower().endswith(".txt"):
                target_filename += ".txt"
            
            new_file_full_path = os.path.join(app.void_dir, target_filename)

            if new_file_full_path != app.current_file_path:
                # Cambiar el archivo activo
                app.current_file_path = new_file_full_path
                # Crear el archivo si no existe
                if not os.path.exists(app.current_file_path):
                    with open(app.current_file_path, 'w', encoding='utf-8') as f:
                        f.write('')
                    print(f"Archivo creado: {os.path.basename(app.current_file_path)}")
                
                # Update txt_files and current_file_index
                if new_file_full_path not in app.txt_files:
                    app.txt_files.append(new_file_full_path)
                    app.txt_files.sort()
                app.current_file_index = app.txt_files.index(new_file_full_path)
                
                print(f"Cambiado al archivo: {os.path.basename(app.current_file_path)}")
                # Resetear el estado de navegación para el nuevo archivo
                app.current_active_line = None
                app.current_active_line_index = None
                app.last_inserted_index = None
            else:
                print(f"Ya estás en el archivo: {os.path.basename(app.current_file_path)}")
            return # Finalizar procesamiento de esta línea

        # --- 2. Manejo de "Mover una Sola Línea" (Ej: "Mi contenido /nombre_archivo") ---
        # Busca el patrón de texto seguido de un espacio y el comando /filename al final de la línea.
        match_single_line_move = re.search(r'(.*)\s+/([a-zA-Z0-9_.-]+\.txt|[a-zA-Z0-9_.-]+)$', line)
        
        if match_single_line_move:
            content_to_move = match_single_line_move.group(1).strip()
            target_filename_raw = match_single_line_move.group(2).strip()

            if not target_filename_raw:
                print("Comando de mover línea incompleto.")
                return

            target_filename = target_filename_raw
            if not target_filename.lower().endswith(".txt"):
                target_filename += ".txt"
            target_file_path = os.path.join(app.void_dir, target_filename)

            # Asegurar que el archivo de destino exista
            if not os.path.exists(target_file_path):
                with open(target_file_path, 'w', encoding='utf-8') as f:
                    f.write('')
            
            # Mover el contenido al archivo de destino
            with open(target_file_path, 'a', encoding='utf-8') as target_f:
                target_f.write(content_to_move + '\n')
            print(f"Línea '{content_to_move}' movida a {os.path.basename(target_file_path)}")

            # Ahora, eliminar la línea del archivo de origen si fue una edición/reemplazo
            if app.current_active_line_index is not None:
                all_file_lines = []
                if os.path.exists(app.current_file_path):
                    with open(app.current_file_path, 'r', encoding='utf-8') as f:
                        all_file_lines = f.readlines()
                
                # Eliminar la línea original que contenía el comando
                if app.current_active_line_index < len(all_file_lines):
                    del all_file_lines[app.current_active_line_index]
                
                # Reescribir el archivo de origen
                with open(app.current_file_path, 'w', encoding='utf-8') as current_f:
                    current_f.writelines(all_file_lines)
                    current_f.flush()
                    os.fsync(current_f.fileno())
                
                # Si el archivo de origen queda vacío después de eliminar la línea (y no es 0.txt), eliminarlo
                if not all_file_lines and app.current_file_path != app.void_file_path:
                    os.remove(app.current_file_path)
                    print(f"Archivo {os.path.basename(app.current_file_path)} vacío y eliminado.")
                    app.current_file_path = app.void_file_path # Volver a 0.txt
                    app.current_file_index = app.txt_files.index(app.current_file_path)
                    print(f"Regresando al archivo: {os.path.basename(app.current_file_path)}")

            app.current_active_line = None
            app.current_active_line_index = None
            app.last_inserted_index = None
            return # Finalizar procesamiento de esta línea

        # --- 3. Manejo de "Mover Bloque Completo" (Ej: "/nombre_archivo" en una línea sola) ---
        if line.startswith("/"): # Solo si no fue manejado por el caso anterior
            target_filename_raw = line[1:].strip()
            if not target_filename_raw:
                print("Comando de mover bloque incompleto. Escribe /nombre_archivo.txt")
                return
            
            target_filename = target_filename_raw
            if not target_filename.lower().endswith(".txt"):
                target_filename += ".txt"
            target_file_path = os.path.join(app.void_dir, target_filename)

            all_file_lines = []
            if os.path.exists(app.current_file_path):
                with open(app.current_file_path, 'r', encoding='utf-8') as f:
                    all_file_lines = f.readlines()
            
            # Determinar el índice donde el comando fue/será insertado
            command_insert_index = len(all_file_lines) # Por defecto, al final
            if app.current_active_line_index is not None:
                command_insert_index = app.current_active_line_index
            
            # Encontrar el inicio del bloque a mover (último punto antes de command_insert_index)
            block_start_index = 0
            for i in range(command_insert_index - 1, -1, -1):
                if all_file_lines[i].strip() == '.':
                    block_start_index = i
                    break
            
            # Extraer el bloque a mover
            block_to_move = all_file_lines[block_start_index : command_insert_index]
            
            # >>> CORRECCIÓN: NUNCA insertar el comando como texto normal si no hay bloque <<<
            if not block_to_move:
                print(f"No se encontró un bloque para mover con el comando '{line}'. No se realizó ninguna acción en el archivo.")
                app.current_active_line = None
                app.current_active_line_index = None
                app.last_inserted_index = None
                return # Simplemente retornar, sin modificar el archivo de origen.

            # Asegurar que el archivo de destino exista
            if not os.path.exists(target_file_path):
                with open(target_file_path, 'w', encoding='utf-8') as f:
                    f.write('')
            
            # >>> NUEVA LÓGICA: Añadir punto al inicio del bloque en el archivo de destino <<<
            with open(target_file_path, 'r+', encoding='utf-8') as target_f: # Abrir para leer y escribir
                target_content = target_f.read()
                # Si el archivo está vacío o no termina con un punto, añadir un punto antes del bloque
                if not target_content.strip() or target_content.strip().endswith('.'):
                    # Si termina con un punto, o está vacío, añadir el bloque directamente
                    # (el punto inicial del bloque se añadirá al escribir)
                    pass 
                else: # Si termina sin punto, pero no está vacío, asegurar que haya un punto antes de añadir el nuevo bloque
                    target_f.write('.\n') # Añadir un punto para separar el bloque anterior del nuevo

                # Mover el puntero al final del archivo para añadir el nuevo contenido
                target_f.seek(0, os.SEEK_END)
                
                # El bloque debe empezar con un punto en el destino
                final_block_to_write = []
                if not block_to_move[0].strip() == '.': # Si el bloque no empieza ya con un punto, añadir uno
                    final_block_to_write.append('.\n')
                final_block_to_write.extend(block_to_move)

                target_f.writelines(final_block_to_write)
            
            # --- CORRECCIÓN: El comando NO se incluye en new_source_lines aquí. ---
            # Construir las nuevas líneas del archivo de origen:
            # Líneas antes del bloque + líneas después de la línea del comando (excluyendo el comando)
            new_source_lines = all_file_lines[:block_start_index] + all_file_lines[command_insert_index + 1:]

            # >>> NUEVA LÓGICA: Reinsertar punto en el archivo de origen si es necesario <<<
            # Esto ocurre si había contenido antes Y después del bloque extraído,
            # y la línea justo antes del bloque extraído NO era ya un punto.
            if block_start_index > 0 and command_insert_index + 1 <= len(all_file_lines): # <= para incluir el caso de que command_insert_index sea el último
                # Verificar si la línea que estaba justo antes del inicio del bloque movido (all_file_lines[block_start_index - 1])
                # era un punto. Si no lo era, y el bloque que se movió SÍ comenzó con un punto
                # (o simplemente hay una brecha entre dos secciones que ahora necesitan un punto)
                # entonces reinsertamos un punto en el origen.
                
                # Si la línea justo ANTES de la brecha no era un punto
                # Y hay contenido ANTES y DESPUÉS de la brecha.
                if all_file_lines[block_start_index - 1].strip() != '.':
                    # Insertar un punto en la posición donde solía comenzar el bloque movido
                    new_source_lines.insert(block_start_index, '.\n')

            # Reescribir el archivo de origen
            with open(app.current_file_path, 'w', encoding='utf-8') as current_f:
                current_f.writelines(new_source_lines)
                current_f.flush()
                os.fsync(current_f.fileno())

            print(f"Bloque movido de {os.path.basename(app.current_file_path)} a {os.path.basename(target_file_path)}")
            
            # Si el archivo de origen queda completamente vacío (incluyendo la ausencia del comando), y no es 0.txt, eliminarlo.
            if not new_source_lines and app.current_file_path != app.void_file_path:
                os.remove(app.current_file_path)
                print(f"Archivo {os.path.basename(app.current_file_path)} vacío y eliminado.")
                app.current_file_path = app.void_file_path # Volver a 0.txt
                app.current_file_index = app.txt_files.index(app.current_file_path)
                print(f"Regresando al archivo: {os.path.basename(app.current_file_path)}")

            app.current_active_line = None
            app.current_active_line_index = None
            app.last_inserted_index = None
            return # Finalizar procesamiento de esta línea

        # --- 4. Manejo de texto normal (si no es un comando) ---
        formatted_lines = [line]
        formatted_text = line

        # Leer líneas del archivo activo
        with open(app.current_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines() 

        if hasattr(app, 'current_active_line_index') and app.current_active_line_index is not None:
            # Si estamos editando una línea existente (navegación previa/siguiente)
            if app.current_active_line_index < len(lines): 
                lines[app.current_active_line_index] = formatted_text + '\n'
                app.last_inserted_index = app.current_active_line_index
                app.current_active_line = formatted_text
                app.current_active_line_index = None  # Reset to allow appending next time
            else:
                # Si el índice está fuera de rango, añadir como nueva línea
                insert_index = len(lines)
                lines.append(formatted_text + '\n')
                app.last_inserted_index = insert_index
                app.current_active_line = formatted_text
                app.current_active_line_index = None
        else:
            # Si estamos añadiendo una nueva línea
            insert_index = (app.last_inserted_index + 1) if hasattr(app, 'last_inserted_index') and app.last_inserted_index is not None else len(lines)
            
            # Asegurarse de que el índice de inserción no exceda el número de líneas existentes + 1
            if insert_index > len(lines):
                insert_index = len(lines)

            lines[insert_index:insert_index] = [line_to_add + '\n' for line_to_add in formatted_lines]
            app.last_inserted_index = insert_index + len(formatted_lines) - 1 
            app.current_active_line = formatted_text
            app.current_active_line_index = None  # Reset to allow appending next time

        # Escribir todas las líneas de vuelta al archivo activo
        with open(app.current_file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
            f.flush()
            os.fsync(f.fileno())
        
        print(f"Líneas insertadas/modificadas en {os.path.basename(app.current_file_path)}.") 
        app.first_up_after_submission = True  # Enable special navigation for first Up press

    except Exception as e:
        print(f"Error en void_line: {e}") 
        app.entry.clear()
        app.entry.setFocus()