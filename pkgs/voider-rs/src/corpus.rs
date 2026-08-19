//! El lado `O/` — el corpus que se lee, no el que se escribe.
//!
//! Port de `f5678_mixin.py`. `O/` es un enlace a un corpus enorme (76 mil
//! libros acá), así que nada lo recorre entero en vivo: hay un cache de nombres
//! en `.o_files_cache.txt`, y el "working set" es un puñado de libros elegidos
//! a mano, uno por ranura, que persiste en `.working_set.json`.
//!
//! Ese JSON lo comparten las dos aplicaciones, y los nombres del corpus traen
//! comas, comillas y acentos. Por eso acá sí se usa `serde_json` en vez del
//! parseo a mano que usa `config.rs`: aquel archivo es nuestro y conviene que
//! sea reparable a ojo; este es del Python también, y escribirlo mal sería
//! corromperle el estado a la otra aplicación.

#![allow(dead_code)]

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

/// Lo que muestra una ranura vacía.
pub const EMPTY: &str = "∅";

const WS_FILE: &str = ".working_set.json";
const CACHE_FILE: &str = ".o_files_cache.txt";

/// Una ranura del working set: un libro y por dónde vas leyéndolo.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Slot {
    #[serde(default)]
    pub path: String,
    #[serde(default)]
    pub position: usize,
}

impl Slot {
    pub fn empty() -> Self {
        Self { path: String::new(), position: 0 }
    }
    pub fn is_empty(&self) -> bool {
        self.path.is_empty()
    }
}

/// El archivo tal como está en disco, con el mismo nombre de campos que el
/// Python usa, para que las dos aplicaciones lo lean igual.
#[derive(Debug, Default, Serialize, Deserialize)]
struct WsFile {
    #[serde(default)]
    books: Vec<Slot>,
    #[serde(default)]
    browser_index: usize,
    // El formato viejo, que el Python todavía migra.
    #[serde(default)]
    locked: Vec<Slot>,
    #[serde(default)]
    unlocked: Vec<Slot>,
}

/// El conjunto de libros elegidos a mano. Nunca se autocompleta: cada ranura la
/// llenó alguien apretando Tab.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WorkingSet {
    pub books: Vec<Slot>,
    pub browser_index: usize,
}

impl Default for WorkingSet {
    fn default() -> Self {
        // Sin nada guardado, una sola ranura vacía desde la cual empezar.
        Self { books: vec![Slot::empty()], browser_index: 1 }
    }
}

pub fn ws_path(o_dir: &Path) -> PathBuf {
    o_dir.join(WS_FILE)
}

pub fn cache_path(void_dir: &Path) -> PathBuf {
    void_dir.join(CACHE_FILE)
}

impl WorkingSet {
    /// Leer el conjunto. Una ranura cuyo libro ya no está en `O/` se descarta:
    /// mejor una ranura menos que un fantasma que no se puede abrir.
    pub fn load(o_dir: &Path) -> Self {
        let Ok(text) = std::fs::read_to_string(ws_path(o_dir)) else {
            return Self::default();
        };
        let Ok(file) = serde_json::from_str::<WsFile>(&text) else {
            return Self::default();
        };
        let mut books = file.books;
        if books.is_empty() {
            // Formato viejo: dos listas que se concatenan.
            books = file.locked;
            books.extend(file.unlocked);
        }
        books.retain(|b| !b.path.is_empty() && o_dir.join(&b.path).exists());
        if books.is_empty() {
            return Self::default();
        }
        Self { books, browser_index: file.browser_index }
    }

    /// Guardar. Sólo las ranuras llenas: una vacía es un estado de trabajo, no
    /// algo que valga la pena recordar entre sesiones.
    pub fn save(&self, o_dir: &Path) -> std::io::Result<()> {
        let file = WsFile {
            books: self.books.iter().filter(|b| !b.is_empty()).cloned().collect(),
            browser_index: self.browser_index,
            locked: Vec::new(),
            unlocked: Vec::new(),
        };
        let text = serde_json::to_string_pretty(&file)
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidData, e))?;
        std::fs::write(ws_path(o_dir), text)
    }

    /// El anillo que ve F7: un separador antes de cada ranura.
    pub fn browser_entries(&self) -> Vec<String> {
        let mut out = Vec::new();
        for slot in &self.books {
            out.push(".".to_string());
            out.push(slot_display(slot));
        }
        if out.is_empty() {
            out.push(".".to_string());
        }
        out
    }

    /// Qué ranura corresponde a una posición del anillo de F7.
    /// El anillo es `['.', ranura0, '.', ranura1, …]`, así que el libro en la
    /// posición r es la ranura (r-1)/2; las pares son separadores.
    pub fn slot_at(&self, ring_index: usize) -> Option<usize> {
        if self.books.is_empty() || ring_index == 0 || ring_index % 2 == 0 {
            return None;
        }
        let i = (ring_index - 1) / 2;
        (i < self.books.len()).then_some(i)
    }

    /// La posición del anillo donde vive una ranura.
    pub fn ring_index_of(&self, slot: usize) -> usize {
        2 * slot + 1
    }

    /// Tab en F7: llenar (o volver a sortear) la ranura actual con un libro al
    /// azar, sin repetir ninguno que ya esté en otra ranura.
    pub fn randomize(&mut self, slot: usize, all_books: &[String]) -> Option<String> {
        if slot >= self.books.len() {
            return None;
        }
        let used: Vec<&String> = self.books.iter().map(|b| &b.path).filter(|p| !p.is_empty()).collect();
        let mut candidates: Vec<&String> =
            all_books.iter().filter(|f| !used.contains(f)).collect();
        if candidates.is_empty() {
            return None;
        }
        crate::library::shuffle(&mut candidates);
        let chosen = candidates[0].clone();
        self.books[slot] = Slot { path: chosen.clone(), position: 0 };
        Some(chosen)
    }

    /// Shift+Enter en F7: una ranura vacía nueva debajo de la actual.
    pub fn add_slot(&mut self, after: Option<usize>) -> usize {
        let at = after.map(|s| s + 1).unwrap_or(self.books.len());
        self.books.insert(at, Slot::empty());
        at
    }

    /// Ctrl+Delete en F7: sacar la ranura. Nunca baja de una: si se vacía del
    /// todo, queda una ranura vacía desde la cual reconstruir.
    /// El libro abierto en F6 no se puede sacar — así, borrar todo lo demás deja
    /// ese libro cargado y no un fantasma en el lector.
    pub fn remove_slot(&mut self, slot: usize, open_in_reader: Option<&str>) -> Option<usize> {
        if slot >= self.books.len() {
            return None;
        }
        let path = self.books[slot].path.clone();
        if !path.is_empty() && open_in_reader == Some(path.as_str()) {
            return None;
        }
        self.books.remove(slot);
        if self.books.is_empty() {
            self.books.push(Slot::empty());
            return Some(0);
        }
        Some(slot.min(self.books.len() - 1))
    }

    /// Recordar por dónde ibas en un libro.
    pub fn save_position(&mut self, fname: &str, position: usize) {
        if let Some(slot) = self.books.iter_mut().find(|b| b.path == fname) {
            slot.position = position;
        }
    }

    pub fn position_of(&self, fname: &str) -> usize {
        self.books
            .iter()
            .find(|b| b.path == fname)
            .map(|b| b.position)
            .unwrap_or(0)
    }
}

/// Lo que muestra una ranura en F7.
pub fn slot_display(slot: &Slot) -> String {
    if slot.is_empty() {
        EMPTY.to_string()
    } else {
        clean_book_title(&slot.path)
    }
}

/// El nombre de archivo de un libro de Gutenberg, hecho un título legible.
/// Port de `_clean_book_title`, sin traer un motor de expresiones regulares por
/// media docena de reglas fijas.
pub fn clean_book_title(fname: &str) -> String {
    let stem = fname.rsplit_once('.').map(|(a, _)| a).unwrap_or(fname);
    let mut name = strip_gutenberg_id(stem);
    name = name.replace('_', " ").replace('-', " ");
    for noise in ["project gutenberg", "ebook of", "the ebook"] {
        name = remove_ci(&name, noise);
    }
    name = strip_by_author(&name);
    name = name.split_whitespace().collect::<Vec<_>>().join(" ");
    let name = name.trim().to_string();
    if name.is_empty() {
        return fname.to_string();
    }
    // Un título todo en minúscula o todo en mayúscula se capitaliza.
    if name.chars().filter(|c| c.is_alphabetic()).all(|c| c.is_lowercase())
        || name.chars().filter(|c| c.is_alphabetic()).all(|c| c.is_uppercase())
    {
        return title_case(&name);
    }
    name
}

/// `pg1234-`, `pg1234_5-`, `42-` al principio.
fn strip_gutenberg_id(s: &str) -> String {
    let lower = s.to_lowercase();
    let rest = if let Some(after) = lower.strip_prefix("pg") {
        let digits = after.chars().take_while(|c| c.is_ascii_digit()).count();
        if digits > 0 {
            let mut i = 2 + digits;
            let bytes: Vec<char> = s.chars().collect();
            // separadores y un segundo número opcional
            while i < bytes.len() && (bytes[i] == '-' || bytes[i] == '_') {
                i += 1;
            }
            while i < bytes.len() && bytes[i].is_ascii_digit() {
                i += 1;
            }
            while i < bytes.len() && (bytes[i] == '-' || bytes[i] == '_') {
                i += 1;
            }
            Some(bytes[i..].iter().collect::<String>())
        } else {
            None
        }
    } else {
        None
    };
    if let Some(r) = rest {
        return r;
    }
    // `42-` o `42_`
    let chars: Vec<char> = s.chars().collect();
    let digits = chars.iter().take_while(|c| c.is_ascii_digit()).count();
    if digits > 0 && chars.get(digits).is_some_and(|c| *c == '-' || *c == '_') {
        return chars[digits + 1..].iter().collect();
    }
    s.to_string()
}

/// Sacar una frase sin importar mayúsculas.
fn remove_ci(haystack: &str, needle: &str) -> String {
    let mut out = String::new();
    let mut rest = haystack;
    loop {
        let lower = rest.to_lowercase();
        match lower.find(needle) {
            Some(i) => {
                out.push_str(&rest[..i]);
                rest = &rest[i + needle.len()..];
            }
            None => {
                out.push_str(rest);
                return out;
            }
        }
    }
}

/// `… by Charles Dickens` al final.
fn strip_by_author(s: &str) -> String {
    let words: Vec<&str> = s.split_whitespace().collect();
    for (i, w) in words.iter().enumerate() {
        if !w.eq_ignore_ascii_case("by") || i == 0 || i + 1 >= words.len() {
            continue;
        }
        // Todo lo que sigue tiene que parecer un nombre propio.
        let tail = &words[i + 1..];
        let looks_like_a_name = tail
            .iter()
            .all(|w| w.chars().next().is_some_and(|c| c.is_uppercase()) && w.chars().all(|c| c.is_alphabetic()));
        if looks_like_a_name {
            return words[..i].join(" ");
        }
    }
    s.to_string()
}

fn title_case(s: &str) -> String {
    s.split(' ')
        .map(|w| {
            let mut c = w.chars();
            match c.next() {
                Some(f) => f.to_uppercase().collect::<String>() + &c.as_str().to_lowercase(),
                None => String::new(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

/// Los nombres del corpus, desde el cache. Nunca se recorre `O/` en vivo: son
/// decenas de miles de archivos y la lista cambia muy de vez en cuando.
pub fn load_cache(void_dir: &Path) -> Vec<String> {
    std::fs::read_to_string(cache_path(void_dir))
        .map(|t| t.lines().filter(|l| !l.trim().is_empty()).map(str::to_string).collect())
        .unwrap_or_default()
}

/// Rehacer el cache leyendo `O/`. Devuelve cuántos encontró.
pub fn rebuild_cache(void_dir: &Path, o_dir: &Path) -> std::io::Result<usize> {
    let mut files: Vec<String> = std::fs::read_dir(o_dir)?
        .flatten()
        .filter_map(|e| e.file_name().to_str().map(str::to_string))
        .filter(|n| n.to_lowercase().ends_with(".txt") && !n.starts_with('.'))
        .collect();
    files.sort();
    std::fs::write(cache_path(void_dir), files.join("\n"))?;
    Ok(files.len())
}

/// Una línea al azar de un archivo al azar del directorio. El oráculo.
/// Port de `_pick_oracle_line`; devuelve "..." cuando no hay nada, como el Python.
pub fn oracle_line(dir: &Path, names: &[String]) -> String {
    if names.is_empty() {
        return "...".to_string();
    }
    let mut pool: Vec<&String> = names.iter().collect();
    crate::library::shuffle(&mut pool);
    for name in pool.into_iter().take(20) {
        let path = dir.join(name);
        let Ok(text) = std::fs::read_to_string(&path) else {
            continue;
        };
        let mut lines: Vec<&str> = text
            .lines()
            .map(str::trim)
            .filter(|l| !l.is_empty() && *l != ".")
            .collect();
        if lines.is_empty() {
            continue;
        }
        crate::library::shuffle(&mut lines);
        return lines[0].to_string();
    }
    "...".to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── títulos ───────────────────────────────────────────────────────────────

    #[test]
    fn se_saca_la_extension() {
        assert_eq!(clean_book_title("Moby Dick.txt"), "Moby Dick");
    }

    #[test]
    fn se_saca_el_id_de_gutenberg() {
        assert_eq!(clean_book_title("pg1234-Moby Dick.txt"), "Moby Dick");
        assert_eq!(clean_book_title("PG42_1-Hamlet.txt"), "Hamlet");
        assert_eq!(clean_book_title("1661-Sherlock.txt"), "Sherlock");
    }

    #[test]
    fn se_saca_el_ruido_de_gutenberg() {
        // Ojo: queda "The Hamlet", no "Hamlet" — el Python saca "project
        // gutenberg" y "ebook of" pero deja el "The" que los precedía, porque
        // su regla "the ebook" ya no matchea una vez sacado "ebook of".
        // Verificado corriendo _clean_book_title: devuelve exactamente esto.
        // Es una rareza suya, y un espejo copia también las rarezas.
        assert_eq!(clean_book_title("The Project Gutenberg eBook of Hamlet.txt"), "The Hamlet");
    }

    #[test]
    fn se_saca_el_autor_del_final() {
        assert_eq!(clean_book_title("Great Expectations by Charles Dickens.txt"), "Great Expectations");
    }

    #[test]
    fn un_by_que_es_parte_del_titulo_se_respeta() {
        // "Passed by" no es un autor; no hay que comerse el final.
        assert_eq!(clean_book_title("The House by the Sea.txt"), "The House by the Sea");
    }

    #[test]
    fn los_guiones_bajos_son_espacios() {
        assert_eq!(clean_book_title("Samlede_Vaerker_Andet_Bind.txt"), "Samlede Vaerker Andet Bind");
    }

    #[test]
    fn todo_minuscula_se_capitaliza() {
        assert_eq!(clean_book_title("moby dick.txt"), "Moby Dick");
    }

    #[test]
    fn los_acentos_sobreviven() {
        assert_eq!(clean_book_title("Syksyä Runoja.txt"), "Syksyä Runoja");
    }

    #[test]
    fn un_nombre_que_queda_vacio_se_devuelve_entero() {
        let raw = "project gutenberg.txt";
        assert!(!clean_book_title(raw).is_empty());
    }

    // ── working set ───────────────────────────────────────────────────────────

    fn o_dir_with(books: &[&str]) -> tempfile::TempDir {
        let d = tempfile::tempdir().unwrap();
        for b in books {
            std::fs::write(d.path().join(b), "una linea\n.\notra linea\n").unwrap();
        }
        d
    }

    #[test]
    fn sin_archivo_hay_una_ranura_vacia() {
        let d = tempfile::tempdir().unwrap();
        let ws = WorkingSet::load(d.path());
        assert_eq!(ws.books.len(), 1);
        assert!(ws.books[0].is_empty());
    }

    #[test]
    fn el_conjunto_va_y_vuelve_del_disco() {
        let d = o_dir_with(&["a.txt", "b.txt"]);
        let ws = WorkingSet {
            books: vec![
                Slot { path: "a.txt".into(), position: 7 },
                Slot { path: "b.txt".into(), position: 0 },
            ],
            browser_index: 3,
        };
        ws.save(d.path()).unwrap();
        assert_eq!(WorkingSet::load(d.path()), ws);
    }

    #[test]
    fn el_json_es_el_mismo_que_lee_el_python() {
        let d = o_dir_with(&["a.txt"]);
        WorkingSet { books: vec![Slot { path: "a.txt".into(), position: 3 }], browser_index: 1 }
            .save(d.path())
            .unwrap();
        let text = std::fs::read_to_string(ws_path(d.path())).unwrap();
        assert!(text.contains("\"books\""));
        assert!(text.contains("\"path\""));
        assert!(text.contains("\"position\""));
        assert!(text.contains("\"browser_index\""));
    }

    #[test]
    fn un_nombre_con_comas_y_comillas_sobrevive_al_json() {
        // Los nombres del corpus son así de sucios; por esto se usa serde.
        let raw = "Aaltonen, Hilja - Syksyä _ $b \"Runoja\".txt";
        let d = o_dir_with(&[raw]);
        WorkingSet { books: vec![Slot { path: raw.into(), position: 0 }], browser_index: 1 }
            .save(d.path())
            .unwrap();
        assert_eq!(WorkingSet::load(d.path()).books[0].path, raw);
    }

    #[test]
    fn una_ranura_cuyo_libro_ya_no_esta_se_descarta() {
        let d = o_dir_with(&["queda.txt"]);
        WorkingSet {
            books: vec![
                Slot { path: "queda.txt".into(), position: 0 },
                Slot { path: "borrado.txt".into(), position: 0 },
            ],
            browser_index: 1,
        }
        .save(d.path())
        .unwrap();
        let ws = WorkingSet::load(d.path());
        assert_eq!(ws.books.len(), 1);
        assert_eq!(ws.books[0].path, "queda.txt");
    }

    #[test]
    fn las_ranuras_vacias_no_se_guardan() {
        let d = o_dir_with(&["a.txt"]);
        WorkingSet {
            books: vec![Slot { path: "a.txt".into(), position: 0 }, Slot::empty()],
            browser_index: 1,
        }
        .save(d.path())
        .unwrap();
        let text = std::fs::read_to_string(ws_path(d.path())).unwrap();
        assert_eq!(text.matches("\"path\"").count(), 1);
    }

    #[test]
    fn se_lee_el_formato_viejo_de_locked_y_unlocked() {
        let d = o_dir_with(&["a.txt", "b.txt"]);
        std::fs::write(
            ws_path(d.path()),
            r#"{"locked":[{"path":"a.txt","position":1}],"unlocked":[{"path":"b.txt","position":2}]}"#,
        )
        .unwrap();
        let ws = WorkingSet::load(d.path());
        assert_eq!(ws.books.len(), 2);
        assert_eq!(ws.books[0].path, "a.txt");
        assert_eq!(ws.books[1].position, 2);
    }

    #[test]
    fn un_json_roto_no_impide_abrir() {
        let d = tempfile::tempdir().unwrap();
        std::fs::write(ws_path(d.path()), "{ no soy json").unwrap();
        assert_eq!(WorkingSet::load(d.path()), WorkingSet::default());
    }

    // ── el anillo de F7 ───────────────────────────────────────────────────────

    #[test]
    fn el_anillo_pone_un_separador_antes_de_cada_ranura() {
        let ws = WorkingSet {
            books: vec![Slot { path: "a.txt".into(), position: 0 }, Slot::empty()],
            browser_index: 1,
        };
        assert_eq!(ws.browser_entries(), vec![".", "A", ".", EMPTY]);
    }

    #[test]
    fn las_posiciones_pares_del_anillo_son_separadores() {
        let ws = WorkingSet {
            books: vec![Slot::empty(), Slot::empty()],
            browser_index: 1,
        };
        assert_eq!(ws.slot_at(0), None);
        assert_eq!(ws.slot_at(1), Some(0));
        assert_eq!(ws.slot_at(2), None);
        assert_eq!(ws.slot_at(3), Some(1));
        assert_eq!(ws.slot_at(5), None); // fuera de rango
        assert_eq!(ws.ring_index_of(1), 3);
    }

    // ── operaciones ───────────────────────────────────────────────────────────

    #[test]
    fn tab_llena_la_ranura_sin_repetir_libros() {
        let mut ws = WorkingSet {
            books: vec![Slot { path: "a.txt".into(), position: 0 }, Slot::empty()],
            browser_index: 1,
        };
        let all = vec!["a.txt".to_string(), "b.txt".to_string()];
        for _ in 0..10 {
            ws.books[1] = Slot::empty();
            let got = ws.randomize(1, &all);
            assert_eq!(got, Some("b.txt".to_string()), "no debe repetir el que ya está");
        }
    }

    #[test]
    fn sin_libros_libres_tab_no_hace_nada() {
        let mut ws = WorkingSet {
            books: vec![Slot { path: "a.txt".into(), position: 0 }],
            browser_index: 1,
        };
        assert_eq!(ws.randomize(0, &["a.txt".to_string()]), None);
        assert_eq!(ws.books[0].path, "a.txt"); // quedó como estaba
    }

    #[test]
    fn una_ranura_nueva_va_debajo_de_la_actual() {
        let mut ws = WorkingSet {
            books: vec![Slot { path: "a.txt".into(), position: 0 }, Slot { path: "b.txt".into(), position: 0 }],
            browser_index: 1,
        };
        assert_eq!(ws.add_slot(Some(0)), 1);
        assert!(ws.books[1].is_empty());
        assert_eq!(ws.books[2].path, "b.txt");
    }

    #[test]
    fn sacar_ranuras_nunca_baja_de_una() {
        let mut ws = WorkingSet {
            books: vec![Slot { path: "a.txt".into(), position: 0 }],
            browser_index: 1,
        };
        assert_eq!(ws.remove_slot(0, None), Some(0));
        assert_eq!(ws.books.len(), 1);
        assert!(ws.books[0].is_empty(), "queda una vacía para reconstruir");
    }

    #[test]
    fn el_libro_abierto_en_el_lector_no_se_puede_sacar() {
        let mut ws = WorkingSet {
            books: vec![Slot { path: "leyendo.txt".into(), position: 0 }, Slot::empty()],
            browser_index: 1,
        };
        assert_eq!(ws.remove_slot(0, Some("leyendo.txt")), None);
        assert_eq!(ws.books.len(), 2, "no se sacó nada");
    }

    #[test]
    fn la_posicion_de_lectura_se_recuerda_por_libro() {
        let mut ws = WorkingSet {
            books: vec![Slot { path: "a.txt".into(), position: 0 }],
            browser_index: 1,
        };
        ws.save_position("a.txt", 42);
        assert_eq!(ws.position_of("a.txt"), 42);
        assert_eq!(ws.position_of("no-esta.txt"), 0);
    }

    // ── cache y oráculo ───────────────────────────────────────────────────────

    #[test]
    fn el_cache_va_y_vuelve() {
        let void = tempfile::tempdir().unwrap();
        let o = o_dir_with(&["b.txt", "a.txt", ".oculto.txt", "no.md"]);
        assert_eq!(rebuild_cache(void.path(), o.path()).unwrap(), 2);
        assert_eq!(load_cache(void.path()), vec!["a.txt", "b.txt"]); // ordenado
    }

    #[test]
    fn sin_cache_la_lista_esta_vacia_y_no_se_rompe() {
        let d = tempfile::tempdir().unwrap();
        assert!(load_cache(d.path()).is_empty());
    }

    #[test]
    fn el_oraculo_devuelve_una_linea_del_corpus() {
        let o = o_dir_with(&["a.txt"]);
        let line = oracle_line(o.path(), &["a.txt".to_string()]);
        assert!(line == "una linea" || line == "otra linea");
    }

    #[test]
    fn el_oraculo_sin_corpus_devuelve_puntos_como_el_python() {
        let d = tempfile::tempdir().unwrap();
        assert_eq!(oracle_line(d.path(), &[]), "...");
        assert_eq!(oracle_line(d.path(), &["no-existe.txt".to_string()]), "...");
    }

    #[test]
    fn el_oraculo_nunca_devuelve_un_separador() {
        let d = tempfile::tempdir().unwrap();
        std::fs::write(d.path().join("puntos.txt"), ".\n.\n.\n").unwrap();
        assert_eq!(oracle_line(d.path(), &["puntos.txt".to_string()]), "...");
    }
}
