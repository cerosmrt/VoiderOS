use std::{fs, path::PathBuf};
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Config {
    pub void_dir:    String,
    pub font_family: String,
    pub font_size:   f32,
    pub text_color:  [u8; 3],
    pub line_height: f32,
}

impl Default for Config {
    fn default() -> Self {
        let home = home_dir();
        Self {
            void_dir:    format!("{}/void", home),
            font_family: "JetBrains Mono".into(),
            font_size:   18.0,
            text_color:  [255, 255, 255],
            line_height: 1.6,
        }
    }
}

impl Config {
    pub fn load() -> Self {
        let path = config_path();
        if path.exists() {
            if let Ok(s) = fs::read_to_string(&path) {
                if let Ok(c) = toml::from_str(&s) {
                    return c;
                }
            }
        }
        let default = Config::default();
        // Write default config so the user can find and edit it
        if let Some(dir) = path.parent() {
            let _ = fs::create_dir_all(dir);
            if let Ok(s) = toml::to_string_pretty(&default) {
                let _ = fs::write(&path, s);
            }
        }
        default
    }

    pub fn void_dir(&self) -> PathBuf {
        PathBuf::from(shellexpand::tilde(&self.void_dir).as_ref())
    }
}

fn config_path() -> PathBuf {
    let home = home_dir();
    PathBuf::from(format!("{home}/.config/voideros/config.toml"))
}

fn home_dir() -> String {
    std::env::var("HOME").unwrap_or_else(|_| "/root".into())
}
