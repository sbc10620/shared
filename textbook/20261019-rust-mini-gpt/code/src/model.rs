use crate::rng::Rng;
use crate::tensor::{Graph, T};

/// Model size settings.
#[derive(Clone, Copy)]
pub struct Config {
    pub vocab: usize,      // number of distinct tokens
    pub block_size: usize, // longest context the model can see
    pub n_embd: usize,     // width of every token vector
    pub n_head: usize,     // attention heads per block
    pub n_layer: usize,    // number of transformer blocks
}

/// Creates parameters on the graph and remembers them for the optimizer.
pub struct ParamBuilder<'a> {
    pub g: &'a mut Graph,
    pub rng: &'a mut Rng,
    pub params: Vec<T>,
}

impl ParamBuilder<'_> {
    /// rows x cols matrix with values drawn from N(0, std^2).
    pub fn normal(&mut self, rows: usize, cols: usize, std: f32) -> T {
        let data = (0..rows * cols)
            .map(|_| self.rng.normal() as f32 * std)
            .collect();
        let t = self.g.leaf(data, rows, cols);
        self.params.push(t);
        t
    }

    /// rows x cols matrix filled with one value.
    pub fn constant(&mut self, rows: usize, cols: usize, value: f32) -> T {
        let t = self.g.leaf(vec![value; rows * cols], rows, cols);
        self.params.push(t);
        t
    }
}

/// y = x @ w + b
pub struct Linear {
    w: T, // n_in x n_out
    b: T, // 1 x n_out
}

impl Linear {
    pub fn new(p: &mut ParamBuilder, n_in: usize, n_out: usize) -> Self {
        Linear {
            w: p.normal(n_in, n_out, 0.02),
            b: p.constant(1, n_out, 0.0),
        }
    }

    pub fn forward(&self, g: &mut Graph, x: T) -> T {
        let y = g.matmul(x, self.w);
        g.add_row(y, self.b)
    }
}

/// Normalize each row, then scale by gamma and shift by beta
/// (both learned).
pub struct LayerNorm {
    gamma: T, // 1 x n
    beta: T,  // 1 x n
}

impl LayerNorm {
    pub fn new(p: &mut ParamBuilder, n: usize) -> Self {
        LayerNorm {
            gamma: p.constant(1, n, 1.0),
            beta: p.constant(1, n, 0.0),
        }
    }

    pub fn forward(&self, g: &mut Graph, x: T) -> T {
        let y = g.layer_norm(x);
        let y = g.mul_row(y, self.gamma);
        g.add_row(y, self.beta)
    }
}

/// Causal multi-head self-attention.
pub struct Attention {
    qkv: Linear,  // n_embd -> 3 * n_embd (query, key, value side by side)
    proj: Linear, // n_embd -> n_embd
    n_head: usize,
}

impl Attention {
    pub fn new(p: &mut ParamBuilder, cfg: &Config) -> Self {
        Attention {
            qkv: Linear::new(p, cfg.n_embd, 3 * cfg.n_embd),
            proj: Linear::new(p, cfg.n_embd, cfg.n_embd),
            n_head: cfg.n_head,
        }
    }

    /// One head for one sequence: q, k, v are seq x head_size.
    fn head(g: &mut Graph, q: T, k: T, v: T) -> T {
        let head_size = g.shape(q).1;
        let kt = g.transpose(k); // head_size x seq
        // seq x seq: how much each query matches each key
        let scores = g.matmul(q, kt);
        let scores = g.scale(scores, 1.0 / (head_size as f32).sqrt());
        let scores = g.causal_mask(scores); // no peeking at future tokens
        let weights = g.softmax(scores); // each row sums to 1
        g.matmul(weights, v) // seq x head_size: weighted average of values
    }

    /// x: (batch * seq) x n_embd -> same shape.
    pub fn forward(
        &self,
        g: &mut Graph,
        x: T,
        batch: usize,
        seq: usize,
    ) -> T {
        let c = g.shape(x).1;
        let hs = c / self.n_head;
        let qkv = self.qkv.forward(g, x); // (batch * seq) x 3c
        let mut seqs = Vec::with_capacity(batch);
        for b in 0..batch {
            // seq x 3c: the rows of one sequence
            let rows = g.slice_rows(qkv, b * seq, seq);
            let mut heads = Vec::with_capacity(self.n_head);
            for h in 0..self.n_head {
                let q = g.slice_cols(rows, h * hs, hs);
                let k = g.slice_cols(rows, c + h * hs, hs);
                let v = g.slice_cols(rows, 2 * c + h * hs, hs);
                heads.push(Self::head(g, q, k, v));
            }
            seqs.push(g.concat_cols(&heads)); // seq x c
        }
        let y = g.concat_rows(&seqs); // (batch * seq) x c
        self.proj.forward(g, y)
    }
}

/// Position-wise feed-forward network: expand 4x, ReLU, project back.
pub struct Mlp {
    fc: Linear,
    proj: Linear,
}

impl Mlp {
    pub fn new(p: &mut ParamBuilder, n_embd: usize) -> Self {
        Mlp {
            fc: Linear::new(p, n_embd, 4 * n_embd),
            proj: Linear::new(p, 4 * n_embd, n_embd),
        }
    }

    pub fn forward(&self, g: &mut Graph, x: T) -> T {
        let h = self.fc.forward(g, x);
        let h = g.relu(h);
        self.proj.forward(g, h)
    }
}

/// One transformer block: x + attn(ln(x)), then x + mlp(ln(x)).
pub struct Block {
    ln1: LayerNorm,
    attn: Attention,
    ln2: LayerNorm,
    mlp: Mlp,
}

impl Block {
    pub fn new(p: &mut ParamBuilder, cfg: &Config) -> Self {
        Block {
            ln1: LayerNorm::new(p, cfg.n_embd),
            attn: Attention::new(p, cfg),
            ln2: LayerNorm::new(p, cfg.n_embd),
            mlp: Mlp::new(p, cfg.n_embd),
        }
    }

    pub fn forward(
        &self,
        g: &mut Graph,
        x: T,
        batch: usize,
        seq: usize,
    ) -> T {
        let h = self.ln1.forward(g, x);
        let h = self.attn.forward(g, h, batch, seq);
        let x = g.add(x, h); // residual connection
        let h = self.ln2.forward(g, x);
        let h = self.mlp.forward(g, h);
        g.add(x, h) // residual connection
    }
}

/// The whole model.
pub struct Gpt {
    pub cfg: Config,
    tok_emb: T, // vocab x n_embd
    pos_emb: T, // block_size x n_embd
    blocks: Vec<Block>,
    ln_f: LayerNorm,
    head: Linear, // n_embd -> vocab
    pub params: Vec<T>,
}

impl Gpt {
    /// Create every parameter. Call this on an empty graph so the
    /// parameters occupy the first `params.len()` slots.
    pub fn new(g: &mut Graph, cfg: Config, rng: &mut Rng) -> Self {
        let mut p = ParamBuilder { g, rng, params: Vec::new() };
        let tok_emb = p.normal(cfg.vocab, cfg.n_embd, 0.02);
        let pos_emb = p.normal(cfg.block_size, cfg.n_embd, 0.02);
        let blocks =
            (0..cfg.n_layer).map(|_| Block::new(&mut p, &cfg)).collect();
        let ln_f = LayerNorm::new(&mut p, cfg.n_embd);
        let head = Linear::new(&mut p, cfg.n_embd, cfg.vocab);
        let params = p.params;
        Gpt { cfg, tok_emb, pos_emb, blocks, ln_f, head, params }
    }

    /// Total number of learned numbers.
    pub fn num_params(&self, g: &Graph) -> usize {
        self.params.iter().map(|&t| g.data(t).len()).sum()
    }

    /// ids: batch * seq token ids -> logits: (batch * seq) x vocab.
    pub fn forward(
        &self,
        g: &mut Graph,
        ids: &[usize],
        batch: usize,
        seq: usize,
    ) -> T {
        assert!(
            seq <= self.cfg.block_size,
            "sequence longer than block_size"
        );
        let positions: Vec<usize> =
            (0..batch).flat_map(|_| 0..seq).collect();
        let tok = g.embedding(self.tok_emb, ids);
        let pos = g.embedding(self.pos_emb, &positions);
        let mut x = g.add(tok, pos);
        for block in &self.blocks {
            x = block.forward(g, x, batch, seq);
        }
        let x = self.ln_f.forward(g, x);
        self.head.forward(g, x)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A model small enough to build in a few milliseconds.
    fn tiny_config() -> Config {
        Config {
            vocab: 65,
            block_size: 8,
            n_embd: 16,
            n_head: 4,
            n_layer: 2,
        }
    }

    #[test]
    fn block_keeps_shape() {
        let cfg = tiny_config();
        let mut rng = Rng::new(1);
        let mut g = Graph::new();
        let mut p =
            ParamBuilder { g: &mut g, rng: &mut rng, params: Vec::new() };
        let block = Block::new(&mut p, &cfg);

        let (batch, seq) = (2, 8);
        let data = (0..batch * seq * cfg.n_embd)
            .map(|_| rng.normal() as f32)
            .collect();
        let x = g.leaf(data, batch * seq, cfg.n_embd);
        let y = block.forward(&mut g, x, batch, seq);
        assert_eq!(g.shape(y), (batch * seq, cfg.n_embd));

        // Backward must run through every op without hitting todo!().
        let targets = vec![0; batch * seq];
        let loss = g.cross_entropy(y, &targets);
        g.backward(loss);
    }

    #[test]
    fn initial_loss_is_near_ln_vocab() {
        let cfg = tiny_config();
        let mut rng = Rng::new(1);
        let mut g = Graph::new();
        let model = Gpt::new(&mut g, cfg, &mut rng);

        let (batch, seq) = (2, 8);
        let ids: Vec<usize> =
            (0..batch * seq).map(|_| rng.below(cfg.vocab)).collect();
        let targets: Vec<usize> =
            (0..batch * seq).map(|_| rng.below(cfg.vocab)).collect();
        let logits = model.forward(&mut g, &ids, batch, seq);
        assert_eq!(g.shape(logits), (batch * seq, cfg.vocab));

        let loss = g.cross_entropy(logits, &targets);
        let value = g.data(loss)[0];
        println!(
            "initial loss {value:.4}, ln(vocab) {:.4}",
            (cfg.vocab as f32).ln()
        );
        assert!((value - (cfg.vocab as f32).ln()).abs() < 0.1);
        g.backward(loss);
    }
}
