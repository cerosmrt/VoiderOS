//! Elegir un archivo o una carpeta, sin diálogos.
//!
//! El Python abre un `QFileDialog` para las tres cosas que hay que apuntar a
//! mano: el archivo activo (Ctrl+F2), la carpeta del libro (Ctrl+F3) y el void
//! entero (Ctrl+F4). Un diálogo del sistema no tiene lugar acá: Voider no tiene
//! ventanas ni barras, y meter una caja gris de GTK en el medio rompería lo
//! único que la aplicación defiende. Así que es un navegador propio, con la
//! misma forma de anillo que F2, F3 y F7.
//!
//! Esta parte es pura: listar, ordenar, filtrar y moverse. Lo que hace la
//! aplicación con lo elegido vive en `app.rs`.

#![allow(dead_code)]

use std::path::{Path, PathBuf};

/// Qué se está buscando.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Looking {
    /// Un `.txt` — el archivo activo.
    File,
    /// Una carpeta — la del libro, o la del void.
    Dir,
}

/// Una entrada de la lista.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Entry {
    pub name: String,
    pub path: PathBuf,
    pub is_dir: bool,
}

impl Entry {
    /// Cómo se muestra: las carpetas se distinguen a simple vista.
    pub fn display(&self) -> String {
        if self.is_dir {
            format!("{}/", self.name)
        } else {
            self.name.clone()
        }
    }
}

/// Lo que hay en `dir`, listo para mostrar.
///
/// Primero `..` (salvo en la raíz), después las carpetas, después los archivos;
/// todo alfabético. Los ocultos no aparecen: son de la máquina, no del texto.
/// Buscando una carpeta, los archivos no se listan — no habría nada que hacer
/// con ellos.
pub fn list(dir: &Path, looking: Looking) -> Vec<Entry> {
    let mut dirs: Vec<Entry> = Vec::new();
    let mut files: Vec<Entry> = Vec::new();

    if let Ok(entries) = std::fs::read_dir(dir) {
        for e in entries.flatten() {
            let name = e.file_name().to_string_lossy().to_string();
            if name.starts_with('.') {
                continue;
            }
            let path = e.path();
            let is_dir = path.is_dir();
            if is_dir {
                dirs.push(Entry { name, path, is_dir });
            } else if looking == Looking::File && name.to_lowercase().ends_with(".txt") {
                files.push(Entry { name, path, is_dir });
            }
        }
    }
    dirs.sort_by(|a, b| a.name.to_lowercase().cmp(&b.name.to_lowercase()));
    files.sort_by(|a, b| a.name.to_lowercase().cmp(&b.name.to_lowercase()));

    let mut out = Vec::new();
    if let Some(parent) = dir.parent() {
        out.push(Entry {
            name: "..".to_string(),
            path: parent.to_path_buf(),
            is_dir: true,
        });
    }
    out.extend(dirs);
    out.extend(files);
    out
}

/// El navegador abierto: dónde está parado y qué está mirando.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Browser {
    pub looking: Looking,
    pub dir: PathBuf,
    pub entries: Vec<Entry>,
    pub index: usize,
    /// Qué se hace con lo elegido.
    pub purpose: Purpose,
}

/// Para qué se abrió.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Purpose {
    ActiveFile,
    BookDir,
    VoidDir,
}

impl Purpose {
    pub fn looking(self) -> Looking {
        match self {
            Purpose::ActiveFile => Looking::File,
            _ => Looking::Dir,
        }
    }

    pub fn title(self) -> &'static str {
        match self {
            Purpose::ActiveFile => "ARCHIVO ACTIVO",
            Purpose::BookDir => "CARPETA DEL LIBRO",
            Purpose::VoidDir => "EL VOID",
        }
    }
}

impl Browser {
    pub fn open(dir: &Path, purpose: Purpose) -> Self {
        let looking = purpose.looking();
        let dir = dir.to_path_buf();
        let entries = list(&dir, looking);
        Self { looking, dir, entries, index: 0, purpose }
    }

    pub fn current(&self) -> Option<&Entry> {
        self.entries.get(self.index)
    }

    /// Moverse por la lista, dando la vuelta.
    pub fn move_by(&mut self, delta: isize) {
        let n = self.entries.len();
        if n == 0 {
            return;
        }
        self.index = (self.index as isize + delta).rem_euclid(n as isize) as usize;
    }

    /// Entrar a la carpeta señalada. El cursor vuelve arriba.
    pub fn descend(&mut self) -> bool {
        let Some(entry) = self.current().cloned() else {
            return false;
        };
        if !entry.is_dir {
            return false;
        }
        self.dir = entry.path;
        self.entries = list(&self.dir, self.looking);
        self.index = 0;
        true
    }

    /// Qué quedaría elegido si se confirma acá. Buscando una carpeta y parado
    /// sobre `..`, no se elige el padre: eso es navegar, no elegir. Se elige la
    /// carpeta en la que uno ESTÁ.
    pub fn selection(&self) -> Option<PathBuf> {
        match self.looking {
            Looking::File => self.current().filter(|e| !e.is_dir).map(|e| e.path.clone()),
            Looking::Dir => Some(self.dir.clone()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tree() -> tempfile::TempDir {
        let d = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(d.path().join("Beta")).unwrap();
        std::fs::create_dir_all(d.path().join("alfa")).unwrap();
        std::fs::create_dir_all(d.path().join(".oculta")).unwrap();
        std::fs::write(d.path().join("uno.txt"), "x").unwrap();
        std::fs::write(d.path().join("Dos.txt"), "x").unwrap();
        std::fs::write(d.path().join("notas.md"), "x").unwrap();
        std::fs::write(d.path().join(".escondido.txt"), "x").unwrap();
        d
    }

    fn names(entries: &[Entry]) -> Vec<String> {
        entries.iter().map(|e| e.name.clone()).collect()
    }

    #[test]
    fn las_carpetas_van_antes_que_los_archivos_y_todo_alfabetico() {
        let d = tree();
        let got = names(&list(d.path(), Looking::File));
        assert_eq!(got, vec!["..", "alfa", "Beta", "Dos.txt", "uno.txt"]);
    }

    #[test]
    fn los_ocultos_no_se_muestran() {
        let d = tree();
        let got = names(&list(d.path(), Looking::File));
        assert!(!got.iter().any(|n| n.starts_with('.') && n != ".."));
    }

    #[test]
    fn solo_los_txt_cuando_se_busca_un_archivo() {
        let d = tree();
        let got = names(&list(d.path(), Looking::File));
        assert!(!got.contains(&"notas.md".to_string()));
    }

    #[test]
    fn buscando_carpeta_los_archivos_no_estorban() {
        let d = tree();
        let got = names(&list(d.path(), Looking::Dir));
        assert_eq!(got, vec!["..", "alfa", "Beta"]);
    }

    #[test]
    fn las_carpetas_se_ven_como_carpetas() {
        let d = tree();
        let entries = list(d.path(), Looking::File);
        let alfa = entries.iter().find(|e| e.name == "alfa").unwrap();
        assert_eq!(alfa.display(), "alfa/");
        let uno = entries.iter().find(|e| e.name == "uno.txt").unwrap();
        assert_eq!(uno.display(), "uno.txt");
    }

    #[test]
    fn moverse_da_la_vuelta() {
        let d = tree();
        let mut b = Browser::open(d.path(), Purpose::ActiveFile);
        let n = b.entries.len();
        b.move_by(-1);
        assert_eq!(b.index, n - 1);
        b.move_by(1);
        assert_eq!(b.index, 0);
    }

    #[test]
    fn entrar_a_una_carpeta_lista_lo_de_adentro() {
        let d = tree();
        std::fs::write(d.path().join("alfa").join("adentro.txt"), "x").unwrap();
        let mut b = Browser::open(d.path(), Purpose::ActiveFile);
        b.index = b.entries.iter().position(|e| e.name == "alfa").unwrap();
        assert!(b.descend());
        assert!(names(&b.entries).contains(&"adentro.txt".to_string()));
        assert_eq!(b.index, 0, "el cursor tiene que volver arriba");
    }

    #[test]
    fn no_se_entra_a_un_archivo() {
        let d = tree();
        let mut b = Browser::open(d.path(), Purpose::ActiveFile);
        b.index = b.entries.iter().position(|e| e.name == "uno.txt").unwrap();
        assert!(!b.descend());
    }

    #[test]
    fn buscando_archivo_se_elige_el_archivo() {
        let d = tree();
        let mut b = Browser::open(d.path(), Purpose::ActiveFile);
        b.index = b.entries.iter().position(|e| e.name == "uno.txt").unwrap();
        assert_eq!(b.selection(), Some(d.path().join("uno.txt")));
    }

    #[test]
    fn parado_sobre_una_carpeta_no_se_elige_como_archivo() {
        let d = tree();
        let mut b = Browser::open(d.path(), Purpose::ActiveFile);
        b.index = b.entries.iter().position(|e| e.name == "alfa").unwrap();
        assert_eq!(b.selection(), None);
    }

    #[test]
    fn buscando_carpeta_se_elige_donde_uno_esta_no_donde_apunta() {
        // Parado sobre '..', confirmar NO elige el padre: eso sería navegar.
        let d = tree();
        let mut b = Browser::open(d.path(), Purpose::VoidDir);
        b.index = 0; // sobre '..'
        assert_eq!(b.selection(), Some(d.path().to_path_buf()));
    }

    #[test]
    fn cada_proposito_busca_lo_suyo() {
        assert_eq!(Purpose::ActiveFile.looking(), Looking::File);
        assert_eq!(Purpose::BookDir.looking(), Looking::Dir);
        assert_eq!(Purpose::VoidDir.looking(), Looking::Dir);
    }

    #[test]
    fn una_carpeta_vacia_no_rompe_nada() {
        let d = tempfile::tempdir().unwrap();
        let mut b = Browser::open(d.path(), Purpose::ActiveFile);
        b.move_by(1); // sólo está '..'
        assert!(b.current().is_some());
    }

    #[test]
    fn una_carpeta_que_no_se_puede_leer_da_una_lista_vacia_sin_panico() {
        let entries = list(Path::new("/no/existe/en/ningun/lado"), Looking::File);
        // Puede traer '..' y nada más; lo que importa es que no explote.
        assert!(entries.iter().all(|e| e.name == ".."));
    }
}
