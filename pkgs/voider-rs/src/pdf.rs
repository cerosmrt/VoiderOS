//! Sacar el libro de la pantalla: PDF e impresión.
//!
//! Port de `_build_reading_html` / `_render_doc` / `export_doc` / `print_doc`.
//! El Python arma HTML y lo pasa por `QTextDocument` a un `QPrinter`. Acá el
//! camino es el mismo — HTML a PDF — porque `printpdf` también renderiza HTML,
//! así que el formato del libro se describe una sola vez y en el mismo lenguaje.
//!
//! Eso además trae la justificación gratis: `text-align: justify` en el PDF es
//! lo que F4 en pantalla todavía no puede hacer (egui no justifica). El libro
//! impreso sale justificado aunque en pantalla se lea en bandera.

#![allow(dead_code)]

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use crate::reading::Section;

/// A5, en milímetros — el tamaño de un libro que se sostiene con una mano.
pub const PAGE_W_MM: f32 = 148.0;
pub const PAGE_H_MM: f32 = 210.0;

/// Escapar lo que va adentro del HTML. Un texto puede tener `<`, `&` o comillas,
/// y sin esto un `<` del manuscrito se comería el resto del párrafo.
pub fn escape(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&#39;"),
            _ => out.push(c),
        }
    }
    out
}

/// El HTML del libro: un título por sección y sus párrafos justificados.
///
/// Cada párrafo lleva su ancla `vparaN`, correlativa a través de TODO el
/// documento — como en el Python, y como espera su `test_open_position`. Es lo
/// que permitiría abrir el PDF en el párrafo que estabas leyendo.
pub fn book_html(sections: &[Section], font_family: &str) -> String {
    let mut out = String::new();
    out.push_str("<html><head><style>");
    out.push_str(&format!(
        "body {{ font-family: '{}', serif; font-size: 11pt; line-height: 1.45; \
         margin: 18mm 16mm; color: #111; }}",
        escape(font_family)
    ));
    out.push_str(
        "h2 { text-align: center; font-weight: normal; font-size: 13pt; \
         margin: 3em 0 2em; }",
    );
    // La sangría francesa del libro: el primer párrafo de cada capítulo va sin
    // sangrar, los que siguen sí. Es como se compone un libro de verdad.
    out.push_str("p { text-align: justify; margin: 0; text-indent: 1.2em; }");
    out.push_str("p.first { text-indent: 0; }");
    out.push_str("</style></head><body>");

    let mut ordinal = 0usize;
    for section in sections {
        if !section.title.is_empty() {
            out.push_str(&format!("<h2>{}</h2>", escape(&section.title)));
        }
        for (i, para) in section.paragraphs.iter().enumerate() {
            let class = if i == 0 { " class=\"first\"" } else { "" };
            out.push_str(&format!(
                "<p{class}><a name=\"vpara{ordinal}\"></a>{}</p>",
                escape(para)
            ));
            ordinal += 1;
        }
    }
    out.push_str("</body></html>");
    out
}

/// Dónde va el PDF de un documento: al lado del void, con el nombre del texto.
pub fn default_path(void_dir: &Path, title: &str) -> PathBuf {
    let safe: String = title
        .chars()
        .map(|c| if "/\\:*?\"<>|".contains(c) { '-' } else { c })
        .collect();
    let safe = safe.trim().to_string();
    let stem = if safe.is_empty() { "voider".to_string() } else { safe };
    void_dir.join(format!("{stem}.pdf"))
}

/// HTML → PDF. La fuente se incrusta si se encontró en la máquina, así el PDF
/// se ve igual en cualquier lado; si no, el renderizador usa la suya.
pub fn render(html: &str, font_family: &str, font_bytes: Option<Vec<u8>>) -> Result<Vec<u8>, String> {
    use printpdf::*;

    let images = BTreeMap::new();
    let mut fonts: BTreeMap<String, Base64OrRaw> = BTreeMap::new();
    if let Some(bytes) = font_bytes {
        fonts.insert(font_family.to_string(), Base64OrRaw::Raw(bytes));
    }
    let options = GeneratePdfOptions {
        page_width: Some(PAGE_W_MM as f32),
        page_height: Some(PAGE_H_MM as f32),
        ..Default::default()
    };
    let mut warnings = Vec::new();
    let doc = PdfDocument::from_html(html, &images, &fonts, &options, &mut warnings)
        .map_err(|e| format!("no se pudo componer el PDF: {e}"))?;
    let mut save_warnings = Vec::new();
    Ok(doc.save(&PdfSaveOptions::default(), &mut save_warnings))
}

/// Mandar un PDF ya escrito a la impresora del sistema.
///
/// El Python abre el diálogo de impresión de Qt. Acá se pasa a `lp`, que es lo
/// que hay en Linux — y si CUPS no está instalado se dice, en vez de fallar en
/// silencio. En esta máquina hoy NO está: imprimir necesita habilitarlo primero.
pub fn send_to_printer(path: &Path) -> Result<(), String> {
    match std::process::Command::new("lp").arg(path).output() {
        Ok(out) if out.status.success() => Ok(()),
        Ok(out) => Err(String::from_utf8_lossy(&out.stderr).trim().to_string()),
        Err(_) => Err("no hay 'lp' — falta habilitar CUPS en el sistema".to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sec(title: &str, paras: &[&str]) -> Section {
        Section {
            title: title.to_string(),
            paragraphs: paras.iter().map(|s| s.to_string()).collect(),
        }
    }

    #[test]
    fn lo_que_rompe_el_html_se_escapa() {
        assert_eq!(escape("a < b & c > d"), "a &lt; b &amp; c &gt; d");
        assert_eq!(escape("dijo \"basta\""), "dijo &quot;basta&quot;");
    }

    #[test]
    fn un_menor_en_el_manuscrito_no_se_come_el_parrafo() {
        let html = book_html(&[sec("T", &["el signo < y lo que sigue"])], "EB Garamond");
        assert!(html.contains("&lt;"));
        assert!(html.contains("y lo que sigue"), "se perdió el resto del párrafo");
    }

    #[test]
    fn los_acentos_pasan_intactos() {
        let html = book_html(&[sec("Capítulo", &["la mitad húmana está acá"])], "EB Garamond");
        assert!(html.contains("la mitad húmana está acá"));
        assert!(html.contains("Capítulo"));
    }

    #[test]
    fn cada_parrafo_tiene_su_ancla() {
        // La expectativa del test_open_position del Python, exactamente.
        let html = book_html(&[sec("T", &["a", "b", "c"])], "EB Garamond");
        assert!(html.contains("name=\"vpara0\""));
        assert!(html.contains("name=\"vpara1\""));
        assert!(html.contains("name=\"vpara2\""));
    }

    #[test]
    fn las_anclas_siguen_contando_entre_capitulos() {
        let html = book_html(&[sec("Uno", &["a", "b"]), sec("Dos", &["c"])], "EB Garamond");
        assert!(html.contains("name=\"vpara2\""), "el contador se reinició por capítulo");
        assert!(!html.contains("name=\"vpara3\""));
    }

    #[test]
    fn el_texto_va_justificado() {
        let html = book_html(&[sec("T", &["a"])], "EB Garamond");
        assert!(html.contains("text-align: justify"));
    }

    #[test]
    fn el_primer_parrafo_de_cada_capitulo_no_sangra() {
        let html = book_html(&[sec("Uno", &["primero", "segundo"])], "EB Garamond");
        let first = html.find("class=\"first\"").expect("falta la clase del primero");
        let segundo = html.find("segundo").unwrap();
        assert!(first < segundo, "la sangría quedó en el párrafo equivocado");
        assert_eq!(html.matches("class=\"first\"").count(), 1);
    }

    #[test]
    fn cada_capitulo_lleva_su_titulo() {
        let html = book_html(&[sec("EL LOGOS", &["a"]), sec("EL ALTAR", &["b"])], "EB Garamond");
        assert!(html.contains("<h2>EL LOGOS</h2>"));
        assert!(html.contains("<h2>EL ALTAR</h2>"));
    }

    #[test]
    fn una_seccion_sin_titulo_no_deja_un_encabezado_vacio() {
        let html = book_html(&[sec("", &["suelto"])], "EB Garamond");
        assert!(!html.contains("<h2></h2>"));
        assert!(html.contains("suelto"));
    }

    #[test]
    fn un_libro_vacio_sigue_siendo_html_valido() {
        let html = book_html(&[], "EB Garamond");
        assert!(html.starts_with("<html>"));
        assert!(html.ends_with("</html>"));
    }

    #[test]
    fn la_fuente_elegida_va_en_el_estilo() {
        let html = book_html(&[sec("T", &["a"])], "Iosevka");
        assert!(html.contains("'Iosevka'"));
    }

    #[test]
    fn el_pdf_va_al_lado_del_void_con_el_nombre_del_texto() {
        let d = Path::new("/void");
        assert_eq!(default_path(d, "Capitulo III"), PathBuf::from("/void/Capitulo III.pdf"));
    }

    #[test]
    fn un_titulo_con_barras_no_inventa_carpetas() {
        let d = Path::new("/void");
        assert_eq!(default_path(d, "a/b:c"), PathBuf::from("/void/a-b-c.pdf"));
    }

    #[test]
    fn un_titulo_vacio_igual_da_un_archivo() {
        assert_eq!(default_path(Path::new("/void"), "   "), PathBuf::from("/void/voider.pdf"));
    }

    #[test]
    fn el_pdf_se_genera_de_verdad_y_empieza_como_un_pdf() {
        let html = book_html(&[sec("PRUEBA", &["Una frase para componer.", "Y otra más."])], "serif");
        let bytes = render(&html, "serif", None).expect("no compuso");
        assert!(bytes.starts_with(b"%PDF"), "no parece un PDF");
        assert!(bytes.len() > 400, "salió sospechosamente chico: {} bytes", bytes.len());
    }

    #[test]
    fn sin_lp_se_avisa_en_vez_de_fallar_en_silencio() {
        // En esta máquina no hay CUPS; el error tiene que decirlo.
        let d = tempfile::tempdir().unwrap();
        let p = d.path().join("x.pdf");
        std::fs::write(&p, b"%PDF-1.4").unwrap();
        if let Err(e) = send_to_printer(&p) {
            assert!(!e.is_empty(), "un error vacío no le sirve a nadie");
        }
    }
}
