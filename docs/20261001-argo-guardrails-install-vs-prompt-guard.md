# install_guardrails_from_config 와 prompt guard 설정의 계층 구조

- 작성일: 2026-10-01
- 기준 코드: ARGO `dev/byungchul.so/guardrails-clawkeeper` HEAD `cef4fdf7ac` (PR #3454), main 기준점 `0f59507f6e`
- 비교 대상: argo-tizen `main` `6d1319c7`

## 결론

`install_guardrails_from_config` 는 **프로세스 전체가 함께 보는 전역 슬롯**에 가드레일을 설치하는 함수입니다. 반면 prompt guard(사용자 입력 검사) 규칙은 **`RuntimeContext` 가 들고 다니는 설정값 `CoreConfig.prompt_guard`** 에 들어갑니다.

install 은 `CoreConfig` 를 입력으로 받지 않습니다. 그리고 tinicli 에서는 install 이 실행되는 시점에 `CoreConfig` 가 아직 만들어지지 않았습니다. 그래서 지금 구조에서는 install 이 prompt guard 를 설정하지 않고, host 가 `CoreConfig` 를 조립할 때 직접 채웁니다.

이 분리는 기술적으로 불가능해서 생긴 것이 아니라 **설계상의 역할 분리**입니다. install 이 prompt guard 설정값을 "만들어서 돌려주고", host 가 그 값을 `CoreConfig` 에 넣는 형태로 바꾸면 분리를 유지하면서 진입점을 하나로 모을 수 있습니다(5절).

## 1. 저장 장소가 두 종류입니다

```
┌──────────────────────── argo process ────────────────────────┐
│                                                               │
│  [A] Global slots  (one per process, tinicore owns them)      │
│      ┌──────────────────────────────────────────────┐         │
│      │ input chain      : PII check                  │         │
│      │ tool_output chain: prompt-injection check     │         │
│      │ masking slot     : PII masking policy         │         │
│      └──────────────────────────────────────────────┘         │
│         ▲ written by install_guardrails_from_config           │
│                                                               │
│  [B] Context config  (held by RuntimeContext, read-only)      │
│      ┌──────────────── RuntimeContext ──────────────┐         │
│      │ config: Arc<CoreConfig>                       │         │
│      │   ├─ llm, memory, agent ...                   │         │
│      │   └─ prompt_guard: [rule1, rule2, ...]  ◀─────┼── here  │
│      └──────────────────────────────────────────────┘         │
└───────────────────────────────────────────────────────────────┘
```

| | [A] 전역 슬롯 | [B] 컨텍스트 설정 (`CoreConfig`) |
| --- | --- | --- |
| 개수 | 프로세스에 하나 | `RuntimeContext` 가 하나씩 보유 |
| 소유자 | tinicore | host 가 조립해서 `RuntimeContext` 에 넘김 |
| 변경 | install 할 때 한 번 | `Arc` 로 감싼 뒤에는 바뀌지 않음 |
| 읽을 수 있는 코드 | `ctx` 가 없는 코드도 읽음 | `ctx` 를 가진 코드만 읽음 |
| 들어 있는 가드 | PII input 체인, tool output prompt injection 체인, PII masking 정책 | `prompt_guard` 규칙 목록 |

- `CoreConfig.prompt_guard` 는 prompt guard 를 도입한 #979(`33987d4386`) 때부터 [B] 의 필드로 설계되었습니다(`tinicore/src/config/core_config.rs:656`).
- 서브에이전트는 부모의 설정을 `Arc::clone` 으로 공유합니다(`tinicore/src/agent/sub_agent_context.rs:614`). 그래서 tinicli 에서 실제로 쓰이는 `CoreConfig` 는 사실상 하나입니다. 그래도 타입 수준에서는 "컨텍스트가 가진 값"이며 전역 상태가 아닙니다.

## 2. 부팅 순서상 install 이 `CoreConfig` 보다 먼저 실행됩니다

```
time ──────────────────────────────────────────────────────────▶

 ① read config.toml   ①' compile_inbound_guard   ② install_guardrails_from_config   ③ build_context
   (CliConfig)          cli_entry.rs:431           cli_entry.rs:442                   cli_entry.rs:556~
                        validate only              writes [A]                         builds [B]
                                                                 └ prompt_guard filled here
                                                                   (inbound_guard_config,
                                                                    context_builder.rs:1154)
                                                              ▲
                                   at this moment, CoreConfig [B] does not exist yet
```

`cli_entry::run()` 안에서 보면 다음과 같습니다.

```
cli_entry::run()
 ├─ :420  to_core_config           (tool-output config; mode typo → exit)
 ├─ :431  compile_inbound_guard    (user-input rules: build + compile → exit on error)
 ├─ :435  parse_pii_mode
 ├─ :442  install_guardrails_from_config   ← [A] global slots
 │        (all of the above sit in ONE #[cfg(feature = "guardrails")] block)
 │
 └─ :556~ build_context            ← [B] CoreConfig; prompt_guard filled here
                                      (inbound_guard_config called again)
```

`compile_inbound_guard` 는 install 과 같은 cfg 블록 안에 있을 뿐 install 의 일부가 아닙니다. 그래서 `inbound_guard_config` 가 두 번 호출됩니다. 한 번은 검증과 캐시 등록을 위해(`:431`), 한 번은 `CoreConfig` 에 값을 넣기 위해(`build_context`) 호출됩니다.

1. **부팅 검증:** install 직전, 같은 `#[cfg(feature = "guardrails")]` 블록 안에서 `compile_inbound_guard`(`tinicli/src/cli_entry.rs:431`) 가 `inbound_guard_config` 를 한 번 호출해 규칙을 컴파일해 봅니다. user input mode 오타나 규칙 오류가 있으면 부팅을 중단합니다(tool output mode 오타는 그보다 앞선 `to_core_config`, `:420` 에서 걸립니다). 컴파일된 guard 는 `compile_cached` 캐시에 남습니다.
2. **설정 채우기:** ③ `build_context` 가 `CoreConfig` 를 조립하면서 `inbound_guard_config` 를 다시 호출해 `core.prompt_guard` 를 채웁니다(`tinicli/src/context_builder.rs:1154`). 이어서 `Arc::new(core)`(`:1419`) 로 감싸 `RuntimeContext::with_required(config_arc, ...)`(`:1513`) 에 넘깁니다.
3. **턴마다:** `gate()`(REPL/TUI 저장 전), gateway handler 의 `admit`(`tinicore/src/gateway/handler.rs:744`), `agent_loop` 안의 `apply_inbound_prompt_guard`(`tinicore/src/agent/loop_.rs:691`) 가 `ctx.config.prompt_guard` 를 읽습니다. 규칙 목록은 부팅 때 고정되고, 패턴 엔진만 턴마다 turn slot 에서 빌드되었다가 턴이 끝나면 해제됩니다.

`build_context` 는 실행 모드(REPL, 단발 실행, daemon 등)마다 진입점에서 한 번씩 호출되며 턴마다 호출되지 않습니다(`cli_entry.rs:556/711/753/801/920`).

## 3. 왜 PII 는 전역이고 prompt guard 는 컨텍스트인가

결정적인 차이는 **검사하는 쪽이 `ctx` 를 가지고 있느냐**입니다.

```
User message ──▶ gate() / admit / agent_loop ──▶ reads [B].prompt_guard
                 (all of these carry ctx)            ✔ context config is enough

Background LLM call (summary, etc.) ──▶ no ctx ──▶ reads [A]
                                                    ✔ only global slots reach here
```

- **prompt guard** 는 사용자가 보낸 메시지만 검사합니다. 사용자 메시지는 항상 `ctx` 를 가진 경로로 들어옵니다. 따라서 컨텍스트 설정으로 충분합니다.
- **PII masking** 은 LLM 클라이언트 계층의 송신 지점(`EgressMask`)에서 적용됩니다. 이 지점은 실행별 설정(`AgentLoopConfig`)을 전혀 받지 못하고, 전역 `OnceLock` 인 `SensitiveMasking` 만 읽습니다. 2026-08 에 턴 단위로 빌드하는 방식을 시도했지만 이 전역 값을 설치하지 않아서, compaction·서브에이전트·A2A 작업의 백그라운드 LLM 호출이 마스킹 없이 나갔고 결국 되돌렸습니다(`tinicore/src/guardrails/pii/install.rs` 모듈 문서 "Why global, not per-turn"). 그림의 "no ctx" 는 엄밀히는 "실행별 설정이 닿지 않는 송신 지점"이라는 뜻입니다.
- **PII input 체인**은 원래부터 `install_guardrails` 의 프로세스 전역 슬롯이었고, `install_guardrails_from_env` 가 넣은 운영자 규칙과 함께 누적됩니다.
- `install_guardrails_from_config` 는 이 전역 설치들의 단일 진입점입니다(#3413).
- `GuardrailsConfig.prompt_injection` 필드는 tool output 지점만 다룹니다(안에 `tool_output` 필드 하나뿐, `prompt_injection/install.rs:30-34`). 필드 문서도 "The inbound-user-message check point is `CoreConfig.prompt_guard`." 라고 명시합니다(`install.rs:45-47`).

## 4. 두 host 의 대응 관계

### 4.1 이번 PR 이전

ARGO main(`0f59507f6e`)에는 `core.prompt_guard` 를 채우는 코드가 한 곳도 없었습니다. #979 는 엔진과 검사 지점만 도입했고, 필드 문서는 규칙을 host 의 몫으로 정했습니다("The rules come from the Product manifest / host config — Core ships none"). 그 host 역할을 실제로 하던 곳은 argo-tizen 뿐이었습니다. `inbound_guard_config` 는 ARGO 에서 처음으로 이 역할을 맡은 함수입니다.

### 4.2 함수 대응

| 역할 | ARGO tinicli | argo-tizen |
| --- | --- | --- |
| config 키 | `user_input_prompt_injection_mode = "off"/"on"` | `[safety.prompt_guard] mode = "off"/"warn"/"block"` (기본 off) |
| 규칙 목록 만들기 | `inbound_guard_config` — 값을 **돌려줌** | `prompt_guard_config_for_mode` — 값을 돌려줌 |
| `CoreConfig` 에 넣기 | `context_builder.rs:1154` 에서 대입 | `apply_prompt_guard_mode(&mut core, ..)` (`crates/argot-daemon/src/context_builder.rs:160`) |
| 규칙 출처 | tinicore `baseline_rules()` 7개 | 자체 baseline 3개(`CORE_PROMPT_GUARD_BASELINE_RULES`) + 제품 규칙 |
| action | 규칙마다 고정(block 6, warn 1) | mode 가 모든 규칙의 action 을 덮어씀 |
| 추가 규칙 | 없음 | 제품 코드의 `ProductDefinition::with_guard_rules` (config.toml 이 아님). 현재 사용하는 제품 없음 |
| 저장 전 검사 | `gate()` — 루프와 같은 규칙 사용 | `compile_pre_persist_prompt_guard` — 별도 규칙 세트(위조 태그 규칙 포함) |
| 부팅 시 컴파일 검증 | `compile_inbound_guard` | `compile_pre_persist_prompt_guard` 가 겸함 |

주의할 점: argo-tizen 의 warn 모드에서는 저장 전 검사 규칙에 위조 태그 규칙 2개만 들어가고(`agent_config.rs:378-389`), 부팅 때 컴파일되는 것도 이것뿐입니다(`turn/mod.rs:339`). 그래서 warn 모드에서는 제품 규칙의 패턴 오류가 부팅 때 잡히지 않습니다. block 모드에서는 baseline, 제품 규칙, 위조 태그 규칙이 모두 컴파일됩니다. 코드를 읽어 확인한 내용이며 실행해 보지는 않았습니다.

### 4.3 sync 후 argo-tizen 에서의 연결

argo-tizen 의 tini 동기화(`project/scripts/sync-tini.sh`, `.github/workflows/tini-sync.yml`)는 `tini/` 아래로 tinicore, tinicore-traits 등을 옮기지만 **tinicli 는 옮기지 않습니다.** argo-tizen 은 루트 `Cargo.toml` 에서 `guardrails` 기능을 켜고 있으므로 `baseline_rules()` 를 쓸 수 있습니다. 따라서 argo-tizen 은 `inbound_guard_config` 를 호출할 수 없고, tinicore 의 `baseline_rules()` 를 받아 자기 `prompt_guard_config_for_mode` 안에서 씁니다.

```rust
// argo-tizen agent_config.rs (after sync, sketch)
pub fn prompt_guard_config_for_mode(mode, additional) -> PromptGuardConfig {
    // CORE_PROMPT_GUARD_BASELINE_RULES (3) → tinicore::guardrails::baseline_rules() (7)
    // + product rules, then apply the mode's action
}
```

주의: argo-tizen 은 mode 가 모든 규칙의 action 을 덮어씁니다. block 모드에서 `invisible_payload`(warn) 까지 block 이 되면, ZWJ 가 들어간 이모지만 보내도 메시지가 거부됩니다. 이 규칙은 action 을 덮어쓰지 말고 warn 으로 유지해야 합니다.

## 5. 검토했으나 채택하지 않은 안: install 이 prompt guard 설정을 "돌려주는" 형태

> **결정 (2026-10-01): 채택하지 않음.** install 이 `CoreConfig` 설정용 값을 돌려주면 `GuardrailsConfig`·`GuardrailsInstall` 에 파라미터만 늘어납니다. 지금처럼 host 가 `CoreConfig.prompt_guard` 를 직접 채우고, 대신 7절처럼 함수 이름과 기능 게이트 범위를 정리합니다. 아래는 검토 기록으로 남깁니다.

```
② install ──returns──▶ PromptGuardConfig (validated)
                              │
③ build_context ──puts it into──▶ [B].prompt_guard
```

```rust
// tinicore (sketch)
pub struct PromptInjectionConfig {
    pub user_input: bool,                        // new
    pub tool_output: PromptInjectionToolOutputConfig,
}

pub struct GuardrailsInstall {
    pub warnings: Vec<String>,
    pub prompt_guard: PromptGuardConfig,         // new: returned, not installed
}
```

- install 은 계속 전역 슬롯에만 씁니다. prompt guard 규칙은 만들고 컴파일해 검증한 뒤 **값으로 돌려주기만** 합니다.
- host 는 돌려받은 값을 지금처럼 ③ 에서 `CoreConfig` 에 넣습니다. 필요하면 그 전에 자기 규칙을 이어 붙입니다.
- tinicli 의 `inbound_guard_config` 와 `compile_inbound_guard` 는 대부분 없어지고, 검증이 install 한 곳으로 모입니다.
- "mode 를 읽어 규칙을 고르고 action 을 정하는" 로직을 tinicore 에 두면 tinicli 와 argo-tizen 이 같은 함수를 쓰게 됩니다. 다만 argo-tizen 의 mode 덮어쓰기와 저장 전 검사 분리는 host 쪽에 남습니다.

## 6. 관련 후속 과제

PR #3454 는 수정하지 않기로 했으므로 아래는 모두 별도 작업입니다.

1. **REPL/TUI `gate()` 기능 게이트 해제 (A1):** `gate()` 는 항상 컴파일되는 `prompt_guard::admit` 만 쓰는데도 tinicli `guardrails::prompt_injection` 모듈째 `#[cfg(feature = "guardrails")]` 안에 있습니다.
2. **host 규칙 도입 시 기능 게이트 범위 축소:** host 규칙이 생기면 `inbound_guard_config`, `compile_inbound_guard`, `context_builder.rs:1153` 블록을 기능 밖으로 옮기고 `baseline_rules()` 호출만 게이트해야 합니다. 그렇지 않으면 기능을 끈 빌드에서 host 규칙까지 사라집니다. A1 은 이 작업의 부분집합입니다.
3. **tool output host 규칙 API:** `SharedEngine` 은 내장 `RULES_YAML`(`&'static str`) 로만 빌드되고 규칙 → label 연결이 고정 표(`label_for`) 라서, argo-tizen 고유 규칙을 tool output 에 걸 수 없습니다. 엔진 입력, label 지정, action 정책을 바꾸는 API 가 필요합니다.
4. **이름 정리:**
   - `baseline_rules` → `user_input_prompt_injection_rules` 권장. 이 함수는 prompt injection 규칙 전체가 아니라 `prompt_guard` 레이어 7개만 돌려주며, config 키 `user_input_prompt_injection_mode` 와 짝이 맞습니다.
   - `inbound_guard_config` → `prompt_guard_config`, `compile_inbound_guard` → `compile_prompt_guard` (argo-tizen `prompt_guard_config_for_mode` 와 대응. tinicli 에는 mode enum 이 없어 `_for_mode` 는 생략).
5. **문서 정정:** `CoreConfig.prompt_guard` 문서의 "Core ships none" 은 이제 tinicore 가 `baseline_rules()` 를 제공하므로 부정확합니다. "Core installs none by default; a host may opt into `guardrails::baseline_rules()`" 정도로 고치면 됩니다.

## 7. 결정 사항 (2026-10-01)

6절의 후속 과제를 아래처럼 구체화했습니다. 모두 PR #3454 밖의 별도 작업입니다.

### 7.1 `compile_inbound_guard` 를 없애고 `build_context` 에서 한 번만 호출

검증(`compile_cached`)을 `prompt_guard_config` 안으로 합칩니다. `build_context` 의 대입부(`context_builder.rs:1154`)에는 이미 `Err` 면 부팅을 중단하는 처리가 있으므로, 별도 검증 함수와 `cli_entry.rs:431` 의 호출이 필요 없어집니다.

```
build_context (no feature gate)
 └─ prompt_guard_config(cfg)
      ├─ layer_on(user_input mode)        typo → Err
      ├─ baseline_rules()                 #[cfg(feature = "guardrails")] only
      ├─ [[user_input_prompt_injection_rules]]
      ├─ compile_cached(&config)          validate + warm the cache → Err
      └─ Ok(config) → core.prompt_guard
```

한 번만 호출해도 되는지 확인했습니다. install(`:442`) 부터 `build_context` 안의 대입 지점까지 실행되는 코드는 다음과 같습니다.

| 구간 | 하는 일 | 부팅이 중단될 때의 영향 |
| --- | --- | --- |
| `cli_entry.rs` | locale 초기화 | 없음 |
| | `--connect` 분기 | 이 경로는 여기서 종료하며 `build_context` 를 거치지 않음 |
| | 문서 디렉터리 생성, SQLite DB 열기 | 디렉터리만 남고 다음 실행에 문제 없음 |
| daemon 경로만 | 로거 설치, `DaemonLock` 획득 | `fd-lock`(flock) 이라 프로세스가 끝나면 OS 가 잠금을 해제 |
| `build_context` 앞부분 | node/python 탐지, template cache 저장소 열기 | 없음 |

daemon 이 연결을 받기 시작하는 `run_daemon` 도 `build_context` 다음입니다. 따라서 규칙 오류로 부팅이 멈춰도 처리 중인 요청은 없습니다.

달라지는 점:

- 규칙 오류로 부팅이 멈추는 시점이 조금 늦어져, 다른 경고(node 없음 등)가 먼저 출력될 수 있습니다.
- `--connect`, `--setup`, `--onboard` 처럼 `build_context` 를 거치지 않는 경로는 규칙을 검증하지 않습니다. 이 경로들은 로컬에서 턴을 실행하지 않으므로 문제가 없습니다.
- 오류 문구 "the built-in prompt-injection rules did not compile" 은 config.toml 규칙도 포함하도록 고쳐야 합니다.

### 7.2 이름 변경

| 위치 | 현재 | 변경 |
| --- | --- | --- |
| tinicore `guardrails` | `baseline_rules` | `user_input_prompt_injection_rules` (권장안) |
| tinicli | `inbound_guard_config` | `prompt_guard_config` |
| tinicli | `compile_inbound_guard` | 없앰 (7.1) |

### 7.3 guardrails 기능 범위 축소 (tinicli)

- user input 쪽(`layer_on`, `prompt_guard_config`, `gate()`/`GateDecision`)을 기능 밖으로 옮기고, `baseline_rules()` 호출에만 `#[cfg(feature = "guardrails")]` 를 겁니다.
- tool output 쪽(`to_core_config`)은 tinicore guardrails 타입을 쓰므로 기능 안에 남습니다.
- 기능이 없는 빌드에서의 동작이 바뀝니다. user input mode 오타는 부팅을 중단하고, `"on"` 이면 "내장 규칙이 이 빌드에 없다"는 경고와 함께 config 규칙만으로 실행합니다. tool output 키는 지금처럼 경고 후 무시합니다.

### 7.4 config.toml 추가 규칙 (두 레이어 모두)

```toml
user_input_prompt_injection_mode = "on"
tool_output_prompt_injection_mode = "on"

[[user_input_prompt_injection_rules]]
id = "ko_ignore_prior"
pattern = '(이전|앞의)\s*(지시|명령)(을|를)?\s*(무시|잊어)'
action = "block"            # block | warn

[[tool_output_prompt_injection_rules]]
id = "turn_context_forgery"
pattern = '(?i)</?turn-context\b'
label = "override"          # existing PromptInjectionLabel
action = "block"            # block | warn
```

- **형식:** config.toml 섹션으로 받습니다. YAML 파일은 보류합니다. tinicore 는 타입이 있는 규칙 목록 API 만 두고, 파싱은 host 가 맡습니다. argo-tizen 은 제품 규칙(`GuardRule`)을 같은 타입으로 넘기면 됩니다.
- **action:** block 과 warn 을 모두 허용합니다. tool output 의 warn 은 `tracing::warn!` 로그 한 줄이며, span 으로 보고하지 않아 차단하지 않습니다(`detector.rs:192-207`). warn 과 block 이 겹쳐도 block 이 적용됩니다.
- **user input:** `prompt_guard_config` 안에서 읽어 baseline 뒤에 붙입니다. 엔진은 `PromptGuardConfig` 로 빌드되므로 tinicore 변경이 필요 없습니다.
- **tool output:** tinicore 변경이 필요합니다. 부팅 때 내장 규칙과 추가 규칙을 `EngineConfig` 하나로 합쳐 `Arc` 로 보관하고, `SharedEngine` 이 `id → label` 표를 갖도록 합니다. 추가 규칙의 layer 는 `tool_output` 으로 고정합니다. `tool_output_prompt_injection_labels` 로 범위를 좁히는 기능은 추가 규칙에도 적용됩니다.
- **검증(부팅 중단):** 내장 규칙과 같거나 서로 중복된 id, 알 수 없는 action·label, 컴파일되지 않는 패턴. mode 가 `"off"` 인데 규칙 섹션이 있으면 경고 후 무시합니다.
- **주의:** 두 엔진 모두 ASCII 모드라 `\s`, `\b`, `(?i)` 가 ASCII 기준이고 lazy 수량자가 greedy 처럼 동작합니다. 비ASCII 문자 클래스에는 `(?u)` 가 필요합니다. config 문서에 반드시 적어야 합니다.

### 7.5 prompt injection 규칙 파싱 결과의 상주 제거

prompt injection 쪽은 파싱한 규칙을 프로세스가 끝날 때까지 보관하지만, PII 는 엔진을 빌드한 직후 파싱 결과를 버립니다.

| | prompt injection | PII |
| --- | --- | --- |
| 원본 YAML | `include_str!` 상수 | 같음 |
| 파싱 결과 보관 | **예.** `static RULES: LazyLock<Vec<Rule>>`(`prompt_injection/mod.rs:232`) 가 처음 접근할 때 파싱하고 프로세스 끝까지 보관 | **아니요.** `compile_from_yaml` 이 엔진을 빌드한 뒤 `EngineConfig` 를 버림(`pii/shared.rs:22-24`) |
| 엔진 빌드 | 턴마다 YAML 을 다시 파싱해서 빌드(`prompt_injection/shared.rs:28`) | 같음 |
| 엔진 수명 | turn slot (턴이 끝나면 해제) | 같음 |

- 엔진 빌드는 `RULES` 를 쓰지 않습니다. `RULES` 를 쓰는 곳은 `SharedEngine::new`(규칙 순서·action·layer 표 생성)와 `baseline_rules()` 두 곳뿐이며, 둘 다 부팅 때 한 번씩 호출됩니다.
- 상주 크기는 규칙 11개 남짓, 패턴 문자열 약 3.2 KB 에 `RecognizerConfig` 의 다른 필드가 더해져 **수 KB 로 추정**합니다(측정하지 않음).
- **할 일:** `LazyLock` 을 없애고 필요할 때 `parse_rules(RULES_YAML)` 을 호출해 PII 와 같은 방식으로 맞춥니다. 호출은 부팅 때 두세 번이라 파싱 비용은 문제가 되지 않습니다. `SharedEngine` 이 가진 규칙 표(id·action·layer)는 tool output 가드레일이 매치를 처리할 때 필요하므로 남깁니다.
- **7.4 와의 관계:** tool output 추가 규칙을 "합친 `EngineConfig` 를 `Arc` 로 보관"하는 방식으로 구현하면 같은 성격의 상주 비용이 다시 생깁니다. PII 방식에 맞추려면 파싱 결과 대신 원본 문자열(내장 YAML, 추가 규칙의 패턴)만 보관하고, 턴마다 다시 파싱해 빌드한 뒤 버리도록 합니다.

### 7.6 작업 목록

| # | 작업 | 바뀌는 곳 | 규모 |
| --- | --- | --- | --- |
| 1 | 이름 변경 | tinicore, tinicli | 작음 |
| 2 | 기능 게이트 축소 (`gate()` 포함) + `compile_inbound_guard` 통합 | tinicli | 작음 |
| 3 | user input 추가 규칙 | tinicli | 작음 |
| 4 | tool output 추가 규칙 API + config 섹션 | tinicore(`SharedEngine`, label 표), tinicli | 중간 |
| 5 | `CoreConfig.prompt_guard` 문서 정정 | tinicore | 작음 |
| 6 | prompt injection `RULES` `LazyLock` 제거 (7.5) | tinicore | 작음 |
