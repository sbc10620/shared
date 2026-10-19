use crate::rng::Rng;

/// Character-level tokenizer: every distinct character is one token.
pub struct Tokenizer {
    chars: Vec<char>, // token id -> character
}

impl Tokenizer {
    /// Build the vocabulary from every character that appears in `text`.
    pub fn new(text: &str) -> Self {
        let mut chars: Vec<char> = text.chars().collect();
        chars.sort();
        chars.dedup();
        Tokenizer { chars }
    }

    pub fn vocab_size(&self) -> usize {
        self.chars.len()
    }

    /// Text -> token ids.
    /// Panics on a character that is not in the vocabulary.
    pub fn encode(&self, text: &str) -> Vec<usize> {
        text.chars()
            .map(|c| {
                self.chars
                    .binary_search(&c)
                    .expect("character not in vocabulary")
            })
            .collect()
    }

    /// Token ids -> text.
    pub fn decode(&self, ids: &[usize]) -> String {
        ids.iter().map(|&i| self.chars[i]).collect()
    }
}

/// Pick `batch` random windows of `seq + 1` tokens from `data`.
/// Inputs are the first `seq` tokens of each window, targets the last `seq`
/// (the same window shifted by one).
/// Both come back flattened: batch * seq ids.
pub fn get_batch(
    data: &[usize],
    batch: usize,
    seq: usize,
    rng: &mut Rng,
) -> (Vec<usize>, Vec<usize>) {
    let mut inputs = Vec::with_capacity(batch * seq);
    let mut targets = Vec::with_capacity(batch * seq);
    for _ in 0..batch {
        let start = rng.below(data.len() - seq);
        inputs.extend_from_slice(&data[start..start + seq]);
        targets.extend_from_slice(&data[start + 1..start + seq + 1]);
    }
    (inputs, targets)
}
