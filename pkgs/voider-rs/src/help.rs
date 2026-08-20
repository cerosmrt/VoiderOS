//! F11 — the shortcut reference, drawn over whatever view you were in.
//!
//! A port of `help_overlay.py` in spirit, but NOT of its table: the Python's
//! HELP list describes the Python's own bindings, several of which this mirror
//! means differently, or that have drifted from its own code: it lists F5 as
//! the `O/` fork and F9 as "Metronome", while its own new_interface.py has F5
//! reordering paragraphs and F9 opening the prose editor — both of which is
//! what this mirror does too. A help screen that lies is worse than none, so
//! this one lists what voider-rs actually does, and nothing it doesn't.

#![allow(dead_code)]

/// One row: `(key, description)`. A `None` description makes it a section head;
/// an empty key and description is a blank spacer.
pub type Row = (&'static str, Option<&'static str>);

pub const ROWS: &[Row] = &[
    ("VIEWS", None),
    ("F1", Some("Write — one line at a time into the active file")),
    ("F2", Some("The document as a ring — edit and reorder its lines")),
    ("F3", Some("The library — the book's chapters in reading order")),
    ("F4", Some("Read — the book set in a column, page by page")),
    ("F5", Some("Paragraphs — move them, send one to a chapter")),
    ("F6", Some("Read a book from O/ — the corpus")),
    ("F7", Some("The working set — the books picked by hand")),
    ("F8", Some("The oracle — a random line from the corpus")),
    ("F9", Some("Prose — the active file as one editable block")),
    ("F10", Some("Settings — the writing font and its size (←→)")),
    ("F11", Some("This help")),
    ("", None),
    ("MOVING", None),
    ("↑ / ↓", Some("Previous / next line")),
    ("Alt+↑ / Alt+↓", Some("Move the line itself (a paragraph, on a dot)")),
    ("Alt+← / Alt+→", Some("Move the word under the caret")),
    ("PageUp / PageDown", Some("Jump to the previous / next paragraph")),
    ("Home / End", Some("Jump to the document's first / last line")),
    ("Alt+↑ / Alt+↓  (F1)", Some("Previous / next file in the library")),
    ("Ctrl+0", Some("Rebase: make the current line the file's first")),
    ("`", Some("To the scratch and back again")),
    ("", None),
    ("THE CUT-UP", None),
    ("Tab  (F1)", Some("Pull a random line from the void into the entry")),
    ("Tab  (F2, on a line)", Some("Insert a random I/ fragment — Tab again re-rolls it")),
    ("Shift+Tab  (F2)", Some("Insert a fragment from the working set instead")),
    ("Tab  (F2, on a dot)", Some("Shuffle the lines within that paragraph")),
    ("Tab  (F2, on the top dot)", Some("Shuffle the order of the paragraphs")),
    ("Tab  (F3, on a dot)", Some("Shuffle that book — numbered titles keep their place")),
    ("Ctrl+0  (F1)", Some("A random line from anywhere in the void")),
    ("Ctrl+.  (F1)", Some("A random line from this file")),
    ("Ctrl+Shift+R", Some("Randomise the whole scratch")),
    ("", None),
    ("SHAPING  (F2)", None),
    ("Ctrl+Shift+F", Some("Reformat: one sentence per line (on the scratch: also split)")),
    ("Ctrl+Shift+S", Some("Seal the file at its /name markers into chapters")),
    ("Ctrl+Shift+D", Some("Dispatch: send each /name-marked paragraph to its file")),
    ("Enter  (on a dot)", Some("Focus that paragraph alone; Enter again releases it")),
    ("Enter  (mid-line)", Some("Split the line in two")),
    ("Ctrl+Delete / Ctrl+⌫", Some("Send the line down: file → scratch → trash → gone")),
    ("", None),
    ("THE LIBRARY  (F3)", None),
    ("Enter", Some("Open the highlighted chapter")),
    ("Shift+Enter", Some("Name a new chapter below this one")),
    ("Ctrl+Shift+M", Some("On a dot: merge that whole book into one chapter")),
    ("Ctrl+Shift+S", Some("Split the highlighted chapter at its markers")),
    ("", None),
    ("EVERYWHERE", None),
    ("Ctrl+F", Some("Search — the document's lines (F2), the chapters (F3)")),
    ("Ctrl+C", Some("Copy the line, or the paragraph on a dot, or the chapter")),
    ("Ctrl+Z / Ctrl+Shift+Z", Some("Undo / redo")),
    ("Ctrl+G", Some("Commit the void to git")),
    ("Ctrl+B", Some("Back the void up to a folder")),
    ("Ctrl+ + / Ctrl+ −", Some("Thin the ground out / fill it back in")),
    ("Ctrl+Shift+W", Some("Typewriter: pin the caret, slide the text")),
    ("Ctrl+Shift+T", Some("Show or hide the pinned title")),
    ("Caps Lock", Some("Scriptio continua: no capitals, no backspace, space commits")),
    ("F12", Some("Screenshot")),
    ("", None),
    ("READING  (F4)", None),
    ("→ / ← , PageDn / PageUp", Some("Turn the page")),
    ("Home / End", Some("First / last page")),
    ("", None),
    ("THE CORPUS  (F6 / F7 / F8)", None),
    ("Tab  (F7)", Some("Draw a book into this slot — never one already used")),
    ("Shift+Enter  (F7)", Some("Add a slot below this one")),
    ("Ctrl+Delete  (F7)", Some("Remove the slot (not the one open in F6)")),
    ("Enter  (F7)", Some("Open that book in the reader")),
    ("↑ / ↓  (F8)", Some("Draw another line")),
    ("Enter  (F8)", Some("Keep it — into the active document")),
    ("Ctrl+T", Some("The voice: read aloud")),
];

/// The rows split into two balanced columns, breaking only between sections so
/// a heading never ends up stranded at the foot of a column without its rows.
pub fn columns(rows: &[Row]) -> (&[Row], &[Row]) {
    let target = rows.len() / 2;
    // Walk out from the middle to the nearest section start (a header, or the
    // blank spacer that precedes one).
    let is_break = |i: usize| rows.get(i).is_some_and(|(k, d)| d.is_none() && !k.is_empty());
    for delta in 0..rows.len() {
        if is_break(target + delta) {
            return rows.split_at(target + delta);
        }
        if delta <= target && is_break(target - delta) {
            return rows.split_at(target - delta);
        }
    }
    rows.split_at(target)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_binding_row_always_has_both_a_key_and_a_description() {
        for (key, desc) in ROWS {
            if let Some(d) = desc {
                assert!(!key.is_empty(), "a binding with no key: {d}");
                assert!(!d.is_empty(), "a binding with no description: {key}");
            }
        }
    }

    #[test]
    fn the_table_has_sections_and_they_all_hold_bindings() {
        let mut sections = 0;
        let mut bindings_in_section = 0;
        for (key, desc) in ROWS {
            match (key, desc) {
                (k, None) if !k.is_empty() => {
                    if sections > 0 {
                        assert!(bindings_in_section > 0, "an empty section before {k}");
                    }
                    sections += 1;
                    bindings_in_section = 0;
                }
                (_, Some(_)) => bindings_in_section += 1,
                _ => {} // a blank spacer
            }
        }
        assert!(sections >= 4, "only {sections} sections");
        assert!(bindings_in_section > 0, "the last section is empty");
    }

    #[test]
    fn the_columns_split_on_a_section_not_inside_one() {
        let (left, right) = columns(ROWS);
        assert!(!left.is_empty() && !right.is_empty());
        assert_eq!(left.len() + right.len(), ROWS.len());
        // The right column opens on a section header, never mid-list.
        let (key, desc) = right[0];
        assert!(desc.is_none() && !key.is_empty(), "right column starts at {key:?}");
    }

    #[test]
    fn the_split_is_somewhere_near_the_middle() {
        let (left, right) = columns(ROWS);
        let diff = left.len().abs_diff(right.len());
        assert!(diff < ROWS.len() / 2, "columns are lopsided: {} vs {}", left.len(), right.len());
    }

    #[test]
    fn a_table_with_no_sections_still_splits() {
        let rows: Vec<Row> = vec![("a", Some("1")), ("b", Some("2")), ("c", Some("3"))];
        let (left, right) = columns(&rows);
        assert_eq!(left.len() + right.len(), 3);
    }
}
