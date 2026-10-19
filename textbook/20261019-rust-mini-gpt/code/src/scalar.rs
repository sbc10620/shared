use crate::rng::Rng;

/// Handle to one value on the tape. It is just an index, so it is Copy.
#[derive(Clone, Copy, Debug)]
pub struct V(pub usize);

/// How a value was produced. The inputs are indices of earlier values.
#[derive(Clone, Copy, Debug)]
enum Op {
    Leaf,
    Add(usize, usize),
    Mul(usize, usize),
    Tanh(usize),
}

/// The tape: every value ever computed, in the order it was computed.
pub struct Tape {
    vals: Vec<f64>,
    grads: Vec<f64>,
    ops: Vec<Op>,
}

impl Tape {
    pub fn new() -> Self {
        Tape { vals: Vec::new(), grads: Vec::new(), ops: Vec::new() }
    }

    /// Append a value and return its handle.
    fn push(&mut self, val: f64, op: Op) -> V {
        self.vals.push(val);
        self.grads.push(0.0);
        self.ops.push(op);
        V(self.vals.len() - 1)
    }

    pub fn leaf(&mut self, x: f64) -> V {
        self.push(x, Op::Leaf)
    }

    pub fn val(&self, v: V) -> f64 {
        self.vals[v.0]
    }

    pub fn grad(&self, v: V) -> f64 {
        self.grads[v.0]
    }

    pub fn add(&mut self, a: V, b: V) -> V {
        let y = self.vals[a.0] + self.vals[b.0];
        self.push(y, Op::Add(a.0, b.0))
    }

    pub fn mul(&mut self, a: V, b: V) -> V {
        let y = self.vals[a.0] * self.vals[b.0];
        self.push(y, Op::Mul(a.0, b.0))
    }

    pub fn tanh(&mut self, a: V) -> V {
        let y = self.vals[a.0].tanh();
        self.push(y, Op::Tanh(a.0))
    }

    /// a - b, built from the ops we already have: a + (-1 * b).
    pub fn sub(&mut self, a: V, b: V) -> V {
        let minus_one = self.leaf(-1.0);
        let neg_b = self.mul(b, minus_one);
        self.add(a, neg_b)
    }

    /// Fill grads[i] = d(out)/d(value i) for every value on the tape.
    pub fn backward(&mut self, out: V) {
        self.grads.fill(0.0);
        self.grads[out.0] = 1.0;
        // Inputs always sit before outputs, so walking backwards
        // visits every node after all of its consumers.
        for i in (0..=out.0).rev() {
            let g = self.grads[i];
            match self.ops[i] {
                Op::Leaf => {}
                Op::Add(a, b) => {
                    self.grads[a] += g;
                    self.grads[b] += g;
                }
                Op::Mul(a, b) => {
                    self.grads[a] += self.vals[b] * g;
                    self.grads[b] += self.vals[a] * g;
                }
                Op::Tanh(a) => {
                    let t = self.vals[i];
                    self.grads[a] += (1.0 - t * t) * g;
                }
            }
        }
    }

    /// Drop everything after the first `len` values (keeps the parameters).
    pub fn truncate(&mut self, len: usize) {
        self.vals.truncate(len);
        self.grads.truncate(len);
        self.ops.truncate(len);
    }

    /// Gradient descent step on parameter `p`.
    pub fn step(&mut self, p: V, lr: f64) {
        self.vals[p.0] -= lr * self.grads[p.0];
    }
}

/// One neuron: tanh(w . x + b).
pub struct Neuron {
    w: Vec<V>,
    b: V,
}

impl Neuron {
    pub fn new(tape: &mut Tape, n_in: usize, rng: &mut Rng) -> Self {
        let w = (0..n_in)
            .map(|_| tape.leaf(rng.uniform() * 2.0 - 1.0))
            .collect();
        let b = tape.leaf(0.0);
        Neuron { w, b }
    }

    pub fn forward(&self, tape: &mut Tape, x: &[V]) -> V {
        let mut sum = self.b;
        for (wi, xi) in self.w.iter().zip(x) {
            let p = tape.mul(*wi, *xi);
            sum = tape.add(sum, p);
        }
        tape.tanh(sum)
    }

    pub fn params(&self) -> Vec<V> {
        let mut p = self.w.clone();
        p.push(self.b);
        p
    }
}

/// A fully connected layer: `n_out` neurons that all see the same input.
pub struct Layer {
    neurons: Vec<Neuron>,
}

impl Layer {
    pub fn new(
        tape: &mut Tape,
        n_in: usize,
        n_out: usize,
        rng: &mut Rng,
    ) -> Self {
        Layer {
            neurons: (0..n_out)
                .map(|_| Neuron::new(tape, n_in, rng))
                .collect(),
        }
    }

    pub fn forward(&self, tape: &mut Tape, x: &[V]) -> Vec<V> {
        self.neurons.iter().map(|n| n.forward(tape, x)).collect()
    }

    pub fn params(&self) -> Vec<V> {
        self.neurons.iter().flat_map(|n| n.params()).collect()
    }
}

/// Layers stacked one after another.
pub struct Mlp {
    layers: Vec<Layer>,
}

impl Mlp {
    /// sizes = [inputs, hidden1, ..., outputs]
    pub fn new(tape: &mut Tape, sizes: &[usize], rng: &mut Rng) -> Self {
        let layers = sizes
            .windows(2)
            .map(|w| Layer::new(tape, w[0], w[1], rng))
            .collect();
        Mlp { layers }
    }

    pub fn forward(&self, tape: &mut Tape, x: &[V]) -> Vec<V> {
        let mut h = x.to_vec();
        for layer in &self.layers {
            h = layer.forward(tape, &h);
        }
        h
    }

    pub fn params(&self) -> Vec<V> {
        self.layers.iter().flat_map(|l| l.params()).collect()
    }
}

/// Check backward by hand on y = a * b + c.
fn hand_check() {
    let mut tape = Tape::new();
    let a = tape.leaf(2.0);
    let b = tape.leaf(-3.0);
    let c = tape.leaf(10.0);
    let ab = tape.mul(a, b);
    let y = tape.add(ab, c);
    tape.backward(y);
    // Expected: dy/da = b = -3, dy/db = a = 2, dy/dc = 1
    println!(
        "y = {}  dy/da = {}  dy/db = {}  dy/dc = {}",
        tape.val(y),
        tape.grad(a),
        tape.grad(b),
        tape.grad(c)
    );
}

/// Train a 3-4-4-1 MLP on four hand-made examples.
pub fn demo() {
    hand_check();

    let xs = [
        [2.0, 3.0, -1.0],
        [3.0, -1.0, 0.5],
        [0.5, 1.0, 1.0],
        [1.0, 1.0, -1.0],
    ];
    let ys = [1.0, -1.0, -1.0, 1.0];

    let mut rng = Rng::new(42);
    let mut tape = Tape::new();
    let mlp = Mlp::new(&mut tape, &[3, 4, 4, 1], &mut rng);
    let params = mlp.params();
    let n_params = params.len(); // parameters occupy tape[0..n_params]
    println!("parameters: {n_params}");

    for step in 0..100 {
        // Forget last step's graph, keep the parameters.
        tape.truncate(n_params);

        // Forward: sum of squared errors over the four examples.
        let mut loss = tape.leaf(0.0);
        let mut preds = Vec::new();
        for (x, y) in xs.iter().zip(ys) {
            let x: Vec<V> = x.iter().map(|&v| tape.leaf(v)).collect();
            let pred = mlp.forward(&mut tape, &x)[0];
            let target = tape.leaf(y);
            let diff = tape.sub(pred, target);
            let sq = tape.mul(diff, diff);
            loss = tape.add(loss, sq);
            preds.push(pred);
        }

        // Backward, then nudge every parameter against its gradient.
        tape.backward(loss);
        for &p in &params {
            tape.step(p, 0.05);
        }

        if step % 10 == 0 || step == 99 {
            let p: Vec<String> = preds
                .iter()
                .map(|&v| format!("{:+.3}", tape.val(v)))
                .collect();
            println!(
                "step {step:3}  loss {:.4}  preds [{}]",
                tape.val(loss),
                p.join(", ")
            );
        }
    }
}
