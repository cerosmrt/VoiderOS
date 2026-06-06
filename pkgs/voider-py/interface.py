import tkinter as tk
from tkinter import font, Canvas, Entry

def setup_ui(app):
    app.root.title("Voider")
    app.root.attributes("-fullscreen", True)
    app.root.attributes("-alpha", 1)
    app.root.config(cursor="none")

    # Loading window
    loading_window = tk.Toplevel(app.root)
    loading_window.overrideredirect(True)
    loading_window.geometry("300x100+{}+{}".format(
        app.root.winfo_screenwidth() // 2 - 150,
        app.root.winfo_screenheight() // 2 - 50
    ))
    loading_window.configure(bg="black")
    tk.Label(loading_window, text="Loading potentiality", fg="white", bg="black", font=("Consolas", 11)).pack(expand=True)
    app.root.update()

    # Canvas and entry setup
    screen_width = app.root.winfo_screenwidth()
    screen_height = app.root.winfo_screenheight()
    thickness = 10
    canvas = Canvas(app.root, highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    center_x = screen_width // 2
    center_y = screen_height // 2
    radius = min(screen_width, screen_height) // 2 - thickness - 25
    canvas.create_oval(center_x - radius, center_y - radius, center_x + radius, center_y + radius, outline="white", width=thickness)
    canvas.configure(bg="black")

    diameter = 2 * radius
    entry_font = font.Font(family="Consolas", size=33)
    average_char_width = entry_font.measure("0")
    entry_width = (diameter - 20) // average_char_width
    entry = Entry(app.root, borderwidth=0, highlightthickness=0, bg="black", fg="white", justify="center", font=entry_font, width=entry_width, insertbackground="white")
    entry.place(x=center_x, y=center_y, anchor="center")
    entry.focus_set()

    loading_window.destroy()
    return canvas, entry

def set_opacity(app):
    app.opacity = max(0.0, min(1.0, app.opacity))
    app.root.attributes("-alpha", app.opacity)

def increase_opacity(app, event=None):
    if app.opacity < 1.0:
        app.opacity = min(1.0, app.opacity + 0.1)
        set_opacity(app)
    return "break"

def decrease_opacity(app, event=None):
    if app.opacity > 0.0:
        app.opacity = max(0.0, app.opacity - 0.1)
        set_opacity(app)
    return "break"