# argot-daemon 에 PII 가드레일 배선하기

## Context

### 왜 지금 이 일을 하나

ARGO 쪽에서 PII 가드레일(`tinicore/src/guardrails` 의 정규식/DFA 엔진 + `agent/pii_masking` 의
마스킹 파이프라인)이 PR #3252 로 머지됐다. argo-tizen 의 `tini/` 는 그 tinicore 를 벤더링하고
있고, PII 관련 소스는 **이미 100% 동기화되어 있다**(`src/guardrails`, `src/sensitive`,
`src/agent` 전부 diff 0). 즉 **코드는 이미 트리 안에 있는데 아무도 쓰지 않는 상태**다.

실측으로 확인한 현재 상태:

```
grep -rniE "guardrail|\bpii\b|install_sensitive_masking|run_input_guardrails" \
  crates/ platform/ libraries/
→ 0건
```

`crates/` 전체에 PII/가드레일 배선이 **하나도 없다.** 완전한 그린필드다.
(`sensitive` 로 잡히는 것들은 전부 무관한 `InteractionRequest.sensitive` 불리언 — 상호작용 UI
비밀번호 필드 마스킹용이다.)

그리고 이건 이미 문서화된 **알려진 공백**이다.
[`project/docs/design/daemon/agent-safety.md:259`](project/docs/design/daemon/agent-safety.md) 가
직접 이렇게 적어놨다:

> **Net:** content-level safety relies on the model's built-in safety and the on-device trust
> model, not prompt-level refusal guardrails — **a deliberate-by-inheritance state worth an
> explicit product decision.**

이 작업이 바로 그 "explicit product decision" 이다. 그래서 계획의 마지막 단계는 코드가 아니라
**그 문장을 사실에 맞게 고치는 것**이다.

### 무엇을 만드는가

`config.toml` 의 `[safety.pii].mode` 스위치 하나로 argot-daemon 이 PII를 탐지·차단·마스킹하게
만든다. 세 가지 모드:

| mode | 하는 일 |
|---|---|
| `off` (기본) | 아무것도 안 함. 오늘과 동일. |
| `block_only` | 입력 게이트만. PII 가 든 사용자 메시지를 **DB 에 쓰기 전에** 거부. 마스킹 없음. |
| `full` | 입력 게이트 + 아웃바운드 마스킹. 클라우드로 나가는 요청에서 PII 를 placeholder 로 치환하고, 응답에서 되돌린다. |

이건 upstream `tinicli` 의 `PiiMode` 와 동일한 3단 구조다 (CLAUDE.md:206 "mirror upstream
ARGO/tinicli unless there is a deliberate Tizen-specific reason to diverge").

### 결정된 사항 (사용자 확인 완료)

**Cargo feature 로 옵트인한다.** `guardrails = ["tinicore/guardrails", "tinicore/sensitive"]`,
기본 OFF. 근거:

- 워크스페이스가 `Cargo.toml:96` 에서 tinicore 를 `default-features = false` + 명시 목록으로
  가져가고 있고, `Cargo.toml:108` 주석이 "keeps tinicore's bundled defaults out" 이라고 의도를
  명시한다. 여기에 얹으려면 그 의도에 반하지 않아야 한다.
- `a2a` / `sim-clock` 이 이미 "off by default in ordinary and shipping builds" 라는 같은 모양의
  선례다.
- CLAUDE.md:232 "features land as leaf additions or behind features."

---

## 반드시 알아야 할 사실 5가지 (실측)

### ① `sensitive` 와 `guardrails` **둘 다** 필요하다

`tini/tinicore/Cargo.toml`:

```toml
sensitive  = []                        # 의존성 0. 마스킹 씸 + AgentLoopConfig.sensitive 필드
guardrails = ["dep:regex-automata"]    # PII 정규식/DFA 엔진
```

`guardrails` 는 `sensitive` 를 **함의하지 않는다.** 그리고 `sensitive` 는 tinicore 의 default
목록에 있지만 argo-tizen 이 `default-features = false` 로 걷어냈기 때문에 **지금 꺼져 있다.**

→ `guardrails` 만 켜면 탐지기는 생기는데 아웃바운드 마스킹 게이트가 통째로 컴파일 아웃된다
(`llm/client.rs` 에 `cfg(feature = "sensitive")` 가 107곳). 사실상 무동작이다.
→ 현재 feature 목록(`sqlite`, `memory-lexical`, `llm-ollama`, `test-fixtures`,
`sub-agent-kinds`, `i18n`, `triage`, `fastpath`, `mcp`, `memory-tizentv`) 중 `sensitive` 를
켜는 것은 **하나도 없다**(확인함). `cognition` 이 켜지만 우리는 그걸 안 쓴다.

### ② `regex-automata` 는 이미 그래프에 있다 — 문제는 **feature 유니피케이션**이다

`regex-automata v0.4.14` 는 `regex`/`bstr`/`globset`/`matchers` 를 통해 이미 링크된다.
새 크레이트 컴파일은 없다. 하지만 루트 `Cargo.toml:173` 이 이렇게 선언돼 있다:

```toml
regex-automata = "0.4.14"      # ← default-features 제한 없음
```

`dep:regex-automata` 를 활성화하면 이 핀의 **full default** 가 켜지고, Cargo 의 feature
유니피케이션이 그걸 **그래프 전체에 전파**한다. 실측한 델타:

```
현재 ship 그래프          →  guardrails+sensitive 켰을 때 추가되는 것
────────────────────────────────────────────────────────────────
alloc, dfa-build,             + default
dfa-search, meta,             + dfa            ← dense/sparse 완전 DFA
nfa-pikevm, nfa-thompson,     + dfa-onepass
perf-literal*, std, syntax,   + hybrid
unicode-*                     + nfa, nfa-backtrack
                              + perf, perf-inline
```

이건 바로 루트 `Cargo.toml:170-172` 의 주석이 막으려던 그 현상이다:

> Keep product consumers aligned with the vendored runtime's slim feature set;
> workspace feature unification otherwise restores regex's full default engines.

**그런데 엔진이 실제로 쓰는 건 그 중 극히 일부다.** `tini/tinicore/src/guardrails/recognizer.rs:23-27`:

```rust
use regex_automata::hybrid::BuildError;
use regex_automata::hybrid::dfa::{self, Config as DfaConfig, DFA, OverlappingState};
use regex_automata::nfa::thompson;
use regex_automata::util::syntax;
use regex_automata::{Anchored, HalfMatch, Input, MatchKind};
```

`hybrid`(lazy DFA) + `nfa-thompson` + `syntax` 뿐이다. `dfa`(dense/sparse), `dfa-onepass`,
`nfa-backtrack`, `meta`, `perf` 는 **전혀 안 쓴다.**

→ **루트 핀을 좁히면 실질 델타가 `hybrid` 단 하나로 줄어든다.** (`nfa-thompson`/`syntax` 는
이미 켜져 있음). 이건 `tini/` 가 아니라 루트 `Cargo.toml` 수정이므로 벤더링 규칙에 안 걸린다.

### ③ argot-daemon 의 `AgentLoopConfig` 생성 지점은 정확히 **2곳**

| # | 위치 | 성격 |
|---|---|---|
| 1 | `crates/argot-daemon/src/turn/mod.rs:1593` (`resolve_dispatch_with_target`) | **범용 레일.** 대화형 채팅, cron/routine, 서브에이전트, telegram, A2A ingest, resume — 전부 여기를 지난다. |
| 2 | `crates/argot-daemon/src/boot/a2a.rs:435` (`build_a2a_config_factory`) | **`a2a` feature 전용**(기본 OFF). A2A-**served** 인바운드. `run_turn` 을 **거치지 않는 유일한 우회로.** |

`AgentLoopConfig::default()` 를 단독으로 만드는 곳은 없다.

> ⚠️ **주의 — 이름 충돌.** `argot_config::AgentLoopConfig`(`argot-config/src/lib.rs:767`)는
> config.toml 의 섹션 타입이고, `tinicore::agent::context::AgentLoopConfig` 와 **완전히 다른
> 타입**이다. 순진하게 grep 하면 대부분 전자가 잡힌다.

### ④ 가드레일 절반은 **전역이 아니라 per-run** 으로 넣는다

`GuardrailSet` 은 4층(`input` / `output` / `tool_input` / `tool_output`)이고, tinicore 에는
"per-run tool 체인은 tool orchestrator 가 안 읽어서 무력하다"는 유명한 함정이
(`agent/guardrails.rs:353-370`) 있다. **하지만 우리에게는 해당 사항이 없다** — PII 가 채우는
층은 `input` 하나뿐이기 때문이다. tinicli 소스가 두 곳에서 명시한다:

> `_OUTPUT`, `_TOOL_INPUT`, and `_TOOL_OUTPUT` remain untouched by the PII set
> (**this module never populates them**)  — `PII_INPUT_GUARDRAILS` doc
>
> **Only `_INPUT` is checked because only the `input` layer is affected**  — `install_pii` doc

실제 구성도 `GuardrailSet::new().with_input(chain)` **한 줄**이다.

**그리고 전역 install 은 오히려 해롭다 — 이유가 둘이다.** tinicli 는
`tinicore::install_guardrails` 를 **일부러 쓰지 않고** 크레이트 로컬 `OnceLock` 에 넣는다:

```rust
static PII_INPUT_GUARDRAILS: OnceLock<Option<GuardrailSet>> = OnceLock::new();
...
let _ = PII_INPUT_GUARDRAILS.set(guardrails);   // ← 가드레일 절반: 로컬
if !install_sensitive_masking(m) { ... }        // ← 마스킹 절반만 전역
```

doc 이 이유를 직접 밝힌다 — *"why the guardrail half is stored **locally rather than in
tinicore's own `install_guardrails` slot**"*.

**(a) 슬롯이 하나뿐이고 `OnceLock` 이라, 둘 중 하나가 조용히 증발한다.**
`install_guardrails_from_env` 도 내부에서 `install_guardrails(set)` 를 부른다
(`guardrails.rs:1166`) — **같은 `GLOBAL` 슬롯**이다. 그리고 그 함수는:

> Returns `false` (and changes nothing) if a set was already installed —
> **first-install wins**. **There is no way to replace or clear the set for the life of the
> process.**

덮어쓰기가 아니라 **먼저 온 쪽이 이기고 나중 쪽은 `tracing::warn!` 한 줄 남기고 사라진다:**

```
env 가 먼저 → PII install 실패 → PII 보호가 통째로 없음   ← fail-OPEN. 최악
PII 가 먼저 → env install 실패 → 운영자 규칙이 통째로 없음
```

**(b) 설령 슬롯을 잡아도, 층 해소(`pick_layer`)가 합집합이 아니라 교체다.**
per-run 세트가 있으면 전역 `input` 체인을 통째로 **밀어낸다.** tinicli 는 그 대신
`GlobalInputChainAdapter` 로 전역 체인을 **먼저** 돌리고 PII 를 두 번째로 돌리게
합성한다(`pii.rs:327`).

> 정확히 해두면 — argo-tizen 은 현재 `install_guardrails_from_env` 를 **부르지 않는다**
> (guardrails 흔적 0건). 그래서 전역을 써도 *오늘은* 동작한다. 로컬로 가는 이유는 그 씸을 미리
> 막지 않기 위함이고(`ProductPolicy.guard_rules` 가 자라날 자리), upstream 과 갈라지지 않기
> 위함이다.

→ 결론: **per-run 이 주 배선**이다. 전역 `install_guardrails` 는 쓰지 않는다.
→ 마스킹 절반(`install_sensitive_masking`)만 전역이다. 다른 슬롯이라 교체 문제가 없다(⑤).
→ 그래서 **5단계의 두 `AgentLoopConfig` 지점이 "중복 안전망"이 아니라 필수**다. 특히
A2A-served(`boot/a2a.rs:435`)를 빼먹으면 그 경로만 무방비가 된다.

### ⑤ 가드레일을 로컬에 둬도 **egress 마스킹은 영향받지 않는다** (검증함)

④의 설계에서 당연히 나오는 의문 — "가드레일 세트를 tinicore 전역에 안 넣으면 main-turn /
background LLM 의 egress 마스킹이 그걸 인지하나?" 코드로 확인했고, **답은 서로 무관하다**이다.
두 절반이 **다른 `OnceLock`** 을 쓴다:

```
agent/guardrails.rs:126    static GLOBAL:         OnceLock<GuardrailSet>       ← 우리가 안 씀
agent/pii_masking.rs:583   static GLOBAL_MASKING: OnceLock<SensitiveMasking>   ← 마스킹
```

마스킹 판정은 `GLOBAL_MASKING` **하나만** 읽는다. `GuardrailSet` 을 어디에 두든 쳐다보지 않는다.
세 경로 전부 `install_sensitive_masking` 하나로 덮이는 것을 확인했다:

| 경로 | 판정 지점 | 결과 |
|---|---|---|
| main turn | `loop_.rs:1445` `inherit_global_sensitive(&mut config)` — `config.sensitive` 가 `None` 이면 전역에서 복사 | ✅ 자동 |
| background | `pii_masking.rs:1540` → `client_must_mask()`. `AgentLoopConfig` 가 아예 관여 안 함 | ✅ 자동 |
| A2A served | `served.rs:489` `force_reveal_to(...)` — 내부에서 `inherit_global_sensitive` 를 먼저 호출 | ✅ 자동 |

핵심은 `client_must_mask()` 가 **fail-closed** 라는 점이다:

```rust
global_sensitive_masking().is_some() && EGRESS_MASKING.try_with(|_| ()).is_err()
```

> **Absence ⇒ mask** (fail-closed): a call path with no `EGRESS_MASKING` scope installed —
> which is **every background caller today, and any new one written tomorrow** — is masked by
> default.

즉 백그라운드 호출은 `AgentLoopConfig` 를 안 거쳐도, 앞으로 새로 생겨도 기본이 "마스킹함"이다.
전역 마스킹 슬롯만 채워져 있으면 된다.

**이 비대칭은 의도된 것이다:**

| | 저장 위치 | 소비 방식 |
|---|---|---|
| 가드레일 (입력 차단) | 크레이트 로컬 | **per-run 으로 명시 전달** — 빠뜨리면 무방비 |
| 마스킹 (egress) | 전역 `GLOBAL_MASKING` | **자동 상속** — 세 경로가 알아서 읽음 |

마스킹은 "못 빠뜨리게" 전역 + fail-closed 로 설계됐고, 가드레일은 운영자 체인과 공존해야 해서
per-run 이다.

---

## 따라야 할 선례 — `[safety.prompt_guard]`

이 저장소에 **똑같은 모양의 완성된 배선이 이미 있다.** 새로 설계하지 말고 이걸 그대로 복제한다.
리뷰어가 즉시 알아본다는 것 자체가 큰 이점이다.

| 단계 | prompt_guard 의 구현 | 우리가 만들 것 |
|---|---|---|
| config 섹션 | `argot-config/src/lib.rs:418` `SafetyConfig` → `:434` `PromptGuardSettings` → `:449` `PromptGuardMode` | `PiiSettings` / `PiiMode` 를 `SafetyConfig` 의 형제 필드로 |
| CoreConfig 접기 | `agent_config::apply_prompt_guard_mode` (`agent_config.rs:302`), 호출 `context_builder.rs:160` | `apply_pii_mode` 를 바로 옆에서 호출 |
| 부팅 시 컴파일 | `compile_pre_persist_prompt_guard` (`agent_config.rs:358`) | `install_pii` — 같은 자리, 같은 이유 |
| 사전-영속 게이트 | `turn/mod.rs:319` 컴파일 → `:155` 러너 필드 → `:515` `prompt_guard::evaluate` | `:515` 바로 뒤에 한 줄. **러너 필드는 안 만든다**(4단계) |
| 관측 | `fire_prompt_guard_event` (`turn/mod.rs:1654`) | `pii.match` 이벤트 |
| 거부 응답 | `send_prompt_guard_refusal` (`turn/mod.rs:1667`), 상수 `:111` | `PII_REFUSAL` 상수 |

`compile_pre_persist_prompt_guard` 의 doc 주석이 **부팅 시 검증**의 근거를 이미 써놨다 —
그대로 인용해서 쓴다:

> The mode is boot-frozen, so compiling here rather than per turn costs nothing live — and it
> turns a bad rule pattern into a **boot failure the operator sees immediately**, instead of a
> terminal error on every turn.

---

## 작업 계획

브랜치: `dev/byungchul.so/argot-pii-guardrails` — **이미 생성됨** (main `d536a81d` 에서 분기,
CLAUDE.md:291 형식). 워킹 트리 clean 확인 완료.

### 실행 순서와 중간 게이트

각 단계는 앞 단계의 검증이 통과해야 넘어간다. 특히 1단계의 컴파일 검증이 실패하면 나머지가
전부 무의미하므로 **거기서 멈추고 보고한다.**

```
1단계 ─ regex-automata 핀 좁히기
        └─ 게이트: cargo check -p tinicore --features guardrails,sensitive   ← 통과 못하면 정지
        └─ 게이트: cargo tree 로 dfa / nfa-backtrack / perf-inline 부재 확인
   ▼
2단계 ─ [safety.pii] 스키마 + patch 서술자 + reload 문자열
        └─ 게이트: cargo test -p argot-config
   ▼
3단계 ─ safety/mod.rs (shim) + safety/pii.rs (실체)
        └─ 선행: install_masking_policy vs install_sensitive_masking 판별
        └─ 게이트: cargo check -p argot-daemon --features guardrails
   ▼
4단계 ─ admission gate 한 줄 (turn/mod.rs:515 뒤)
        └─ 선행: turn/mod.rs:500-530 직접 읽기
   ▼
5단계 ─ AgentLoopConfig 2곳 + ratchet 테스트 2개
        └─ 게이트: 음성 테스트 (게이트 무력화 시 차단 테스트가 실제로 깨지는지)
   ▼
6~7단계 ─ CI lane + 문서
        └─ 최종 게이트: ./project/scripts/preflight.sh --full
```

**커밋은 하지 않는다.** 3개 커밋으로 나눌 계획은 아래에 있지만, 실제 커밋은 preflight 통과 후
사용자 확인을 받고 만든다.

### 1단계 — Cargo feature 와 의존성 핀

**`Cargo.toml`** (루트) — `regex-automata` 핀을 좁힌다. 이게 ②의 유니피케이션 폭발을 막는
핵심이고, 반드시 feature 를 켜기 **전에** 들어가야 한다:

```toml
# The guardrails PII engine uses the lazy (hybrid) DFA only — see
# tinicore/src/guardrails/recognizer.rs. Taking the crate's defaults here would
# unify `dfa` / `dfa-onepass` / `nfa-backtrack` / `perf` onto the whole graph,
# re-inflating the very engines the `regex` pin above keeps out.
regex-automata = { version = "0.4.14", default-features = false, features = [
    "std", "syntax", "hybrid", "nfa-thompson", "unicode",
] }
```

> ⚠️ **이 feature 목록은 검증 전 추정치다.** `recognizer.rs` 의 `use` 문에서 뽑았는데,
> `filter.rs`(18 KB)와 `detector.rs`(55 KB)는 심볼 스윕을 안 했고 완전수식 경로는 `use` 에
> 안 잡힌다. `MatchKind` / `Anchored` 는 크레이트 루트에 있어 `dfa` 를 끌 수도 있다.
> **핀을 좁힌 상태에서 반드시 먼저 컴파일을 통과시킨다:**
>
> ```bash
> cargo check -p tinicore --features guardrails,sensitive
> ```
>
> 실패하면 에러가 지목하는 것만 **최소로** 넓힌다. 추측으로 넓히지 않는다.
> 그리고 이 핀은 **바닥이지 천장이 아니다** — `regex` 가 이미 `dfa-build`/`dfa-search`/`meta`
> 를 그래프에 올리므로, 6단계의 CI 단언은 `dfa`(dense/sparse) / `dfa-onepass` /
> `nfa-backtrack` / `perf-inline` 의 **부재만** 검사해야 한다. `dfa-search` 부재를 단언하면
> 오늘의 그래프에서도 실패한다.

**`crates/argot-daemon/Cargo.toml`** — `telemetry = [..., "tinicore/otel"]`(`:154`)이 이미
증명한 패턴 그대로. `a2a` / `sim-clock` 의 형제로 둔다:

```toml
# PII guardrails: the vendored engine's detector (`guardrails`) plus the masking
# seam it feeds (`sensitive`). Both ride this feature rather than the workspace
# tinicore edge, so an ordinary or shipping build carries neither. Off by
# default like `a2a` and `sim-clock`; `[safety.pii].mode` still defaults to
# `off` even in a build that opts in.
guardrails = ["tinicore/guardrails", "tinicore/sensitive"]
```

**`crates/argot/Cargo.toml`** — `argot` 에서 포워딩(telemetry 가 `:29` 에서 하는 것과 동일).

### 2단계 — config 스키마

**`crates/argot-config/src/lib.rs`** — `SafetyConfig`(`:418`) 에 `pii` 필드 추가 +
`PiiSettings` / `PiiMode` 를 `PromptGuardSettings`/`PromptGuardMode` 와 같은 모양으로.
`#[serde(default, skip_serializing_if = ...)]`, `PiiMode::Off` 가 `#[default]`.

`PiiSettings` 는 **필드 둘을 가진 하나의 섹션**이다 — 별도 섹션을 만들지 않는다:

```rust
pub struct PiiSettings {
    // 스칼라가 먼저. 아래 ⚠️ 참조.
    #[serde(default, skip_serializing_if = "PiiMode::is_off")]
    pub mode: PiiMode,
    /// Tool wire name → argument paths to un-mask before execution.
    /// Only effective when `mode = "full"`.
    #[serde(default, skip_serializing_if = "HashMap::is_empty")]
    pub demask_tool_args: HashMap<String, Vec<String>>,
}
```

**`default_config.toml` 에는 주석 처리된 인라인 예시를 둔다:**

```toml
[safety.pii]
# off (default) | block_only | full
# mode = "full"

# Tool arguments to un-mask right before the tool runs. In `full` mode the model
# only ever sees `[SENS:PII:…]` placeholders, so a tool that must act on the real
# value needs its argument listed here. Everything upstream — hooks, the approval
# prompt, the broker's audit trail — still sees the placeholder.
# demask_tool_args = { bash_run = ["command"] }
```

`bash_run` 을 예시로 고른 이유: (a) 에이전트가 사용자 데이터를 담은 셸 명령을 조립하는 건 이
기능이 필요해지는 가장 흔한 상황이고, (b) `bash_run` 은 `ApprovalMode::Never`
(`tools/mod.rs:520`) 라 **주석을 풀어도 승인 충돌 검사에 안 걸린다.** 예시는 그대로 켜도 부팅이
깨지지 않아야 한다 — `file_write` 를 예시로 썼다면 `[interactions]` 켠 사용자가 복사하는 순간
부팅이 실패한다.

> ⚠️ **다만 이 예시에는 경고를 붙인다.** argot 의 `bash_run` 은 **컨테인먼트가 없다**
> (`security-boundary.md:173` — *"`working_dir` honored verbatim — **no containment**"*).
> `command` 를 demask 한다는 건 임의 셸 명령에 평문 PII 가 주입된다는 뜻이므로, 주석에
> "실행되는 명령 전체가 실값을 보게 된다"는 한 줄을 같이 적는다. 예시가 가르치는 것이
> 기본값이 되므로, 무엇을 감수하는지 모르고 켜게 두지 않는다.

TOML 은 같은 필드를 서브테이블로도 표기할 수 있고(`[safety.pii.demask_tool_args]`) 파서는 둘 다
받지만, **서브테이블 표기에는 함정이 있다** — 헤더 뒤의 모든 키가 그 테이블 소속이라 운영자가
나중에 `mode = "full"` 을 아래쪽에 추가하면 **조용히 `demask_tool_args` 안으로 들어간다.**
인라인은 이 사고가 구조적으로 불가능하다. 우리가 쓰는 예시는 인라인으로 통일하고, 손으로
서브테이블을 쓴 설정도 깨지지 않으므로 파싱 테스트는 **두 표기 모두** 커버한다.

> ⚠️ **필드 순서 제약.** `save()`(`lib.rs:2103`)가 `toml::to_string_pretty(self)` 로 config 를
> 되쓴다. TOML 직렬화는 **스칼라를 테이블보다 먼저** 내보내야 하므로 `mode` 가
> `demask_tool_args` **앞**이어야 한다. 선례는 바로 옆 `MemoryConfig`(`enabled: bool` →
> `consolidation: 중첩`). 순서를 지키고, **기본값이 아닌 값으로 채운 config 의 save→load
> 왕복 테스트**로 고정한다 — `skip_serializing_if` 가 기본값을 빼주는 바람에 문제가 가려질 수
> 있어서, 왕복 테스트는 반드시 두 필드를 모두 비-기본값으로 채워서 돌린다.

**왜 필요하냐.** `full` 모드에서 모델은 placeholder 만 본다. 모델이
`notify_user(message="전화번호는 [SENS:PII:PHONE:1:b801…] 입니다")` 를 부르면, 이 설정이 없는
한 도구는 **그 문자열 그대로** 받는다. `demask_tool_args` 는 실행 직전에만 되돌릴 인자를
지정하는 화이트리스트다 — 전체를 되돌리지 않는 이유는 되돌린 값이 전사(transcript)에 남으면
안 되기 때문.

upstream 은 이걸 최상위 `[pii_demask_tool_args]` 로 두지만, 우리는 `mode` 와 같은 섹션 아래에
넣는다 — `[safety]` 의 리로드 시맨틱을 함께 상속하고, 두 키가 항상 같이 읽히기 때문.

> **`PiiDemaskTiming` 은 노출하지 않는다 (검토 후 결정).** demask 에는 노브가 둘이다 —
> "무엇을"(`demask_tool_args`) 과 "언제"(`PiiDemaskTiming`). 후자는 tinicore 기본값
> `AfterApproval` 에 그대로 맡긴다. upstream tinicli 도 열지 않는다(grep 0건).
>
> 기본값이 옳은 값이기 때문이다 — doc: *"Restore the real value at the **LAST moment** — after
> the broker, the policy engine, and the approval prompt have all decided, so **only the
> executing tool ever sees it**. A call that is DENIED ... **never materialises the real value
> anywhere**."* 반대편 `BeforeGates` 는 훅·승인 UI·감사 로그가 실값을 보게 하는 대신, **거부된
> 호출에서도** 평문 PII 가 그 관찰자들을 거친다. 노출하면 운영자가 그 트레이드를 모르고 켤 수
> 있으므로, 필요해질 때 별도 결정으로 연다.

`[safety]` **아래**에 두는 게 핵심이다 — `reload.rs::field_effect`(`:456`)가 이미
`"safety" => (Effect::NeedsRestart, ...)` 로 매핑하므로 리로드 시맨틱을 **배선 0줄로 상속**한다.
새 최상위 섹션을 만들면 `_` 폴백으로 떨어진다.

같이 손봐야 할 두 곳:

- `reload.rs:456` 의 detail 문자열 — `"prompt guard config is built at boot"` 는 PII 가 들어온
  뒤엔 부정확해진다. `"safety config is built at boot"` 류로.
- `crates/argot-config/src/patch.rs:307-320`, `:568` — 섹션 서술자. 없으면
  `argot config get/set/schema` 가 새 키를 못 본다. `:1676` 의 테스트도 같은 모양으로 추가.
  ⚠️ `mode` 는 기존 `prompt_guard_mode` 와 같은 스칼라라 그대로 따라가면 되지만,
  **`demask_tool_args` 는 임의 키를 갖는 테이블**이라 스칼라 서술자 모양에 안 맞는다. 기존
  서술자에 테이블 필드 선례가 있는지 먼저 확인하고, 없으면 `mode` 만 노출하고
  `demask_tool_args` 는 파일 직접 편집 전용으로 둔다(문서에 명시). `argot config set` 으로
  중첩 맵을 편집하는 UX 를 새로 발명하지 않는다.
- `crates/argot-config/src/default_config.toml` — 위의 주석 처리된 `[safety.pii]` 블록.

`argot-config` 는 feature 를 타지 않는다. **스키마는 항상 파싱된다.** 그래서 feature 없이
빌드된 바이너리가 `mode = "block_only"` / `"full"` 을 만날 수 있다.

**이 경우 부팅을 실패시킨다. 경고 로그로 넘기지 않는다.** 운영자가 `full` 을 켜놓고 로그 한 줄만
받으면, 보호받고 있다고 믿는 채로 PII 가 그대로 나간다 — 침묵하는 실패 중 최악의 종류다.
`compile_pre_persist_prompt_guard` 의 doc 주석이 정확히 이 논리를 위해 쓰였고("a **boot failure
the operator sees immediately**, instead of a terminal error on every turn"), 여기 그대로
적용된다. `#[cfg(not(feature = "guardrails"))]` 쪽 `install_pii` 가 non-`off` 모드에 대해
"이 빌드는 `guardrails` feature 없이 만들어졌다"는 에러를 반환한다.

### 3단계 — 배선 (신규 모듈 `crates/argot-daemon/src/safety/`)

**파일이 둘이다. tinicli 의 구조를 그대로 따른다** (`tinicli/src/guardrails/` 대조 확인):

#### `safety/mod.rs` — cfg 를 **한 곳에 가두는** 얇은 shim (~22줄)

```rust
//! PII guardrail + masking wiring.
#[cfg(feature = "guardrails")]
pub(crate) mod pii;

/// The value every `AgentLoopConfig` construction site in this crate should
/// set its `guardrails` field to.
#[cfg(feature = "guardrails")]
pub(crate) fn input_guardrails_for_run() -> Option<tinicore::agent::guardrails::GuardrailSet> {
    pii::input_guardrails_for_run()
}
#[cfg(not(feature = "guardrails"))]
pub(crate) fn input_guardrails_for_run() -> Option<tinicore::agent::guardrails::GuardrailSet> {
    None
}
```

**이게 핵심 설계다.** 덕분에 5단계의 호출 지점들이 **cfg 없이 그냥 부른다.** upstream doc 이
이유를 직접 쓴다:

> Having this stub live here (rather than each call site repeating the `#[cfg(feature =
> "guardrails")]` / `#[cfg(not(...))]` pair `repl.rs`/`run_tui.rs` used to each carry their own
> copy of) is what let `tinicli/src/daemon.rs`'s two cron-driven `AgentLoopConfig`s be added
> later **without anyone re-deriving — or forgetting — that pair** (codex review, 2026-09-01).

#### `safety/pii.rs` — 실체 (`#![cfg(feature = "guardrails")]`)

tinicli 의 994줄짜리 파일을 통째로 옮기지 **않는다** — prompt_guard 의 함수 3인방과 같은 크기로
맞춘다. 필요한 tinicore API 는 전부 public 임을 확인했다:

```rust
use tinicore::agent::guardrails::{GuardrailSet, global_guardrails};
use tinicore::agent::pii_masking::{
    SensitiveMasking, install_sensitive_masking,
    validate_demask_paths, conflicting_approval_gated_demask_tools,
};
use tinicore::guardrails::{PiiSpanDetector, build_filters_with_params, DEFAULT_CHUNK_SIZE};
use tinicore::sensitive::{DetectorChain, OnIncomplete, RevealTo};
```

**저장 위치가 절반씩 다르다** (④ 참조) — 이게 이 모듈 구조의 핵심이다:

```rust
// 가드레일 절반: 크레이트 로컬. tinicore 의 install_guardrails 를 쓰면
// 운영자의 전역 input 체인을 밀어낸다 (pick_layer 는 교체, 합집합 아님).
static PII_INPUT_GUARDRAILS: OnceLock<Option<GuardrailSet>> = OnceLock::new();
```

네 함수:

- `pii_guardrail_set(mode, global) -> Option<GuardrailSet>` — 순수 함수.
  `PiiSpanDetector::from_filter("guardrails:input", ...)` → `DetectorChain::single(...)` →
  `SensitiveGuardrail::new("pii.input", ...).on_incomplete(OnIncomplete::Block)` →
  `GuardrailSet::new().with_input(chain)`. **`with_input` 만 채운다** — output / tool 층은
  건드리지 않는다.
  `global_guardrails()` 가 비어있지 않으면 `GlobalInputChainAdapter` 로 **전역 체인을 먼저**
  체인에 넣고 PII 를 두 번째로 넣어 **합성**한다(tinicli `pii.rs:327` 그대로). 순서가
  운영자-우선인 이유도 그쪽 주석에 있다 — `pii_mode` 를 켠다고 기존 거부의 사유 이름이
  바뀌면 안 되기 때문.
- `pii_masking_for_mode(mode, tool_args) -> Option<SensitiveMasking>` — `full` 에서만 `Some`.
- `input_guardrails_for_run() -> Option<GuardrailSet>` — `safety/mod.rs` 의 shim 이 위임하는
  실체. 5단계의 모든 `AgentLoopConfig.guardrails` 지점이 **shim 하나만** 호출한다.
- `install_pii(mode, tool_args) -> Result<(), TinicoreError>` — 부팅 때 한 번.
  `PII_INPUT_GUARDRAILS.set(...)` + `install_sensitive_masking(...)`.
  `SensitiveMasking::tool_args(Arc::new(map))` 로 맵을 싣는다. 설치 **전에** 아래 두 검증을
  돌려 잘못된 설정을 **부팅 실패**로 만든다.

#### `demask_tool_args` 부팅 검증 — 둘 다 필수

**(1) 구조 검증 — `validate_demask_paths(&map) -> Vec<DemaskPathError>`**

세 가지를 잡는다: `BadToolName`(wire name 이 아닌 키 — 네임스페이스/별칭이 "가장 흔한
오설정"), `NoPaths`(빈 경로 목록), `EmptySegment`(빈 경로나 끝 점). doc 이 왜 부팅에서
잡아야 하는지 밝힌다:

> A malformed entry ... is a SILENT no-op at runtime ... The loop's trace diagnostic helps, but
> only once the model happens to call that tool, **which may be never during testing and always
> in production**.

**(2) 승인 충돌 검증 — 이건 우리가 직접 짜야 한다**

tinicore 에 `conflicting_approval_gated_demask_tools(map, gated)` 가 있고 `agent_loop` 가
이걸로 **거부까지 한다**(`loop_.rs:3622` → `:3659`, `TinicoreError::Config`). 문제의 조합은:

```
도구가 승인 대기로 park  →  agent_loop 가 반환  →  사용자 승인 후 NEW agent_loop 로 재개
                                                        │
                        per-turn vault 는 이 경계를 못 넘음 (평문 PII 를 저장할 수 없으므로)
                                                        ▼
                        도구가 "[SENS:PII:PHONE:1:…]" 를 리터럴로 받아 실행
```

**그런데 argot 에서는 Core 의 검사가 무력하다.** 그 함수는 `config.flow_gated_tools` 만 보는데,
argot 은 그걸 안 채운다(`context.rs:1584` 기본 `Vec::new()`, `crates/` 에 0건). Core 도 이 한계를
스스로 명시한다:

> `flow_gated_tools` is the only approval-gating signal Core can see. **A host's own
> `ApprovalHandler` is opaque**, so silence here does not prove the combination is absent.

argot 의 승인은 `ArgotApprovalHandler` + `[interactions]` 로 도는 — 정확히 그 "opaque" 한
경로다. 그리고 **실제로 충돌 가능한 도구가 있다**: `file_write` / `file_edit` / `http_fetch` /
`memory_forget` 이 전부 `ApprovalMode::Auto` 다(`tools/mod.rs:519-536`). 누가
`file_write = ["path"]` 를 설정하고 `[interactions]` 를 켜면, 승인 후 재개된 `file_write` 가
**placeholder 문자열을 경로로 삼아 파일을 쓴다.**

→ 그러므로 `install_pii` 는 **argot 자신의 레지스트리**를 대조하는 검사를 직접 수행한다:
`demask_tool_args` 의 키 중 `approval_mode != Never` 인 것이 있고 `[interactions]` 가 켜져
있으면 **부팅 실패**. 메시지는 `approval_demask_conflict_message(&conflicts)` 를 재사용해
upstream 과 문구를 맞춘다.

> **Core 처럼 per-turn 거부로 두지 않는 이유.** Core 의 주석이 직접 경고한다 — *"⚠ BREAKING,
> and this is NOT a startup check. It runs per `agent_loop` CALL. A host that assembles one
> config at boot **fails on its first turn and stays broken until the config changes**."*
> 우리는 config 를 부팅에 한 번 조립하므로 정확히 그 케이스다. 부팅에서 잡으면 운영자가 즉시
> 본다.
>
> **`flow_gated_tools` 를 채우는 방법은 택하지 않는다.** 그러면 Core 의 검사가 살아나지만
> per-turn 거부로 돌아가고, 그 필드는 승인 게이팅이 아니라 flow 게이팅이라는 다른 의미를
> 갖는다. 남의 필드 의미를 빌려 쓰는 대신 우리 검사를 짠다.

> ⚠️ **구현 전에 확인할 것 — 설치 함수가 두 개다.** `pii_masking.rs` 에
> `install_masking_policy`(`:508`)와 `install_sensitive_masking`(`:606`)이 **둘 다** 있고,
> `inherit_global_masking`(`:521`)과 `inherit_global_sensitive`(`:881`)도 쌍으로 있다.
> 같은 파일 `:512-513` 에 `global_masking_policy` 가 `#[deprecated]` 구명으로 남아 있는 전례가
> 있으니, 한쪽이 옛 이름인지 아니면 **서로 다른 슬롯**에 설치하는지 먼저 읽는다.
> (상속 쪽은 ⑤ 에서 이미 확정했다 — `inherit_global_sensitive` 가 `agent_loop`
> `loop_.rs:1445` 에서 자동으로 도는 정식 경로다. 남은 건 install 쪽 둘 중 어느 것이
> `GLOBAL_MASKING` 의 정식 진입점인지뿐. upstream `install_pii` 는
> `install_sensitive_masking` 을 쓴다.)

호출 지점은 `context_builder.rs:160` 의 `apply_prompt_guard_mode` 바로 옆.

> **부팅 순서 제약.** upstream 은 `cli_entry.rs:158` 에서 `install_guardrails_from_env("ARGO")`
> 를 먼저 부르고 `:389` 에서 `install_pii` 를 부른다. 순서가 뒤집히면 `pii_guardrail_set` 이
> 스냅샷하는 `global_guardrails()` 가 비어 있어, `GlobalInputChainAdapter` 합성이 일어나지 않고
> 운영자 체인이 조용히 가려진다(④-b). argo-tizen 은 현재 env 설치를 **부르지 않으므로 문제가
> 없지만**, 나중에 추가한다면 반드시 `install_pii` **앞**이다. upstream 이 이 순서를
> `debug_assert!` 로 지키고 있으니 그 가드도 같이 가져온다.

### 4단계 — 사전-영속 입력 게이트 (= tinicore 가 말하는 **admission gate**)

**이름 정리부터.** tinicore 의 `run_input_guardrails_with_text` doc 첫 줄이
*"This is the **host-side admission gate**. Hosts call it before `save_message` and before
pushing the user message into history"* 라고 쓴다. 즉 "admission gate" 와 "사전-영속 게이트" 는
**같은 것**이다.

> ⚠️ **`transport/grpc/admission.rs` 와 혼동 금지.** 이름만 같고 성격이 완전히 다르다. 그쪽은
> **동시 실행 개수 세마포어**(`DEFAULT_GRPC_CHAT_DISPATCH_LIMIT: usize = 16`)로, 내용 검사와
> 무관하다. 거기에 PII 검사를 넣으면 안 되는 이유 둘: (a) `kernel.dispatch` **이전**이라
> 메시지가 아직 `ChatMessage` 로 파싱되기도 전이고, (b) gRPC 전용이라 telegram / cron /
> A2A 는 애초에 안 지나간다(모듈 doc 이 명시) — 나머지 문으로 다 샌다.

**게이트는 두 곳이다 — ③의 두 `AgentLoopConfig` 지점과 짝을 이룬다.**

#### (가) `turn/mod.rs:515` — 이 기기의 모든 턴

기존 `pre_persist_guard` 레일에 **얹는다.** 두 번째 게이트를 만들지 않는다. 자리는
`async fn prepare()`(`:435`) 안, `prompt_guard::evaluate`(`:515`) 직후.

#### (나) `transport/a2a/executor.rs:105` — 원격 피어 요청 (**빠뜨리면 안 되는 곳**)

`ArgotA2aRunner::run()` 의 실행 순서를 읽고 확인한 공백이다:

```rust
async fn run(&self, requester: &str, task: &Task) -> Result<String, _> {
    persist_request_best_effort(&self.ctx, requester, task).await;   // :105  ← DB 쓰기
    let mut config = (self.config_factory)(task)?;                   // :106  ← 5단계 필드
    ...
    let result = serve_delegated_task(..., config, ...).await;       // :126  ← in-loop 검사
```

**영속화가 첫 줄이다.** 5단계로 `config.guardrails` 를 채워도 검사는 `:126` 에서야 도니, 그때는
이미 원격 피어의 메시지가 DB 에 들어간 뒤다. 5단계만으로는 A2A 가 이렇게 된다:

| | ① turn/mod.rs | ② A2A |
|---|---|---|
| 사전-영속 게이트 | ✅ | ❌ **공백** |
| in-loop 검사 (5단계) | ✅ | ✅ |
| 차단 시 DB | 안 남음 | **이미 남음** |

**그리고 A2A 쪽이 더 위험하다.** `turn/mod.rs` 는 이 기기 사용자 입력이지만 A2A 는 원격
피어이고, executor 스스로 `TrustTier::Untrusted`(`:118`) 로 넘긴다 — 가장 안 믿는 입력이 가장
약한 방어를 받는 꼴이다. admission gate doc 이 정확히 이 이유를 쓴다:

> When it returns `Err`, the host must skip the persist and history push entirely — **the
> credential never reaches the DB and never appears in a later turn's replay.**

→ `:105` **앞**에 게이트를 넣는다. 텍스트는 `message_text(task)` 로 뽑는다(이미 import 돼 있다),
`run()` 은 `async` 라 `.await` 가 그대로 붙고, 반환은
`Err(ServedExecutionError::Failed(...))` 로 매핑한다.

**코드를 읽고 확정한 사항 — 계획이 단순해진다:**

- 그 자리는 이미 `async` 라 `.await` 가 그대로 붙는다.
- `run_input_guardrails_with_text(text, per_run)` 의 `per_run` 에 **`input_guardrails_for_run()`
  의 결과를 넘긴다** (`Option<&GuardrailSet>`). ④ 에서 확인했듯 우리는 전역
  `install_guardrails` 를 쓰지 않으므로, **`None` 을 넘기면 아무것도 검사하지 않는다.**
  upstream 의 `repl.rs:490` / `run_tui.rs:465` 도 `pii_input_guardrails()` 를 넘긴다.
- 내부적으로 `resolve_against(per_run, global_guardrails())` 를 타므로, 운영자가 나중에 전역
  체인을 설정해도 함께 해소된다.
- `pre_persist_pii` 러너 필드는 만들지 않는다 — `input_guardrails_for_run()` 이 이미
  `OnceLock` 캐시라 러너에 또 들고 있을 이유가 없다.

반환은 양쪽 다 `Result<(), GuardrailTripwireError>` 다. (가)는 `send_prompt_guard_refusal` 과
같은 모양의 거부 경로(`return Ok(None)`)를 타고 `fire_prompt_guard_event` 로 `pii.block` 을
쏜다. (나)는 `ServedExecutionError::Failed` 로 매핑한다 — 원격 피어에게는 **매칭된 내용을
돌려주지 않는다** (거부 사유가 곧 PII 탐지 결과라, 피어가 그걸로 프로빙할 수 있다).

"거부가 위조 메시지를 영속 히스토리에서 막아낸다"는 시맨틱이 (가) 자리에 **이미 문서화돼 있다.**
그 문장이 PII 에도 그대로 적용되는 게 이 자리를 고른 이유다.

### 5단계 — per-run 필드 (**보조가 아니라 주 배선**)

③의 두 `AgentLoopConfig` 생성 지점에서 `guardrails` 필드를 채운다. 전역
`install_guardrails` 를 쓰지 않기로 했으므로(④), **이걸 빠뜨린 경로는 그냥 무방비다.**

두 곳 다 지금은 `..Default::default()` 로 끝나서 이 필드가 `None` 이다. **cfg 없이** shim 을
부른다(3단계):

```rust
guardrails: crate::safety::input_guardrails_for_run(),
```

- `turn/mod.rs:1593` — 범용 레일 (대화형/cron/서브에이전트/telegram/resume 전부)
- `boot/a2a.rs:435` — `a2a` feature 전용, A2A-served 인바운드

**`sensitive` 필드는 손으로 채우지 않는다.** ⑤ 에서 확인했듯 `agent_loop` 가
`inherit_global_sensitive`(`loop_.rs:1445`)로 전역에서 알아서 채운다. 오히려 손으로 채우면
그 함수가 *"an explicit per-run config always wins, **whole**"* 로 early-return 해서 전역
정책을 통째로 밀어낸다 — A2A served 경로가 `force_reveal_to` 로 `RevealTo::NoOne` 을 거는 것도
이 자리라(`served.rs:489`), per-run 을 하드코딩하면 그 강제도 함께 무력화된다.

**upstream 이 실제로 낸 사고가 이 자리다.** `daemon.rs` ratchet 테스트의 doc:

> of this file's `AgentLoopConfig` struct-literal construction sites, the two cron-driven ones
> (`RoutineAction::Llm`, `RoutineAction::SpawnAgent`) were the only ones in the crate that never
> set `guardrails:` — so **the boot-installed PII input chain silently never reached a routine
> fire.**

#### ratchet 테스트를 **그대로 포팅한다** (`daemon.rs:2595-2690`)

두 지점이 서로 다른 파일에 있으므로 **두 파일 각각**에 넣는다(upstream 도 `repl.rs` /
`daemon.rs` 에 하나씩 둔다). 동작:

- `include_str!` 로 **자기 소스를 다시 파싱**한다.
- `AgentLoopConfig {` 마커를 찾되 **바로 앞이 `::` 인 것만** 센다 — 이 가드가 없으면 스캔이
  자기 코드의 마커 문자열 리터럴을 세 번째 생성 지점으로 잘못 잡고 브레이스 균형이 깨진다.
- 여는 `{` 부터 **중괄호 균형**으로 본문 끝을 찾는다 (중첩 블록이 있어도 안 깨짐).
- 각 본문이 `guardrails:` 를 포함하는지 단언. 더해서 `bodies.len() >= 1` 을 단언해 **마커가
  드리프트해서 0개를 찾고 통과하는 가짜 패스**를 막는다.

> ⚠️ **테스트의 doc 주석에 마커 문자열을 절대 쓰지 않는다.** 스캔은 주석인지 코드인지 모른다.
> upstream 이 이 함정을 doc 에 명시해뒀다 — *"This doc deliberately never writes the marker
> string this scan looks for."*

> **A2A 인바운드는 명시적으로 커버한다 — 두 겹으로.** ARGO 에서는 유사한 ACP 경로가 "문서화된
> 공백"으로 남았는데, 여기서는 남기지 않는다. A2A-served 는 **원격 피어**의 입력이라 신뢰
> 경계가 가장 바깥이고, executor 가 스스로 `TrustTier::Untrusted` 로 넘긴다.
>
> - **5단계(여기)** = `config.guardrails` → in-loop 검사. 하지만 `serve_delegated_task`
>   (`executor.rs:126`)에서야 돌아 **영속화(`:105`)보다 늦다.**
> - **4단계(나)** = `executor.rs:105` 앞의 사전-영속 게이트. 이게 있어야 차단된 메시지가 DB 에
>   안 남는다.
>
> 둘 다 필요하다. 그리고 per-run 이 주 배선이 된 이상 5단계를 빼면 **덮어줄 전역이 없다.**
> 이 판단을 커밋 본문에 명시한다 — 리뷰어가 가장 먼저 물어볼 지점이다.

### 6단계 — CI lane (선택 아님, 필수)

**기본 OFF 인 feature 는 preflight 의 기본 lane 에 안 잡힌다.** ARGO 에서 정확히 이걸 놓쳤고
(`668456e525`: "the `guardrails` feature was never run in CI") 뒤늦게 고쳤다. 반복하지 않는다.

`project/scripts/preflight.sh` — TEL(`:138`)/SIMCLOCK(`:241`) 과 똑같은 모양으로:

- `lane_guardrails()` — `cargo clippy -p argot -p argot-daemon --features guardrails
  --all-targets -- -D warnings` + `cargo test -p argot-daemon --features guardrails`
- `LANES+=(guardrails)` (`:318`, `--full` 일 때)
- **그래프 검증 추가** — `lane_a2a` 의 `assert_tinicore_defaults_disabled`(`:207-220`) 와 같은
  모양으로, `cargo tree -p argot --features guardrails -e features -i regex-automata` 가
  `"dfa"` / `"nfa-backtrack"` 을 켜지 **않았는지** 단언한다. 1단계의 핀이 나중에 풀리면 조용히
  바이너리만 커지는 종류의 회귀라, 이 단언이 유일한 방어선이다.

`.github/workflows/preflight.yml:161` 의 blast-radius 정규식은 **손댈 필요 없다** —
`crates/argot-daemon/` 과 `Cargo.toml` 이 이미 `--full` 을 트리거한다 (확인함).

`.github/workflows/tizen-build.yml:209-218` 은 feature 플래그를 안 넘기므로 ARM 크로스컴파일이
이 코드를 안 본다. 32비트(`target_pointer_width = 32`) 문제가 나올 곳이라, ARMv7 체크를 하나
넣을지 리뷰에서 논의한다. (tinicore 주석은 `sensitive` 가 "32-bit-safe" 라고 명시하지만,
`guardrails` 엔진에 대해서는 같은 보증이 없다.)

### 7단계 — 문서

- **`CLAUDE.md` + `AGENTS.md`** (`:240-257`) — "telemetry/a2a feature lanes" 열거에
  `guardrails` 추가. ⚠️ **두 파일은 바이트 동일해야 하고 `parity.sh` 가 fast-fail 게이트다.**
  하나만 고치면 필수 체크가 깨진다.
- **`project/docs/preflight.md:6-38`** — lane 목록.
- **`project/docs/design/daemon/agent-safety.md`** — Context 에 쓴 대로, `:259` 의
  "deliberate-by-inheritance state worth an explicit product decision" 이 이 작업으로
  **해소된다.** §1.1 의 ASCII 다이어그램("LOOKS LIKE SAFETY, ISN'T")과 §2.8 Summary 를
  갱신한다. 이 문서가 "Matches what ships" 를 표방하므로, 안 고치면 문서가 즉시 거짓이 된다.
- `[safety.pii]` 사용자 문서 — `docs/book/` 의 config 레퍼런스.

---

## 테스트 계획

**`OnceLock` 이 테스트 설계를 제약한다.** 크레이트 로컬 `PII_INPUT_GUARDRAILS` 와 전역
`install_sensitive_masking` 둘 다 프로세스당 한 번만 성공한다. argot-daemon 의 유닛 테스트는 한
바이너리 안에서 같은 프로세스를 공유하므로, 첫 install 이 이후 모든 테스트로 샌다.

→ 그래서 3단계에서 **순수 빌더 함수와 install 을 분리**했다. 테스트 무게는 빌더 쪽에 싣는다:

1. **순수 유닛 테스트** (전역 상태 안 건드림)
   - `pii_guardrail_set(Off)` → `None`; `(BlockOnly)`/`(Full)` → 입력 체인 있는 `Some`
   - `pii_masking_for_mode(BlockOnly)` → `None` (block_only 는 마스킹 안 함 — 이게 모드
     구분의 본질이라 반드시 고정한다)
   - config 파싱: `mode = "block_only"` 왕복, 미지의 값 거부, 미지정 시 `Off`
   - **`demask_tool_args` 파싱**: 인라인 표기와 서브테이블 표기 **둘 다** 파싱되는지, 미지정 시
     빈 맵인지 (upstream `pii_demask_tool_args_deserializes_from_toml` / `_defaults_to_none` 과
     동형)
   - **save→load 왕복**: `mode` 와 `demask_tool_args` 를 **둘 다 비-기본값**으로 채운 config 를
     `save()` 후 다시 읽어 동일한지. TOML 의 "스칼라 먼저" 제약을 이 테스트가 지킨다.
   - **`demask_tool_args` 검증** — 셋 다 부팅 실패가 되는지:
     - 잘못된 wire name (`"argo.file_write"`) → `BadToolName`
     - 빈 경로 목록 (`file_write = []`) → `NoPaths`
     - 끝 점 경로 (`file_write = ["a."]`) → `EmptySegment`
   - **승인 충돌 검증** — `file_write = ["path"]` + `[interactions]` 켬 → **부팅 실패**.
     같은 설정에 `[interactions]` 끔 → 통과. `notify_user`(`ApprovalMode::Never`)는 켜도 통과.
     이 세 조합이 검사의 본체라 반드시 고정한다.
2. **install 경로는 `#[test]` 하나** — 순서 의존을 만들지 않도록 단일 테스트에서만.
3. **e2e** — `crates/argot-e2e` 는 데몬을 `Command::new(&self.argot_bin)` 으로
   **서브프로세스**로 띄운다(`world.rs:314` 확인). 즉 전역 install 오염이 **없다.**
   `[safety.pii].mode` 를 세 값으로 바꿔가며 데몬을 띄우는 시나리오를 추가할 수 있다.
4. **A2A 게이트 순서 테스트** (`--features a2a,guardrails`) — 4단계(나)가 지키는 성질은
   "**차단되면 DB 에 안 남는다**"이므로, 그걸 직접 단언한다: PII 가 든 `Task` 로
   `ArgotA2aRunner::run()` 을 호출 → `Err` 반환 **그리고** 세션 스토어에 그 메시지가 없는지.
   게이트를 `persist_request_best_effort` **뒤로** 옮기면 깨져야 한다 — 순서가 곧 이 게이트의
   전부다.
5. **음성 테스트** — 4단계 게이트 두 곳을 각각 임시로 무력화했을 때 해당 차단 테스트가
   **실제로 실패하는지** 확인. 실패하지 않으면 그 테스트는 아무것도 지키지 않는 것이다.

### 수동 E2E 검증

```bash
# feature 없는 빌드: PII 코드가 0바이트인지
cargo build -p argot --release
cargo tree -p argot -e features -i regex-automata | grep -c '"hybrid"'   # → 0 기대

# feature 켠 빌드
cargo build -p argot --release --features guardrails
cargo tree -p argot --features guardrails -e features -i regex-automata | \
  grep -E '"(dfa|nfa-backtrack|perf)"'                                   # → 없어야 함

# 바이너리 크기 델타 실측 (저장소에 크기 게이트가 없으므로 직접 잰다)
ls -l target/release/argot     # 전후 비교

# 런타임: mode 별로 데몬 띄우고 확인
#   off        → 오늘과 동일하게 통과
#   block_only → PII 든 메시지 거부, DB에 안 남음 (sqlite 로 직접 확인)
#   full       → 통과하되 아웃바운드 요청 바디에 placeholder, 응답은 원문 복원
```

`full` 모드의 마스킹 검증은 **와이어를 직접 봐야 한다.** `[safety.pii].mode = "full"` +
`dev-service` 의 LLM 와이어 트레이싱(기본 ON)으로 아웃바운드 바디를 캡처해
`[SENS:PII:PHONE:1:...]` 형태의 placeholder 가 실제로 나가는지 확인한다.

### 게이트

```bash
./project/scripts/fmt.sh
./project/scripts/preflight.sh --full      # 새 guardrails lane 포함
```

`project/docs/preflight.md` 의 수동 체크리스트를 먼저 읽고, 특히 "Ownership drift: keep changes
inside the intended ownership boundary, especially around vendored upstream code" 항목을
확인한다 — 이 작업은 `tini/` 를 **한 줄도 건드리지 않는다.**

---

## 커밋 구성

`type(scope): imperative summary`, 72자 이내 (CONTRIBUTING.md:105). 리뷰 가능한 단위로 3개:

1. `build(deps): pin regex-automata to the lazy-DFA feature subset`
   — 1단계의 루트 핀만. 단독으로도 옳고(현재 그래프를 안 바꿈), feature 를 켜기 전에 들어가야
   유니피케이션 폭발이 애초에 안 일어난다.
2. `feat(config): add the [safety.pii] mode and demask-tool-args keys`
   — 2단계. 스키마(`mode` + `demask_tool_args`) + patch 서술자 + reload detail 문자열.
   아직 아무 동작 없음.
3. `feat(daemon): wire the PII guardrails behind an opt-in feature`
   — 3~7단계. 배선 + CI lane + 문서.

3번 본문에 담을 것: `sensitive` 와 `guardrails` 가 **둘 다** 필요한 이유(①),
`tinicore::install_guardrails` 를 **쓰지 않고** 크레이트 로컬 `OnceLock` + per-run 으로 간 이유
(④ — 전역 슬롯은 `OnceLock` 이라 env 설정과 둘 중 하나가 조용히 증발하고, 잡아도 `pick_layer`
가 전역 체인을 교체해 버린다), **승인 충돌 검사를 Core 에 맡기지 않고 직접 짠 이유**
(`flow_gated_tools` 가 비어 있어 Core 의 검사가 argot 에서 무력하고, argot 의 승인은 Core 가 못
보는 `ArgotApprovalHandler` 경로다 — 3단계), A2A-served 를 공백으로 남기지 **않은** 판단(5단계),
그리고 `agent-safety.md` 의 "explicit product decision" 이 이걸로 해소된다는 점.
