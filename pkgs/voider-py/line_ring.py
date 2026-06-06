# line_ring.py - Estructura circular de líneas con navegación mejorada
class LineRing:
    def __init__(self, lines=None):
        self.lines = list(lines) if lines else [""]
        self.index = 0

    def current(self):
        return self.lines[self.index]

    def move(self, delta):
        if not self.lines:
            return
        self.index = (self.index + delta) % len(self.lines)

    def get(self, offset=0):
        if not self.lines:
            return ""
        return self.lines[(self.index + offset) % len(self.lines)]

    def insert(self, text, after_current=False):
        pos = self.index + 1 if after_current else self.index
        self.lines.insert(pos, text)
        if after_current:
            self.move(1)

    def remove_current(self):
        if len(self.lines) <= 1:
            self.lines = [""]
            self.index = 0
            return
        del self.lines[self.index]
        if self.index >= len(self.lines):
            self.index = len(self.lines) - 1

    def to_list_from_current(self):
        """Para exportar/imprimir con la línea actual primero"""
        return self.lines[self.index:] + self.lines[:self.index]
    
    def rebase_to_current(self):
        """
        Reordena circularmente para que la línea actual sea el nuevo índice 0.
        Ejemplo: [a, b, c, d, e] con index=2 → [c, d, e, a, b] con index=0
        """
        if not self.lines or self.index == 0:
            return  # Ya está en 0 o está vacío
        
        # Reordenar circularmente
        new_lines = self.lines[self.index:] + self.lines[:self.index]
        self.lines = new_lines
        self.index = 0
        
        print(f"🔄 Rebase: Nueva primera línea: '{self.lines[0][:50]}...'")