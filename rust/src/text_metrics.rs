//! Glyph-accurate text measurement over the bundled caption fonts.
//!
//! Caption layout used to guess line widths from a character count, which is
//! why lines overflowed the frame and why the editor preview never matched the
//! burn. Measuring the actual font removes the guess: the same numbers drive
//! the ASS document and the preview layout the editor draws.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};

/// Advance widths of one font, in em units (multiply by font size in px).
pub struct FontMetrics {
    advances: HashMap<char, f32>,
    units_per_em: f32,
    fallback_advance: f32,
}

impl FontMetrics {
    fn from_file(path: &Path) -> Option<FontMetrics> {
        let data = std::fs::read(path).ok()?;
        let face = ttf_parser::Face::parse(&data, 0).ok()?;
        let units_per_em = face.units_per_em() as f32;
        if units_per_em <= 0.0 {
            return None;
        }

        // Cover Latin plus the Nordic letters captions actually contain; a
        // character outside the set falls back to the average advance, which
        // only ever affects exotic punctuation.
        let mut advances = HashMap::new();
        let mut total = 0.0f32;
        let mut counted = 0u32;
        for c in (0x20u32..0x17Fu32).filter_map(char::from_u32) {
            if let Some(gid) = face.glyph_index(c) {
                if let Some(adv) = face.glyph_hor_advance(gid) {
                    let em_fraction = adv as f32 / units_per_em;
                    advances.insert(c, em_fraction);
                    total += em_fraction;
                    counted += 1;
                }
            }
        }
        if counted == 0 {
            return None;
        }

        Some(FontMetrics {
            advances,
            units_per_em,
            fallback_advance: total / counted as f32,
        })
    }

    /// Width of `text` when set at `font_px`, in pixels.
    pub fn measure(&self, text: &str, font_px: f32) -> f32 {
        let em_width: f32 = text
            .chars()
            .map(|c| self.advances.get(&c).copied().unwrap_or(self.fallback_advance))
            .sum();
        em_width * font_px
    }

    /// The font size at which `text` is exactly `target_px` wide.
    pub fn size_for_width(&self, text: &str, target_px: f32) -> f32 {
        let em_width = self.measure(text, 1.0);
        if em_width <= 0.0 {
            return 0.0;
        }
        target_px / em_width
    }

    #[allow(dead_code)]
    pub fn units_per_em(&self) -> f32 {
        self.units_per_em
    }
}

fn fonts_dir() -> Option<PathBuf> {
    if let Ok(path) = std::env::var("CAPSLAP_FONTS_DIR") {
        let p = PathBuf::from(path);
        if p.is_dir() {
            return Some(p);
        }
    }
    let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("src/fonts");
    if dev.is_dir() {
        return Some(dev);
    }
    let exe = std::env::current_exe().ok()?;
    let dir = exe.parent()?;
    [dir.join("fonts"), dir.parent()?.join("Resources/fonts")]
        .into_iter()
        .find(|candidate| candidate.is_dir())
}

/// Find the font file whose family or full name matches `family`.
///
/// The style presets name fonts the way libass resolves them ("Roboto Bold"),
/// which is a full name rather than a family, so both are matched.
fn find_font_file(family: &str) -> Option<PathBuf> {
    let dir = fonts_dir()?;
    let wanted = normalize_name(family);

    let mut fallback: Option<PathBuf> = None;
    for entry in std::fs::read_dir(dir).ok()?.flatten() {
        let path = entry.path();
        let ext = path
            .extension()
            .and_then(|e| e.to_str())
            .map(|e| e.to_lowercase());
        if !matches!(ext.as_deref(), Some("ttf") | Some("otf")) {
            continue;
        }

        if let Ok(data) = std::fs::read(&path) {
            if let Ok(face) = ttf_parser::Face::parse(&data, 0) {
                for name in face.names().into_iter() {
                    // 1 = family, 4 = full name.
                    if !matches!(name.name_id, 1 | 4) {
                        continue;
                    }
                    if let Some(value) = name.to_string() {
                        if normalize_name(&value) == wanted {
                            return Some(path);
                        }
                    }
                }
            }
        }
        if fallback.is_none() {
            fallback = Some(path);
        }
    }
    fallback
}

fn normalize_name(name: &str) -> String {
    name.chars()
        .filter(|c| c.is_alphanumeric())
        .flat_map(|c| c.to_lowercase())
        .collect()
}

type MetricsCache = HashMap<String, Option<&'static FontMetrics>>;

/// Metrics for a font family, loaded once per process.
pub fn metrics_for(family: &str) -> Option<&'static FontMetrics> {
    static CACHE: OnceLock<Mutex<MetricsCache>> = OnceLock::new();
    let cache = CACHE.get_or_init(|| Mutex::new(HashMap::new()));

    let mut guard = cache.lock().ok()?;
    if let Some(hit) = guard.get(family) {
        return *hit;
    }

    let loaded = find_font_file(family)
        .as_deref()
        .and_then(FontMetrics::from_file)
        // Leaked deliberately: one small table per font, alive for the process.
        .map(|m| &*Box::leak(Box::new(m)));
    guard.insert(family.to_string(), loaded);
    loaded
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn measures_a_bundled_font_and_scales_linearly() {
        let m = metrics_for("Montserrat Black").expect("bundled font should load");

        let at_50 = m.measure("KAUPPA", 50.0);
        let at_100 = m.measure("KAUPPA", 100.0);

        assert!(at_50 > 0.0);
        assert!((at_100 - at_50 * 2.0).abs() < 0.01);
        // A wider string must measure wider at the same size.
        assert!(m.measure("MIESVALINNASTA", 50.0) > at_50);
    }

    #[test]
    fn size_for_width_round_trips() {
        let m = metrics_for("Montserrat Black").expect("bundled font should load");

        let size = m.size_for_width("VÄHÄN NIINKU", 900.0);
        assert!(size > 0.0);
        assert!((m.measure("VÄHÄN NIINKU", size) - 900.0).abs() < 0.5);
    }

    #[test]
    fn unknown_family_still_returns_something_measurable() {
        // libass would fall back too; layout must not divide by zero.
        let m = metrics_for("No Such Font 12345").expect("a fallback face");
        assert!(m.measure("ABC", 40.0) > 0.0);
    }
}
