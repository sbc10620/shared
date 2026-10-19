use crate::tensor::{Graph, T};

/// Adam with decoupled weight decay.
pub struct AdamW {
    pub lr: f32,
    beta1: f32,
    beta2: f32,
    eps: f32,
    weight_decay: f32,
    t: i32,          // steps taken so far
    m: Vec<Vec<f32>>, // running mean of gradients, one Vec per parameter
    v: Vec<Vec<f32>>, // running mean of squared gradients
}

impl AdamW {
    pub fn new(g: &Graph, params: &[T], lr: f32) -> Self {
        let zeros =
            || params.iter().map(|&p| vec![0.0; g.data(p).len()]).collect();
        AdamW {
            lr,
            beta1: 0.9,
            beta2: 0.99,
            eps: 1e-8,
            weight_decay: 0.1,
            t: 0,
            m: zeros(),
            v: zeros(),
        }
    }

    pub fn step(&mut self, g: &mut Graph, params: &[T]) {
        self.t += 1;
        // Early on m and v are biased toward 0; these factors undo that.
        let bc1 = 1.0 - self.beta1.powi(self.t);
        let bc2 = 1.0 - self.beta2.powi(self.t);
        for (i, &p) in params.iter().enumerate() {
            // Decay matrices only; biases and LayerNorm gains are 1 x n.
            let decay =
                if g.shape(p).0 > 1 { self.weight_decay } else { 0.0 };
            let (data, grad) = g.data_and_grad(p);
            let (m, v) = (&mut self.m[i], &mut self.v[i]);
            for j in 0..data.len() {
                m[j] = self.beta1 * m[j] + (1.0 - self.beta1) * grad[j];
                v[j] = self.beta2 * v[j]
                    + (1.0 - self.beta2) * grad[j] * grad[j];
                let m_hat = m[j] / bc1;
                let v_hat = v[j] / bc2;
                data[j] -= self.lr
                    * (m_hat / (v_hat.sqrt() + self.eps) + decay * data[j]);
            }
        }
    }
}
