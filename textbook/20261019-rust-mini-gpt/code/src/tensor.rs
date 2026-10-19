/// Handle to one tensor on the graph (an index, like `V` in part 1).
#[derive(Clone, Copy, Debug)]
pub struct T(pub usize);

/// How a tensor was produced. Inputs are indices of earlier tensors.
#[derive(Clone, Debug)]
enum Op {
    Leaf,
    MatMul(usize, usize),
    Add(usize, usize),
    AddRow(usize, usize),
    MulRow(usize, usize),
    Scale(usize, f32),
    Relu(usize),
    Transpose(usize),
    SliceRows(usize, usize),
    SliceCols(usize, usize),
    ConcatRows(Vec<usize>),
    ConcatCols(Vec<usize>),
    CausalMask(usize),
    Softmax(usize),
    LayerNorm(usize),
    Embedding(usize, Vec<usize>),
    CrossEntropy(usize, Vec<usize>),
}

/// One 2-D tensor, stored row-major: element (r, c) is data[r * cols + c].
struct Node {
    data: Vec<f32>,
    grad: Vec<f32>,
    rows: usize,
    cols: usize,
    op: Op,
}

/// The tape of tensors. Same idea as `Tape` in part 1.
pub struct Graph {
    nodes: Vec<Node>,
}

impl Graph {
    pub fn new() -> Self {
        Graph { nodes: Vec::new() }
    }

    fn push(
        &mut self,
        data: Vec<f32>,
        rows: usize,
        cols: usize,
        op: Op,
    ) -> T {
        assert_eq!(
            data.len(),
            rows * cols,
            "data length must equal rows * cols"
        );
        let grad = vec![0.0; data.len()];
        self.nodes.push(Node { data, grad, rows, cols, op });
        T(self.nodes.len() - 1)
    }

    pub fn leaf(&mut self, data: Vec<f32>, rows: usize, cols: usize) -> T {
        self.push(data, rows, cols, Op::Leaf)
    }

    pub fn shape(&self, t: T) -> (usize, usize) {
        (self.nodes[t.0].rows, self.nodes[t.0].cols)
    }

    pub fn data(&self, t: T) -> &[f32] {
        &self.nodes[t.0].data
    }

    #[allow(dead_code)] // only the tests read gradients directly
    pub fn grad(&self, t: T) -> &[f32] {
        &self.nodes[t.0].grad
    }

    /// Mutable values and read-only gradient of one tensor,
    /// for the optimizer.
    pub fn data_and_grad(&mut self, t: T) -> (&mut [f32], &[f32]) {
        let n = &mut self.nodes[t.0];
        (&mut n.data, &n.grad)
    }

    pub fn len(&self) -> usize {
        self.nodes.len()
    }

    pub fn truncate(&mut self, len: usize) {
        self.nodes.truncate(len);
    }

    // ---- forward ops ----

    /// (n x k) @ (k x m) -> (n x m)
    pub fn matmul(&mut self, a: T, b: T) -> T {
        let (n, k) = self.shape(a);
        let (k2, m) = self.shape(b);
        assert_eq!(k, k2, "matmul: inner dimensions differ");
        let (ad, bd) = (self.data(a), self.data(b));
        let mut out = vec![0.0; n * m];
        for i in 0..n {
            for kk in 0..k {
                let a_ik = ad[i * k + kk];
                for j in 0..m {
                    out[i * m + j] += a_ik * bd[kk * m + j];
                }
            }
        }
        self.push(out, n, m, Op::MatMul(a.0, b.0))
    }

    /// Elementwise a + b, same shape.
    pub fn add(&mut self, a: T, b: T) -> T {
        assert_eq!(self.shape(a), self.shape(b), "add: shapes differ");
        let out = self
            .data(a)
            .iter()
            .zip(self.data(b))
            .map(|(x, y)| x + y)
            .collect();
        let (n, m) = self.shape(a);
        self.push(out, n, m, Op::Add(a.0, b.0))
    }

    /// (n x m) + (1 x m): the row b is added to every row of a.
    pub fn add_row(&mut self, a: T, b: T) -> T {
        let (n, m) = self.shape(a);
        assert_eq!(self.shape(b), (1, m), "add_row: b must be 1 x cols");
        let bd = self.data(b);
        let out = self
            .data(a)
            .iter()
            .enumerate()
            .map(|(i, x)| x + bd[i % m])
            .collect();
        self.push(out, n, m, Op::AddRow(a.0, b.0))
    }

    /// (n x m) * (1 x m): every row of a is multiplied elementwise by b.
    pub fn mul_row(&mut self, a: T, b: T) -> T {
        let (n, m) = self.shape(a);
        assert_eq!(self.shape(b), (1, m), "mul_row: b must be 1 x cols");
        let bd = self.data(b);
        let out = self
            .data(a)
            .iter()
            .enumerate()
            .map(|(i, x)| x * bd[i % m])
            .collect();
        self.push(out, n, m, Op::MulRow(a.0, b.0))
    }

    /// Every element times the constant s.
    pub fn scale(&mut self, a: T, s: f32) -> T {
        let out = self.data(a).iter().map(|x| x * s).collect();
        let (n, m) = self.shape(a);
        self.push(out, n, m, Op::Scale(a.0, s))
    }

    pub fn relu(&mut self, a: T) -> T {
        let out = self.data(a).iter().map(|x| x.max(0.0)).collect();
        let (n, m) = self.shape(a);
        self.push(out, n, m, Op::Relu(a.0))
    }

    /// (n x m) -> (m x n)
    pub fn transpose(&mut self, a: T) -> T {
        let (n, m) = self.shape(a);
        let ad = self.data(a);
        let mut out = vec![0.0; n * m];
        for r in 0..n {
            for c in 0..m {
                out[c * n + r] = ad[r * m + c];
            }
        }
        self.push(out, m, n, Op::Transpose(a.0))
    }

    /// Rows start..start+len of a.
    pub fn slice_rows(&mut self, a: T, start: usize, len: usize) -> T {
        let (_, m) = self.shape(a);
        let out = self.data(a)[start * m..(start + len) * m].to_vec();
        self.push(out, len, m, Op::SliceRows(a.0, start))
    }

    /// Columns start..start+len of a.
    pub fn slice_cols(&mut self, a: T, start: usize, len: usize) -> T {
        let (n, m) = self.shape(a);
        let ad = self.data(a);
        let mut out = Vec::with_capacity(n * len);
        for r in 0..n {
            out.extend_from_slice(&ad[r * m + start..r * m + start + len]);
        }
        self.push(out, n, len, Op::SliceCols(a.0, start))
    }

    /// Stack tensors with the same column count on top of each other.
    pub fn concat_rows(&mut self, parts: &[T]) -> T {
        let m = self.shape(parts[0]).1;
        let mut out = Vec::new();
        let mut n = 0;
        for &p in parts {
            assert_eq!(
                self.shape(p).1,
                m,
                "concat_rows: column counts differ"
            );
            out.extend_from_slice(self.data(p));
            n += self.shape(p).0;
        }
        let ids = parts.iter().map(|p| p.0).collect();
        self.push(out, n, m, Op::ConcatRows(ids))
    }

    /// Place tensors with the same row count side by side.
    pub fn concat_cols(&mut self, parts: &[T]) -> T {
        let n = self.shape(parts[0]).0;
        let m: usize = parts.iter().map(|&p| self.shape(p).1).sum();
        let mut out = Vec::with_capacity(n * m);
        for r in 0..n {
            for &p in parts {
                let (pn, pm) = self.shape(p);
                assert_eq!(pn, n, "concat_cols: row counts differ");
                out.extend_from_slice(&self.data(p)[r * pm..(r + 1) * pm]);
            }
        }
        let ids = parts.iter().map(|p| p.0).collect();
        self.push(out, n, m, Op::ConcatCols(ids))
    }

    /// Square matrix: entries above the diagonal (col > row) become -inf.
    pub fn causal_mask(&mut self, a: T) -> T {
        let (n, m) = self.shape(a);
        assert_eq!(n, m, "causal_mask: matrix must be square");
        let mut out = self.data(a).to_vec();
        for r in 0..n {
            for c in r + 1..m {
                out[r * m + c] = f32::NEG_INFINITY;
            }
        }
        self.push(out, n, m, Op::CausalMask(a.0))
    }

    /// Softmax of each row: exp(x) / sum(exp(x)).
    pub fn softmax(&mut self, a: T) -> T {
        let (n, m) = self.shape(a);
        let mut out = self.data(a).to_vec();
        for row in out.chunks_mut(m) {
            softmax_in_place(row);
        }
        self.push(out, n, m, Op::Softmax(a.0))
    }

    /// Each row shifted to mean 0 and scaled to variance 1.
    pub fn layer_norm(&mut self, a: T) -> T {
        let (n, m) = self.shape(a);
        let mut out = self.data(a).to_vec();
        for row in out.chunks_mut(m) {
            let (mean, rstd) = mean_rstd(row);
            for x in row.iter_mut() {
                *x = (*x - mean) * rstd;
            }
        }
        self.push(out, n, m, Op::LayerNorm(a.0))
    }

    /// Output row r is row ids[r] of the table.
    pub fn embedding(&mut self, table: T, ids: &[usize]) -> T {
        let (_, m) = self.shape(table);
        let td = self.data(table);
        let mut out = Vec::with_capacity(ids.len() * m);
        for &id in ids {
            out.extend_from_slice(&td[id * m..(id + 1) * m]);
        }
        self.push(out, ids.len(), m, Op::Embedding(table.0, ids.to_vec()))
    }

    /// Mean over rows of -log(softmax(row)[target]).
    /// Returns a 1 x 1 tensor.
    pub fn cross_entropy(&mut self, logits: T, targets: &[usize]) -> T {
        let (n, m) = self.shape(logits);
        assert_eq!(n, targets.len(), "cross_entropy: one target per row");
        let mut probs = self.data(logits).to_vec();
        let mut loss = 0.0;
        for (row, &t) in probs.chunks_mut(m).zip(targets) {
            softmax_in_place(row);
            loss -= row[t].max(1e-30).ln();
        }
        self.push(
            vec![loss / n as f32],
            1,
            1,
            Op::CrossEntropy(logits.0, targets.to_vec()),
        )
    }

    // ---- backward ----

    /// Fill every tensor's grad with d(loss)/d(tensor).
    /// `loss` must be 1 x 1.
    pub fn backward(&mut self, loss: T) {
        assert_eq!(
            self.shape(loss),
            (1, 1),
            "backward: loss must be a 1 x 1 tensor"
        );
        for node in self.nodes.iter_mut() {
            node.grad.fill(0.0);
        }
        self.nodes[loss.0].grad[0] = 1.0;
        for i in (0..=loss.0).rev() {
            for (input, g) in self.input_grads(i) {
                for (dst, src) in self.nodes[input].grad.iter_mut().zip(&g)
                {
                    *dst += src;
                }
            }
        }
    }

    /// For node i, return pairs of
    /// (input index, gradient to add to that input).
    fn input_grads(&self, i: usize) -> Vec<(usize, Vec<f32>)> {
        let node = &self.nodes[i];
        let dy = &node.grad;
        match &node.op {
            Op::Leaf => vec![],
            Op::MatMul(a, b) => self.back_matmul(dy, *a, *b),
            Op::Add(a, b) => vec![(*a, dy.clone()), (*b, dy.clone())],
            Op::AddRow(a, b) => self.back_add_row(dy, *a, *b),
            Op::MulRow(a, b) => self.back_mul_row(dy, *a, *b),
            Op::Scale(a, s) => {
                vec![(*a, dy.iter().map(|g| g * s).collect())]
            }
            Op::Relu(a) => self.back_relu(dy, *a),
            Op::Transpose(a) => self.back_transpose(dy, *a),
            Op::SliceRows(a, start) => self.back_slice_rows(dy, *a, *start),
            Op::SliceCols(a, start) => {
                self.back_slice_cols(dy, node.cols, *a, *start)
            }
            Op::ConcatRows(parts) => self.back_concat_rows(dy, parts),
            Op::ConcatCols(parts) => {
                self.back_concat_cols(dy, node.rows, parts)
            }
            Op::CausalMask(a) => self.back_causal_mask(dy, node.cols, *a),
            Op::Softmax(a) => {
                self.back_softmax(dy, &node.data, node.cols, *a)
            }
            Op::LayerNorm(a) => {
                self.back_layer_norm(dy, &node.data, node.cols, *a)
            }
            Op::Embedding(table, ids) => {
                self.back_embedding(dy, *table, ids)
            }
            Op::CrossEntropy(logits, targets) => {
                self.back_cross_entropy(dy[0], *logits, targets)
            }
        }
    }

    fn back_matmul(
        &self,
        dy: &[f32],
        a: usize,
        b: usize,
    ) -> Vec<(usize, Vec<f32>)> {
        let (n, k) = (self.nodes[a].rows, self.nodes[a].cols);
        let m = self.nodes[b].cols;
        let (ad, bd) = (&self.nodes[a].data, &self.nodes[b].data);
        let mut da = vec![0.0; n * k];
        let mut db = vec![0.0; k * m];
        for i in 0..n {
            for kk in 0..k {
                let a_ik = ad[i * k + kk];
                let mut sum = 0.0;
                for j in 0..m {
                    let g = dy[i * m + j];
                    sum += g * bd[kk * m + j]; // dA = dY @ B^T
                    db[kk * m + j] += a_ik * g; // dB = A^T @ dY
                }
                da[i * k + kk] = sum;
            }
        }
        vec![(a, da), (b, db)]
    }

    fn back_add_row(
        &self,
        dy: &[f32],
        a: usize,
        b: usize,
    ) -> Vec<(usize, Vec<f32>)> {
        let m = self.nodes[b].cols;
        let mut db = vec![0.0; m];
        for (i, g) in dy.iter().enumerate() {
            db[i % m] += g; // b was used once per row, so its grads add up
        }
        vec![(a, dy.to_vec()), (b, db)]
    }

    fn back_mul_row(
        &self,
        dy: &[f32],
        a: usize,
        b: usize,
    ) -> Vec<(usize, Vec<f32>)> {
        let m = self.nodes[b].cols;
        let (ad, bd) = (&self.nodes[a].data, &self.nodes[b].data);
        let mut da = vec![0.0; dy.len()];
        let mut db = vec![0.0; m];
        for (i, g) in dy.iter().enumerate() {
            da[i] = g * bd[i % m];
            db[i % m] += g * ad[i];
        }
        vec![(a, da), (b, db)]
    }

    fn back_relu(&self, dy: &[f32], a: usize) -> Vec<(usize, Vec<f32>)> {
        let ad = &self.nodes[a].data;
        let da = dy
            .iter()
            .zip(ad)
            .map(|(g, x)| if *x > 0.0 { *g } else { 0.0 })
            .collect();
        vec![(a, da)]
    }

    fn back_transpose(
        &self,
        dy: &[f32],
        a: usize,
    ) -> Vec<(usize, Vec<f32>)> {
        let (n, m) = (self.nodes[a].rows, self.nodes[a].cols);
        let mut da = vec![0.0; n * m];
        for r in 0..n {
            for c in 0..m {
                da[r * m + c] = dy[c * n + r];
            }
        }
        vec![(a, da)]
    }

    fn back_slice_rows(
        &self,
        dy: &[f32],
        a: usize,
        start: usize,
    ) -> Vec<(usize, Vec<f32>)> {
        let m = self.nodes[a].cols;
        let mut da = vec![0.0; self.nodes[a].data.len()];
        da[start * m..start * m + dy.len()].copy_from_slice(dy);
        vec![(a, da)]
    }

    fn back_slice_cols(
        &self,
        dy: &[f32],
        len: usize,
        a: usize,
        start: usize,
    ) -> Vec<(usize, Vec<f32>)> {
        let (n, m) = (self.nodes[a].rows, self.nodes[a].cols);
        let mut da = vec![0.0; n * m];
        for r in 0..n {
            da[r * m + start..r * m + start + len]
                .copy_from_slice(&dy[r * len..(r + 1) * len]);
        }
        vec![(a, da)]
    }

    fn back_concat_rows(
        &self,
        dy: &[f32],
        parts: &[usize],
    ) -> Vec<(usize, Vec<f32>)> {
        let mut offset = 0;
        let mut result = Vec::new();
        for &p in parts {
            let size = self.nodes[p].data.len();
            result.push((p, dy[offset..offset + size].to_vec()));
            offset += size;
        }
        result
    }

    fn back_concat_cols(
        &self,
        dy: &[f32],
        n: usize,
        parts: &[usize],
    ) -> Vec<(usize, Vec<f32>)> {
        let m: usize = parts.iter().map(|&p| self.nodes[p].cols).sum();
        let mut col = 0;
        let mut result = Vec::new();
        for &p in parts {
            let pm = self.nodes[p].cols;
            let mut dp = Vec::with_capacity(n * pm);
            for r in 0..n {
                dp.extend_from_slice(&dy[r * m + col..r * m + col + pm]);
            }
            result.push((p, dp));
            col += pm;
        }
        result
    }

    fn back_causal_mask(
        &self,
        dy: &[f32],
        m: usize,
        a: usize,
    ) -> Vec<(usize, Vec<f32>)> {
        let mut da = dy.to_vec();
        for r in 0..m {
            for c in r + 1..m {
                // Masked entries did not affect the output.
                da[r * m + c] = 0.0;
            }
        }
        vec![(a, da)]
    }

    fn back_softmax(
        &self,
        dy: &[f32],
        y: &[f32],
        m: usize,
        a: usize,
    ) -> Vec<(usize, Vec<f32>)> {
        let mut da = vec![0.0; dy.len()];
        for ((dx, g), y) in
            da.chunks_mut(m).zip(dy.chunks(m)).zip(y.chunks(m))
        {
            let dot: f32 = g.iter().zip(y).map(|(g, y)| g * y).sum();
            for j in 0..m {
                dx[j] = y[j] * (g[j] - dot);
            }
        }
        vec![(a, da)]
    }

    fn back_layer_norm(
        &self,
        dy: &[f32],
        y: &[f32],
        m: usize,
        a: usize,
    ) -> Vec<(usize, Vec<f32>)> {
        let x = &self.nodes[a].data;
        let mut da = vec![0.0; dy.len()];
        for r in 0..dy.len() / m {
            let row = r * m..(r + 1) * m;
            let (_, rstd) = mean_rstd(&x[row.clone()]);
            let (g, xhat) = (&dy[row.clone()], &y[row.clone()]);
            let g_mean = g.iter().sum::<f32>() / m as f32;
            let gx_mean =
                g.iter().zip(xhat).map(|(g, h)| g * h).sum::<f32>()
                    / m as f32;
            for j in 0..m {
                da[r * m + j] = rstd * (g[j] - g_mean - xhat[j] * gx_mean);
            }
        }
        vec![(a, da)]
    }

    fn back_embedding(
        &self,
        dy: &[f32],
        table: usize,
        ids: &[usize],
    ) -> Vec<(usize, Vec<f32>)> {
        let m = self.nodes[table].cols;
        let mut dt = vec![0.0; self.nodes[table].data.len()];
        for (r, &id) in ids.iter().enumerate() {
            for j in 0..m {
                // The same id may appear many times.
                dt[id * m + j] += dy[r * m + j];
            }
        }
        vec![(table, dt)]
    }

    fn back_cross_entropy(
        &self,
        g: f32,
        logits: usize,
        targets: &[usize],
    ) -> Vec<(usize, Vec<f32>)> {
        let (n, m) = (self.nodes[logits].rows, self.nodes[logits].cols);
        let mut d = self.nodes[logits].data.clone();
        for (row, &t) in d.chunks_mut(m).zip(targets) {
            softmax_in_place(row);
            row[t] -= 1.0; // softmax - one_hot(target)
            for x in row.iter_mut() {
                *x *= g / n as f32;
            }
        }
        vec![(logits, d)]
    }
}

/// Numerically stable softmax: subtract the max before exp.
pub fn softmax_in_place(row: &mut [f32]) {
    let max = row.iter().cloned().fold(f32::NEG_INFINITY, f32::max);
    let mut sum = 0.0;
    for x in row.iter_mut() {
        *x = (*x - max).exp();
        sum += *x;
    }
    for x in row.iter_mut() {
        *x /= sum;
    }
}

/// Mean and 1 / standard deviation of a row (with a small epsilon).
fn mean_rstd(row: &[f32]) -> (f32, f32) {
    let m = row.len() as f32;
    let mean = row.iter().sum::<f32>() / m;
    let var = row.iter().map(|x| (x - mean) * (x - mean)).sum::<f32>() / m;
    (mean, 1.0 / (var + 1e-5).sqrt())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::rng::Rng;

    /// Turn any tensor y into a 1 x 1 loss: u @ y @ r,
    /// with fixed random u and r. Every element of y gets
    /// its own random weight, so every element is checked.
    fn reduce(g: &mut Graph, y: T) -> T {
        let (n, m) = g.shape(y);
        let mut rng = Rng::new(99); // same seed every call -> same u and r
        let u = g.leaf((0..n).map(|_| rng.normal() as f32).collect(), 1, n);
        let r = g.leaf((0..m).map(|_| rng.normal() as f32).collect(), m, 1);
        let uy = g.matmul(u, y);
        g.matmul(uy, r)
    }

    /// Compare backward() with finite differences for every input element.
    /// `build` gets the input tensors and returns the tensor to check.
    fn grad_check(
        shapes: &[(usize, usize)],
        build: impl Fn(&mut Graph, &[T]) -> T,
    ) {
        let mut rng = Rng::new(7);
        let inputs: Vec<Vec<f32>> = shapes
            .iter()
            .map(|&(n, m)| {
                (0..n * m).map(|_| rng.normal() as f32).collect()
            })
            .collect();

        // Loss for a given set of input values.
        let eval = |vals: &[Vec<f32>]| -> f32 {
            let mut g = Graph::new();
            let ts: Vec<T> = vals
                .iter()
                .zip(shapes)
                .map(|(v, &(n, m))| g.leaf(v.clone(), n, m))
                .collect();
            let y = build(&mut g, &ts);
            let loss = reduce(&mut g, y);
            g.data(loss)[0]
        };

        // Analytic gradients from backward().
        let mut g = Graph::new();
        let ts: Vec<T> = inputs
            .iter()
            .zip(shapes)
            .map(|(v, &(n, m))| g.leaf(v.clone(), n, m))
            .collect();
        let y = build(&mut g, &ts);
        let loss = reduce(&mut g, y);
        g.backward(loss);

        // Numeric gradients: (f(x + eps) - f(x - eps)) / (2 eps).
        let eps = 1e-2;
        for (ti, t) in ts.iter().enumerate() {
            for e in 0..inputs[ti].len() {
                let mut plus = inputs.clone();
                plus[ti][e] += eps;
                let mut minus = inputs.clone();
                minus[ti][e] -= eps;
                let numeric = (eval(&plus) - eval(&minus)) / (2.0 * eps);
                let analytic = g.grad(*t)[e];
                let tol = 1e-3 + 1e-2 * numeric.abs();
                assert!(
                    (numeric - analytic).abs() < tol,
                    "input {ti}[{e}]: numeric {numeric}, analytic {analytic}"
                );
            }
        }
    }

    #[test]
    fn matmul() {
        grad_check(&[(3, 4), (4, 5)], |g, x| g.matmul(x[0], x[1]));
    }

    #[test]
    fn add_and_rows() {
        grad_check(&[(3, 4), (3, 4), (1, 4), (1, 4)], |g, x| {
            let y = g.add(x[0], x[1]);
            let y = g.add_row(y, x[2]);
            let y = g.mul_row(y, x[3]);
            g.scale(y, 0.5)
        });
    }

    #[test]
    fn relu() {
        grad_check(&[(4, 5)], |g, x| g.relu(x[0]));
    }

    #[test]
    fn transpose_and_slices() {
        grad_check(&[(4, 6)], |g, x| {
            let t = g.transpose(x[0]); // 6 x 4
            let a = g.slice_rows(t, 1, 3); // 3 x 4
            let b = g.slice_cols(a, 1, 2); // 3 x 2
            let c = g.slice_cols(a, 0, 3); // 3 x 3
            let y = g.concat_cols(&[b, c]); // 3 x 5
            g.concat_rows(&[y, y]) // 6 x 5
        });
    }

    #[test]
    fn mask_and_softmax() {
        grad_check(&[(4, 4)], |g, x| {
            let y = g.causal_mask(x[0]);
            g.softmax(y) // -inf entries become exact zeros here
        });
    }

    #[test]
    fn layer_norm() {
        grad_check(&[(3, 5)], |g, x| g.layer_norm(x[0]));
    }

    #[test]
    fn embedding() {
        grad_check(&[(5, 3)], |g, x| g.embedding(x[0], &[1, 3, 1, 0]));
    }

    #[test]
    fn cross_entropy() {
        grad_check(&[(3, 5)], |g, x| g.cross_entropy(x[0], &[0, 2, 4]));
    }
}
