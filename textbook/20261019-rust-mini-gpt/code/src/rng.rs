/// A tiny pseudo-random number generator (xorshift64*).
/// Same seed -> same sequence, so every run is reproducible.
pub struct Rng {
    state: u64,
}

impl Rng {
    pub fn new(seed: u64) -> Self {
        // A zero state would stay zero forever, so avoid it.
        Rng { state: seed.max(1) }
    }

    /// Next raw 64-bit random number.
    pub fn next_u64(&mut self) -> u64 {
        let mut x = self.state;
        x ^= x >> 12;
        x ^= x << 25;
        x ^= x >> 27;
        self.state = x;
        x.wrapping_mul(0x2545_F491_4F6C_DD1D)
    }

    /// Uniform float in [0, 1).
    pub fn uniform(&mut self) -> f64 {
        // Keep the top 53 bits: exactly the precision of an f64 mantissa.
        (self.next_u64() >> 11) as f64 / (1u64 << 53) as f64
    }

    /// Uniform integer in [0, n).
    pub fn below(&mut self, n: usize) -> usize {
        (self.uniform() * n as f64) as usize
    }

    /// Standard normal sample (mean 0, std 1) via the Box-Muller transform.
    pub fn normal(&mut self) -> f64 {
        let u1 = self.uniform().max(1e-12); // avoid ln(0)
        let u2 = self.uniform();
        (-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos()
    }
}
