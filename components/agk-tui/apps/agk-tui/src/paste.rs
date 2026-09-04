use rmux_sdk::{Pane, Result};

const BRACKETED_PASTE_START: &str = "\u{1b}[200~";
const BRACKETED_PASTE_END: &str = "\u{1b}[201~";
const PASTE_CHUNK_BYTES: usize = 16 * 1024;

/// Forward one clipboard paste without turning it into simulated typing.
///
/// The outer markers let provider editors render their native compact paste
/// indicator while UTF-8-safe chunks keep very large payloads below transport
/// frame and PTY pressure limits. The closing marker is attempted even if a
/// body write fails so the provider cannot remain stuck in paste mode.
pub async fn send(pane: &Pane, text: &str) -> Result<()> {
    pane.send_text(BRACKETED_PASTE_START).await?;

    let mut body_result = Ok(());
    for chunk in utf8_chunks(text, PASTE_CHUNK_BYTES) {
        if let Err(error) = pane.send_text(chunk).await {
            body_result = Err(error);
            break;
        }
    }

    let end_result = pane.send_text(BRACKETED_PASTE_END).await;
    match body_result {
        Err(error) => Err(error),
        Ok(()) => end_result,
    }
}

fn utf8_chunks(text: &str, max_bytes: usize) -> Vec<&str> {
    assert!(max_bytes > 0, "paste chunks must not be empty");

    let mut chunks = Vec::new();
    let mut start = 0;
    while start < text.len() {
        let mut end = (start + max_bytes).min(text.len());
        while !text.is_char_boundary(end) {
            end -= 1;
        }
        if end == start {
            end = start
                + text[start..]
                    .chars()
                    .next()
                    .expect("start is before the end of the paste")
                    .len_utf8();
        }
        chunks.push(&text[start..end]);
        start = end;
    }
    chunks
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn long_pastes_are_chunked_without_losing_text() {
        let text = format!("{}{}{}", "a".repeat(17_000), "東京 🛰️", "z".repeat(17_000));
        let chunks = utf8_chunks(&text, 1_003);

        assert!(chunks.len() > 2);
        assert!(chunks.iter().all(|chunk| chunk.len() <= 1_003));
        assert_eq!(chunks.concat(), text);
    }

    #[test]
    fn one_character_can_exceed_a_tiny_test_chunk() {
        let chunks = utf8_chunks("🛰️ok", 1);

        assert_eq!(chunks.concat(), "🛰️ok");
        assert!(chunks.iter().all(|chunk| !chunk.is_empty()));
    }

    #[test]
    fn empty_paste_has_no_body_chunks() {
        assert!(utf8_chunks("", PASTE_CHUNK_BYTES).is_empty());
    }
}
