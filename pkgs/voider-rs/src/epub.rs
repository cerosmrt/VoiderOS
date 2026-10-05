//! EPUB export, for the PDF + EPUB + TXT sale bundle.
//!
//! A port of `epub_export.py`. The content model is the same as the PDF's —
//! sections of `(chapter title, raw dot-model lines)` — and paragraphs come out
//! of `reformat::lines_to_paragraphs`, so a paragraph in the EPUB is exactly the
//! paragraph the PDF sets: one rule for "where does this sentence break".
//!
//! An EPUB is a ZIP with a fixed shape. There is no `zip` crate in this build,
//! and none is needed: the entries are stored uncompressed (the format allows
//! it, and a book is small), so the writer is a few dozen lines plus a CRC-32.

#![allow(dead_code)]

use crate::reformat;
use std::io;
use std::path::Path;

/// Build the EPUB in memory. `sections` is `[(chapter title, lines)]`; a title
/// may be empty (no heading is drawn). One XHTML chapter per section, in order,
/// with a working table of contents.
pub fn build_epub(
    sections: &[(String, Vec<String>)],
    title: &str,
    author: &str,
    lang: &str,
) -> Vec<u8> {
    // The chapters first: their file names and display titles feed the contents.
    let mut chapters: Vec<(String, String, String)> = Vec::new(); // (id, display title, document)
    for (i, (chapter_title, lines)) in sections.iter().enumerate() {
        let heading = if chapter_title.is_empty() {
            String::new()
        } else {
            format!("<h1>{}</h1>", xml_escape(chapter_title))
        };
        let body: String = reformat::lines_to_paragraphs(lines)
            .iter()
            .map(|p| format!("<p>{}</p>", xml_escape(p)))
            .collect();
        let shown = if chapter_title.is_empty() {
            format!("Capitulo {}", i + 1)
        } else {
            chapter_title.clone()
        };
        let doc = xhtml(&shown, lang, &format!("{heading}{body}"));
        chapters.push((format!("chap_{}", i + 1), shown, doc));
    }

    let mut files: Vec<(String, Vec<u8>)> = vec![
        // Readers sniff the type from the first bytes: this entry goes first,
        // uncompressed, with nothing after its name.
        ("mimetype".into(), b"application/epub+zip".to_vec()),
        ("META-INF/container.xml".into(), CONTAINER_XML.as_bytes().to_vec()),
        ("EPUB/content.opf".into(), package_opf(&chapters, title, author, lang).into_bytes()),
        ("EPUB/nav.xhtml".into(), nav_xhtml(&chapters, lang).into_bytes()),
        ("EPUB/toc.ncx".into(), toc_ncx(&chapters, title).into_bytes()),
    ];
    for (id, _, doc) in chapters {
        files.push((format!("EPUB/{id}.xhtml"), doc.into_bytes()));
    }
    zip_stored(&files)
}

const CONTAINER_XML: &str = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n\
<container version=\"1.0\" xmlns=\"urn:oasis:names:tc:opendocument:xmlns:container\">\n\
  <rootfiles>\n\
    <rootfile full-path=\"EPUB/content.opf\" media-type=\"application/oebps-package+xml\"/>\n\
  </rootfiles>\n\
</container>\n";

/// The five characters XML will not take as they are.
pub fn xml_escape(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&#39;"),
            c => out.push(c),
        }
    }
    out
}

/// One chapter document. `body` is already escaped markup.
fn xhtml(title: &str, lang: &str, body: &str) -> String {
    format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<!DOCTYPE html>\n\
<html xmlns=\"http://www.w3.org/1999/xhtml\" xmlns:epub=\"http://www.idpf.org/2007/ops\" lang=\"{l}\" xml:lang=\"{l}\">\n\
<head><meta charset=\"utf-8\"/><title>{t}</title></head>\n\
<body>{body}</body>\n</html>\n",
        l = xml_escape(lang),
        t = xml_escape(title),
    )
}

fn package_opf(
    chapters: &[(String, String, String)],
    title: &str,
    author: &str,
    lang: &str,
) -> String {
    let creator = if author.is_empty() {
        String::new()
    } else {
        format!("    <dc:creator>{}</dc:creator>\n", xml_escape(author))
    };
    let mut manifest = String::from(
        "    <item id=\"nav\" href=\"nav.xhtml\" media-type=\"application/xhtml+xml\" properties=\"nav\"/>\n\
    <item id=\"ncx\" href=\"toc.ncx\" media-type=\"application/x-dtbncx+xml\"/>\n",
    );
    let mut spine = String::from("    <itemref idref=\"nav\"/>\n");
    for (id, _, _) in chapters {
        manifest.push_str(&format!(
            "    <item id=\"{id}\" href=\"{id}.xhtml\" media-type=\"application/xhtml+xml\"/>\n"
        ));
        spine.push_str(&format!("    <itemref idref=\"{id}\"/>\n"));
    }
    format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n\
<package xmlns=\"http://www.idpf.org/2007/opf\" version=\"3.0\" unique-identifier=\"bookid\" xml:lang=\"{lang}\">\n\
  <metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\">\n\
    <dc:identifier id=\"bookid\">urn:uuid:{uuid}</dc:identifier>\n\
    <dc:title>{title}</dc:title>\n\
    <dc:language>{lang}</dc:language>\n\
{creator}\
    <meta property=\"dcterms:modified\">{modified}</meta>\n\
  </metadata>\n\
  <manifest>\n{manifest}  </manifest>\n\
  <spine toc=\"ncx\">\n{spine}  </spine>\n\
</package>\n",
        lang = xml_escape(lang),
        uuid = new_uuid(),
        title = xml_escape(title),
        modified = chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ"),
    )
}

/// The EPUB 3 navigation document — the contents a reader shows.
fn nav_xhtml(chapters: &[(String, String, String)], lang: &str) -> String {
    let items: String = chapters
        .iter()
        .map(|(id, shown, _)| format!("<li><a href=\"{id}.xhtml\">{}</a></li>", xml_escape(shown)))
        .collect();
    xhtml(
        "Contenido",
        lang,
        &format!("<nav epub:type=\"toc\" id=\"toc\"><h1>Contenido</h1><ol>{items}</ol></nav>"),
    )
}

/// The EPUB 2 contents, which older readers and Kindle conversion still look for.
fn toc_ncx(chapters: &[(String, String, String)], title: &str) -> String {
    let points: String = chapters
        .iter()
        .enumerate()
        .map(|(i, (id, shown, _))| {
            format!(
                "    <navPoint id=\"navPoint-{n}\" playOrder=\"{n}\"><navLabel><text>{}</text></navLabel><content src=\"{id}.xhtml\"/></navPoint>\n",
                xml_escape(shown),
                n = i + 1
            )
        })
        .collect();
    format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n\
<ncx xmlns=\"http://www.daisy.org/z3986/2005/ncx/\" version=\"2005-1\">\n\
  <head><meta name=\"dtb:depth\" content=\"1\"/></head>\n\
  <docTitle><text>{}</text></docTitle>\n\
  <navMap>\n{points}  </navMap>\n\
</ncx>\n",
        xml_escape(title)
    )
}

/// A random version-4 UUID, from std alone (no `uuid` crate in this build).
fn new_uuid() -> String {
    use std::collections::hash_map::RandomState;
    use std::hash::{BuildHasher, Hasher};
    let mut bytes = [0u8; 16];
    for half in 0..2 {
        let mut h = RandomState::new().build_hasher();
        h.write_u128(
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or(0),
        );
        h.write_u32(std::process::id());
        bytes[half * 8..half * 8 + 8].copy_from_slice(&h.finish().to_le_bytes());
    }
    bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
    bytes[8] = (bytes[8] & 0x3f) | 0x80; // the RFC 4122 variant
    let hex: String = bytes.iter().map(|b| format!("{b:02x}")).collect();
    format!("{}-{}-{}-{}-{}", &hex[..8], &hex[8..12], &hex[12..16], &hex[16..20], &hex[20..])
}

/// CRC-32 (IEEE), the checksum every ZIP entry carries.
pub fn crc32(data: &[u8]) -> u32 {
    let mut crc = 0xFFFF_FFFFu32;
    for &byte in data {
        crc ^= byte as u32;
        for _ in 0..8 {
            crc = if crc & 1 != 0 { (crc >> 1) ^ 0xEDB8_8320 } else { crc >> 1 };
        }
    }
    !crc
}

/// A ZIP archive with every entry stored, uncompressed. The date is fixed
/// (1980-01-01) so the same book always yields the same bytes.
fn zip_stored(files: &[(String, Vec<u8>)]) -> Vec<u8> {
    const TIME: u16 = 0;
    const DATE: u16 = (1 << 5) | 1; // 1980-01-01
    let mut out: Vec<u8> = Vec::new();
    let mut central: Vec<u8> = Vec::new();
    for (name, data) in files {
        let offset = out.len() as u32;
        let crc = crc32(data);
        let size = data.len() as u32;
        let name_bytes = name.as_bytes();

        out.extend_from_slice(&0x0403_4b50u32.to_le_bytes()); // local header
        out.extend_from_slice(&20u16.to_le_bytes()); // version needed
        out.extend_from_slice(&0u16.to_le_bytes()); // flags
        out.extend_from_slice(&0u16.to_le_bytes()); // method: stored
        out.extend_from_slice(&TIME.to_le_bytes());
        out.extend_from_slice(&DATE.to_le_bytes());
        out.extend_from_slice(&crc.to_le_bytes());
        out.extend_from_slice(&size.to_le_bytes()); // compressed
        out.extend_from_slice(&size.to_le_bytes()); // uncompressed
        out.extend_from_slice(&(name_bytes.len() as u16).to_le_bytes());
        out.extend_from_slice(&0u16.to_le_bytes()); // no extra field
        out.extend_from_slice(name_bytes);
        out.extend_from_slice(data);

        central.extend_from_slice(&0x0201_4b50u32.to_le_bytes()); // central header
        central.extend_from_slice(&20u16.to_le_bytes()); // made by
        central.extend_from_slice(&20u16.to_le_bytes()); // needed
        central.extend_from_slice(&0u16.to_le_bytes()); // flags
        central.extend_from_slice(&0u16.to_le_bytes()); // method
        central.extend_from_slice(&TIME.to_le_bytes());
        central.extend_from_slice(&DATE.to_le_bytes());
        central.extend_from_slice(&crc.to_le_bytes());
        central.extend_from_slice(&size.to_le_bytes());
        central.extend_from_slice(&size.to_le_bytes());
        central.extend_from_slice(&(name_bytes.len() as u16).to_le_bytes());
        central.extend_from_slice(&0u16.to_le_bytes()); // extra
        central.extend_from_slice(&0u16.to_le_bytes()); // comment
        central.extend_from_slice(&0u16.to_le_bytes()); // disk
        central.extend_from_slice(&0u16.to_le_bytes()); // internal attrs
        central.extend_from_slice(&0u32.to_le_bytes()); // external attrs
        central.extend_from_slice(&offset.to_le_bytes());
        central.extend_from_slice(name_bytes);
    }
    let cd_offset = out.len() as u32;
    let cd_size = central.len() as u32;
    out.extend_from_slice(&central);
    out.extend_from_slice(&0x0605_4b50u32.to_le_bytes()); // end of central directory
    out.extend_from_slice(&0u16.to_le_bytes()); // this disk
    out.extend_from_slice(&0u16.to_le_bytes()); // disk with the directory
    out.extend_from_slice(&(files.len() as u16).to_le_bytes());
    out.extend_from_slice(&(files.len() as u16).to_le_bytes());
    out.extend_from_slice(&cd_size.to_le_bytes());
    out.extend_from_slice(&cd_offset.to_le_bytes());
    out.extend_from_slice(&0u16.to_le_bytes()); // no comment
    out
}

/// Build the EPUB and write it to `path`, whole or not at all.
pub fn write_epub(
    path: &Path,
    sections: &[(String, Vec<String>)],
    title: &str,
    author: &str,
    lang: &str,
) -> io::Result<()> {
    let bytes = build_epub(sections, title, author, lang);
    let tmp = path.with_extension("epub.tmp");
    std::fs::write(&tmp, &bytes)?;
    std::fs::rename(&tmp, path)
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── a minimal ZIP reader, only for checking what the writer produced ─────

    struct Entry {
        name: String,
        data: Vec<u8>,
        /// Whether it was stored (method 0) rather than compressed.
        stored: bool,
        /// Where its local header begins in the archive.
        offset: usize,
        crc_ok: bool,
    }

    fn le16(b: &[u8], at: usize) -> usize {
        u16::from_le_bytes([b[at], b[at + 1]]) as usize
    }
    fn le32(b: &[u8], at: usize) -> usize {
        u32::from_le_bytes([b[at], b[at + 1], b[at + 2], b[at + 3]]) as usize
    }

    /// Read every entry through the central directory, as a real reader would.
    fn read_zip(bytes: &[u8]) -> Vec<Entry> {
        assert!(bytes.len() > 22, "not a zip: {} bytes", bytes.len());
        // The end-of-central-directory record is the last 22 bytes (no comment).
        let eocd = bytes.len() - 22;
        assert_eq!(&bytes[eocd..eocd + 4], b"PK\x05\x06", "no end record");
        let count = le16(bytes, eocd + 10);
        let mut at = le32(bytes, eocd + 16);
        let mut out = Vec::new();
        for _ in 0..count {
            assert_eq!(&bytes[at..at + 4], b"PK\x01\x02", "bad central header");
            let method = le16(bytes, at + 10);
            let crc = le32(bytes, at + 16);
            let size = le32(bytes, at + 24);
            let name_len = le16(bytes, at + 28);
            let extra_len = le16(bytes, at + 30);
            let comment_len = le16(bytes, at + 32);
            let local = le32(bytes, at + 42);
            let name = String::from_utf8(bytes[at + 46..at + 46 + name_len].to_vec()).unwrap();
            // The local header repeats the name and may carry its own extra.
            assert_eq!(&bytes[local..local + 4], b"PK\x03\x04", "bad local header");
            let l_name = le16(bytes, local + 26);
            let l_extra = le16(bytes, local + 28);
            let start = local + 30 + l_name + l_extra;
            let data = bytes[start..start + size].to_vec();
            out.push(Entry {
                crc_ok: crc32(&data) as usize == crc,
                name,
                data,
                stored: method == 0,
                offset: local,
            });
            at += 46 + name_len + extra_len + comment_len;
        }
        out
    }

    fn entry<'a>(zip: &'a [Entry], name: &str) -> &'a Entry {
        zip.iter()
            .find(|e| e.name == name)
            .unwrap_or_else(|| panic!("no entry {name}; have {:?}", zip.iter().map(|e| &e.name).collect::<Vec<_>>()))
    }

    fn text(zip: &[Entry], name: &str) -> String {
        String::from_utf8(entry(zip, name).data.clone()).unwrap()
    }

    fn secs(v: &[(&str, &[&str])]) -> Vec<(String, Vec<String>)> {
        v.iter()
            .map(|(t, ls)| (t.to_string(), ls.iter().map(|l| l.to_string()).collect()))
            .collect()
    }

    fn book(v: &[(&str, &[&str])]) -> Vec<Entry> {
        read_zip(&build_epub(&secs(v), "Libro", "", "es"))
    }

    /// All the chapter documents, concatenated.
    fn chapters_text(zip: &[Entry]) -> String {
        zip.iter()
            .filter(|e| e.name.starts_with("EPUB/chap_"))
            .map(|e| String::from_utf8(e.data.clone()).unwrap())
            .collect()
    }

    // ── the writer's own pieces ───────────────────────────────────────────────

    #[test]
    fn crc32_matches_the_standard_check_value() {
        assert_eq!(crc32(b"123456789"), 0xCBF4_3926);
        assert_eq!(crc32(b""), 0);
    }

    #[test]
    fn xml_escaping_covers_the_five_characters() {
        assert_eq!(xml_escape("a <b> & \"c\" 'd'"), "a &lt;b&gt; &amp; &quot;c&quot; &#39;d&#39;");
    }

    // ── what the Python's test_epub_export.py checks, one for one ─────────────

    #[test]
    fn writes_a_valid_epub_file() {
        let bytes = build_epub(&secs(&[("Capitulo Uno", &["Una linea.", ".", "Otra linea."])]), "Mi Libro", "", "es");
        let zip = read_zip(&bytes); // panics if it is not a zip a reader could open
        assert!(zip.iter().all(|e| e.crc_ok), "a checksum is wrong");
        assert!(text(&zip, "EPUB/content.opf").contains("<dc:title>Mi Libro</dc:title>"));
    }

    #[test]
    fn one_chapter_per_section() {
        let zip = book(&[("Uno", &["Primera.", "."]), ("Dos", &["Segunda.", "."]), ("Tres", &["Tercera.", "."])]);
        let n = zip.iter().filter(|e| e.name.starts_with("EPUB/chap_")).count();
        assert_eq!(n, 3);
    }

    #[test]
    fn paragraph_text_is_in_the_content() {
        let zip = book(&[("Cap", &["Una frase reconocible aqui.", "."])]);
        assert!(chapters_text(&zip).contains("Una frase reconocible aqui."));
    }

    #[test]
    fn the_chapter_title_is_in_the_content() {
        let zip = book(&[("El Titulo Del Capitulo", &["linea.", "."])]);
        assert!(chapters_text(&zip).contains("<h1>El Titulo Del Capitulo</h1>"));
    }

    #[test]
    fn dots_become_paragraph_breaks_never_literal_text() {
        let zip = book(&[("Cap", &["Primera.", ".", "Segunda."])]);
        let body = chapters_text(&zip);
        assert_eq!(body.matches("<p>").count(), 2);
        assert!(!body.contains("<p>.</p>"));
    }

    #[test]
    fn html_special_characters_are_escaped() {
        let zip = book(&[("Cap", &["Texto con <tag> y & ampersand.", "."])]);
        let body = chapters_text(&zip);
        assert!(!body.contains("<tag>"));
        assert!(body.contains("&lt;tag&gt;"));
        assert!(body.contains("&amp; ampersand"));
    }

    #[test]
    fn an_empty_chapter_title_draws_no_heading_and_does_not_crash() {
        let zip = book(&[("", &["Solo texto, sin titulo de capitulo.", "."])]);
        let body = chapters_text(&zip);
        assert!(!body.contains("<h1>"));
        assert!(body.contains("Solo texto"));
    }

    #[test]
    fn the_author_is_set_when_given_and_absent_when_not() {
        let with = read_zip(&build_epub(&secs(&[("Cap", &["linea.", "."])]), "Libro", "Federico Moret", "es"));
        assert!(text(&with, "EPUB/content.opf").contains("<dc:creator>Federico Moret</dc:creator>"));
        let without = book(&[("Cap", &["linea.", "."])]);
        assert!(!text(&without, "EPUB/content.opf").contains("<dc:creator>"));
    }

    // ── what makes it an EPUB and not just a zip ──────────────────────────────

    #[test]
    fn the_mimetype_comes_first_uncompressed_and_exact() {
        let bytes = build_epub(&secs(&[("Cap", &["linea.", "."])]), "Libro", "", "es");
        let zip = read_zip(&bytes);
        assert_eq!(zip[0].name, "mimetype");
        assert!(zip[0].stored);
        assert_eq!(zip[0].data, b"application/epub+zip");
        // Readers sniff the type from fixed offsets: "PK" at 0, the name at 30.
        assert_eq!(zip[0].offset, 0);
        assert_eq!(&bytes[30..38], b"mimetype");
        // ...and the content right after it, with no extra field in between.
        assert_eq!(&bytes[38..38 + 20], b"application/epub+zip");
    }

    #[test]
    fn container_xml_points_at_the_package_document() {
        let zip = book(&[("Cap", &["linea.", "."])]);
        assert!(text(&zip, "META-INF/container.xml").contains("full-path=\"EPUB/content.opf\""));
    }

    #[test]
    fn the_package_lists_every_chapter_in_manifest_and_spine_in_order() {
        let zip = book(&[("Uno", &["a.", "."]), ("Dos", &["b.", "."])]);
        let opf = text(&zip, "EPUB/content.opf");
        for id in ["chap_1", "chap_2"] {
            assert!(opf.contains(&format!("<item id=\"{id}\" href=\"{id}.xhtml\"")), "{id} not in the manifest");
        }
        let spine: Vec<&str> = opf.match_indices("<itemref idref=\"").map(|(i, _)| &opf[i..i + 30]).collect();
        assert!(spine[0].contains("nav"));
        assert!(spine[1].contains("chap_1"));
        assert!(spine[2].contains("chap_2"));
    }

    #[test]
    fn the_nav_document_is_a_working_table_of_contents() {
        let zip = book(&[("Uno", &["a.", "."]), ("", &["b.", "."])]);
        let nav = text(&zip, "EPUB/nav.xhtml");
        assert!(nav.contains("epub:type=\"toc\""));
        assert!(nav.contains("<a href=\"chap_1.xhtml\">Uno</a>"));
        // A chapter with no title is still reachable, under a fallback name.
        assert!(nav.contains("<a href=\"chap_2.xhtml\">Capitulo 2</a>"));
    }

    #[test]
    fn the_ncx_is_there_for_older_readers() {
        let zip = book(&[("Uno", &["a.", "."])]);
        assert!(text(&zip, "EPUB/toc.ncx").contains("<navPoint"));
    }

    #[test]
    fn every_document_is_well_formed_enough_to_balance_its_tags() {
        let zip = book(&[("Uno", &["Texto <raro> & mas.", ".", "Otro."]), ("", &["x."])]);
        for e in zip.iter().filter(|e| e.name.ends_with(".xhtml") || e.name.ends_with(".opf")) {
            let t = String::from_utf8(e.data.clone()).unwrap();
            assert_eq!(t.matches("<p>").count(), t.matches("</p>").count(), "{} unbalanced", e.name);
            assert!(t.starts_with("<?xml"), "{} lacks the xml declaration", e.name);
        }
    }

    #[test]
    fn a_book_with_no_sections_is_still_a_valid_archive() {
        let zip = read_zip(&build_epub(&[], "Vacio", "", "es"));
        assert!(zip.iter().all(|e| e.crc_ok));
        assert!(text(&zip, "EPUB/content.opf").contains("<dc:title>Vacio</dc:title>"));
    }

    #[test]
    fn accents_survive_as_utf8() {
        let zip = book(&[("Capítulo", &["El niño comió ñoquis.", "."])]);
        assert!(chapters_text(&zip).contains("El niño comió ñoquis."));
        assert!(chapters_text(&zip).contains("Capítulo"));
    }

    #[test]
    fn writing_to_disk_leaves_no_temp_file_and_a_real_epub() {
        let d = tempfile::tempdir().unwrap();
        let out = d.path().join("libro.epub");
        write_epub(&out, &secs(&[("Cap", &["linea.", "."])]), "Libro", "", "es").unwrap();
        let bytes = std::fs::read(&out).unwrap();
        assert_eq!(&bytes[..2], b"PK");
        assert!(read_zip(&bytes).iter().all(|e| e.crc_ok));
        let left: Vec<_> = std::fs::read_dir(d.path()).unwrap().map(|e| e.unwrap().file_name()).collect();
        assert_eq!(left.len(), 1, "stray files: {left:?}");
    }
}
