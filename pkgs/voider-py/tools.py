# --- tools.py ---
def clean_text(text):
    return text  # Devolver texto sin cambios

def close_program(app, event=None):
    app.close()

def show_cursor(app, event=None):
    app.entry.setCursorVisible(True)