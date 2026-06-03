use std::{collections::HashMap, f64::consts::PI};
use fontdue::Font;

use crate::app::UiState;
use crate::input::View;

// ── Glyph cache ───────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
struct GlyphKey(char, u32); // (char, size_px * 64)

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
        self.bitmaps.entry(key).or_insert_with(|| {
            self.font.rasterize(ch, size)
        });
    }

    fn get(&self, ch: char, size: f32) -> Option<&(fontdue::Metrics, Vec<u8>)> {
        self.bitmaps.get(&GlyphKey(ch, (size * 64.0) as u32))
    }

    fn advance(&mut self, ch: char, size: f32) -> f32 {
        self.ensure(ch, size);
        self.get(ch, size).map(|(m, _)| m.advance_width).unwrap_or(size * 0.6)
    }

    fn text_width(&mut self, text: &str, size: f32) -> f32 {
        text.chars().map(|c| self.advance(c, size)).sum()
    }
}

// ── Main draw entry ───────────────────────────────────────────────────────────

pub fn draw_frame(
    buf:    &mut [u8],   // ARGB8888 shared memory buffer
    cache:  &mut GlyphCache,
    ui:     &UiState,
    width:  u32,
    height: u32,
) {
    // Clear to black
    for chunk in buf.chunks_exact_mut(4) {
        chunk[0] = 0;   // B
        chunk[1] = 0;   // G
        chunk[2] = 0;   // R
        chunk[3] = 255; // A
    }

    let font_size = ui.config.font_size;
    let line_h    = (font_size * ui.config.line_height) as i32;

    match ui.view {
        View::Write    => draw_write(buf, cache, ui, width, height, font_size, line_h),
        View::Navigate => draw_navigate(buf, cache, ui, width, height, font_size, line_h),
        View::Void     => {} // pure black — already cleared
    }
}

// ── Write view (F1) ───────────────────────────────────────────────────────────

fn draw_write(
    buf:       &mut [u8],
    cache:     &mut GlyphCache,
    ui:        &UiState,
    width:     u32,
    height:    u32,
    font_size: f32,
    line_h:    i32,
) {
    let cx = width as i32 / 2;
    let cy = height as i32 / 2;

    // Lines above center: previously committed lines, fading upward
    let max_lines = (height as i32 / 2 / line_h) + 2;

    for offset in -max_lines..=max_lines {
        let y_center = cy + offset * line_h;
        let falloff  = alpha_falloff(y_center, cy, height as i32);
        if falloff < 0.01 { continue; }

        let text = if offset == 0 {
            // Center line: current input (with cursor)
            if ui.command_mode {
                // In command mode, center shows "!" + buffer
                Some(format!("!{}{}", ui.cmd_buffer, if (ui.blink_tick / 30) % 2 == 0 { "▋" } else { "" }))
            } else {
                Some(format!("{}{}", ui.input, if (ui.blink_tick / 30) % 2 == 0 { "▋" } else { "" }))
            }
        } else if offset < 0 {
            // Above center: committed lines (most recent = offset -1)
            ui.ring.get_from_head((-offset - 1) as isize).map(str::to_owned)
        } else {
            None // nothing below the input line
        };

        if let Some(text) = text {
            draw_text_centered(buf, cache, &text, cx, y_center, font_size, falloff, width, height);
        }
    }

    // Command mode bottom bar
    if ui.command_mode {
        let prompt = format!("  !{}  ", ui.cmd_buffer);
        let bar_y  = height as i32 - (font_size * 2.5) as i32;
        draw_text_centered(buf, cache, &prompt, cx, bar_y, font_size, 1.0, width, height);
    }
}

// ── Navigate view (F2) ───────────────────────────────────────────────────────

fn draw_navigate(
    buf:       &mut [u8],
    cache:     &mut GlyphCache,
    ui:        &UiState,
    width:     u32,
    height:    u32,
    font_size: f32,
    line_h:    i32,
) {
    let cx = width as i32 / 2;
    let cy = height as i32 / 2;

    let filtered = ui.file_index.filter(&ui.search_query);
    let total    = filtered.len();
    if total == 0 {
        draw_text_centered(buf, cache, "(no files)", cx, cy, font_size, 0.5, width, height);
        return;
    }

    let sel = ui.nav_cursor.min(total.saturating_sub(1));
    let max_lines = (height as i32 / 2 / line_h) + 2;

    for offset in -max_lines..=max_lines {
        let idx = sel as isize + offset as isize;
        if idx < 0 || idx >= total as isize { continue; }

        let path = filtered[idx as usize];
        let name = path.file_stem().unwrap_or_default().to_string_lossy();

        let y_center = cy + offset as i32 * line_h;
        let falloff  = alpha_falloff(y_center, cy, height as i32);
        if falloff < 0.01 { continue; }

        // Selected line: full brightness. Others: dimmed.
        let alpha = if offset == 0 { falloff } else { falloff * 0.45 };
        draw_text_centered(buf, cache, &name, cx, y_center, font_size, alpha, width, height);
    }

    // Search query bottom bar
    if !ui.search_query.is_empty() {
        let bar_y = height as i32 - (font_size * 2.5) as i32;
        draw_text_centered(buf, cache, &format!("/ {}", ui.search_query), cx, bar_y, font_size, 0.8, width, height);
    }
}

// ── Alpha falloff ─────────────────────────────────────────────────────────────

fn alpha_falloff(y: i32, center_y: i32, screen_h: i32) -> f32 {
    let dist = (y - center_y).unsigned_abs() as f64;
    let half  = screen_h as f64 / 2.0;
    let t     = (dist / half).min(1.0);
    (t * PI / 2.0).cos() as f32
}

// ── Text drawing ──────────────────────────────────────────────────────────────

fn draw_text_centered(
    buf:       &mut [u8],
    cache:     &mut GlyphCache,
    text:      &str,
    cx:        i32,
    cy:        i32,
    font_size: f32,
    alpha:     f32,
    width:     u32,
    height:    u32,
) {
    let w = cache.text_width(text, font_size) as i32;
    let x = cx - w / 2;
    draw_text_at(buf, cache, text, x, cy, font_size, alpha, width, height);
}

fn draw_text_at(
    buf:       &mut [u8],
    cache:     &mut GlyphCache,
    text:      &str,
    x0:        i32,
    baseline:  i32,
    font_size: f32,
    alpha:     f32,
    width:     u32,
    height:    u32,
) {
    let mut x = x0;
    let w = width as i32;
    let h = height as i32;

    for ch in text.chars() {
        cache.ensure(ch, font_size);
        let Some((metrics, bitmap)) = cache.get(ch, font_size) else {
            x += (font_size * 0.6) as i32;
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

                let combined = ((src_a as f32) / 255.0 * alpha).min(1.0);
                let v        = (combined * 255.0) as u8;

                let off = ((py * w + px) * 4) as usize;
                // ARGB8888 in memory: B G R A
                buf[off]     = v; // B
                buf[off + 1] = v; // G
                buf[off + 2] = v; // R
                buf[off + 3] = 255; // A
            }
        }
        x += metrics.advance_width as i32;
    }
}
