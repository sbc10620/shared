mod data;
mod model;
mod optim;
mod rng;
mod scalar;
mod tensor;

use data::{get_batch, Tokenizer};
use model::{Config, Gpt};
use optim::AdamW;
use rng::Rng;
use std::time::Instant;
use tensor::{softmax_in_place, Graph};

const BATCH: usize = 16;
const STEPS: usize = 2000;
const EVAL_EVERY: usize = 200;

fn main() {
    let cmd = std::env::args().nth(1).unwrap_or_default();
    match cmd.as_str() {
        "scalar" => scalar::demo(),
        "data" => data_demo(),
        "train" => train(),
        _ => println!("usage: cargo run --release -- [scalar|data|train]"),
    }
}

fn data_demo() {
    let text =
        std::fs::read_to_string("input.txt").expect("input.txt not found");
    let tok = Tokenizer::new(&text);
    println!(
        "characters: {}  vocab: {}",
        text.chars().count(),
        tok.vocab_size()
    );
    let ids = tok.encode("Hello!");
    println!(
        "encode(\"Hello!\") = {ids:?}  decode -> {:?}",
        tok.decode(&ids)
    );

    let data = tok.encode(&text);
    let mut rng = Rng::new(1);
    let (x, y) = get_batch(&data, 1, 16, &mut rng);
    println!("input : {:?}", tok.decode(&x));
    println!("target: {:?}", tok.decode(&y));
}

/// Average loss over a few random batches, without training.
fn estimate_loss(
    model: &Gpt,
    g: &mut Graph,
    data: &[usize],
    rng: &mut Rng,
) -> f32 {
    let n_params = g.len();
    let seq = model.cfg.block_size;
    let mut total = 0.0;
    for _ in 0..10 {
        g.truncate(n_params);
        let (x, y) = get_batch(data, BATCH, seq, rng);
        let logits = model.forward(g, &x, BATCH, seq);
        let loss = g.cross_entropy(logits, &y);
        total += g.data(loss)[0];
    }
    total / 10.0
}

/// Generate `n` new tokens after `prompt`, one at a time.
fn generate(
    model: &Gpt,
    g: &mut Graph,
    prompt: &[usize],
    n: usize,
    temperature: f32,
    rng: &mut Rng,
) -> Vec<usize> {
    let n_params = g.len();
    let mut ids = prompt.to_vec();
    for _ in 0..n {
        g.truncate(n_params);
        // Only the last block_size tokens fit in the context.
        let start = ids.len().saturating_sub(model.cfg.block_size);
        let context = &ids[start..];
        let logits = model.forward(g, context, 1, context.len());
        // The last row predicts the token that comes next.
        let vocab = model.cfg.vocab;
        let last = &g.data(logits)[(context.len() - 1) * vocab..];
        let mut probs: Vec<f32> =
            last.iter().map(|x| x / temperature).collect();
        softmax_in_place(&mut probs);
        ids.push(sample(&probs, rng));
    }
    ids
}

/// Draw an index with probability probs[i].
fn sample(probs: &[f32], rng: &mut Rng) -> usize {
    let mut r = rng.uniform() as f32;
    for (i, &p) in probs.iter().enumerate() {
        if r < p {
            return i;
        }
        r -= p;
    }
    probs.len() - 1 // rounding left a tiny remainder
}

fn train() {
    let text =
        std::fs::read_to_string("input.txt").expect("input.txt not found");
    let tok = Tokenizer::new(&text);
    let data = tok.encode(&text);
    let split = data.len() * 9 / 10;
    let (train_data, val_data) = (&data[..split], &data[split..]);

    let cfg = Config {
        vocab: tok.vocab_size(),
        block_size: 32,
        n_embd: 64,
        n_head: 4,
        n_layer: 4,
    };
    let mut rng = Rng::new(1337);
    let mut g = Graph::new();
    let model = Gpt::new(&mut g, cfg, &mut rng);
    let n_params = g.len();
    println!("parameters: {}", model.num_params(&g));

    let mut opt = AdamW::new(&g, &model.params, 1e-3);
    let start = Instant::now();
    for step in 0..=STEPS {
        if step % EVAL_EVERY == 0 {
            let train_loss =
                estimate_loss(&model, &mut g, train_data, &mut rng);
            let val_loss =
                estimate_loss(&model, &mut g, val_data, &mut rng);
            let secs = start.elapsed().as_secs_f32();
            print!("step {step:5}  train {train_loss:.3}  ");
            println!("val {val_loss:.3}  ({secs:.0}s)");
        }
        if step == STEPS {
            break;
        }
        g.truncate(n_params);
        let (x, y) = get_batch(train_data, BATCH, cfg.block_size, &mut rng);
        let logits = model.forward(&mut g, &x, BATCH, cfg.block_size);
        let loss = g.cross_entropy(logits, &y);
        g.backward(loss);
        opt.step(&mut g, &model.params);
    }

    let prompt = tok.encode("\n");
    let out = generate(&model, &mut g, &prompt, 500, 0.8, &mut rng);
    println!("{}", tok.decode(&out));
}
