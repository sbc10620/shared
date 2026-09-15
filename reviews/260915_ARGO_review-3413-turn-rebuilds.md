# ARGO #3413 턴 재빌드 브랜치 코드 리뷰 결과 (2026-09-15)

다른 세션에 인계하기 위해 `/code-review high` 결과를 그대로 정리한 문서입니다.

## 리뷰 대상

- 레포: `~/Works/ARGO`
- 브랜치: `dev/byungchul.so/guardrails-turn-rebuilds`
- 범위: `origin/main...dev/byungchul.so/guardrails-turn-rebuilds` (로컬 커밋 2개, push·PR 없음)
- 리뷰 수준: high
- 관련 이슈: #3413

### 커밋

| 해시 | 제목 |
|---|---|
| `a7f8f0fffb` | perf(guardrails): build the PII engine once per turn and once at boot (#3413) |
| `9878a76895` | perf(guardrails): compile each chunk's NFAs once per engine build (#3413) |

### 변경 파일

```
tinicli/src/cli_entry.rs                     |  12 +-
tinicli/src/guardrails/pii.rs                | 842 ++----------------------
tinicli/src/repl.rs                          |   6 +
tinicli/src/run_tui.rs                       |  10 +
tinicore/examples/guardrails/bench_engine.rs |  82 ++-
tinicore/src/agent/loop_/wrap_up.rs          | 115 ++++
tinicore/src/gateway/handler.rs              |   9 +
tinicore/src/gateway/kernel/mod.rs           |   9 +
tinicore/src/guardrails/AGENTS.md            |  37 +-
tinicore/src/guardrails/README.md            |   5 +-
tinicore/src/guardrails/detector.rs          |   7 +
tinicore/src/guardrails/filter.rs            |  17 +
tinicore/src/guardrails/install.rs           | 944 +++++++++++++++++++++++++++
tinicore/src/guardrails/mod.rs               |  17 +-
tinicore/src/guardrails/recognizer.rs        | 269 ++++++++++++++--------------------
tinicore/tests/gateway_turn_scope.rs         | 169 +++++
tinicore/tests/guardrails/turn_scope_test.rs |  61 ++
```

## 결론

동작을 깨뜨리는 정합성 버그는 찾지 못했고, 낮은 심각도의 지적 사항 3건만 보고되었습니다.

## 검토한 범위와 확인한 내용

- `turn_scope` 가드의 pin/unpin/adopt 의미를 읽고, 새로 가드를 잡는 6개 지점(`install_guardrails`, `PiiSpanDetector::for_layer`, `repl.rs`, `run_tui.rs`, `gateway/handler.rs`, `gateway/kernel`)과 detached task로 가드를 넘기는 2개 지점(`wrap_up.rs`)이 모두 `agent_loop`의 가드가 살아 있는 동안 중첩되며, 조기 `continue`·abort 경로에서도 가드가 정상적으로 drop되는 것을 확인했습니다. 데드락 가능성(빌드 클로저가 가드를 재진입하는 경우)도 없었습니다.
- `recognizer.rs`의 NFA 1회 컴파일 재작성은 regex-automata 0.4.14 소스로 대조했습니다. 기존 `hybrid::dfa::Builder::build_many`가 forward NFA에도 `WhichCaptures::None`을 강제하고, `build_from_nfa` 경로에서는 builder의 `syntax()`/`thompson()`이 무시되므로, 새 `pattern_syntax()` + 명시적 `which_captures(None)` 경로는 기존과 동일한 DFA를 만듭니다.
- `tinicli::guardrails::pii` → `tinicore::guardrails::install` 이관은 옛 코드와 한 줄씩 대조했고, 에러·경고 경로가 그대로 보존되었습니다. feature 배선(`tinicli/guardrails` = `tinicore/guardrails` + `tinicore/sensitive`), 새 테스트 바이너리의 자동 발견(`gateway_kernel_basic.rs` 선례 존재), Core 누출 감사 스크립트 3종도 모두 통과했습니다.

## 지적 사항

| # | 위치 | 판정 | 심각도 | 요약 |
|---|---|---|---|---|
| 1 | `tinicore/src/guardrails/recognizer.rs:746` | PLAUSIBLE | 낮음 | forward DFA 최소 캐시가 capture 없는 NFA 기준으로 줄어듦, 스캔 지연 재측정 필요 |
| 2 | `tinicore/src/agent/loop_/wrap_up.rs:267` | PLAUSIBLE | 낮음 | memorize detached task의 가드에 cancel·시간 제한 없음 |
| 3 | `tinicore/src/guardrails/install.rs:174` | CONFIRMED | 낮음 | Core 에러 메시지·모듈 문서가 CLI 전용 안내(`config.toml`, `ARGO_GUARDRAIL_DENY_INPUT`)를 담고 있음 |

### 1. forward DFA 캐시 용량 감소 (`recognizer.rs:746`)

forward DFA의 최소 캐시를 이제 capture 없는 NFA에서 측정하므로, 운영 환경의 forward 캐시 용량이 이전보다 줄어듭니다. 정확성에는 영향이 없지만(`minimum_cache_clear_count` 미설정이라 절대 실패하지 않음), 긴 입력에서 캐시 clear가 늘어날 수 있는데 `bench_scan` 표 3(스캔 지연)이 재측정되지 않았습니다.

### 2. memorize detached task의 가드 수명 (`wrap_up.rs:267`)

memorize detached task에 넘긴 가드에는 cancel이나 시간 제한이 없어서, 호스트 훅이 느리면 PII 엔진과 등록된 모든 turn-scoped 슬롯이 훅이 끝날 때까지 상주합니다. 형제 함수 `spawn_memory_intervention_check`는 `cancel`을 전달하는 것과 비대칭입니다.

### 3. Core 진입점의 CLI 전용 안내 문구 (`install.rs:174`)

Core의 운영자용 에러 메시지가 `config.toml`을 지목하고, 모듈 문서가 `ARGO_GUARDRAIL_DENY_INPUT`을 명시합니다. 이제 모든 호스트가 공유하는 Core 진입점이므로 tiniffi/argot 같은 비 CLI 호스트에는 잘못된 안내가 되며, 감사 스크립트가 잡지 못하는 Core 보호 규칙 위반에 해당합니다.

## 인계 시 참고 사항

- 위 3건은 아직 처리하지 않은 상태입니다. 처리 여부와 순서는 사용자 결정이 필요합니다.
- 브랜치는 로컬 커밋만 있고 push와 PR은 아직 하지 않았습니다. push와 PR은 각각 별도 지시가 있을 때만 진행합니다.
- argot 반영은 이 브랜치 범위에 포함되지 않은 후속 작업입니다.
