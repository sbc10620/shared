# 프롬프트 인젝션 가드레일 배선 계획 (구현 전 문서)

**전제**: `~/Works/ARGO-ClawKeeper` 브랜치 `dev/byungchul.so/guardrails-clawkeeper`의 재구성 시리즈(계획서 `20260921-prompt-injection-restructure-plan.md`)가 끝난 상태. 이 문서는 그 위에 얹을 **배선(부팅 시 설치)** 작업의 형태만 적는다. 아직 구현하지 않는다.

## 현재 상태 (재구성 후)

| 구성 요소 | 위치 | 상태 |
|---|---|---|
| 룰 파일 | `tinicore/src/guardrails/prompt_injection/rules.yaml` (13개, `layers`로 `prompt_guard`/`tool_output` 구분) | 완료 |
| 공유 엔진 | `prompt_injection::SharedEngine::new(host_rules)` — YAML + 호스트 룰을 한 `TurnSlot<PatternEngine>`에 | 완료, 호출자 없음 |
| 사용자 입력 소비자 | `agent::prompt_guard::compile_shared(&shared)` → `CompiledGuard`, `loop_.rs:684`가 `CoreConfig.prompt_guard`로 컴파일한 것을 `evaluate` | `compile_shared` 완료, `loop_.rs`는 아직 `CoreConfig.prompt_guard`만 읽음 |
| 툴 결과 소비자 | `prompt_injection::tool_output_guardrail(&shared)` → `SensitiveGuardrail` (`sensitive` feature) | 완료, 등록하는 곳 없음(e2e 테스트만) |
| PII 설치 | `pii/install.rs::install_guardrails_from_config(GuardrailsConfig)` | 기존 |
| feature | `prompt_injection/` 전체가 `guardrails` 뒤, 툴 결과 탐지기는 `sensitive`도 필요 | argo-tizen은 둘 다 켜져 있음 |

## 1. 설정 표면

`GuardrailsConfig`(`pii/install.rs`)에 필드 하나를 더한다. `#[serde(default)]`라 기존 호스트 설정은 그대로 파싱된다.

```rust
pub struct GuardrailsConfig {
    pub pii: PiiConfig,                              // 기존
    #[serde(default)]
    pub prompt_injection: PromptInjectionConfig,     // 신규
}

pub struct PromptInjectionConfig {
    pub input: PromptInjectionLayerConfig,           // 사용자 입력 층 (PromptGuard 경로)
    pub tool_output: PromptInjectionLayerConfig,     // 툴 결과 층 (SensitiveGuardrail 경로)
    /// 호스트 자체 룰. `SharedEngine::new`에 넘어가 `prompt_guard` 층에 얹힌다.
    /// YAML 룰과 id가 겹치면 부팅 실패(fail-closed).
    #[serde(skip)]
    pub additional_rules: Vec<PromptGuardRule>,
}

pub struct PromptInjectionLayerConfig {
    pub enabled: bool,                               // 기본 false
    /// 차단할 라벨의 부분집합. `None`이면 그 층의 block 룰 라벨 전부.
    /// 사용자 입력 층은 지금 `Override`뿐이므로 사실상 on/off.
    pub labels: Option<Vec<PromptInjectionLabel>>,
}
```

`config.toml` 예시(tinicli):

```toml
[prompt_injection.input]
enabled = true

[prompt_injection.tool_output]
enabled = true
labels = ["override", "embedded_directive", "comment_directive", "base64_decoded_to_shell"]
```

`additional_rules`는 파일이 아니라 호스트 코드가 채운다(argo-tizen의 raw 룰 2개, `ProductPolicy.guard_rules`).

## 2. `install_guardrails_from_config` 확장

```rust
// pii/install.rs — 기존 PII 설치 뒤에
if config.prompt_injection.input.enabled || config.prompt_injection.tool_output.enabled {
    let shared = SharedEngine::new(&config.prompt_injection.additional_rules)?;   // 한 번, 부팅 시 검증

    if config.prompt_injection.tool_output.enabled {
        let mut guard = tool_output_guardrail(&shared)?;
        if let Some(labels) = &config.prompt_injection.tool_output.labels {
            guard = guard.with_block(labels.iter().map(|l| SensitiveKind::PromptInjection(*l)).collect());
            // ↑ SensitiveGuardrail 에 block 목록 교체 생성자가 없으면 추가
        }
        set = set.with_tool_output(vec![Box::new(guard)]);                        // PII 입력 가드레일과 같은 전역 GuardrailSet
    }

    if config.prompt_injection.input.enabled {
        let compiled = prompt_guard::compile_shared(&shared);
        install_prompt_guard(compiled);                                            // 신설 전역 슬롯 (OnceLock<CompiledGuard>)
    }
}
```

- 공유 엔진은 두 층이 같이 켜지면 **턴마다 1회** 빌드된다(첫 `acquire`가 빌드, 턴 종료 시 해제).
- **슬롯 등록 시점 (2026-09-22 코드 리뷰 발견 1의 처리)**: `turn_guard()`는 guard를 잡는 순간 registry에 있는 슬롯만 pin한다. 현행 `compile_cached` 경로는 슬롯을 턴 중간(`loop_.rs:684`)에 만들기 때문에 새 설정의 첫 턴에는 pin이 없고, 그 턴에 `Sanitize` 룰이 걸리면 뒤 룰 재스캔에서 DFA를 한 번 더 빌드한다(결과는 같고 비용만 추가, `prompt_guard.rs` 모듈 doc에 기록). 배선에서는 `install_guardrails_from_config`이 **부팅 시** `SharedEngine::new`를 호출하므로 슬롯이 첫 턴 전에 등록되어 PII의 `engine_guard()`와 같은 효과를 낸다. 즉 `compile_shared` 경로에서는 이 문제가 없다. 남는 경우는 (1) `CoreConfig.prompt_guard` 경로(argo-tizen 전환 전), (2) `turn_guard()` 밖에서 `evaluate`를 직접 부르는 호출자 — 둘 다 없어지면 자연히 해소되고, 그 전에 없애려면 `evaluate`가 진입 시 엔진 `Arc`를 한 번 붙들고 재스캔까지 쓰는 국소 수정(`PatternFilter`에 hold 헬퍼 + `build_count` 단언 테스트)을 넣는다.
- 툴 결과 층에 `labels`로 warn 룰의 라벨(`InvisibleChars`)을 지정하면 경고 후 무시한다. 스팬을 내지 않는 룰은 차단 목록에 있어도 의미가 없다.
- `PromptInjectionLabel`은 `serde(rename_all = "snake_case")`라 TOML 값은 `override`, `embedded_directive`… 이다.

## 3. `loop_.rs`의 fallback

`apply_inbound_prompt_guard`(`loop_.rs:684`)는 지금 `ctx.config.prompt_guard`(`CoreConfig`)만 읽는다. 배선 후:

```rust
let guard = if ctx.config.prompt_guard.is_empty() {
    match installed_prompt_guard() { Some(g) => g, None => return Ok(None) }   // 전역 슬롯
} else {
    prompt_guard::compile_cached(&ctx.config.prompt_guard)?                     // 기존 경로 그대로
};
```

`CoreConfig::prompt_guard`는 공개 계약(argo-tizen이 채움)이라 유지한다. 두 경로가 동시에 켜지면 `CoreConfig` 쪽이 이긴다(호스트가 명시적으로 준 룰이 우선). argo-tizen이 전환하면 `CoreConfig.prompt_guard`를 비우고 `additional_rules`로 옮긴다.

## 4. argo-tizen 정리 (배선 후, 별도 PR)

| 항목 | 처분 |
|---|---|
| `CORE_PROMPT_GUARD_BASELINE_RULES` 3개 (`agent_config.rs:87`) | 삭제. 세 룰 모두 원문 그대로 `rules.yaml`에 있음 |
| `RAW_PROMPT_GUARD_RULES` 2개 (`argot_context_forgery`, `turn_context_forgery`) | 유지 → `additional_rules`. argo-tizen 페르소나의 신뢰 태그 위조 탐지라 tinicore가 알 수 없음 |
| `ProductPolicy.guard_rules` | 유지 → `additional_rules` |
| `prompt_guard_config_for_mode`의 `PromptGuardMode::{Warn,Block}` → 단일 액션 | 삭제 후보. 룰별 액션이 YAML에 있고 `baseline_rules_with_action`도 없어짐. 모드는 `Off`/`On`으로 |
| `core.prompt_guard` 직접 설정 (`apply_prompt_guard_mode`) | `install_guardrails_from_config`의 `prompt_injection` 설정으로 대체 |

전환 전까지는 argo-tizen이 자기 룰을 계속 쓴다(`compile`은 id 기반으로 바뀌었지만 경로는 유지). **주의**: 재구성 시리즈가 `PiiError`→`EngineError` 등을 바꿨으므로 argo-tizen PR #1395(`e8dc41e9`)가 먼저 병합돼 있어야 한다.

## 5. 후속 항목

- 툴 결과 층 warn의 소비자: `execution.rs:3231`이 통과 결과의 메타데이터를 버리므로 지금 warn은 탐지기의 `guardrails::audit` 로그뿐이다. 훅 이벤트로 올리려면 그 호출부의 `Ok` 분기에서 메타데이터를 읽어 `guardrail.warn` 이벤트를 내면 된다.
- 툴 결과 층에 호스트 룰 얹기: `PromptGuardRule`에 라벨이 없어 지금은 `prompt_guard` 층 전용. `tool_output.additional_rules` + 라벨 지정(또는 `PromptInjectionLabel::Custom`)이 필요.
- 엔진 공유 범위: PII 슬롯과 인젝션 슬롯은 별개다(룰 세트가 다르고 `extensions()`도 다름). 합칠 이유는 없다.
- 추가 개선 후보(계획서 §6): `certificate` 인식기 앵커에 OPENSSH/RSA/EC/DSA PRIVATE KEY 추가; base64 디코드 후 Credential·PII 재스캔 탐지기; 오탐 말뭉치 예제; `trust_this_source` 원문 수정 여부; ZWJ 이모지 예외로 `invisible_payload` block 승격.
