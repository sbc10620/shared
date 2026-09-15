# ClawKeeper 룰을 YAML로 옮기고 PII 엔진을 범용 패턴 엔진으로 통일

**작업 위치**: `~/Works/ARGO`, 브랜치 `dev/byungchul.so/guardrails-reorg` (원격 `dev/byungchul.so/guardrails-clawkeeper`)
**base**: `origin/main` 위의 커밋 3개(P0 `c5371b2bf0`, P1 `fdf3aa3f49`, P3사전 `97988798f0`) 뒤에 이어서 쌓는다.

---

## Context

### 왜 하는가

- `guardrails/` 안에 정규식 엔진이 **둘** 있다. PII 인식기 49종은 `regex-automata` hybrid DFA(`pii/recognizer.rs`)로 돌고, ClawKeeper PI 룰 10개는 `regex::Regex`(`agent/prompt_guard.rs`)로 돈다. 룰 데이터는 한 벌인데 실행 엔진이 둘이라, 같은 정규식이 두 엔진에서 다르게 해석될 여지가 있고 메모리도 두 방식으로 잡힌다.
- 메모리 관점에서 hybrid DFA 쪽이 맞다. `regex::Regex` 하나는 meta 엔진(PikeVM·backtracker·onepass·lazy DFA·prefilter)과 자기 캐시를 통째로 들고 있어 룰 10개면 10벌이다. PII 엔진은 패턴을 청크 하나의 DFA 쌍에 모으고 최소 캐시 + 마진(`CACHE_MARGIN_RATIO`, `recognizer.rs:181`)으로 크기를 잡으며, main이 최근 넣은 `TurnSlot`(`sensitive/turn_scope.rs`) 덕분에 턴이 끝나면 엔진을 통째로 놓는다.
- ClawKeeper 룰을 PII 인식기와 같은 YAML 스키마(`RecognizerConfig`, `pii/config.rs:49`)로 표현하면, 룰마다 `patterns`·`layers`(검사 지점별 on/off)·`action`만 적으면 되고 엔진은 그대로 쓸 수 있다. 계획서 §7-B가 말한 "룰이 자라면 데이터 파일로"도 처음부터 충족된다.

### 확인된 사실 (2026-09-15 실측)

| 항목 | 결과 |
|---|---|
| ClawKeeper 룰 10개를 PII 엔진 설정(`unicode(false).utf8(false)`, `MatchKind::All`)으로 컴파일 | `invisible_payload`만 실패. 코드포인트 클래스 `[\u{200B}…]`는 ASCII 모드에서 거부됨 |
| `invisible_payload`에 `(?u)` 접두사 | 10개 전부 컴파일. ZWSP·U+00AD 매치 확인 |
| argo-tizen 자체 룰(`agent_config.rs:90-110`, `\b`·`\s`·`(?i)` 사용) | 같은 설정에서 수정 없이 컴파일 |
| `regex-automata`가 슬림 빌드에 있는가 | 있다. `regex`가 그 위에 있어서 `meta`·`nfa-pikevm`·`unicode-*`가 이미 들어 있고, `guardrails` feature가 더하는 것은 `hybrid` 하나뿐 |
| `aho-corasick`(handwritten 탐지기) | 게이트 없는 상시 의존 (`Cargo.toml:1285`) |
| argo-tizen이 import하는 tinicore 심볼 | `PiiSpanDetector`, `shared_layer_filter` 둘뿐. `PiiEngine`·`PiiFilter`·`PiiMatch`는 tinicore 안에서만 쓰인다 |
| `PiiFilter::analyze` | 모든 패턴을 다 돌린 뒤 `keep_table`(`filter.rs:57`)로 층별 결과만 걸러낸다 → PI 룰은 별도 엔진 인스턴스여야 PII 49종을 같이 돌리지 않는다 |
| `RecognizerConfig` serde | `deny_unknown_fields` 없음 → 필드 추가 자유 |
| `sensitive::turn_scope` | feature 게이트 없이 항상 컴파일 (`sensitive/mod.rs:53`) |

### 결과적으로 무엇이 달라지나

- 런타임 판정(Block/Warn)은 같다. 단 `\b`·`\s`·`(?i)`가 ASCII 의미가 되고(PII 엔진이 이미 감수하는 조건), `Sanitize`는 "가장 긴 매치 치환"이 된다.
- `agent::prompt_guard::{compile, compile_cached, evaluate, CompiledGuard, GuardOutcome}`의 **시그니처는 유지**하므로 argo-tizen(참조 12곳)과 `loop_.rs`(`:691`, `:707`)는 코드 변경 없이 새 백엔드를 탄다.
- ARGO를 켜는 배선(`CliConfig.prompt_guard`)은 여전히 이번 범위 밖이다.

---

## 1. 최종 구조

```
tinicore/src/guardrails/                 지붕. lib.rs:480 의 #[cfg(feature="guardrails")] 제거 → 항상 컴파일
├── mod.rs                               파사드. pii 재수출 블록만 #[cfg(feature="guardrails")]
├── engine/                              ★ 도메인 무관 패턴 엔진. 항상 컴파일
│   ├── mod.rs                           pub use { PatternEngine, PatternFilter, PatternMatch, EngineConfig, RecognizerConfig, EngineError, DEFAULT_CHUNK_SIZE }
│   ├── config.rs        ← pii/config.rs      + action 필드, entity_type(alias pii_type)
│   ├── recognizer.rs    ← pii/recognizer.rs  PiiEngine→PatternEngine, keyword 조회 주입, 스팬 문자경계 스냅
│   ├── filter.rs        ← pii/filter.rs      PiiFilter→PatternFilter. analyze/mask/from_yaml_str/compile_from_yaml/layer_filter_from 만 남김
│   ├── error.rs, validator.rs          그대로 이동
│   └── (boundary.rs 는 만들지 않는다 — P2 는 이 분리로 흡수됨)
├── pii/                                 #[cfg(feature="guardrails")]  PII 제품 부분만
│   ├── mod.rs                           UNIFIED_CONFIG_YAML, ROUTING_NUMBER_TXT, keyword_file_content, extensions(), shared_input_filter
│   ├── shared.rs        ← filter.rs 하단   shared_slot, shared_layer_filter, shared_filter_for_pii_types, build_filters_with_params, shared_engine_*
│   ├── handwritten/                     남는다 — card·aho-corasick 탐지기 1,850줄은 PII 전용. engine::MatchEngine 을 구현만 함
│   ├── detector.rs, hook.rs, config/, {README,AGENTS,CLAUDE}.md   그대로
└── clawkeeper/                          항상 컴파일 (데이터 + 어댑터, 외부 의존 없음)
    ├── mod.rs                           baseline_rules() / baseline_rules_with_action() — YAML에서 파생
    ├── prompt_injection.yaml            ★ 룰 10개. prompt_injection.rs 는 삭제
    └── tool_output.rs                   observe_only 중복 제거, 나머지 유지

tinicore/src/agent/prompt_guard.rs       백엔드만 regex::Regex → guardrails::engine::PatternEngine
```

**게이트 경계의 근거**: `engine/`이 새로 요구하는 것은 `regex-automata/hybrid` feature뿐이고 크레이트 자체는 이미 슬림 그래프에 있다. 24 KB 임베디드 YAML·`PiiSpanDetector`·hook은 `pii/`에 남아 슬림 빌드에서 계속 빠진다.

---

## 2. 커밋 순서 (각 커밋마다 §5 검증 통과)

### C0. 측정 — 착수 게이트 (코드 변경 0)

메모리 이득은 아직 가정이다. 리팩터링 전에 지금 트리로 잴 수 있으므로 먼저 잰다.

- `examples/guardrails/bench_prompt_guard_memory.rs`(신규, `required-features = ["guardrails"]`): 카운팅 전역 할당자로 (a) `prompt_injection.rs`의 룰 10개를 `regex::Regex`로 컴파일한 뒤 상주 바이트, (b) 같은 10개를 `PiiConfig`로 구성해 `PiiEngine::from_config`로 컴파일한 뒤 상주 바이트 + `min_cache_info()` 합계, (c) 각각 1 KB·64 KB 텍스트를 스캔한 뒤의 상주 바이트(lazy DFA 캐시 성장분)를 출력한다. 기존 `bench_session_cache.rs`의 측정 방식을 따른다.
- 슬림 바이너리 영향: `cargo build -p tinicore --no-default-features --release`의 rlib 크기를 `regex-automata/hybrid` 추가 전후로 비교한다(feature 한 줄만 바꿔 측정).
- **수치를 사용자에게 보고하고 C1 이후 진행 여부를 다시 확인한다.** 이득이 미미하면 C1~C4는 하지 않고, 룰 YAML화(C4의 데이터 부분)와 `observe_only` 중복 제거만 `regex` 백엔드 위에서 수행한다.

### C1. 엔진 일반화 — 파일 이동 없이, PII 동작 변화 0

`pii/` 안에서만 고친다. 이름 바꾸기와 스키마 확장을 먼저 끝내 두면 C2의 이동 diff가 rename-only로 남는다.

| 대상 | 변경 |
|---|---|
| `pii/config.rs` | `PiiConfig`→`EngineConfig`. `RecognizerConfig`에 `entity_type: String` (`#[serde(alias = "pii_type")]`), `action: Option<GuardAction>` (`#[serde(default)]`, 값은 `block`/`warn`/`sanitize`) 추가. `tinicore_traits::prompt_guard::GuardAction`을 그대로 씀 |
| `pii/recognizer.rs` | `PiiEngine`→`PatternEngine`, `PatternMeta.pii_type`→`entity_type`. `from_config*`에 `ext: &EngineExtensions` 인자 추가. `EngineExtensions { keyword_lookup: fn(&str) -> Option<&'static str>, handwritten: fn(&[&RecognizerConfig], usize) -> (Vec<Box<dyn MatchEngine>>, Vec<…>) }` — `expand_template`(`:1034`)·`keyword_files_available`(`:1127`)이 `pii::keyword_file_content`를, `collect_patterns_and_detectors`(`:~650`)가 `handwritten::build_handwritten_detectors`를 직접 부르는 결합 두 개를 끊는다. `EngineExtensions::default()`는 keyword `None` + handwritten 항목 warn 후 skip. `MatchEngine` 트레잇은 `pub(crate)`로 올려 `pii/handwritten/`이 구현하게 둔다. `collect_raw_matches` 직후 스팬을 문자 경계로 스냅(`utf8(false)`라 호스트 룰의 `.`이 코드포인트 중간에서 끝날 수 있음 — 현재 `:318`의 `&text[start..end]`가 패닉하는 잠재 결함) |
| `pii/filter.rs` | `PiiFilter`→`PatternFilter`, `PiiMatch`→`PatternMatch`(`pii_type`→`entity_type`). `analyze`·`mask`·`from_yaml_str*`·`compile_from_yaml`·`layer_filter_from`·`compile_and_drop_config`는 그대로, `ext`를 받아 넘긴다. `pii/shared.rs`(C2)와 `PiiSpanDetector`만 `pii::extensions()`(keyword + handwritten 둘 다)를 넘기고, 나머지 호출자는 `default()` |
| `pii/error.rs` | `PiiError`→`EngineError` |
| 파사드·테스트·예제·tinicli | 이름 일괄 치환. 별칭은 두지 않는다 (사용자 확인: 호환 부담 없음) |

### C2. 파일 이동 + 게이트 경계 이동

- `git mv pii/{config,recognizer,filter,error,validator}.rs → engine/`. `handwritten/`은 `pii/`에 남긴다. `filter.rs` 하단의 shared-slot 함수군(`:404-530`)은 `pii/shared.rs`로 분리(이 함수들만 `UNIFIED_CONFIG_YAML`을 안다). `serde_yaml`은 슬림 그래프에 이미 있으므로(`Cargo.toml:1214`, 상시) `engine/filter.rs`의 `from_yaml_str`이 새 의존을 만들지 않는다.
- `lib.rs:480` cfg 제거. `guardrails/mod.rs`에서 `mod pii;`와 `pub use pii::…`만 `#[cfg(feature = "guardrails")]`.
- `Cargo.toml`: `regex-automata`를 상시 의존으로(`dep:` 목록에서 제거, `hybrid`·`syntax`·`std` 상시). `guardrails` feature는 남기되 내용은 빈 배열 + 주석(임베디드 YAML·PII 표면 게이트). `:791-812` 주석 갱신.
- `tinicore/CLAUDE.md`·`.github/workflows/CLAUDE.md`에 슬림 빌드 설명이 있으면 갱신.
- `tests/guardrails/*`의 `[[test]] required-features`는 그대로(`pii/`를 쓰므로).

### C3. `agent::prompt_guard` 백엔드 교체

```rust
pub struct CompiledGuard {
    slot: Arc<TurnSlot<PatternEngine, EngineError>>,   // 턴 단위 build-and-drop, PII 와 같은 수명
    rules: Vec<(String /*id*/, GuardAction)>,            // 호스트가 준 순서 유지
}
```

- `compile(&PromptGuardConfig)`: `PromptGuardRule → RecognizerConfig { entity_type: id, patterns: [pattern], action, boundary_check: false }`로 변환해 `EngineConfig`를 만든다. **`TurnSlot`은 빌드를 `acquire()` 시점까지 미루므로, 패턴 오류를 부팅 시점에 잡으려면 `compile`이 먼저 `PatternEngine::from_config`를 한 번 즉시 실행해 검증해야 한다.** 검증용 인스턴스는 버리고, 슬롯에는 같은 `EngineConfig`를 담아 턴마다 다시 빌드하게 한다(부팅 시 빌드 1회 추가 비용, 룰 10개 규모에서는 무시할 수 있음). 오류는 지금처럼 `TinicoreError::Config`(룰 id 포함, 패턴 본문 미포함). 빈 룰셋은 빈 `CompiledGuard` → `loop_.rs:681`의 스킵 그대로.
- `evaluate(&CompiledGuard, &str)`: `slot.acquire()?.scan(text)` 한 번 → 매치된 `entity_type` 집합. 룰 순서대로 Block → `Block{rule_id}` 즉시 반환, Warn → `warned` 누적. Sanitize 룰이 있으면 그 룰의 스팬(길이 우선, 겹침 제거)을 `replacement`로 치환하고 이후 룰은 치환된 텍스트를 재스캔(체이닝 의미 유지, `prompt_guard.rs:255`). 스팬 치환은 `PatternFilter::mask`(`filter.rs:281`)의 루프 구조를 따르되 `*` 대신 `replacement`를 넣는다.
- `compile_cached`: 메모 키는 지금처럼 `PromptGuardConfig` 값. `TurnSlot`이 엔진 수명을 맡으므로 메모는 슬롯만 들고 있다.
- 모듈 doc의 "UTF-8-safe sanitisation… the `regex` crate guarantees" 문단을 C1의 스냅 규칙으로 교체.
- `tinicore/tests/prompt_guard_e2e.rs`와 `prompt_guard.rs` 인라인 테스트를 새 의미로 갱신. `test_hooks`(컴파일 지연 테스트)는 유지.

### C4. ClawKeeper 룰을 YAML로

`clawkeeper/prompt_injection.yaml` (ClawKeeper 원문 정규식 그대로, `invisible_payload`만 `(?u)` 접두사):

```yaml
recognizers:
  ignore_prior:
    recognizer_type: pattern
    entity_type: ignore_prior
    patterns: ['(?i)\b(ignore|disregard|forget|override)\s+…']
    layers: [prompt_guard, tool_output]
    action: block
  imperative_credential_read:   { …, action: warn }   # 사용자 결정: 오탐 6/9
  comment_directive:            { …, action: warn }   # 오탐 3/4
  trust_this_source:            { …, action: warn }   # 오탐 3/9
  invisible_payload:
    patterns: ['(?u)[\u{200B}\u{200C}\u{200D}\u{2060}\u{FEFF}\u{202A}-\u{202E}\u{2066}-\u{2069}\u{00AD}]']
    action: warn
```

- `clawkeeper/mod.rs`: `include_str!`로 YAML을 임베드하고 `serde_yaml`로 `EngineConfig` 파싱 → `baseline_rules() -> Vec<PromptGuardRule>`은 여기서 파생(반환 타입 유지, argo-tizen의 `additional` 체이닝 그대로). `baseline_rules_with_action`은 유지. `prompt_injection.rs`와 `BLOCK_RULES`/`WARN_RULES` 삭제. 룰 개수·액션 분포 테스트를 "6 Block + 4 Warn"으로 갱신.
- 인라인 테스트에서 `regex::Regex::new(&rule.pattern)` 직접 호출(`mod.rs:175,197,224,244`)을 `prompt_guard::{compile, evaluate}`로 바꾼다. 룰이 실제로 어떤 엔진에서 어떻게 판정되는지를 고정하는 것이 목적이므로.
- `tool_output.rs`: `observe_only`의 인라인 `map`(`:200-210`)을 `baseline_rules_with_action(GuardAction::Warn)`으로 대체. `ClawKeeperScanPack::from_rules`의 Sanitize 거부 로직은 유지.
- 모듈 doc에 ASCII 모드 주의(`\b`·`\s`·`(?i)`가 Python `re`와 다름)와 `(?u)` 옵트인 규칙을 남긴다.

### C5. 사후 측정과 문서

- C0의 벤치를 새 `PatternEngine` 경로로 다시 돌려 전후 수치를 커밋 메시지에 남긴다.
- `pii/AGENTS.md`·`README.md`: 엔진 위치 변경 반영. `guardrails/mod.rs` 모듈 doc의 서브모듈 목록에 `engine` 추가.

---

## 3. 의미 변화 — 코드 주석과 테스트로 고정할 것

| 항목 | 지금 | 이후 | 고정 방법 |
|---|---|---|---|
| `\b`·`\s`·`(?i)` | 유니코드 | ASCII | 테스트: `"ignore\u{00A0}previous instructions"`(NBSP)가 **매치되지 않음**을 의도된 한계로 고정 |
| 코드포인트 클래스 | 그대로 | `(?u)` 옵트인 | 테스트: `invisible_payload`가 ZWSP·bidi에 매치, `👨‍👩‍👧`는 Warn이지 Block이 아님(기존 테스트 3 유지) |
| `.{0,800}?` | 게으른 매치 | 가장 긴 매치 | 판정 불변. 스팬을 외부에 내보내는 경로 없음(`tool_output.rs`는 id·count만 메타데이터에 실음) |
| `Sanitize` | `replace_all` | 스팬 치환 | 테스트: 치환 결과 + 체이닝 + 비ASCII 텍스트에서 코드포인트가 깨지지 않음 |
| 호스트 룰 오류 | `regex` 파싱 오류 | DFA 빌드 오류 | 기존처럼 `TinicoreError::Config`. 메시지에 룰 id 포함, 패턴 본문 미포함 |

---

## 4. 이번 범위 밖

- ARGO `CliConfig.prompt_guard` 설정 표면(배선).
- P4~P7, argo-tizen 베이스라인 교체. argo-tizen이 `from_filter`·`ToolDef.server_tool` 때문에 이미 main과 어긋난 것은 별도 커밋.
- YAML 키 `pii_type`을 임베디드 PII YAML 49건에서 `entity_type`으로 일괄 개명(alias로 충분, 원하면 후속).

---

## 5. 검증

```bash
export PATH="$HOME/.cargo/bin:$PATH"; cd ~/Works/ARGO
# 각 커밋마다 — CI 레인과 feature 집합 동일하게 (target/ 재사용)
cargo clippy -p tinicore --features guardrails,sensitive,cognition,test-fixtures --all-targets -- -D warnings
cargo nextest run --profile ci -p tinicore --features guardrails,sensitive,cognition,test-fixtures
cargo nextest run --profile ci -p tinicli --features guardrails
cargo check -p tinicore && cargo check -p tinicli                     # feature OFF
cargo check -p tinicore --no-default-features                          # 슬림 — C2 이후 engine/ 이 여기서 컴파일돼야 함
cargo tree -p tinicore --no-default-features -i regex-automata -e features | grep -c hybrid   # 1 이어야 함

# ABA 인식기 가짜 통과 방지 (계획서 §8) — nextest 는 0 매치여도 exit 0
cargo nextest run -p tinicore --features guardrails,sensitive,cognition,test-fixtures -E 'test(us_bank_account)' 2>&1 | tee /tmp/aba.log
grep -qE '[1-9][0-9]* tests? run' /tmp/aba.log

# PromptGuard 백엔드 (C3 이후)
cargo nextest run -p tinicore --features test-fixtures -E 'test(prompt_guard)'

# argo-tizen 파사드 게이트 — rsync 는 mtime 을 보존하므로 반드시 clean 후 check
ARGOT=~/Works/argo-tizen
rsync -a --delete --exclude target tinicore/ $ARGOT/tini/tinicore/ && rsync -a --delete --exclude target tinicore-traits/ $ARGOT/tini/tinicore-traits/
( cd $ARGOT && cargo clean -p tinicore -p tinicore-traits && cargo check -p argot-daemon 2>&1 | grep -E "E0432|E0433" ; echo "unresolved-import 0건이면 통과. from_filter/server_tool 13건은 main 기존 결함" )
( cd $ARGOT && git checkout -- tini/ && git clean -fdq tini/ )

# Core 게이트 + 재구현 감사 (C3 의 스팬 치환 루프가 PatternFilter::mask 와 겹쳐 보일 수 있음 — 걸리면 mask 쪽을 공용 헬퍼로 빼서 둘 다 호출)
python3 scripts/audit_core_layer_deps.py && python3 scripts/audit_core_product_leak.py && python3 scripts/audit_core_crate_name_leak.py
python3 scripts/audit_reimpl.py --self-test && python3 scripts/audit_reimpl.py
python3 scripts/risky_unwrap.py | tail -1        # baseline 8

# C0 / C5 측정
cargo run -p tinicore --example bench_prompt_guard_memory --features guardrails
```

**완료 조건**
- [ ] C0 수치를 보고하고 사용자가 C1 진행을 확인함
- [ ] C1 직후 PII 테스트 결과가 이전과 동일(16,949 passed, `us_bank_account` 14건)
- [ ] C2 직후 `--no-default-features` 컴파일 통과, `hybrid` feature가 슬림 그래프에 잡힘
- [ ] C3 직후 argo-tizen rsync 검증에서 unresolved import 0건
- [ ] C4 직후 `baseline_rules()`가 10개, Block 6 + Warn 4
- [ ] C5 측정 수치가 커밋 메시지에 기록됨
- [ ] `git log --follow`로 `engine/recognizer.rs`가 `pii/recognizer.rs` → `guardrails/recognizer.rs` 이력까지 이어짐
