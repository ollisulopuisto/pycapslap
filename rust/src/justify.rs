//! Two-line captions flush to the same width, each line sized to fit it.
//!
//! The look every short-form editor calls "justified": the cue is split into
//! two lines and each line gets its own font size so both end up exactly as
//! wide as the caption box. A short line therefore renders big and a long one
//! small, and the block reads as one solid rectangle of text.

use crate::text_metrics::{self, FontMetrics};

/// One laid-out line: which of the cue's words it holds, and at what size.
#[derive(Debug, Clone, PartialEq)]
pub struct JustifiedLine {
    /// Index range into the cue's token list, `start..end`.
    pub start: usize,
    pub end: usize,
    pub font_px: u32,
}

/// How far a line's size may stray from the style's own font size before the
/// split is considered ugly and another one is tried.
/// A long line is *meant* to render small in this style, so the floor is
/// about readability, not about staying near the style's size.
const MIN_SIZE_RATIO: f32 = 0.35;
const MAX_SIZE_RATIO: f32 = 2.2;

/// Split `tokens` into at most two lines, each scaled to `target_w`.
///
/// Falls back to a single line when there is only one word, or when no split
/// keeps both lines within a sane size range.
pub fn justify_two_lines(
    tokens: &[String],
    font_family: &str,
    target_w: f32,
    base_px: u32,
) -> Vec<JustifiedLine> {
    if tokens.is_empty() || target_w <= 0.0 {
        return Vec::new();
    }

    let metrics = match text_metrics::metrics_for(font_family) {
        Some(m) => m,
        // No measurable font: one line at the style's own size, and libass
        // wraps it like any other cue.
        None => {
            return vec![JustifiedLine {
                start: 0,
                end: tokens.len(),
                font_px: base_px,
            }]
        }
    };

    if tokens.len() == 1 {
        return vec![JustifiedLine {
            start: 0,
            end: 1,
            font_px: line_size(metrics, tokens, 0, 1, target_w, base_px),
        }];
    }

    let min_px = (base_px as f32 * MIN_SIZE_RATIO).max(8.0);
    let max_px = base_px as f32 * MAX_SIZE_RATIO;

    // Start from an even word split — the first line ends up holding the
    // shorter half, which is what makes it the big one — and walk outwards
    // until both lines sit within the allowed size range.
    let n = tokens.len();
    let preferred = (n / 2).max(1);
    let mut candidates: Vec<usize> = vec![preferred];
    for offset in 1..n {
        for split in [preferred.wrapping_sub(offset), preferred + offset] {
            if split >= 1 && split < n && !candidates.contains(&split) {
                candidates.push(split);
            }
        }
    }

    for split in candidates {
        let first = raw_size(metrics, tokens, 0, split, target_w);
        let second = raw_size(metrics, tokens, split, n, target_w);
        if first >= min_px && first <= max_px && second >= min_px && second <= max_px {
            return vec![
                JustifiedLine {
                    start: 0,
                    end: split,
                    font_px: first.round() as u32,
                },
                JustifiedLine {
                    start: split,
                    end: n,
                    font_px: second.round() as u32,
                },
            ];
        }
    }

    // Nothing balanced: one line, clamped so it still fits the box.
    vec![JustifiedLine {
        start: 0,
        end: n,
        font_px: line_size(metrics, tokens, 0, n, target_w, base_px),
    }]
}

fn line_text(tokens: &[String], start: usize, end: usize) -> String {
    tokens[start..end].join(" ")
}

fn raw_size(
    metrics: &FontMetrics,
    tokens: &[String],
    start: usize,
    end: usize,
    target_w: f32,
) -> f32 {
    metrics.size_for_width(&line_text(tokens, start, end), target_w)
}

fn line_size(
    metrics: &FontMetrics,
    tokens: &[String],
    start: usize,
    end: usize,
    target_w: f32,
    base_px: u32,
) -> u32 {
    let size = raw_size(metrics, tokens, start, end, target_w);
    if size <= 0.0 {
        return base_px;
    }
    // A single line may be smaller than the style asks for (it has to fit) but
    // never larger, or one-word cues would fill the frame.
    size.min(base_px as f32 * MAX_SIZE_RATIO).round() as u32
}

#[cfg(test)]
mod tests {
    use super::*;

    fn toks(words: &[&str]) -> Vec<String> {
        words.iter().map(|w| w.to_string()).collect()
    }

    #[test]
    fn both_lines_end_up_the_same_width() {
        let tokens = toks(&["VÄHÄN", "NIINKU", "HUONOSTA", "MIESVALINNASTA"]);
        let target = 900.0;

        let lines = justify_two_lines(&tokens, "Montserrat Black", target, 80);
        assert_eq!(lines.len(), 2);

        let metrics = text_metrics::metrics_for("Montserrat Black").unwrap();
        for line in &lines {
            let text = line_text(&tokens, line.start, line.end);
            let width = metrics.measure(&text, line.font_px as f32);
            // Rounding the size to whole pixels is the only slack allowed.
            assert!(
                (width - target).abs() < target * 0.01,
                "line {:?} rendered {width}px wide, wanted {target}px",
                text
            );
        }
    }

    #[test]
    fn the_shorter_line_gets_the_bigger_font() {
        let tokens = toks(&["VÄHÄN", "NIINKU", "HUONOSTA", "MIESVALINNASTA"]);
        let lines = justify_two_lines(&tokens, "Montserrat Black", 900.0, 80);

        assert_eq!(lines.len(), 2);
        assert!(
            lines[0].font_px > lines[1].font_px,
            "first line {:?} should be the big one",
            lines
        );
    }

    #[test]
    fn a_single_word_stays_on_one_line() {
        let lines = justify_two_lines(&toks(&["KAUPPAKESKUS"]), "Montserrat Black", 900.0, 80);
        assert_eq!(lines.len(), 1);
        assert_eq!((lines[0].start, lines[0].end), (0, 1));
    }

    #[test]
    fn a_wildly_lopsided_split_is_avoided() {
        // "I" alone would have to be rendered absurdly large to fill the box.
        let tokens = toks(&["I", "AJATTELIN", "ETTÄ", "TÄMÄ", "ON", "IHAN", "HYVÄ"]);
        let lines = justify_two_lines(&tokens, "Montserrat Black", 900.0, 80);

        for line in &lines {
            assert!(line.font_px as f32 <= 80.0 * MAX_SIZE_RATIO);
            assert!(line.font_px as f32 >= 80.0 * MIN_SIZE_RATIO);
        }
    }
}

