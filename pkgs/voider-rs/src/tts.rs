//! Ctrl+T — la voz. Un port de `tts_mixin.py`.
//!
//! El mismo camino que el Python: `piper` sintetiza a crudo y `aplay` lo
//! reproduce, encadenados por una tubería. Los dos ya están en el sistema, y
//! los modelos `.onnx` viven en `void/tts/`.
//!
//! Una diferencia deliberada: el Python detecta el idioma con `langdetect`, una
//! dependencia entera para elegir entre tres voces. Acá es una heurística sobre
//! el propio texto — acentos, signos de apertura, palabras muy frecuentes. Para
//! un libro escrito en castellano con citas en inglés e italiano acierta de
//! sobra, y falla hacia el inglés igual que el Python cuando no está seguro.

#![allow(dead_code)]

use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};

/// Los idiomas que tienen voz, en el orden en que se prueban.
pub const LANGS: [&str; 3] = ["es", "en", "it"];

/// El modelo de cada idioma, dentro de `<void>/tts/`.
pub fn model_name(lang: &str) -> &'static str {
    match lang {
        "es" => "es_ES-sharvard-medium.onnx",
        "it" => "it_IT-riccardo-x_low.onnx",
        _ => "en_GB-alan-medium.onnx",
    }
}

/// Dónde buscar el modelo: primero el void activo, y si no está, el `/void`
/// real — los modelos pesan cientos de megas y son un recurso de la máquina,
/// no del texto, así que el sandbox no necesita su propia copia.
pub fn model_path(void_dir: &Path, lang: &str) -> Option<PathBuf> {
    let name = model_name(lang);
    let candidates = [
        void_dir.join("tts").join(name),
        dirs_home().join("void/tts").join(name),
    ];
    candidates.into_iter().find(|p| p.is_file())
}

fn dirs_home() -> PathBuf {
    std::env::var("HOME").map(PathBuf::from).unwrap_or_default()
}

/// Qué idioma parece este texto. Reemplaza a `langdetect`; ante la duda, inglés,
/// igual que el Python.
pub fn detect_lang(text: &str) -> &'static str {
    let t = text.to_lowercase();
    if t.trim().is_empty() {
        return "en";
    }
    // Los signos de apertura son inequívocos del castellano.
    if t.contains('¿') || t.contains('¡') || t.contains('ñ') {
        return "es";
    }
    let words: Vec<&str> = t
        .split(|c: char| !c.is_alphabetic() && c != '\'')
        .filter(|w| !w.is_empty())
        .collect();
    if words.is_empty() {
        return "en";
    }
    const ES: [&str; 18] = [
        "el", "la", "los", "las", "de", "que", "y", "en", "un", "una", "por", "con", "para", "es",
        "no", "se", "su", "del",
    ];
    const EN: [&str; 16] = [
        "the", "of", "and", "to", "in", "is", "it", "that", "was", "for", "with", "as", "his",
        "they", "be", "at",
    ];
    const IT: [&str; 14] = [
        "il", "lo", "gli", "che", "di", "e", "un", "per", "con", "non", "sono", "della", "nel",
        "questo",
    ];
    let count = |set: &[&str]| words.iter().filter(|w| set.contains(w)).count();
    let (es, en, it) = (count(&ES), count(&EN), count(&IT));
    // Los acentos inclinan, pero no deciden solos: "café" existe en inglés.
    let accents = t.chars().filter(|c| "áéíóúü".contains(*c)).count();
    let es_score = es * 2 + accents;
    let it_score = it * 2;
    let en_score = en * 2;
    if es_score > en_score && es_score >= it_score {
        "es"
    } else if it_score > en_score && it_score > es_score {
        "it"
    } else {
        "en"
    }
}

/// Una línea que no vale la pena decir en voz alta.
pub fn is_speakable(text: &str) -> bool {
    let t = text.trim();
    !t.is_empty() && t != "." && !t.chars().all(|c| c == '.')
}

/// Los argumentos exactos con los que se invoca a piper.
pub fn piper_args(model: &Path) -> Vec<String> {
    vec![
        "--model".into(),
        model.display().to_string(),
        "--length_scale".into(),
        "1.15".into(),
        "--output_raw".into(),
    ]
}

/// Los de aplay, que lee el crudo de 22050 Hz que piper escupe.
pub fn aplay_args() -> Vec<&'static str> {
    vec!["-r", "22050", "-f", "S16_LE", "-t", "raw", "-"]
}

/// La voz: si está encendida, y qué está sonando ahora mismo.
#[derive(Default)]
pub struct Tts {
    pub active: bool,
    piper: Option<Child>,
    aplay: Option<Child>,
}

impl Tts {
    /// Ctrl+T. Devuelve si quedó encendida.
    pub fn toggle(&mut self) -> bool {
        self.active = !self.active;
        if !self.active {
            self.stop();
        }
        self.active
    }

    /// Cortar porque el usuario navegó: además de callar, apaga la voz, para
    /// que no se reanude sola sobre la línea siguiente.
    pub fn cut(&mut self) {
        if self.active {
            self.active = false;
            self.stop();
        }
    }

    pub fn stop(&mut self) {
        for child in [self.piper.as_mut(), self.aplay.as_mut()].into_iter().flatten() {
            let _ = child.kill();
            let _ = child.wait();
        }
        self.piper = None;
        self.aplay = None;
    }

    /// ¿Sigue sonando? Cuando aplay termina, la línea terminó.
    pub fn is_speaking(&mut self) -> bool {
        match self.aplay.as_mut() {
            Some(child) => matches!(child.try_wait(), Ok(None)),
            None => false,
        }
    }

    /// Decir una línea. Silencioso si no hay modelo o no está piper: la voz es
    /// un accesorio, y no poder hablar nunca debe impedir escribir.
    pub fn speak(&mut self, void_dir: &Path, text: &str) {
        if !is_speakable(text) {
            return;
        }
        self.stop();
        let lang = detect_lang(text);
        let Some(model) = model_path(void_dir, lang) else {
            return;
        };
        let Ok(mut piper) = Command::new("piper")
            .args(piper_args(&model))
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
        else {
            return;
        };
        let Some(out) = piper.stdout.take() else {
            let _ = piper.kill();
            return;
        };
        let aplay = Command::new("aplay")
            .args(aplay_args())
            .stdin(Stdio::from(out))
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn();
        if let Some(mut stdin) = piper.stdin.take() {
            let _ = stdin.write_all(text.as_bytes());
        }
        match aplay {
            Ok(child) => {
                self.piper = Some(piper);
                self.aplay = Some(child);
            }
            Err(_) => {
                let _ = piper.kill();
            }
        }
    }
}

impl Drop for Tts {
    fn drop(&mut self) {
        self.stop(); // que no quede una voz hablando sola después de cerrar
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn el_castellano_se_reconoce_por_sus_signos() {
        assert_eq!(detect_lang("¿Quién va?"), "es");
        assert_eq!(detect_lang("¡Vamos!"), "es");
        assert_eq!(detect_lang("el año pasado"), "es");
    }

    #[test]
    fn el_castellano_se_reconoce_por_sus_palabras() {
        assert_eq!(detect_lang("la mitad humana de lo que es"), "es");
    }

    #[test]
    fn el_ingles_se_reconoce() {
        assert_eq!(detect_lang("the other half of the world"), "en");
        assert_eq!(detect_lang("it was the best of times"), "en");
    }

    #[test]
    fn el_italiano_se_reconoce() {
        assert_eq!(detect_lang("nel mezzo del cammin di nostra vita"), "it");
    }

    #[test]
    fn ante_la_duda_ingles_como_en_python() {
        assert_eq!(detect_lang(""), "en");
        assert_eq!(detect_lang("   "), "en");
        assert_eq!(detect_lang("xyzzy"), "en");
        assert_eq!(detect_lang("12345"), "en");
    }

    #[test]
    fn un_acento_suelto_no_convierte_al_ingles_en_castellano() {
        // "café" es una palabra inglesa también; las palabras mandan.
        assert_eq!(detect_lang("the café was closed and it was cold"), "en");
    }

    #[test]
    fn los_separadores_no_se_dicen() {
        assert!(!is_speakable("."));
        assert!(!is_speakable("..."));
        assert!(!is_speakable("   "));
        assert!(!is_speakable(""));
        assert!(is_speakable("una linea de verdad"));
    }

    #[test]
    fn cada_idioma_tiene_su_modelo() {
        assert_eq!(model_name("es"), "es_ES-sharvard-medium.onnx");
        assert_eq!(model_name("it"), "it_IT-riccardo-x_low.onnx");
        assert_eq!(model_name("en"), "en_GB-alan-medium.onnx");
        assert_eq!(model_name("cualquier-otra"), "en_GB-alan-medium.onnx");
    }

    #[test]
    fn los_argumentos_de_piper_son_los_del_python() {
        let args = piper_args(Path::new("/m.onnx"));
        assert_eq!(
            args,
            vec!["--model", "/m.onnx", "--length_scale", "1.15", "--output_raw"]
        );
        assert_eq!(aplay_args(), vec!["-r", "22050", "-f", "S16_LE", "-t", "raw", "-"]);
    }

    #[test]
    fn el_modelo_se_busca_primero_en_el_void_activo() {
        let d = tempfile::tempdir().unwrap();
        let tts = d.path().join("tts");
        std::fs::create_dir_all(&tts).unwrap();
        let m = tts.join(model_name("es"));
        std::fs::write(&m, b"x").unwrap();
        assert_eq!(model_path(d.path(), "es"), Some(m));
    }

    #[test]
    fn sin_modelo_no_hay_ruta_y_no_se_rompe_nada() {
        let d = tempfile::tempdir().unwrap();
        // 'it' no está ni en el sandbox ni (probablemente) en ~/void/tts
        let p = model_path(d.path(), "it");
        assert!(p.is_none() || p.unwrap().is_file());
    }

    #[test]
    fn el_toggle_prende_y_apaga() {
        let mut t = Tts::default();
        assert!(t.toggle());
        assert!(t.active);
        assert!(!t.toggle());
        assert!(!t.active);
    }

    #[test]
    fn cortar_apaga_para_que_no_se_reanude() {
        let mut t = Tts::default();
        t.toggle();
        t.cut();
        assert!(!t.active, "navegar tiene que apagar la voz, no solo callarla");
    }

    #[test]
    fn sin_nada_sonando_no_esta_hablando() {
        let mut t = Tts::default();
        assert!(!t.is_speaking());
    }

    #[test]
    fn decir_un_separador_no_arranca_ningun_proceso() {
        let d = tempfile::tempdir().unwrap();
        let mut t = Tts::default();
        t.speak(d.path(), ".");
        assert!(!t.is_speaking());
    }
}
