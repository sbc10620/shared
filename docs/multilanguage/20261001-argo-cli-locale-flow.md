# ARGO CLI의 locale 처리 흐름 (main → config.toml → 사용처)

- 작성일: 2026-10-01
- 기준 코드: ARGO `origin/main` **908f35fbac** (2026-10-01, PR #3460 merge)
- 범위: `argo-cli` → `tinicli` → `tinicore`. argo-pc, Android(`tiniffi`), argo-tizen은 다루지 않습니다.
- 모든 `파일:줄` 표기는 위 커밋 기준입니다. 작업 브랜치 `dev/byungchul.so/multilingual-support`는 `tinicli/src/config.rs`, `tinicli/src/context_builder.rs`, `tinicli/src/repl.rs`, `tinicore/src/prompt/build.rs`의 줄 번호가 다릅니다.

## 0. 요약

**`config.toml`의 `locale`은 "CLI가 직접 출력하는 문장"과 "도구·sub-agent"에만 적용됩니다. 메인 에이전트의 시스템 프롬프트(LLM 응답 언어)에는 적용되지 않습니다.**

- locale 값은 두 갈래로 나뉩니다.
  - **설정 locale:** `--locale` → `config.toml`의 `locale` → OS locale → `en-US` 순서로 정합니다. 프로세스 전역 `OnceLock`(`CLI_LOCALE`)에 한 번 저장합니다.
  - **기기 locale:** `config.toml`을 보지 않고 OS에서 직접 읽습니다. 메인 에이전트의 시스템 프롬프트가 턴마다 이 값을 다시 계산합니다.
- 이 차이 때문에 OS가 `en-US`이고 `config.toml`에 `locale = "ko-KR"`을 쓰면 결과가 섞입니다.
  - CLI 화면 문구, `ask_user` 결과 문구, sub-agent: 한국어 기준으로 동작합니다.
  - 메인 LLM 응답: 영어 기준 지시(`## Output Language & Tone`)를 받습니다.
- 번역 카탈로그는 정확히 같은 태그만 찾습니다. 그래서 `locale = "ko"`처럼 국가 부분을 생략하면 UI 문구가 영어로 나옵니다 (4절).
- guardrails(PII, prompt injection)는 locale을 탐지에 쓰지 않습니다. 입력을 차단했을 때 보여 주는 안내 문구를 번역할 때만 씁니다.

## 1. 전체 호출 트리

```
argo-cli/src/main.rs:10  fn main()
└─ tinicli::run_cli()                              tinicli/src/lib.rs:202
   └─ cli_entry::run()                             tinicli/src/cli_entry.rs:150
      │
      ├─ (operator 하위 명령 분기, --smoke)         cli_entry.rs:221-351
      │     번역 문구를 쓰지 않으므로 locale과 무관
      │
      ├─ [A] config.toml 읽기
      │   ├─ default_config_path()                 tinicli/src/config.rs:1687  → ~/.argo/config.toml
      │   ├─ load_config(path)                     config.rs:1463
      │   │     CliConfig.locale: Option<String>   config.rs:75
      │   └─ cli.locale 이 있으면 cfg.locale 덮어씀   cli_entry.rs:377-379
      │         (--locale 옵션 정의: tinicli/src/cli.rs:159)
      │
      ├─ guardrails 설치 (install_guardrails_from_config)  cli_entry.rs:415-482
      │     PiiConfig 에 locale 없음. locale 결정보다 먼저 실행됨
      │
      ├─ [B] init_cli_locale(cli.locale.or(cfg.locale))   cli_entry.rs:507
      │   └─ resolve_with_override(user_override)         tinicli/src/i18n.rs:81
      │       ├─ OS locale: locale_native::current_locale() → LANG → LC_ALL
      │       └─ tinicore::i18n::resolve_locale_policy(user_override, None, Some(os))
      │                                                     tinicore/src/i18n/resolve.rs:56
      │       결과 → CLI_LOCALE (OnceLock)                  tinicli/src/i18n.rs:35
      │       읽기 → cli_locale_policy()                    tinicli/src/i18n.rs:70
      │
      ├─ [C] 설정 locale 사용처 ── 3절
      │   ├─ CLI 문자열 t!(..., cli_locale_policy())
      │   └─ build_context() → ctx.locale_policy          tinicli/src/context_builder.rs:1846
      │       ├─ ask_user / tone_update / sub_agent 문구
      │       └─ sub-agent 시스템 프롬프트 (build_kind_config)
      │
      └─ [D] 기기 locale 사용처 ── 5절
          REPL/TUI/daemon cron 과 gateway handler(daemon 웹 채팅·ACP)가
          AgentLoopConfig.locale_policy = None 으로 agent_loop 호출
          └─ agent_loop → … → gather_sections()
              └─ resolve_locale_policy(None, None, Some(&device.locale))
                  └─ 메인 시스템 프롬프트의 ## Output Language & Tone
```

## 2. config.toml에서 locale을 읽고 결정하는 과정

### 2.1 진입점

| 순서 | 위치 | 하는 일 |
|---|---|---|
| 1 | `argo-cli/src/main.rs:10` `main()` | 제품 확장을 등록하고, 8 MiB 스택 스레드에서 Tokio 런타임으로 `tinicli::run_cli()`를 실행합니다 |
| 2 | `tinicli/src/lib.rs:202` `run_cli()` | `cli_entry::run()`을 호출하기만 합니다 |
| 3 | `tinicli/src/cli_entry.rs:150` `run()` | 인자 파싱, 설정 읽기, guardrails 설치, locale 결정, 실행 모드 분기를 모두 이 함수가 합니다 |

### 2.2 config.toml 읽기

| 위치 | 내용 |
|---|---|
| `config.rs:1687` `default_config_path()` | `~/.argo/config.toml`을 돌려줍니다. `--config <경로>`를 주면 그 경로를 씁니다 (`cli_entry.rs:354-357`) |
| `config.rs:1463` `load_config()` | 파일이 없거나 읽지 못하면(권한 오류, 크기 상한 초과 포함) 아무 메시지 없이 `CliConfig::default()`를 돌려줍니다 (`:1464-1467`). TOML 파싱에 실패하면 `warning: failed to parse config at …`를 stderr에 출력하고 역시 기본값을 돌려줍니다. 두 경우 모두 `locale`은 `None`이 됩니다 |
| `config.rs:75` `CliConfig.locale` | `#[serde(default)] pub locale: Option<String>`. `config.toml`의 **최상위** 키이므로 첫 번째 `[섹션]` 헤더보다 위에 써야 합니다 |
| `cli.rs:159` `Cli.locale` | `--locale <TAG>` 옵션입니다 |
| `cli_entry.rs:377-379` | `--locale`이 있으면 `cfg.locale`을 그 값으로 덮어씁니다 |

**설정 예시:**
```toml
locale = "ko-KR"

[auth]
# ...
```

### 2.3 locale 결정 (`init_cli_locale`)

`cli_entry.rs:507`에서 `init_cli_locale(cli.locale.as_deref().or(cfg.locale.as_deref()))`를 호출합니다. 377행에서 이미 `cfg.locale`을 덮어썼으므로, 실제로는 `cfg.locale` 하나만 넘기는 것과 결과가 같습니다.

| 위치 | 내용 |
|---|---|
| `tinicli/src/i18n.rs:56` `init_cli_locale()` | `CLI_LOCALE.set(...)`을 호출합니다. 이미 값이 있으면 아무 일도 하지 않습니다 |
| `tinicli/src/i18n.rs:81` `resolve_with_override()` | OS locale을 `sys_locale::get_locale()` → `LANG` → `LC_ALL` 순서로 읽습니다. `.UTF-8` 같은 접미사를 떼고 `_`를 `-`로 바꿉니다. 그다음 tinicore resolver를 호출합니다. manifest 인자는 `None`입니다 |
| `tinicore/src/i18n/resolve.rs:56` `resolve_locale_policy()` | `resolve_inner()`(`:96`)가 사용자 지정 값 → manifest → 기기 값 → `english_internal()`(`en-US`) 순서로 처음 파싱되는 값을 고릅니다. 결과에는 출처(`LocaleSource::UserOverride`, `Device`, `Fallback` 등)가 함께 기록됩니다 |
| `resolve.rs:128` `parse_tag()` | 앞뒤 공백을 지우고 `_`를 `-`로 바꾼 뒤 `unic_langid::LanguageIdentifier`로 파싱합니다. 빈 문자열이나 파싱 실패는 "값 없음"으로 취급합니다 |
| `tinicli/src/i18n.rs:70` `cli_locale_policy()` | 이후 모든 사용처가 이 함수로 값을 읽습니다. `init_cli_locale`보다 먼저 호출되면 OS locale만으로 값을 정해 버립니다 |

**잘못된 값의 처리:** 오류나 경고는 없습니다. 결과는 값이 BCP-47 형식으로 파싱되는지에 따라 갈립니다.
- **형식상 파싱되는 값:** `unic-langid` 0.9.6은 2~3자 또는 5~8자 알파벳을 언어 subtag로 받습니다 (`unic-langid-impl-0.9.6/src/subtags/language.rs:15`). 그래서 `"korean"`, `"kr"`, `"jp"` 같은 오타도 파싱에 성공하고, `UserOverride`로 고정됩니다. 그러면 UI 문구는 영어로 나오고(4절), sub-agent 프롬프트의 언어 이름은 `the user's communication language`가 됩니다. OS locale로 넘어가지 않습니다.
- **파싱되지 않는 값:** `"ko_KR.UTF-8"`(`.` 때문), `"!@#"`, 4자 언어처럼 형식이 깨진 값만 무시되고 OS locale로 넘어갑니다.
- `i18n.rs:51-55`의 주석은 `"korean"`을 "넘어가는 예"로 들지만, 위 이유로 사실과 다릅니다. `:154` 테스트는 `"not-a-real-locale-tag-zzz"`(한 글자 subtag `a` 때문에 실패)만 확인합니다.

**`i18n` feature:** tinicore의 기본 feature에 포함되어 있습니다 (`tinicore/Cargo.toml:117`). `argo-cli/Cargo.toml:77`은 tinicore를 `default-features = false`로 가져오지만, `tinicli/Cargo.toml:166`이 기본 feature를 그대로 가져오므로 feature 통합으로 argo-cli에서도 켜집니다. 이 feature가 꺼진 빌드에서는 `resolve_locale_policy()`가 항상 `en-US`를 돌려주고 (`tinicore/src/i18n/mod.rs:120`), `t!`는 메시지 ID를 그대로 돌려줍니다 (`tinicore/src/lib.rs:313`).

### 2.4 `init_cli_locale`보다 먼저 실행되는 코드

- operator 하위 명령(`op`, `skills`, `marketplace`, `auth`, `service`, `hub`, `mesh`, `impact`)과 `--smoke`는 507행보다 먼저 분기해서 종료합니다 (`cli_entry.rs:221-351`).
- 이 경로와 해당 모듈(`commands_operator.rs`, `commands_*.rs`, `smoke.rs`)에는 `t!`나 `cli_locale_policy()` 호출이 없습니다. 따라서 이 경로들은 locale과 관계가 없고, `OnceLock`을 먼저 채우는 문제도 일어나지 않습니다.
- guardrails 설치(`cli_entry.rs:415-482`)도 507행보다 먼저 실행됩니다. 설치 과정의 오류 메시지는 번역하지 않은 영어 문자열입니다.

## 3. 설정 locale(`CLI_LOCALE`)을 쓰는 곳

### 3.1 CLI가 직접 출력하는 문자열

모두 `tinicore::t!(메시지_ID, cli_locale_policy())` 형태입니다.

| 위치 | 출력 내용 |
|---|---|
| `cli_entry.rs:562-566` | `--setup`의 배너와 의존성 점검 보고 (`commands::format_bootstrap_report`, `commands.rs:203`) |
| `run_onboarding.rs:15` | 초기 설정 wizard (`--onboard`) |
| `commands.rs:408` | `--doctor` 출력 (`doctor()`, `:405`) |
| `daemon.rs:171-511` | daemon 시작, cron 주기, 종료 안내 |
| `slash_commands/builtins.rs:124` | `/help` 명령 설명 |
| `tui/ui.rs` (403, 481, 583, 659, 716, 881행), `tui/app.rs` (172, 244, 260, 419행), `tui/event.rs:715` | TUI 화면 문자열, 상태 표시줄 |
| `repl.rs:495-498`, `run_tui.rs:488-491` | PII guardrail이 입력을 차단했을 때의 안내 (`pii-admission-blocked`) |
| `guardrails/prompt_injection.rs:173-177` | prompt injection guardrail이 입력을 차단했을 때의 안내 (`prompt-injection-blocked`) |

guardrails 쪽 사용처는 마지막 두 줄뿐입니다. 탐지 로직에는 locale이 들어가지 않습니다.

### 3.2 `RuntimeContext.locale_policy`를 거쳐 tinicore로 가는 값

`context_builder.rs:1846` (`build_context()` 안, 함수 시작은 `:553`):
```rust
ctx.locale_policy = Some(crate::i18n::cli_locale_policy().clone());
```

`build_context()`는 에이전트가 필요한 모든 경로에서 호출됩니다: `--doctor`(`cli_entry.rs:556`), daemon(`:711`), ACP(`:753`), `-p`·REPL(`:801`), 전체 TUI(`:920`). 이 값을 쓰는 곳은 다음과 같습니다.

| 위치 | 용도 |
|---|---|
| `tinicore/src/context.rs:2117` `locale_policy_or_default()` | `ctx.locale_policy`가 없으면 `en-US`를 돌려주는 도우미 함수입니다 |
| `tools/builtins/ask_user.rs:536` | 사용자가 질문을 취소하거나 답 없이 진행했을 때 LLM에게 돌려주는 결과 문구 |
| `tools/builtins/tone_update.rs:159` | 말투 설정을 적용했거나 되돌렸다는 결과 문구 |
| `tools/builtins/sub_agent.rs:3614`, `:3899` | sub-agent가 취소되었을 때의 PARTIAL 요약 문구 등 |
| `agent/kind_executor.rs:258-264` `build_kind_config()` | sub-agent의 locale을 정합니다. 우선순위는 sub-agent 종류가 고정한 값(`locale_policy_override()`) → `ctx.locale_policy` → `en-US`입니다. 이 값으로 `i18n_section()`을 만들어 sub-agent 시스템 프롬프트 끝에 붙이고, `:331`에서 `config.locale_policy`에도 넣습니다 |
| `tools/builtins/sub_agent.rs:2699`, `agent/parallel.rs:133` | `build_kind_config()`를 호출하는 곳입니다 |
| `agent/sub_agent_context.rs:991-995` | sub-agent의 `RuntimeContext.locale_policy`도 같은 우선순위로 부모 값을 물려받습니다. 그래서 중첩된 sub-agent에도 값이 전달됩니다 |

## 4. 번역 카탈로그 조회 방식

`t!` 매크로(`tinicore/src/i18n/macros.rs:60`)는 `bundle::t()`(`tinicore/src/i18n/bundle.rs:299`)를 호출합니다.

- **카탈로그:** `tinicore/i18n/*.ftl` 13개를 `include_str!`로 바이너리에 넣습니다 (`bundle.rs:65-84`). 태그는 `en-US`, `ko-KR`, `ja-JP`, `zh-CN`, `zh-TW`, `es-ES`, `fr-FR`, `de-DE`, `pt-BR`, `ru-RU`, `vi-VN`, `ar-SA`, `he-IL`입니다.
- **저장 구조:** `HashMap<LanguageIdentifier, Vec<Bundle>>`이며, 위 태그 문자열을 그대로 키로 씁니다 (`bundle.rs:87-111`).
- **조회 순서:** `lookup_chain()`(`bundle.rs:342`)은 `[policy.tag, en-US]`를 돌려줍니다. 각 태그로 `HashMap::get`을 호출하고, 메시지가 없으면 다음 태그로 넘어갑니다. 둘 다 없으면 메시지 ID를 그대로 돌려줍니다.
- **정확히 같은 태그만 찾습니다.** 조회 경로 어디에도 `ko` → `ko-KR` 같은 언어 단위 대체나 협상 단계가 없습니다. `parse_tag()`도 `_`→`-` 변환만 합니다. 따라서 다음 값은 모두 영어 문구로 나옵니다.
  - `locale = "ko"`, `"ja"`처럼 국가 부분을 생략한 값
  - `locale = "zh-Hant-TW"`처럼 script가 들어간 값 (카탈로그 키는 `zh-TW`)
  - `locale = "en-GB"`, `"es-MX"`처럼 카탈로그에 없는 국가 조합

  그런데 `config.rs:63-64`의 doc 주석은 `"ja"`, `"zh-Hant-TW"`를 예시로 듭니다. 이 결론은 코드를 읽고 내린 것이며, 실행해서 확인하지는 않았습니다.
- 시스템 프롬프트의 `i18n_section()`은 언어 이름을 직접 만듭니다 (`display_language_label`). 말투 지시(register micro-prompt)는 `t!`를 쓰지만, 메시지 ID를 언어 subtag(`ko`)로만 만들고 항상 `en-US` 카탈로그에서 찾습니다 (`prompt/i18n_section.rs:164-166`). 그래서 `ko`나 `zh-Hant-TW`에서도 동작하고, 이 문제는 UI `t!` 문구에만 해당합니다.
- OS에서 온 값도 같은 문제를 겪을 수 있습니다 (추론, 실행 확인 안 함). macOS의 `sys-locale`은 선호 언어 목록에서 값을 가져오므로 `zh-Hans-CN`이나 `en-KR`처럼 카탈로그 키와 다른 태그를 돌려줄 수 있습니다.

## 5. 기기 locale을 쓰는 곳: 메인 에이전트 시스템 프롬프트

### 5.1 tinicli가 `locale_policy`를 넘기지 않음

| 위치 | 내용 |
|---|---|
| `repl.rs:620`, `:662` | REPL 턴의 `AgentLoopConfig`. `locale_policy: None`이며, 주석은 "re-resolves locale from device per turn; no override pinned here"입니다 |
| `run_tui.rs:575`, `:608` | TUI 턴. `locale_policy: None` |
| `daemon.rs:1175`, `:1237` | daemon의 cron routine이 실행하는 LLM action. `locale_policy: None` |
| `tinicore/src/gateway/handler.rs:814`, `:843` (`handle_message_core()`, `:600`) | daemon의 HTTP gateway(`tinicli/src/gateway.rs:581`, `:637`), WebSocket(`websocket.rs:418`), 세션(`daemon_sessions.rs:504`), ACP(`acp.rs:1244`) 턴이 모두 이 handler를 거칩니다. `locale_policy: None`이며, 주석은 "gateway-driven loops resolve locale from device locale at gather_sections time"입니다. gateway 요청 타입에도 locale 필드가 없습니다 |
| `repl.rs:272` | harness dream proposer 템플릿. `..Default::default()`이므로 역시 `None`입니다 |
| `daemon.rs:1509` | sub-agent 실행용 기본 config. `..Default::default()`이지만, `build_kind_config()`가 3.2절의 규칙으로 `locale_policy`를 다시 채웁니다 |

### 5.2 tinicore의 프롬프트 빌드 경로

```
agent_loop()                                tinicore/src/agent/loop_.rs:1428
└─ prompt::build_init_context()             호출 loop_.rs:2717, 정의 prompt/build.rs:2131
   └─ build_scope_context()                 호출 build.rs:2250, 정의 :237
      └─ build_scope_context_inner()        호출 build.rs:259, 정의 :438
         ├─ gather_sections(…, config.locale_policy.clone())   build.rs:483-513
         │   └─ locale_policy_override.unwrap_or_else(||
         │        resolve_locale_policy(None, None, Some(&device.locale)))
         │                                  build.rs:5812-5818 (omit_argo_md 경로는 :5776)
         └─ PromptConfig {                  build.rs:1376
              reply_language_query: match_query 일 때만 마지막 사용자 문장,   :1420
              locale_policy: Some(locale_policy),                              :1425 }
            └─ PromptBuilder::assemble()    prompt/builder.rs:774
               ├─ i18n_section(policy)      builder.rs:905-906 → prompt/i18n_section.rs:36
               └─ reply_language_section()  builder.rs:1276 (reply_language_query 가 있을 때)
```

- `config.locale_policy`가 `None`이므로 `gather_sections()`는 **턴마다** 기기 locale로 값을 다시 계산합니다. user override 인자에는 `None`을 넘깁니다. 주석은 "wired in a later phase"라고 적혀 있습니다.
- 기기 locale은 `tinicli/src/adapters/device.rs:28`의 `DeviceContext.locale`이며, `resolve_locale()`(`:133`)이 `sys_locale` → `LANG` → `LC_ALL` → `en_US.UTF-8` 순서로 읽습니다. `config.toml`은 보지 않습니다.
- `i18n_section()`이 만드는 `## Output Language & Tone` 섹션은 LLM에게 세 가지를 지시합니다.
  - 내부 추론, 도구 인자, sub-agent 프롬프트는 영어로 씁니다.
  - 사용자에게 보이는 최종 답변과 `argo_ask_user` 질문은 locale의 언어로 씁니다.
  - 한국어 존댓말처럼 언어별 말투(register) 지시를 덧붙입니다 (`locale_register_microprompt`).
- `match_query`(`und`) 정책일 때만 "사용자가 마지막에 쓴 언어로 답하라"는 지시와 `## Reply Language` 섹션이 추가됩니다. tinicli는 코드에서 `match_query` 정책을 만들지 않으므로, 메인 프롬프트에서는 이 분기가 실행되지 않습니다. 다만 사용자가 `locale = "und"`라고 쓰면 그 값이 정상적으로 파싱되어, sub-agent 프롬프트에서는 이 분기가 실행됩니다.

### 5.3 `context` 도구

`tools/builtins/context.rs:96-100`은 LLM에게 기기 정보를 돌려줄 때 `resolve_locale_policy(None, None, Some(&device.locale))`로 만든 locale을 넣습니다. 이 값도 기기 locale입니다.

## 6. 일관되지 않은 부분

| # | 내용 | 근거 |
|---|---|---|
| 1 | 메인 에이전트 프롬프트는 기기 locale을 쓰고, 도구 문구와 sub-agent는 설정 locale을 씁니다. `context_builder.rs:1839-1845` 주석은 "tools … see the same locale the prompt builder uses"라고 말하지만 실제 동작과 다릅니다 | 3.2절, 5.1절 |
| 2 | `config.toml`의 `locale`이 메인 LLM의 응답 언어를 바꾸지 못합니다. REPL, TUI뿐 아니라 daemon 웹 채팅과 ACP도 마찬가지입니다. `config.rs:63-69`의 doc 주석은 "forwarded to the agent loop as the user-override slot"이라고 설명하지만, 그렇게 연결된 코드가 없습니다 | 5.1절 |
| 3 | 국가 부분이 없는 태그(`ko`, `ja`)나 script가 들어간 태그(`zh-Hant-TW`)는 UI 문구가 영어로 나옵니다 | 4절 |
| 4 | OpenAI content filter 차단 문구는 항상 `en-US`입니다. `state.locale_policy`를 채우는 코드가 없기 때문입니다 (`llm/providers/openai.rs:1480-1489`, 주석 "no caller plumbs it yet") | — |
| 5 | 잘못된 `locale` 값에 경고가 없습니다. `"korean"`, `"kr"` 같은 오타는 OS locale로 넘어가지도 않고 그대로 고정되어, UI가 영어로 나옵니다 | 2.3절 |
| 6 | `--locale`을 한 번만 주고 실행해도, 그 실행 중에 `--import-env`(`cli_entry.rs:628`), `--onboard`(`run_onboarding.rs:81`, `:89`), TUI `/save`(`run_tui.rs:407-410`)로 설정을 저장하면 `locale`이 `config.toml`에 기록됩니다. `--provider`, `--model` 등 다른 명령줄 옵션도 같은 방식이라, `locale`만의 문제는 아닙니다 | 2.2절 |

**1번과 2번을 고치는 방법:** 두 곳을 고쳐야 합니다.
- **tinicli:** REPL, TUI, daemon cron의 `AgentLoopConfig`에 `locale_policy: Some(cli_locale_policy().clone())`을 넘깁니다. 각 위치에서 한 줄씩만 바꾸면 됩니다.
- **tinicore:** gateway handler(`handler.rs:843`)는 tinicore 안에서 config를 만들므로 tinicli에서 고칠 수 없습니다. handler나 `gather_sections()`가 `ctx.locale_policy`를 대체값으로 쓰게 바꿔야 합니다. 이 변경은 tinicore를 쓰는 다른 gateway 호스트에도 영향을 줍니다.

다만 이렇게 하면 사용자가 locale을 지정하지 않았을 때도 값이 프로세스 시작 시점에 고정됩니다. 따라서 "턴마다 기기 locale을 다시 읽는다"는 현재 동작이 바뀝니다. 데스크톱 CLI에서는 영향이 거의 없지만, 변경할 때 확인해야 합니다.

## 7. PII 다국어 지원과의 관계

- 위 경로는 모두 **출력 언어**만 다룹니다. guardrails의 recognizer 선택에 locale을 쓰는 곳은 없습니다.
- guardrails 설치(`cli_entry.rs:415-482`)는 locale 결정(`:507`)보다 먼저 실행됩니다. 현재 논의 중인 PII 전용 옵션(`pii_locales`, 이 커밋에는 아직 없음)은 `cfg`에서 바로 읽으므로 이 순서의 영향을 받지 않습니다. 나중에 `locale`의 국가 부분을 PII 기본값으로 쓰려면, 설치 시점에 `cfg.locale`을 직접 파싱하거나 locale 결정을 설치보다 앞으로 옮겨야 합니다.
- `locale`에서 국가 코드를 꺼낼 때는 `LocalePolicy.tag.region`을 씁니다. `locale = "ko"`처럼 국가 부분이 없으면 이 값은 비어 있습니다.
