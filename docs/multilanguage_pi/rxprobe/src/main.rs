//! rxprobe — check prompt-injection patterns on the same regex settings as
//! tinicore's guardrails engine (`guardrails/engine/recognizer.rs`):
//! `unicode(false).utf8(false)`, captures off, hybrid DFA pair with
//! `MatchKind::All`, start found by an anchored reverse search, longest match
//! per start, zero-width matches dropped.
//!
//! Usage:
//!   rxprobe check <cases-file>...   run every case, exit 1 on a failure
//!   rxprobe mem   <cases-file>...   minimum lazy-DFA cache of all patterns as one chunk
//!
//! Cases file, one directive per line (`#` starts a comment line):
//!   P <pattern>   start a pattern (taken verbatim after `P `)
//!   + <text>      the pattern must match the text
//!   - <text>      the pattern must not match the text
//! In a text, `\u{XXXX}` is replaced by that code point and `\n` by a newline.
use regex_automata::hybrid::dfa::{Config as DfaConfig, DFA, OverlappingState};
use regex_automata::nfa::thompson;
use regex_automata::util::syntax;
use regex_automata::{Anchored, Input, MatchKind};

fn sx() -> syntax::Config {
    syntax::Config::new().unicode(false).utf8(false)
}

fn nfas(ps: &[&str]) -> Result<(thompson::NFA, thompson::NFA), String> {
    let fwd = thompson::Compiler::new().syntax(sx())
        .configure(thompson::Config::new().which_captures(thompson::WhichCaptures::None))
        .build_many(ps).map_err(|e| e.to_string())?;
    let rev = thompson::Compiler::new().syntax(sx())
        .configure(thompson::Config::new().reverse(true).which_captures(thompson::WhichCaptures::None))
        .build_many(ps).map_err(|e| e.to_string())?;
    Ok((fwd, rev))
}

fn fwd_cfg() -> DfaConfig { DfaConfig::new().match_kind(MatchKind::All) }
fn rev_cfg() -> DfaConfig {
    DfaConfig::new().match_kind(MatchKind::All).starts_for_each_pattern(true)
        .prefilter(None).specialize_start_states(false)
}

fn parse_error(p: &str) -> String {
    match regex_syntax::ParserBuilder::new().unicode(false).utf8(false).build().parse(p) {
        Err(e) => e.to_string().lines().last().unwrap_or("").trim().to_string(),
        Ok(_) => String::new(),
    }
}

fn build(p: &str) -> Result<(DFA, DFA), String> {
    let (f, r) = nfas(&[p]).map_err(|e| { let d = parse_error(p); if d.is_empty() { e } else { d } })?;
    let f = DFA::builder().configure(fwd_cfg()).build_from_nfa(f).map_err(|e| e.to_string())?;
    let r = DFA::builder().configure(rev_cfg()).build_from_nfa(r).map_err(|e| e.to_string())?;
    Ok((f, r))
}

fn scan(f: &DFA, r: &DFA, t: &str) -> Vec<(usize, usize)> {
    let (mut cf, mut cr) = (f.create_cache(), r.create_cache());
    let mut st = OverlappingState::start();
    let inp = Input::new(t);
    let mut raw = vec![];
    loop {
        f.try_search_overlapping_fwd(&mut cf, &inp, &mut st).unwrap();
        let Some(hm) = st.get_match() else { break };
        let ri = Input::new(t).range(0..hm.offset()).anchored(Anchored::Yes);
        if let Some(s) = r.try_search_rev(&mut cr, &ri).unwrap() { raw.push((s.offset(), hm.offset())); }
    }
    raw.sort_by(|a, b| a.0.cmp(&b.0).then(b.1.cmp(&a.1)));
    raw.dedup_by_key(|m| m.0);
    let mut out = vec![]; let mut last = 0;
    for (s, e) in raw { if s == e || s < last { continue; } last = e; out.push((s, e)); }
    out
}

fn unescape(t: &str) -> String {
    let mut out = String::new();
    let mut rest = t;
    while let Some(i) = rest.find('\\') {
        out.push_str(&rest[..i]);
        let tail = &rest[i..];
        if let Some(body) = tail.strip_prefix("\\u{") {
            if let Some(j) = body.find('}') {
                if let Some(c) = u32::from_str_radix(&body[..j], 16).ok().and_then(char::from_u32) {
                    out.push(c); rest = &body[j + 1..]; continue;
                }
            }
        }
        if let Some(r) = tail.strip_prefix("\\n") { out.push('\n'); rest = r; continue; }
        out.push('\\'); rest = &tail[1..];
    }
    out.push_str(rest);
    out
}

fn snap(t: &str, s: usize, e: usize) -> &str {
    let (mut s, mut e) = (s, e);
    while !t.is_char_boundary(s) { s -= 1; }
    while !t.is_char_boundary(e) { e += 1; }
    &t[s..e]
}

fn patterns(files: &[String]) -> Vec<String> {
    files.iter().flat_map(|f| std::fs::read_to_string(f).unwrap().lines()
        .filter_map(|l| l.strip_prefix("P ").map(str::to_string)).collect::<Vec<_>>()).collect()
}

fn check(files: &[String]) -> bool {
    let mut ok = true;
    for file in files {
        println!("== {file}");
        let mut cur: Option<Result<(DFA, DFA), String>> = None;
        for line in std::fs::read_to_string(file).unwrap().lines() {
            if let Some(p) = line.strip_prefix("P ") {
                let b = build(p);
                match &b { Ok(_) => println!("P {p}"), Err(e) => { println!("P {p}\n  BUILD ERROR: {e}"); ok = false; } }
                cur = Some(b);
            } else if let Some((want, t)) = line.strip_prefix("+ ").map(|t| (true, t)).or_else(|| line.strip_prefix("- ").map(|t| (false, t))) {
                let Some(Ok((f, r))) = &cur else { continue };
                let t = unescape(t);
                let m = scan(f, r, &t);
                let pass = m.is_empty() != want;
                if !pass { ok = false; }
                let spans: Vec<String> = m.iter().map(|&(s, e)| format!("{:?}", snap(&t, s, e))).collect();
                println!("  {} {} {:?} -> {}", if pass { "ok  " } else { "FAIL" }, if want { "+" } else { "-" }, t, spans.join(", "));
            }
        }
    }
    ok
}

fn mem(files: &[String]) {
    let ps = patterns(files);
    let refs: Vec<&str> = ps.iter().map(String::as_str).collect();
    let (f, r) = nfas(&refs).expect("patterns build");
    let (nf, nr) = (f.memory_usage(), r.memory_usage());
    let mf = fwd_cfg().get_minimum_cache_capacity(&f).unwrap();
    let mr = rev_cfg().get_minimum_cache_capacity(&r).unwrap();
    println!("patterns={} nfa_fwd={}KB nfa_rev={}KB min_cache_fwd={}KB min_cache_rev={}KB total={}KB",
        ps.len(), nf / 1024, nr / 1024, mf / 1024, mr / 1024, (nf + nr + mf + mr) / 1024);
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("check") => if !check(&args[1..]) { std::process::exit(1) },
        Some("mem") => mem(&args[1..]),
        _ => { eprintln!("usage: rxprobe check|mem <cases-file>..."); std::process::exit(2) }
    }
}
