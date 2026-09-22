# 프롬프트 인젝션 가드레일 배선 — tinicore 부팅 설치 + tinicli 참조 배선

**작업 위치**: `~/Works/ARGO-ClawKeeper`(worktree), 브랜치 `dev/byungchul.so/guardrails-clawkeeper`(HEAD `b334b73bd6`, base `origin/main` `3734f7068c`, 원격과 동일). 재구성 8커밋 **위에 새 커밋 4개**를 쌓는다(기존 커밋 amend 없음: 배선은 새 기능). 로컬 커밋까지만, push·PR은 별도 지시.
**1차 대상**: tinicore + tinicli(`argo` CLI, 참조 호스트). **argo-tizen은 범위 밖**(참고만; 전환은 별도 PR).
**기준 문서**: `~/Works/shared/plans/20260921-prompt-injection-guardrails-wiring-plan.md`(구현 후 최종 모양으로 갱신·push).

---

## Context

재구성 시리즈로 룰(YAML 13개), 공유 엔진(`SharedEngine`), 두 소비자(`prompt_guard::compile_shared`, `prompt_injection::tool_output_guardrail`)까지 만들어졌지만 **아무도 부르지 않는다**. 사용자 입력 층은 지금도 `CoreConfig.prompt_guard`(호스트가 채움, tinicli는 항상 비어 있음)로만 동작하고, 툴 결과 층은 어디에도 등록되지 않았다. 이 계획은 PII가 이미 쓰는 `install_guardrails_from_config` 한 진입점에 프롬프트 인젝션을 얹어, 부팅 한 번으로 두 층이 켜지게 한다.

탐색으로 확인한 제약(설계를 정한 사실):

| 사실 | 위치 | 결과 |
|---|---|---|
| `apply_inbound_prompt_guard`는 `ctx.config.prompt_guard.is_empty()`면 **즉시 반환** | `loop_.rs:698` | 설치된 가드를 읽는 fallback을 이 지점에 넣어야 함. 안 넣으면 tinicli에서 죽은 코드 |
| 전역 `GuardrailSet`은 `install_guardrails`가 층별 **append**, 다른 소유자가 있으면 층을 버림 | `agent/guardrails.rs:199-317` | PII 입력 가드 + 인젝션 툴 결과 가드를 **한 세트로 한 번** 설치 |
| `turn_guard()`는 잡는 순간 등록된 슬롯만 pin | `turn_scope.rs:196` | `SharedEngine::new`를 **부팅**에서 호출해 첫 턴 전에 슬롯 등록(리뷰 발견 1의 해소) |
| tinicli REPL/TUI는 저장 전 게이트 **앞에서 이미 `turn_guard()`를 잡음** | `repl.rs:453`, `run_tui.rs:474` | 게이트 스캔과 loop 스캔이 빌드 1회 공유. 옮길 것 없음 |
| REPL/TUI는 PII 게이트 → `save_message` → agent_loop 순서 | `repl.rs:481-509` | loop 안 검사만으로는 인젝션 메시지가 **저장된 뒤** 차단됨 → 저장 전 게이트에 프롬프트 가드도 넣어야 함(사용자 지적) |
| loop는 **최신 사용자 메시지 하나만** 검사(`rposition`) | `loop_.rs:715-722` | 저장된 옛 메시지가 다음 턴에 다시 차단되지는 않지만, 검사 없이 LLM에 전달됨 → 게이트 필요성의 근거 |
| `SensitiveGuardrail`에는 block 목록을 뒤에서 좁히는 API 없음; `block`이 비면 `is_inert()` | `sensitive/guardrail.rs:97-143` | `labels`는 `new(...)`에 작은 목록을 넘겨 좁힘. 빈 목록은 **오류** |
| `PromptInjectionDetector::kinds()` = block 룰의 라벨만(4개, `InvisibleChars` 없음) | `detector.rs:124-127` | "라벨이 `kinds()`에 없음" 검사 하나로 warn 전용 라벨·없는 라벨을 모두 잡음 |
| `PromptGuardRule`의 serde는 `action = { action = "block" }`(중첩) | `tinicore-traits/src/prompt_guard.rs` `rule_round_trips` | tinicli TOML은 평면 문자열(`action = "block"`)로 받고 부팅 때 변환 |
| tinicli `load_config`는 TOML 파싱 실패 시 **파일 전체를 기본값으로** 대체 | `config.rs:1415-1428` | tinicli 쪽 설정은 문자열로 받아 부팅에서 검증(`pii_mode` 관례). 오타가 provider까지 지우면 안 됨 |
| `GuardrailsConfig { pii: … }` 구조체 리터럴: tinicli 2곳·tinicore 테스트 1곳·**argo-tizen 1곳**(`..Default::default()` 없음) | `cli_entry.rs:420`, `guardrails/pii.rs:207`, `tests/guardrails/turn_scope_test.rs:293`, argo-tizen `guardrails/mod.rs:45` | 필드 추가 시 in-tree 3곳은 이번에 수정, argo-tizen은 전환 PR에서 한 줄(`..Default::default()`) 필요 → 병합 순서 제약으로 기록 |
| `install_sensitive_masking`은 `bool`(OnceLock first-wins) | `pii_masking.rs:632-642` | `prompt_guard::install`도 같은 모양, 실패는 `PromptGuardSlotTaken` |
| i18n `pii-admission-blocked`는 `en-US.ftl:481`, `ko-KR.ftl:176` 두 곳뿐 | `tinicore/i18n/` | 형제 키 `prompt-injection-blocked`를 같은 두 파일에만 추가 |

### 사용자 결정

| 항목 | 결정 |
|---|---|
| tinicli TOML 모양 | **중첩 테이블** `[prompt_injection.input]` / `[prompt_injection.tool_output]` / `[[prompt_injection.rules]]`. 기존 `pii_*` 키는 그대로. 기본 off |
| 호스트 룰(`additional_rules`) | tinicore 필드 + tinicli `[[prompt_injection.rules]]`로 **config.toml에서 넣을 수 있게** 구현·문서화. 지금 쓰는 곳은 없으므로 역직렬화·변환 테스트만 |
| 저장 전 게이트 | **A안**: tinicore가 `prompt_guard::installed() -> Option<Arc<CompiledGuard>>`만 노출, tinicli가 기존 `evaluate`를 `save_message` 전에 호출(Block=미저장·거절, Sanitize=정제 텍스트 저장, Warn=로그) |
| loop 안 검사 | 유지 + fallback(`CoreConfig.prompt_guard` 비어 있으면 `installed()`). 게이트 없는 호스트(tiniffi 등) 보호 |
| feature | 새 feature 없음. `guardrails`(+탐지기·설치는 `sensitive`) 그대로 |
| 이월(문서만) | Sanitize 재스캔 재빌드(`compile_cached` 경로에만 남음), `comment_directive` 바이트 창, 툴 결과 warn 소비자, 툴 결과 층 호스트 룰, 게이트웨이 저장 전 프롬프트 가드 |

---

## 0. 커밋 0 — 사전 정리: YAML 파서를 엔진으로 (기존 커밋 amend, 사용자 지적)

"YAML → `EngineConfig`" 파싱이 `pii/shared.rs:31`, `prompt_injection/mod.rs:220`(`engine_config_from`), `prompt_injection/mod.rs:176`(`parse_rules`의 `RuleFile { recognizers: serde_yaml::Mapping }` — `EngineConfig.recognizers`가 `HashMap`이라 파일 순서를 지키려고 따로 만든 파서) 세 곳에 있다. 스키마 소유자인 엔진이 파서도 하나로 제공한다.

- **C1 amend** (`a3fb20b037`… 리베이스 후 `1c640908d7`): `engine/config.rs`에
  ```rust
  impl EngineConfig { pub fn from_yaml(yaml: &str) -> Result<Self, EngineError> }          // 유일한 YAML 진입점
  pub fn parse_recognizers(yaml: &str) -> Result<Vec<(String, RecognizerConfig)>, EngineError>  // 파일 순서 보존(Mapping 읽기를 여기로 이동); from_yaml 은 이것을 collect
  ```
  `pii/shared.rs::compile_from_yaml`이 `EngineConfig::from_yaml` 사용. 테스트: 순서 보존, 키 중복 시 동작(serde_yaml Mapping의 마지막 값 승리 → `Config` 오류로 명시 거부), `from_yaml`과 `parse_recognizers`가 같은 집합을 냄.
- **R1 amend** (`83d0bca372`): `engine_config_from` 삭제 → `EngineConfig::from_yaml`; `parse_rules`는 `parse_recognizers(yaml)?` 위에 인젝션 고유 검증(키 == `entity_type`, `action` 필수, `layers` 필수)만 남김. `RuleFile` 삭제.
- 뒤 커밋(R2·N1·C5) 재적용, 커밋별 clippy, `range-diff`로 나머지 커밋 diff 동일 확인. 이 amend는 원격(`b334b73bd6`)과 갈라지므로 push 시 다시 force-with-lease.

## 1. 커밋 1 — tinicore: `prompt_guard` 설치 슬롯 + loop fallback

**파일**: `tinicore/src/agent/prompt_guard.rs`, `tinicore/src/agent/loop_.rs`, 신규 `tinicore/tests/prompt_guard_installed_e2e.rs`(+`tinicore/Cargo.toml` `[[test]]`, `required-features = ["test-fixtures"]`, `prompt_guard_e2e` 옆 ~1834).

`prompt_guard.rs`(항상 컴파일, 게이트 없음):

```rust
static INSTALLED_GUARD: OnceLock<Arc<CompiledGuard>> = OnceLock::new();

/// Install once per process; `false` when a guard is already there
/// (same shape as `pii_masking::install_sensitive_masking`).
#[must_use] pub fn install(guard: CompiledGuard) -> bool
/// The boot-installed guard. `agent_loop` reads it when
/// `CoreConfig.prompt_guard` is empty; a host's pre-persist gate reads it
/// to run `evaluate` before `save_message`.
#[must_use] pub fn installed() -> Option<Arc<CompiledGuard>>
```

빌드 횟수 진단(PII `shared_engine_build_count()`(`pii/shared.rs:125`) 대응, "부팅 1회·턴당 1회" 단언용):
```rust
/// How many times the installed guard's engine has been built. Diagnostics and tests.
#[doc(hidden)] #[must_use] pub fn installed_engine_build_count() -> Option<usize>   // installed().map(|g| g.filter.build_count())
```
이를 위해 `PatternFilter::build_count`의 `#[cfg(test)]`를 떼고 `pub(crate)`로(값은 `TurnSlot::build_count`, 이미 pub). `CompiledGuard`에 `pub(crate) fn engine_build_count(&self) -> Option<usize>`(filter 없으면 None).

rustdoc에 반드시: (a) 우선순위 — `CoreConfig.prompt_guard`가 비어 있지 않으면 설치된 가드는 **절대 안 읽힘**(argo-tizen 경로), (b) `Arc<CompiledGuard>`가 `PatternFilter`→`TurnSlot`을 붙들어 슬롯 등록이 유지됨, (c) 리셋 없음. 모듈 doc 18-32행: "설치 경로는 부팅에서 슬롯을 등록하므로 첫 턴 재빌드 공백은 `compile_cached` 경로에만 남는다" 한 문장 추가.

`loop_.rs:697-711` 교체:

```rust
let guard = if ctx.config.prompt_guard.is_empty() {
    let Some(guard) = prompt_guard::installed() else { return Ok(None); };
    guard
} else {
    prompt_guard::compile_cached(&ctx.config.prompt_guard)?
};
if guard.is_empty() { return Ok(None); }
```
674-690행 doc·1945-1958행 호출부 주석 갱신("빈 룰셋 + 설치 없음 ⇒ 비용 0"). `GuardOutcome` 분기·훅 이벤트·거절 문구는 그대로.

**테스트**: 단위 `install_is_first_wins_and_installed_returns_the_same_arc`(`#[serial]`, lib 바이너리에서 `INSTALLED_GUARD`를 만지는 유일한 단위 테스트라고 doc에 명시); e2e 신규 바이너리(`tests/prompt_guard_e2e.rs:44-240`의 mock-LLM 하네스 복사, `guardrail_layers_e2e.rs:134-154`의 `Once` 래치): `installed_guard_blocks_when_core_config_is_empty`(Blocked, LLM 호출 0, `prompt_guard.match` 이벤트에 본문 없음), `core_config_rules_take_precedence_over_the_installed_guard`(CoreConfig에 무관한 Warn 룰 하나 → 설치 가드의 Block 마커가 **통과**), `compile_shared_builds_once_per_turn_once_registered`(단위, `build_count()`로 게이트+loop 2회 `evaluate`에 빌드 1회; `engine_is_built_once_per_turn_once_the_slot_is_registered` 990-1009 모방).

## 2. 커밋 2 — tinicore: 설정 타입 + 설치 확장 + block 목록 좁히기

**파일**: `tinicore-traits/src/sensitive.rs`, `tinicore/src/guardrails/prompt_injection/{mod.rs,detector.rs}`, `tinicore/src/guardrails/pii/install.rs`, `tinicore/src/guardrails/mod.rs`, 리터럴 3곳(`tests/guardrails/turn_scope_test.rs:293`, `tinicli/src/cli_entry.rs:420`, `tinicli/src/guardrails/pii.rs:207`)에 `..Default::default()`.

### 2a. traits — `PromptInjectionLabel` (`PiiLabel::as_str`/`PiiMode: FromStr` 관례)
```rust
pub const fn as_str(self) -> &'static str   // serde 철자: "override" | "embedded_directive" | …
pub struct UnknownPromptInjectionLabel(pub String);   // Display: unrecognized prompt-injection label {:?} (expected one of …)
impl FromStr for PromptInjectionLabel { type Err = UnknownPromptInjectionLabel; }
```
테스트: `ALL` 전부 `serde_json::to_string(&l) == "\"{as_str}\""`이고 `as_str().parse() == Ok(l)`.

### 2b. `prompt_injection/mod.rs` — 설정 타입 (`guardrails`, serde 없음: `GuardrailsConfig`/`PiiConfig` 관례)
```rust
#[derive(Debug, Clone, Default)]
pub struct PromptInjectionConfig {
    pub input: PromptInjectionInputConfig,            // { enabled: bool }  ← labels 없음(입력 소비자는 CompiledGuard, 룰 id별 GuardAction 판정이라 라벨 block 목록이 없음)
    pub tool_output: PromptInjectionToolOutputConfig, // { enabled: bool, labels: Option<Vec<PromptInjectionLabel>> }
    pub additional_rules: Vec<PromptGuardRule>,       // prompt_guard 층, 임베디드 룰 뒤. id 충돌·컴파일 실패는 설치 실패
}
```
`labels` doc: `None` = 이 층 block 룰의 라벨 전부(4개); block 룰이 없는 라벨(`invisible_chars`)은 **경고 후 무시**; `Some(vec![])`은 **거부**(트립할 수 없는 가드레일이 설치된 척하면 안 됨). 모듈 doc 4-9행 "아무것도 배선되지 않음" → 배선 설명·우선순위·부팅 슬롯 등록으로 교체.

### 2c. `detector.rs` — 좁히기 생성자 (`guardrails`+`sensitive`)
```rust
#[must_use]
pub fn tool_output_guardrail_with_block(detector: PromptInjectionDetector, block: Vec<SensitiveKind>) -> SensitiveGuardrail
// = SensitiveGuardrail::new(GUARDRAIL_NAME, DetectorChain::single(Arc::new(detector)), block).on_incomplete(OnIncomplete::Block)
pub fn tool_output_guardrail(shared: &SharedEngine) -> Result<SensitiveGuardrail, EngineError>   // from_shared → kinds().to_vec() → 위 함수
```
탐지기를 받는 이유: 설치자가 `kinds()`를 한 번 읽어 검증한 뒤 같은 탐지기를 넘김(이중 생성 없음, `GUARDRAIL_NAME` 비공개 유지). `guardrails/mod.rs` 재수출: `tool_output_guardrail_with_block`(`all(guardrails, sensitive)`), 설정 타입 3종(`guardrails`); 파사드 doc의 "배선 안 됨" 문구 갱신.

### 2d. `pii/install.rs`
- `GuardrailsConfig { pii, prompt_injection: PromptInjectionConfig }` (`Default` 유지).
- `GuardrailsInstallError`에 두 변형: `PromptInjection { detail: String }`(호스트 룰 컴파일 실패·id 충돌·빈 labels·임베디드 파일 자체 검증 실패), `PromptGuardSlotTaken`. Display는 PII 관례대로 **탈출구를 이름으로** 명시: `PromptInjection` → "… Fix the rule or label named above, or set `prompt_injection.input.enabled` / `prompt_injection.tool_output.enabled` to false."; `PromptGuardSlotTaken` → "… a compiled guard already occupies the process-global slot …". `GuardrailMerge` 문구는 "PII input guardrail"에서 "the boot-time guardrail set (PII input, prompt-injection tool-output)"로 일반화(문구 단언 테스트 없음 확인).
- 순수 빌더(전역 안 만짐, `build_pii`의 형제):
  ```rust
  struct PromptInjectionBuild { tool_output: Option<SensitiveGuardrail>, input: Option<CompiledGuard> }
  fn build_prompt_injection(config: PromptInjectionConfig, warnings: &mut Vec<String>) -> Result<PromptInjectionBuild, GuardrailsInstallError>
  ```
  순서: ① 두 층 다 꺼짐 → `additional_rules`·`labels`가 있으면 각각 경고(`prompt_injection.additional_rules is set but neither layer is enabled — ignored` 식, **필드 경로로 시작**), 엔진 **빌드 안 함**(슬롯 registry는 Weak라 소비자 없는 슬롯은 다음 `turn_guard()`에서 제거됨) → `Ok(None, None)`. ② `SharedEngine::new(&additional_rules)` 실패 → `PromptInjection { detail }`(`EngineError` 문구가 룰 id를 이미 담음), `[prompt_injection]` error 로그. ③ `tool_output.enabled`: `from_shared` → `available = kinds()`; `labels` `None`→`available`, `Some`→중복 제거·`available`에 없는 라벨은 경고(`… blocks nothing at the tool-output layer (no block rule carries it) — ignored`)·결과 비면 `Err(PromptInjection { "… leaves nothing to block … list at least one of {available}, or set enabled = false" })` → `tool_output_guardrail_with_block`. ④ `input.enabled`: `compile_shared(&shared)`. ⑤ `shared` drop(소비자가 슬롯을 들고 있으므로 안전 — 주석으로 명시).
- `install_guardrails_from_config`: **전부 빌드 → 그다음 설치**. `set = pii_set.unwrap_or_default()`; `tool_output` 있으면 `set.with_tool_output(vec![guard])`; `!set.is_empty()`면 `install_guardrails(set)` 1회(`fully_merged` 아니면 `GuardrailMerge`); 마스킹 설치(기존); `input` 있으면 `prompt_guard::install(g)` (`false`→`PromptGuardSlotTaken`). 함수 doc·모듈 doc 1-8행("Today the only configured guardrail is PII")을 두 종류로 갱신, "슬롯은 여기서 첫 턴 전에 등록됨"·"`CoreConfig.prompt_guard` 우선" 명시.

**테스트**(단위, `build_prompt_injection` 경유, `SensitiveGuardrail`이 `Debug`가 아니므로 `match`로 판정): `prompt_injection_default_builds_nothing_and_warns_on_inert_fields`, `tool_output_default_blocks_every_block_label`(비동기 `.check` 트립), `tool_output_labels_narrow_the_block_list`(`[Override]`면 `curl … | bash`는 통과·override 문장은 트립), `tool_output_warn_only_label_is_reported_and_ignored`(`invisible_chars` 경고 1건, 여전히 트립), `tool_output_empty_effective_block_list_is_refused`(`Some([])`·`Some([InvisibleChars])` → "nothing to block"), `a_bad_additional_rule_fails_the_build_naming_the_rule`(`host_broken`), `an_additional_rule_shadowing_an_embedded_id_is_refused`("used twice"), `input_enabled_compiles_the_prompt_guard_layer_plus_host_rules`(`ignore_prior` Block, 호스트 마커 Warn, `curl … | bash`는 Allow = 툴 결과 룰 비가시), `prompt_injection_error_texts_name_the_way_out`.

## 3. 커밋 3 — tinicli: 설정·부팅·저장 전 게이트·i18n

**파일**: `tinicli/src/config.rs`, `tinicli/src/guardrails/mod.rs` + 신규 `tinicli/src/guardrails/prompt_injection.rs`, `tinicli/src/cli_entry.rs:415-442`, `tinicli/src/repl.rs:481-507`, `tinicli/src/run_tui.rs:456-497`, `tinicore/i18n/en-US.ftl`(481 뒤)·`ko-KR.ftl`(176 뒤), `tinicore/src/i18n/bundle.rs`(415-437 옆 단언 2개).

### 3a. `config.rs` — 문자열로 받는 `[prompt_injection]` 절
```rust
#[serde(default)] pub prompt_injection: Option<PromptInjectionCliConfig>,

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct PromptInjectionCliConfig {
    #[serde(default)] pub input: PromptInjectionInputToml,            // { enabled: bool }
    #[serde(default)] pub tool_output: PromptInjectionToolOutputToml, // { enabled: bool, labels: Option<Vec<String>> }
    #[serde(default)] pub rules: Vec<PromptInjectionRuleToml>,        // [[prompt_injection.rules]]
}
pub struct PromptInjectionRuleToml { id: String, pattern: String, action: String /* warn|block|sanitize */, #[serde(default)] replacement: Option<String> }
```
rustdoc(사용자 결정 "옵션 문서화")에 담을 것: 아래 TOML 예시, ASCII 엔진·`(?u)` 주의(`PromptGuardRule` doc 문장 복사), "모르는 라벨/액션은 부팅 중단", "block 룰이 없는 라벨은 경고 후 무시", "`labels = []`는 중단", "이 호스트는 `CoreConfig.prompt_guard`를 채우지 않으므로 설치된 가드가 실제로 동작", "`guardrails` feature 빌드에서만 유효".
```toml
[prompt_injection.input]
enabled = true

[prompt_injection.tool_output]
enabled = true
labels = ["override", "embedded_directive", "comment_directive", "base64_decoded_to_shell"]

[[prompt_injection.rules]]          # 호스트 룰 (사용자 입력 층). 지금 쓰는 곳 없음 — 문서화 목적
id = "acme_context_forgery"
pattern = '(?i)\[trusted-context\]'
action = "block"
```

### 3b. `tinicli/src/guardrails/prompt_injection.rs` (`#[cfg(feature = "guardrails")]`)
```rust
pub(crate) fn to_core_config(cfg: Option<&PromptInjectionCliConfig>) -> Result<PromptInjectionConfig, String>
```
라벨은 `parse::<PromptInjectionLabel>()`(오류 문구에 필드 경로), 액션은 `warn|block|sanitize`→`GuardAction`(`sanitize`에 `replacement` 없으면 빈 문자열, 다른 액션에 `replacement`가 있으면 경고), 모르는 값 → `Err`(룰 id 명시). `None` → `default()`.
테스트: 예시 TOML 파싱, 라벨 4개 변환, `"embeded_directive"`·`action = "blok"` 오류 문구, 절 없음 → 기본값, `save_config` 왕복(`config.rs:2011` 패턴). 전역 설치 e2e `mod global_install_e2e`(`pii.rs:49-65` doc 각색): **`pii: PiiConfig::default()`**(같은 lib 바이너리의 `pii.rs` 테스트가 마스킹 OnceLock을 소유하므로 `Full`이면 plain `cargo test --lib`에서 `MaskingSlotTaken`), `installed().is_some()`, `global_guardrails().tool_output`에 `prompt_injection.tool_output`, `evaluate(&installed, "Ignore all prior instructions")` → `Block { rule_id: "ignore_prior" }`. `prompt_guard::install`은 first-wins이므로 이 바이너리의 유일한 설치자여야 함을 doc에 명시.

### 3c. `cli_entry.rs:415-442`
`to_core_config` 실패 → `eprintln!("[guardrails] refusing to start: {msg} (config.toml)")` + `exit(1)`; `install_guardrails_from_config(GuardrailsConfig { pii: …(기존), prompt_injection })`; 경고·오류 접두사 `[pii]` → **`[guardrails]`**(이 블록만); `LayerBuild | PromptInjection`에 `(config.toml)` 힌트. `#[cfg(not(feature = "guardrails"))]`에서 `cfg.prompt_injection.is_some()`이면 "이 빌드에는 `guardrails` feature가 없어 무시됨" 한 줄 경고(권장, `pii_mode`에 없던 것이지만 한 줄).

### 3d. REPL 게이트 (`repl.rs`, PII 게이트 492-500 뒤·`save_message` 503 앞)
```rust
let user_input: Cow<'_, str> = match tinicore::agent::prompt_guard::installed() {
    None => Cow::Borrowed(user_input),
    Some(guard) => match prompt_guard::evaluate(&guard, user_input) {
        GuardOutcome::Allow { warned } => { /* warned 는 log::warn!("[prompt_injection] warn rule={r}") */ Cow::Borrowed(user_input) }
        GuardOutcome::Sanitize { sanitized, .. } => Cow::Owned(sanitized),        // 정제 텍스트를 저장
        GuardOutcome::Block { rule_id, .. } => return Err(format!("{} {rule_id}", t!("prompt-injection-blocked", locale))),   // 저장 안 함
    },
};
let user_msg = ChatMessage::user(&user_input, now);   // 503, user_input 의 유일한 후속 사용
```
본문은 절대 로그·에코 금지(룰 id만). 훅 이벤트는 loop의 몫(loop가 저장된 텍스트를 다시 스캔하므로 Sanitize는 이중 발화 없음, Warn은 loop에서 1회). 함수 상단 `turn_guard()`(453)가 이미 있어 빌드 1회.

### 3e. TUI 게이트 (`run_tui.rs`, PII 게이트의 `continue` 490 뒤·`save_message` 497 앞)
같은 match; `user_text`가 `String`이라 Sanitize는 `user_text = sanitized;`. Block은 `app.finish_thinking()` 후 `System` 메시지 push + `continue`(PII 분기 479-484와 같은 재진입 논리). 화면 `app.messages`는 원문, DB는 정제 텍스트라는 차이를 주석으로 기록.

### 3f. i18n
`en-US.ftl`: `prompt-injection-blocked = Input blocked by a prompt-injection rule:`; `ko-KR.ftl`: `prompt-injection-blocked = 프롬프트 인젝션 규칙에 의해 입력이 거부되었습니다:`(룰 id는 Rust에서 뒤에 붙임, 469-479행 주석에 두 키 모두 언급); `bundle.rs`에 영어·한국어 단언 각 1개. 다른 11개 FTL은 손대지 않음(`pii-admission-blocked`도 두 파일뿐).

### 3g. 바뀌지 않는 것
`daemon.rs`(`guardrails: None` — loop fallback이 덮음), 게이트웨이 핸들러(저장 전 프롬프트 가드 없음 → loop가 최신 메시지만 보므로 오염은 없음, 후속으로 기록), `context_builder.rs`(`CoreConfig.prompt_guard`는 이 호스트에서 계속 빈 값).

## 4. 커밋 4 — 문서 + e2e

**e2e** 신규 `tinicore/tests/prompt_injection_install_e2e.rs`(`required-features = ["guardrails","sensitive","test-fixtures"]`, `#![cfg(all(...))]`; `Once` 래치로 `install_guardrails_from_config(GuardrailsConfig { pii: Off, prompt_injection: { input on, tool_output on, labels None, additional_rules: [Warn "zz-host-marker"] } })`): `the_install_registers_both_consumers`, `an_injection_in_a_tool_result_is_replaced_on_the_real_dispatch_path`(`guardrail_layers_e2e.rs:167+`의 SpyTool·오케스트레이터 복사, 본문 1회 실행·`result.output` 교체), `an_injection_in_the_user_message_is_refused_before_the_llm_with_empty_core_config`(mock-LLM, Blocked, 호출 0; 호스트 마커는 Allow+warn 이벤트), `a_second_install_with_input_enabled_is_refused`(`PromptGuardSlotTaken`), **`one_build_serves_boot_gate_loop_and_tool_output`**: `ensure_installed` 직후 `installed_engine_build_count() == Some(1)`(부팅 검증 빌드 1회); 그 뒤 `let _g = turn_guard();` 아래에서 게이트처럼 `evaluate(&installed, text)` → mock-LLM 턴(loop의 `apply_inbound_prompt_guard`) → SpyTool 툴 결과 스캔까지 한 턴을 돌리고 `== Some(2)`(턴당 정확히 1회 추가); guard drop 후 다시 한 턴 → `Some(3)`. tinicli 쪽 `global_install_e2e`에도 같은 단언(REPL `run_single_turn`의 `turn_guard` 아래 게이트+loop 한 턴 = +1).

**문서**: `pii/install.rs` 모듈 doc(두 종류·부팅 슬롯 등록·한 세트 설치), `prompt_injection/mod.rs`·`detector.rs` doc(배선됨·설정 의미·우선순위·이월 4건), `guardrails/mod.rs` 파사드 doc(argo-tizen이 만지는 심볼에 `GuardrailsConfig.prompt_injection` 추가, 리터럴 `..Default::default()` 필요 명시), `agent/prompt_guard.rs` 모듈 doc, `pii/AGENTS.md`("Enabling PII guardrails" 절에 `[prompt_injection]` 하위 절: TOML 예시·라벨 목록·경고/중단 규칙·`[guardrails]` 접두사·게이트웨이 이월; "Scope" 목록에 게이트 호출 지점 2곳), `pii/README.md:42-44`, `tests/guardrail_layers_e2e.rs:417-420` 주석("아무도 등록 안 함" → 부팅 설치자가 등록, 이 파일은 격리용 자체 등록), `tinicli/src/guardrails/pii.rs` 모듈 doc(형제 모듈 언급).
**shared 계획서** `20260921-prompt-injection-guardrails-wiring-plan.md`: §1-§3을 최종 모양(설정 구조체 2종, 입력 층 `labels` 없음, tinicli 문자열, `install -> bool`, 오류 변형)으로 갱신, 상태 줄 추가, §4 argo-tizen 목록에 `..Default::default()` 한 줄 항목 추가 → commit·push(문서 관례).

---

## 5. 위험·경계 (읽으며 확인한 것)

1. `loop_.rs:698`의 early return을 남겨 두면 tinicli에서 설치 가드가 죽은 코드 → `installed_guard_blocks_when_core_config_is_empty`로 고정.
2. 슬롯 registry는 Weak: 소비자 없이 `SharedEngine`만 만들면 다음 `turn_guard()`에서 제거되어 매 스캔 빌드(정확하지만 느리고 조용함) → 두 층 다 꺼지면 빌드 안 함.
3. `guardrail_scan_cache`가 첫 입력 패스 후 INPUT 체인을 영구 pin(`agent/guardrails.rs:241-249`) → 부팅에서 **한 세트 한 번** 설치가 필수.
4. `install_guardrails_from_env("ARGO")`(`cli_entry.rs:158`)의 `ARGO_GUARDRAIL_TOOL_PACK` 체인이 먼저 append되어 있으면 체인 순서상 그쪽 tripwire 문구가 먼저 이김(첫 히트 중단). 허용, 문서에 기록.
5. 우선순위 함정: `CoreConfig.prompt_guard`를 채우면서 `prompt_injection.input`도 켠 호스트는 설치 가드가 조용히 안 돎(설치자는 `CoreConfig`를 못 봄) → 양쪽 rustdoc에 명시. argo-tizen 전환이 겹침을 없앰.
6. 게이트에서 막힌 Block은 `prompt_guard.match` 훅 이벤트가 안 남(PII 게이트와 동일). 필요하면 후속.
7. `labels` 검사가 `detector.kinds()` 기준이라, 나중에 `invisible_payload`가 block으로 승격되면 코드 변경 없이 `invisible_chars`가 유효 라벨이 됨.
8. plain `cargo test --lib`에서는 tinicli lib 바이너리에 전역 설치 테스트가 두 개(PII·인젝션) 공존 → 인젝션 쪽은 `pii: Off`, 각 바이너리에 설치자 하나 원칙을 doc으로.
9. tinicore-traits 추가(`as_str`/`FromStr`)는 additive. 대안(tinicli 내부 문자열 표)은 철자 표가 둘이 되어 더 나쁨.
10. feature 게이트 배치: `install`/`installed`/loop fallback은 게이트 없음(`CompiledGuard`만 사용), `compile_shared`·설정 타입은 `guardrails`, `tool_output_guardrail_with_block`·`build_prompt_injection`·설치 확장은 `all(guardrails, sensitive)`. "`guardrails`만" clippy 레인이 오배치를 잡음.
11. **호환성 결정**: `GuardrailsConfig`에 필드 추가(모듈 doc이 이미 "나중 종류는 필드로"라고 약속). in-tree 리터럴 3곳은 커밋 2에서 `..Default::default()`; argo-tizen `guardrails/mod.rs:45`는 전환 PR에서 한 줄 필요 → argo-tizen rsync 게이트는 이번에 **E0063(missing field) 1건이 예상값**, unresolved import(E0432/E0433)는 계속 0이어야 함. `#[non_exhaustive]`(리터럴 자체 금지)·별도 진입점(한 세트 설치 불변 조건 분산)은 기각.

---

## 6. 검증 (커밋마다; 마지막에 전체)

```bash
export PATH="$HOME/.cargo/bin:$PATH"; cd ~/Works/ARGO-ClawKeeper
cargo fmt --all -- --check
cargo clippy -p tinicore-traits -p tinicore --features guardrails,sensitive,cognition,test-fixtures --all-targets -- -D warnings
cargo clippy -p tinicore --features guardrails --all-targets -- -D warnings          # guardrails 만: cfg 게이트 검증
cargo clippy -p tinicore --no-default-features --all-targets -- -D warnings          # 슬림
cargo check  -p tinicore --no-default-features --features sensitive
cargo nextest run --profile ci -p tinicore-traits
cargo nextest run --profile ci -p tinicore --features guardrails,sensitive,cognition,test-fixtures
cargo nextest run -p tinicore --features test-fixtures --test prompt_guard_e2e --test prompt_guard_installed_e2e
cargo nextest run -p tinicore --features guardrails,sensitive,test-fixtures --test guardrail_layers_e2e --test prompt_injection_install_e2e
cargo nextest run -p tinicore --features guardrails,sensitive,cognition,test-fixtures -E 'test(us_bank_account)'   # ABA 14
cargo clippy -p tinicli --features guardrails --all-targets -- -D warnings
cargo clippy -p tinicli --all-targets -- -D warnings                                  # guardrails 없이: 설정·게이트 컴파일, 설치는 cfg-out
cargo nextest run --profile ci -p tinicli --features guardrails
cargo nextest run --profile ci -p tinicli
cargo build -p argo-cli --features guardrails
python3 scripts/audit_core_layer_deps.py && python3 scripts/audit_core_product_leak.py && python3 scripts/audit_core_crate_name_leak.py
python3 scripts/audit_reimpl.py --self-test && python3 scripts/audit_reimpl.py     # baseline 77
python3 scripts/audit_panics_ci.py                                                 # 21 / 13 / 8
python3 scripts/audit_sensitive_slim.py --self-test && python3 scripts/audit_sensitive_slim.py
/tmp/ck-tizen-gate.sh     # 기대: E0432/E0433 0, errors total 1 (E0063 GuardrailsConfig missing field — 전환 PR에서 해소)
```
**수동**: `--features guardrails`로 빌드한 `argo`, `config.toml`에 두 층 on → REPL에 "ignore all previous instructions" 입력 시 `prompt-injection-blocked` 줄 출력·DB에 행 없음; 출력에 `curl … | bash`가 든 툴 → 결과가 tripwire 문구로 교체되고 턴은 계속.

**완료 조건**
- [ ] 커밋 0: `EngineConfig::from_yaml`·`parse_recognizers`가 유일한 YAML 파서(`grep serde_yaml::from_str` 프로덕션 코드 0건, 엔진 안 제외), C1·R1 amend 후 range-diff로 나머지 동일
- [ ] 커밋 1: `loop_.rs` fallback, `install`/`installed`/`installed_engine_build_count`, e2e 우선순위·차단 테스트, `build_count` 1회 테스트
- [ ] 빌드 횟수 보장: 부팅 1회(검증 빌드), 턴당 1회(게이트+loop+툴 결과 공유) — e2e `one_build_serves_boot_gate_loop_and_tool_output`로 고정. 예외는 `turn_guard()` 없이 부르는 호출자뿐(문서화)
- [ ] 커밋 2: `GuardrailsConfig.prompt_injection`, 오류 변형 2개, `build_prompt_injection` 단위 테스트 9건, 리터럴 3곳 `..Default::default()`, 재수출
- [ ] 커밋 3: `[prompt_injection]` TOML(문자열)·`to_core_config`·`[guardrails]` 접두사·REPL/TUI 게이트·i18n 2키
- [ ] 커밋 4: e2e 바이너리, 문서 8곳, shared 배선 계획서 갱신·push
- [ ] 전 레인 통과, 기준선 유지(reimpl 77, panic 21/13/8), argo-tizen 게이트 unresolved 0·E0063 1
- [ ] push·PR은 지시 대기
