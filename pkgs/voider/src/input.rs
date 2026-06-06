use smithay_client_toolkit::seat::keyboard::{Keysym, Modifiers};

#[derive(Debug, Clone)]
pub enum Action {
    // View switching
    SwitchView(View),

    // Text input
    Char(char),
    Backspace,
    Delete,
    Enter,
    ShiftEnter,   // F2: edit current line
    Escape,

    // Cursor movement (F2 editor)
    CursorLeft,
    CursorRight,

    // Navigation
    NavUp,
    NavDown,
    AltUp,     // Alt+Up   — swap in F2/F3, file-prev in F1
    AltDown,   // Alt+Down — swap in F2/F3, file-next in F1
    PageUp,    // paragraph prev
    PageDown,  // paragraph next

    // F1 random/recycle
    RandomSelf,   // Ctrl+.  — random line from current file
    RandomOther,  // Ctrl+0 in F1 — random line from any other file
    Recycle,      // *       — random line from any file except active (cut-up)

    // F2/F3 operations
    Rebase,      // Ctrl+0 in F2/F3
    Reshuffle,   // Ctrl+R
    OpacityUp,   // Ctrl++
    OpacityDown, // Ctrl+-
    Reformat,    // Ctrl+Shift+F

    // UI extras
    Tab,
    ToggleOverlay,

    Nothing,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum View { Write, Doc, Book, Vault }

pub fn map(keysym: Keysym, utf8: Option<&str>, mods: &Modifiers) -> Action {
    let ctrl  = mods.ctrl;
    let alt   = mods.alt;
    let shift = mods.shift;

    match keysym {
        Keysym::F1 => Action::SwitchView(View::Write),
        Keysym::F2 => Action::SwitchView(View::Doc),
        Keysym::F3 => Action::SwitchView(View::Book),
        Keysym::F4 => Action::SwitchView(View::Vault),

        Keysym::Tab    => Action::Tab,
        Keysym::Escape => Action::Escape,

        Keysym::Return | Keysym::KP_Enter => {
            if shift { Action::ShiftEnter } else { Action::Enter }
        }
        Keysym::BackSpace => Action::Backspace,
        Keysym::Delete    => Action::Delete,

        Keysym::Left  => Action::CursorLeft,
        Keysym::Right => Action::CursorRight,

        Keysym::Up   => if alt { Action::AltUp   } else { Action::NavUp   },
        Keysym::Down => if alt { Action::AltDown  } else { Action::NavDown },

        Keysym::Page_Up   => Action::PageUp,
        Keysym::Page_Down => Action::PageDown,

        // Ctrl+0 — context-sensitive (F1: random other; F2/F3: rebase)
        // We emit Ctrl0 and let app.rs decide per view
        Keysym::_0 if ctrl => Action::RandomOther, // overridden in F2/F3 as Rebase
        Keysym::KP_0 if ctrl => Action::RandomOther,

        // Ctrl+. → random from current file
        Keysym::period if ctrl => Action::RandomSelf,

        // * → recycle (cut-up)
        Keysym::asterisk => Action::Recycle,

        // Ctrl+R → reshuffle
        Keysym::r if ctrl && !shift => Action::Reshuffle,
        Keysym::R if ctrl && !shift => Action::Reshuffle,

        // Ctrl++ / Ctrl+= → opacity up
        Keysym::equal if ctrl => Action::OpacityUp,
        Keysym::plus  if ctrl => Action::OpacityUp,

        // Ctrl+- → opacity down
        Keysym::minus if ctrl => Action::OpacityDown,

        // Ctrl+Shift+F → reformat
        Keysym::f if ctrl && shift => Action::Reformat,
        Keysym::F if ctrl && shift => Action::Reformat,

        _ => match utf8 {
            Some(s) if !s.is_empty() => {
                let ch = s.chars().next().unwrap();
                if ch.is_control() { Action::Nothing } else { Action::Char(ch) }
            }
            _ => Action::Nothing,
        }
    }
}
