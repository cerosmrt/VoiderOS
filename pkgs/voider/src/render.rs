use std::{collections::HashMap, f64::consts::PI};
use fontdue::Font;

use crate::app::{F2Mode, UiState};
use crate::input::View;

// ── Glyph cache ───────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
struct GlyphKey(char, u32);

pub struct GlyphCache {
    font:    Font,
    bitmaps: HashMap<GlyphKey, (fontdue::Metrics, Vec<u8>)>,
}

impl GlyphCache {
    pub fn new(font_bytes: &[u8]) -> anyhow::Result<Self> {
        let font = Font::from_bytes(font_bytes, fontdue::FontSettings::default())
            .map_err(|e| anyhow::anyhow!("fontdue: {e}"))?;
        Ok(Self { font, bitmaps: HashMap::new() })
    }

    fn ensure(&mut self, ch: char, size: f32) {
        let key = GlyphKey(ch, (size * 64.0) as u32);
        self.bitmaps.entry(key).or_insert_with(|| self.font.rasterize(ch, size));
    }

    fn get(&self, ch: char, size: f32) -> Option<&(fontdue::Metrics, Vec<u8>)> {
        self.bitmaps.get(&GlyphKey(ch, (size * 64.0) as u32))
    }

    pub fn advance(&mut self, ch: char, size: f32) -> f32 {
        self.ensure(ch, size);
        self.get(ch, size).map(|(m, _)| m.advance_width).unwrap_or(size * 0.6)
    }

    pub fn text_width(&mut self, text: &str, size: f32) -> f32 {
        text.chars().map(|c| self.advance(c, size)).sum()
    }

    pub fn line_height(&mut self, size: f32) -> i32 {
        self.ensure(' ', size);
        self.get(' ', size)
            .map(|(m, _)| (m.advance_width * 1.8) as i32)
            .unwrap_or((size * 1.8) as i32)
    }
}

// ── Entry point ───────────────────────────────────────────────────────────────

pub fn draw_frame(buf: &mut [u8], cache: &mut GlyphCache, ui: &UiState, width: u32, height: u32) {
    // Clear to black
    for chunk in buf.chunks_exact_mut(4) {
        chunk[0] = 0; chunk[1] = 0; chunk[2] = 0; chunk[3] = 255;
    }
    let fs = ui.config.font_size;
    match ui.view {
        View::Write => draw_write(buf, cache, ui, width, height, fs),
        View::Doc   => draw_doc  (buf, cache, ui, width, height, fs),
        View::Book  => draw_book (buf, cache, ui, width, height, fs),
        View::Vault => draw_vault(buf, cache, ui, width, height, fs),
    }

    // TAB status overlay
    if ui.show_overlay {
        draw_overlay(buf, cache, ui, width, height, fs);
    }

    // Apply global opacity (multiply all RGB by opacity)
    if ui.opacity < 0.999 {
        let scale = ui.opacity;
        for chunk in buf.chunks_exact_mut(4) {
            chunk[0] = (chunk[0] as f32 * scale) as u8;
            chunk[1] = (chunk[1] as f32 * scale) as u8;
            chunk[2] = (chunk[2] as f32 * scale) as u8;
        }
    }
}

// ── F1: Write ─────────────────────────────────────────────────────────────────

fn draw_write(buf: &mut [u8], cache: &mut GlyphCache, ui: &UiState, width: u32, height: u32, fs: f32) {
    let cx = width  as i32 / 2;
    let cy = height as i32 / 2;

    // White circle
    let radius = (width.min(height) as i32 / 2 - 35).max(1);
    draw_circle(buf, cx, cy, radius, 10, width, height);

    // Centered input with blinking cursor
    let text = format!("{}{}", ui.input, if (ui.blink_tick / 30) % 2 == 0 { "▋" } else { "" });
    draw_text_centered(buf, cache, &text, cx, cy, fs, 1.0, width, height);
}

fn draw_circle(buf: &mut [u8], cx: i32, cy: i32, radius: i32, thickness: i32, width: u32, height: u32) {
    let r      = radius as f32;
    let half_t = thickness as f32 / 2.0;
    let r_in   = r - half_t;
    let r_out  = r + half_t;
    let sq_in  = ((r_in  - 1.0).max(0.0)).powi(2) as i64;
    let sq_out = (r_out  + 1.0).powi(2) as i64;
    let scan   = (r_out  + 1.5) as i32;
    let w = width as i32;
    let h = height as i32;

    for dy in -scan..=scan {
        for dx in -scan..=scan {
            let dsq = (dx as i64) * (dx as i64) + (dy as i64) * (dy as i64);
            if dsq < sq_in || dsq > sq_out { continue; }
            let dist  = (dsq as f32).sqrt();
            let alpha = if dist < r_in  { dist - (r_in  - 1.0) }
                        else if dist > r_out { (r_out + 1.0) - dist }
                        else { 1.0_f32 }
                        .clamp(0.0, 1.0);
            if alpha < 0.01 { continue; }
            let px = cx + dx;
            let py = cy + dy;
            if px < 0 || py < 0 || px >= w || py >= h { continue; }
            let v = (alpha * 255.0) as u8;
            let off = ((py * w + px) * 4) as usize;
            buf[off] = v; buf[off+1] = v; buf[off+2] = v;
        }
    }
}

// ── F2: Doc ring ──────────────────────────────────────────────────────────────

const LINE_H: f32 = 38.0; // pixels between ring lines

fn draw_doc(buf: &mut [u8], cache: &mut GlyphCache, ui: &UiState, width: u32, height: u32, fs: f32) {
    let cx = width  as i32 / 2;
    let cy = height as i32 / 2;
    let h  = height as i32;

    let text_w = (width as i32 - 100).min(800);
    let margin = (width as i32 - text_w) / 2;

    let max_slots = (h as f32 / LINE_H) as isize + 3;

    for offset in -max_slots..=max_slots {
        let y_pos = cy as f32 + (offset as f32 + ui.f2_offset) * LINE_H;
        let dist  = (y_pos - cy as f32).abs();
        let base  = cosine_alpha(dist, h as f32);
        if base < 0.01 { continue; }

        let text = ui.ring.get(offset);

        // Opacity rules matching Python's CircularView:
        // Edit mode: center line hidden (editor renders it), others at 0.3
        // Insert mode: all at 0.3 except the line below center
        // Normal mode: full opacity based on distance
        let alpha = match ui.f2_mode {
            F2Mode::Normal => base,
            F2Mode::Editing => {
                if offset == 0 { 0.0 } // editor widget covers it
                else { base * 0.3 }
            }
            F2Mode::Inserting => base * 0.3,
        };

        if alpha < 0.01 { continue; }

        let color = if text == "." {
            // Dots drawn dimmer
            [((alpha * 100.0) as u8), ((alpha * 100.0) as u8), ((alpha * 100.0) as u8)]
        } else {
            let v = (alpha * 255.0) as u8;
            [v, v, v]
        };

        let tw = cache.text_width(text, fs) as i32;
        let tx = margin + (text_w - tw).max(0) / 2;
        let ty = y_pos as i32;
        draw_text_color(buf, cache, text, tx, ty, fs, color, width, height);
    }

    // Inline editor (Editing or Inserting mode)
    match ui.f2_mode {
        F2Mode::Editing => {
            let editor_y = cy;
            draw_editor(buf, cache, ui, cx, editor_y, fs, width, height);
        }
        F2Mode::Inserting => {
            let editor_y = cy + (LINE_H * 0.6) as i32;
            draw_editor(buf, cache, ui, cx, editor_y, fs, width, height);
        }
        F2Mode::Normal => {}
    }
}

fn draw_editor(
    buf: &mut [u8], cache: &mut GlyphCache, ui: &UiState,
    cx: i32, cy: i32, fs: f32, width: u32, height: u32,
) {
    let before = &ui.f2_editor[..ui.f2_cursor];
    let after  = &ui.f2_editor[ui.f2_cursor..];
    let cursor = if (ui.blink_tick / 30) % 2 == 0 { "▋" } else { "" };
    let display = format!("{before}{cursor}{after}");
    draw_text_centered(buf, cache, &display, cx, cy, fs, 1.0, width, height);
}

fn cosine_alpha(dist_px: f32, screen_h: f32) -> f32 {
    let t = (dist_px / (screen_h / 2.0)).min(1.0) as f64;
    (t * PI / 2.0).cos() as f32
}

// ── F3: Book browser ──────────────────────────────────────────────────────────

fn draw_book(buf: &mut [u8], cache: &mut GlyphCache, ui: &UiState, width: u32, height: u32, fs: f32) {
    let cx = width  as i32 / 2;
    let cy = height as i32 / 2;
    let h  = height as i32;

    let max_slots = (h as f32 / LINE_H) as isize + 3;

    for offset in -max_slots..=max_slots {
        let y_pos = cy as f32 + offset as f32 * LINE_H;
        let dist  = (y_pos - cy as f32).abs();
        let alpha = cosine_alpha(dist, h as f32);
        if alpha < 0.01 { continue; }

        let text  = ui.book_ring.get(offset);
        let alpha = if offset == 0 { alpha } else { alpha * 0.45 };
        let v     = (alpha * 255.0) as u8;
        draw_text_centered_color(buf, cache, text, cx, y_pos as i32, fs, [v, v, v], width, height);
    }

    // Header hint
    let hint = "F3: chapters — Enter to open — Alt+↑↓ swap";
    let v    = (255.0 * 0.25) as u8;
    let bar_y = height as i32 - (fs * 2.5) as i32;
    draw_text_centered_color(buf, cache, hint, cx, bar_y, fs * 0.85, [v, v, v], width, height);
}

// ── F4: Vault ─────────────────────────────────────────────────────────────────

fn draw_vault(buf: &mut [u8], cache: &mut GlyphCache, ui: &UiState, width: u32, height: u32, fs: f32) {
    let cx = width  as i32 / 2;
    let cy = height as i32 / 2;
    let h  = height as i32;

    let max_slots = (h as f32 / LINE_H) as isize + 3;

    for offset in -max_slots..=max_slots {
        let y_pos = cy as f32 + offset as f32 * LINE_H;
        let dist  = (y_pos - cy as f32).abs();
        let alpha = cosine_alpha(dist, h as f32);
        if alpha < 0.01 { continue; }

        let text  = ui.vault_ring.get(offset);
        let alpha = if offset == 0 { alpha } else { alpha * 0.45 };
        let v     = (alpha * 255.0) as u8;
        draw_text_centered_color(buf, cache, text, cx, y_pos as i32, fs, [v, v, v], width, height);
    }

    let hint = "F4: vault — Enter to insert — Ctrl+R shuffle";
    let v    = (255.0 * 0.25) as u8;
    let bar_y = height as i32 - (fs * 2.5) as i32;
    draw_text_centered_color(buf, cache, hint, cx, bar_y, fs * 0.85, [v, v, v], width, height);
}

// ── Text drawing ──────────────────────────────────────────────────────────────

fn draw_text_centered(
    buf: &mut [u8], cache: &mut GlyphCache, text: &str,
    cx: i32, cy: i32, fs: f32, alpha: f32, width: u32, height: u32,
) {
    let v = (alpha * 255.0) as u8;
    draw_text_centered_color(buf, cache, text, cx, cy, fs, [v, v, v], width, height);
}

fn draw_text_centered_color(
    buf: &mut [u8], cache: &mut GlyphCache, text: &str,
    cx: i32, cy: i32, fs: f32, color: [u8; 3], width: u32, height: u32,
) {
    let tw = cache.text_width(text, fs) as i32;
    let x  = cx - tw / 2;
    draw_text_color(buf, cache, text, x, cy, fs, color, width, height);
}

fn draw_text_color(
    buf: &mut [u8], cache: &mut GlyphCache, text: &str,
    x0: i32, baseline: i32, fs: f32, color: [u8; 3], width: u32, height: u32,
) {
    let mut x = x0;
    let w = width  as i32;
    let h = height as i32;

    for ch in text.chars() {
        cache.ensure(ch, fs);
        let Some((metrics, bitmap)) = cache.get(ch, fs) else {
            x += (fs * 0.6) as i32;
            continue;
        };
        let gw = metrics.width  as i32;
        let gh = metrics.height as i32;
        let gx = x + metrics.xmin;
        let gy = baseline - metrics.height as i32 - metrics.ymin;

        for row in 0..gh {
            for col in 0..gw {
                let px = gx + col;
                let py = gy + row;
                if px < 0 || py < 0 || px >= w || py >= h { continue; }
                let src_a = bitmap[(row * gw + col) as usize];
                if src_a == 0 { continue; }
                let a = src_a as f32 / 255.0;
                let off = ((py * w + px) * 4) as usize;
                buf[off]   = blend(buf[off],   color[2], a); // B
                buf[off+1] = blend(buf[off+1], color[1], a); // G
                buf[off+2] = blend(buf[off+2], color[0], a); // R
            }
        }
        x += metrics.advance_width as i32;
    }
}

// ── TAB status overlay ────────────────────────────────────────────────────────

fn draw_overlay(buf: &mut [u8], cache: &mut GlyphCache, ui: &UiState, width: u32, height: u32, fs: f32) {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let secs  = now % 60;
    let mins  = (now / 60) % 60;
    let hours = (now / 3600) % 24;

    let file  = ui.active_file.file_name()
        .unwrap_or_default().to_string_lossy().to_string();
    let n_lines = ui.ring.lines().iter()
        .filter(|l| l.trim() != "." && !l.is_empty()).count();
    let view_name = match ui.view {
        crate::input::View::Write => "F1 write",
        crate::input::View::Doc   => "F2 doc",
        crate::input::View::Book  => "F3 book",
        crate::input::View::Vault => "F4 vault",
    };

    let lines = [
        format!("{:02}:{:02}:{:02}", hours, mins, secs),
        format!("{file}  ·  {n_lines} lines"),
        view_name.to_string(),
    ];

    let box_w = 260i32;
    let line_h = (fs * 1.6) as i32;
    let box_h  = line_h * lines.len() as i32 + 20;
    let bx = width as i32 - box_w - 20;
    let by = height as i32 - box_h - 20;

    // Background box (semi-transparent black)
    for row in by..(by + box_h) {
        for col in bx..(bx + box_w) {
            if col < 0 || row < 0 || col >= width as i32 || row >= height as i32 { continue; }
            let off = ((row * width as i32 + col) * 4) as usize;
            buf[off]   = (buf[off]   as f32 * 0.2) as u8;
            buf[off+1] = (buf[off+1] as f32 * 0.2) as u8;
            buf[off+2] = (buf[off+2] as f32 * 0.2) as u8;
        }
    }

    // Text lines
    for (i, line) in lines.iter().enumerate() {
        let text_y = by + 12 + (i as i32) * line_h + line_h / 2;
        let cx     = bx + box_w / 2;
        let alpha  = if i == 0 { 0.95 } else { 0.65 };
        draw_text_centered(buf, cache, line, cx, text_y, fs, alpha, width, height);
    }
}

#[inline(always)]
fn blend(dst: u8, src: u8, alpha: f32) -> u8 {
    ((1.0 - alpha) * dst as f32 + alpha * src as f32).min(255.0) as u8
}
