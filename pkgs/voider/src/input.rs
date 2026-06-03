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
    Escape,

    // Navigation (F2)
    NavUp,
    NavDown,

    // Global
    Tab,        // status overlay
    Save,       // Ctrl+S
    NewFile,    // Ctrl+N

    Nothing,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum View { Write, Navigate, Void }

pub fn map(keysym: Keysym, utf8: Option<&str>, mods: &Modifiers) -> Action {
    let ctrl  = mods.ctrl;
    let _alt  = mods.alt;

    match keysym {
        Keysym::F1     => Action::SwitchView(View::Write),
        Keysym::F2     => Action::SwitchView(View::Navigate),
        Keysym::F3     => Action::SwitchView(View::Void),
        Keysym::Tab    => Action::Tab,
        Keysym::Escape => Action::Escape,

        Keysym::Return | Keysym::KP_Enter => Action::Enter,

        Keysym::BackSpace => Action::Backspace,
        Keysym::Delete    => Action::Delete,

        Keysym::Up   => Action::NavUp,
        Keysym::Down => Action::NavDown,
        Keysym::k    => if ctrl { Action::Nothing } else { Action::Char('k') },
        Keysym::j    => if ctrl { Action::Nothing } else { Action::Char('j') },

        Keysym::s if ctrl => Action::Save,
        Keysym::n if ctrl => Action::NewFile,

        _ => match utf8 {
            Some(s) if !s.is_empty() => {
                let ch = s.chars().next().unwrap();
                if ch.is_control() { Action::Nothing } else { Action::Char(ch) }
            }
            _ => Action::Nothing,
        }
    }
}
