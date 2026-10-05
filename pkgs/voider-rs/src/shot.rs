//! Shift+F12 — a 1:1 screenshot of the window, for carousel cover art.
//!
//! The pure half of `take_circle_screenshot` in `io_mixin.py`. The window's own
//! position and size come from `hyprctl -j clients` (matched by this process's
//! pid), not from what the toolkit believes: for a floating window the two did
//! not agree, and the crop landed over other windows. `hyprctl` and `grim` both
//! speak the compositor's own coordinates, so anchoring to hyprctl is what keeps
//! them in agreement.

#![allow(dead_code)]

use serde_json::Value;

/// Where a window sits on screen, in the compositor's coordinates.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct WindowRect {
    pub x: i64,
    pub y: i64,
    pub w: i64,
    pub h: i64,
}

/// `(x, y, side)` of a centred 1:1 crop of a window: the wider axis is trimmed
/// down to the narrower one (the "side bars"). A degenerate window gives a side
/// of 0 — nothing to capture, not a crash.
pub fn square_crop_for(win: WindowRect) -> (i64, i64, i64) {
    let side = win.w.min(win.h).max(0);
    (win.x + (win.w - side) / 2, win.y + (win.h - side) / 2, side)
}

/// The window of process `pid` in the output of `hyprctl -j clients`, or `None`
/// when the text is not that JSON or no client has that pid.
pub fn window_for_pid(clients_json: &str, pid: u32) -> Option<WindowRect> {
    let clients: Value = serde_json::from_str(clients_json).ok()?;
    clients.as_array()?.iter().find_map(|c| {
        if c.get("pid")?.as_u64()? != pid as u64 {
            return None;
        }
        let at = c.get("at")?.as_array()?;
        let size = c.get("size")?.as_array()?;
        Some(WindowRect {
            x: at.first()?.as_i64()?,
            y: at.get(1)?.as_i64()?,
            w: size.first()?.as_i64()?,
            h: size.get(1)?.as_i64()?,
        })
    })
}

/// What a command printed, and whether it succeeded.
#[derive(Debug, Clone)]
pub struct CmdOutput {
    pub ok: bool,
    pub stdout: String,
    pub stderr: String,
}

/// Run a program for real. Kept apart from the logic that decides what to run so
/// that logic can be driven by a script in tests, with nothing on the screen.
pub fn real_run(prog: &str, args: &[String]) -> std::io::Result<CmdOutput> {
    let out = std::process::Command::new(prog).args(args).output()?;
    Ok(CmdOutput {
        ok: out.status.success(),
        stdout: String::from_utf8_lossy(&out.stdout).into_owned(),
        stderr: String::from_utf8_lossy(&out.stderr).into_owned(),
    })
}

/// The `grim` geometry argument for a square: `"x,y SIDExSIDE"`.
pub fn grim_geometry(x: i64, y: i64, side: i64) -> String {
    format!("{x},{y} {side}x{side}")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn win(x: i64, y: i64, w: i64, h: i64) -> WindowRect {
        WindowRect { x, y, w, h }
    }

    // ── the crop (test_circular_view_bbox.py) ────────────────────────────────

    #[test]
    fn the_side_is_the_smaller_dimension() {
        assert_eq!(square_crop_for(win(0, 0, 1117, 916)).2, 916);
    }

    #[test]
    fn it_is_centred_trimming_the_wider_axis() {
        let (x, y, _) = square_crop_for(win(0, 0, 1117, 916));
        assert_eq!(x, (1117 - 916) / 2);
        assert_eq!(y, 0);
    }

    #[test]
    fn it_offsets_by_the_windows_own_position() {
        let (x, y, _) = square_crop_for(win(291, 136, 1117, 916));
        assert_eq!(x, 291 + (1117 - 916) / 2);
        assert_eq!(y, 136);
    }

    #[test]
    fn a_taller_than_wide_window_trims_vertically_instead() {
        let (x, y, side) = square_crop_for(win(0, 0, 600, 900));
        assert_eq!((x, y, side), (0, (900 - 600) / 2, 600));
    }

    #[test]
    fn a_zero_size_window_is_a_degenerate_point_not_a_crash() {
        assert_eq!(square_crop_for(win(0, 0, 0, 0)).2, 0);
    }

    // ── finding the window ───────────────────────────────────────────────────

    #[test]
    fn the_window_is_the_client_with_this_processs_pid() {
        let json = r#"[
            {"pid": 11, "at": [0, 0], "size": [10, 10]},
            {"pid": 4242, "at": [291, 136], "size": [1117, 916]}
        ]"#;
        assert_eq!(window_for_pid(json, 4242), Some(win(291, 136, 1117, 916)));
    }

    #[test]
    fn no_client_with_that_pid_is_none() {
        let json = r#"[{"pid": 1, "at": [0, 0], "size": [800, 600]}]"#;
        assert_eq!(window_for_pid(json, 99), None);
    }

    #[test]
    fn text_that_is_not_json_is_none_not_a_panic() {
        assert_eq!(window_for_pid("not json", 1), None);
        assert_eq!(window_for_pid("", 1), None);
        assert_eq!(window_for_pid("{\"pid\": 1}", 1), None); // JSON, but not a list
    }

    #[test]
    fn a_client_missing_its_geometry_is_skipped() {
        let json = r#"[{"pid": 7}, {"pid": 7, "at": [1, 2], "size": [30, 40]}]"#;
        assert_eq!(window_for_pid(json, 7), Some(win(1, 2, 30, 40)));
    }

    // ── what grim is asked ───────────────────────────────────────────────────

    #[test]
    fn grim_is_given_the_square_in_its_own_syntax() {
        // side = min(1117, 916) = 916; x = 291 + 100 = 391; y = 136
        let (x, y, side) = square_crop_for(win(291, 136, 1117, 916));
        assert_eq!(grim_geometry(x, y, side), "391,136 916x916");
    }
}
