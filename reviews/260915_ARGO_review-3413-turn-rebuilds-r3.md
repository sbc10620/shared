# ARGO #3413 턴 재빌드 브랜치 3차 리뷰 결과 (2026-09-16, r3)

r2(`260915_ARGO_review-3413-turn-rebuilds-r2.md`)의 지적 4건에 대한 구현자 처리 결과를 검증한 결과입니다. r1은 `260915_ARGO_review-3413-turn-rebuilds.md`입니다.

## 리뷰 대상

- 레포: `~/Works/ARGO`
- 브랜치: `dev/byungchul.so/guardrails-turn-rebuilds`
- 범위: `origin/main...dev/byungchul.so/guardrails-turn-rebuilds` (로컬 커밋 2개, push·PR 없음)
- merge-base: `0721ca2692` (구현자 전달 내용에는 `c873b9ca82`로 적혀 있었으나, amend 과정에서 브랜치가 현재 `origin/main`(#3412 머지) 위로 리베이스되었습니다. `git range-diff c873b9ca82..68bd35e427 0721ca2692..HEAD`로 확인했고, 둘째 커밋은 `=`(동일), 첫째 커밋은 `!`(amend)입니다. 이 때문에 `git diff 8bd284ccd4 4843d5dca8`에는 main 쪽 변경(llm/fallback.rs 등 8개 파일)이 섞여 보이며, 실제 amend는 아래 3개 파일뿐입니다.)
- 관련 이슈: #3413

### 커밋

| 해시 | 제목 | r2 이후 |
|---|---|---|
| `4843d5dca8` | perf(guardrails): build the PII engine once per turn and once at boot (#3413) | amend됨 (3개 파일) |
| `a794dbbe9c` | perf(guardrails): compile each chunk's NFAs once per engine build (#3413) | 변경 없음 (range-diff `=`로 확인) |

### amend된 차이 (`8bd284ccd4` → `4843d5dca8`, 브랜치 파일만)

- `tinicli/src/guardrails/pii.rs`: `map_err`를 `match`로 바꿔 `LayerBuild`에만 ` (config.toml)` 접미사.
- `tinicore/src/agent/loop_/wrap_up.rs`: `spawn_post_task_reflect`에 가드 인계 추가, memorize 주석 수정, 테스트 모듈 문서 수정, `reflect_task_keeps_the_turn_engine_until_the_hook_finishes` 테스트 추가.
- `tinicore/src/guardrails/install.rs`: 모듈 문서 4행 호스트 예시 제거, 47행 열거에 reflect 추가, 필드·상수·함수 문서와 에러·경고 문자열에서 TOML 표기 제거, `LayerBuild`·`MaskingSlotTaken` 메시지의 부팅 가정 제거, 테스트 assertion 갱신.
- 커밋 메시지 "Post-turn" 문단이 사후 task 셋을 열거하도록 수정됨.

## 결론

**PR 준비 완료.** r2의 지적 4건은 모두 해소되었고, amend에서 새로 생긴 문제는 없습니다. 아래에 코드 변경이 필요 없는 참고 사항 2건만 적어 두었습니다.

## r2 지적별 검증 결과

### 1. `tinicli/src/guardrails/pii.rs:80` ` (config.toml)` 접미사 → 해소

`match e { GuardrailsInstallError::LayerBuild { .. } => format!("{e} (config.toml)"), _ => e.to_string() }`로 분기합니다. 분기 조건은 맞습니다. `GuardrailsInstallError`의 세 변형 중 설정 편집으로 고칠 수 있는 것은 `LayerBuild`뿐입니다.

- `GuardrailMerge`: 다른 체인이 이미 전역 슬롯에 설치되어 있고 live 참조를 쥐고 있어 merge에서 한 층이 drop된 경우입니다. 메시지 자체가 "boot-ordering bug, not a configuration error"라고 말하며, 설정으로 고칠 수 없습니다.
- `MaskingSlotTaken`: 다른 정책이 먼저 `OnceLock`을 차지한 경우이며, 역시 설치 순서 문제입니다.

`_` arm은 앞으로 변형이 추가되어도 접미사를 붙이지 않는 안전한 기본값입니다. `LayerBuild { .. }` 패턴은 필드를 바인딩하지 않으므로 arm 안에서 `e`를 그대로 쓸 수 있고, 컴파일과 테스트(`install_pii_full_closes_the_background_egress_gap` 포함 3건)도 통과했습니다.

### 2. `wrap_up.rs:442` `spawn_post_task_reflect` 가드 인계 → 해소

가드 위치는 충분합니다. 근거는 다음과 같습니다.

- 가드는 두 발화 게이트(`post_task_reflect` 배선 여부, `post_task_should_fire`) 다음에 잡히므로(`wrap_up.rs:442`), reflect가 발화하지 않는 턴에는 가드가 생기지 않습니다.
- `async move` 블록이 `turn_scope`를 캡처하므로 가드는 future가 만들어지는 시점, 즉 spawn 시점부터 wrapper task가 쥡니다. 첫 poll을 기다리지 않습니다.
- wrapper task는 `wrap_up.rs:451`에서 안쪽 hook task의 `JoinHandle`을 await하므로, hook이 끝나거나 panic해서 `JoinError`가 돌아오기 전에는 wrapper가 끝나지 않고, 따라서 가드도 놓이지 않습니다. 안쪽 task까지 덮입니다.
- 어디에서도 wrapper를 abort하지 않습니다. 런타임 종료 시 future가 drop되면 가드도 함께 drop되므로 누수는 없습니다.

memorize·intervention·reflect 세 곳(`wrap_up.rs:273,360,442`)이 같은 형태이고, `loop_.rs:6825,6830,6977` 호출 지점 모두 `loop_.rs:1479`의 루프 가드가 살아 있는 동안이므로 세 가드 모두 루프 엔진을 adopt합니다.

테스트(`wrap_up.rs:1275`)는 memorize 테스트(`wrap_up.rs:1219`)와 같은 이유로 pin-count 대신 `is_built()`만 단언합니다. lib 바이너리의 다른 테스트가 가드를 잡으면 pin-count는 비결정적이지만 `is_built()`는 거짓 실패가 없다는 모듈 문서의 논리가 reflect에도 그대로 적용됩니다. 훅이 `entered`를 알린 뒤 `release`를 기다리는 동안 loop 가드가 이미 drop된 상태에서 `is_built()`를 확인하므로, 검사 창은 의도한 창("루프는 돌아갔고 훅은 아직 도는 중")입니다. `Notify::notify_one`은 대기자가 없으면 permit을 저장하므로 `entered`/`release` 신호가 유실되지 않고, wrapper `JoinHandle`을 5초 timeout으로 await해서 wrapper panic도 테스트 실패로 드러납니다. 같은 테스트 필터를 5회 반복 실행해서 모두 통과했습니다.

문서 쪽도 확인했습니다. `install.rs:47-48`의 열거는 "(memorize, intervention check, post-task reflect — they all scan)"으로, `wrap_up.rs` memorize 주석은 "the three detached post-turn tasks … the turn really ends when the last of them does"로, 커밋 메시지 "Post-turn" 문단은 셋을 이름으로 열거하도록 각각 수정되었습니다. `tinicore/src/guardrails/AGENTS.md`, `README.md`, `filter.rs`, `turn_scope.rs`, `bench_engine.rs`에는 사후 task를 열거하는 문장이 없어서 추가로 고칠 곳이 없습니다.

### 3. `install.rs` TOML 표기 → 해소

에러 문자열(`install.rs:225`), 경고·에러 문자열(`install.rs:264,272`), `PiiConfig` 필드 문서(`install.rs:83,86`), `PII_FILTER_LAYERS`·`check_filter_label_layers` 문서(`install.rs:199,205`)에서 대괄호와 점 경로가 모두 빠졌습니다. 모듈 문서 4행의 호스트 이름 예시도 제거되었습니다.

`install.rs` 전체를 `[pii_`, `toml`, `tinicli`, `argot`, `tiniffi`, `ARGO_`, `stderr`, `CLI`, `start`, `process will`로 다시 검색한 결과 남은 것은 다음뿐이며, 모두 문제가 아닙니다.

- `install.rs:10` "This code lived in `tinicli::guardrails::pii` until #3413": 이력 설명이며 r2에서 유지해도 된다고 판정한 항목입니다. crate-name 감사는 베이스라인 대비 증가만 잡으므로 통과합니다.
- `install.rs:120` "visible on stderr at boot": 특정 호스트가 아니라 "a host that wants …" 형태의 일반 서술입니다.
- "boot"라는 단어 다수(`install.rs:4,12,106,137,202,246,250,311,333,363,415,419,440,448,856,859,879`): 이 함수의 계약 자체가 "call exactly once, at boot, before any turn runs"이므로 호스트 종류와 무관하게 참입니다.

### 4. `install.rs:176,189` 부팅 가정 문구 → 해소

- `LayerBuild`: "no turn must be served under it"은 모듈 문서의 계약 "A host must not serve turns after receiving one"과 같은 내용입니다. `pii_mode` 값 표기도 "set `pii_mode` to `off`"로 형식 중립이 되었습니다.
- `MaskingSlotTaken`: "Refusing to serve turns rather than mask under a policy this process did not build"로, 같은 계약과 일치합니다.
- `layer_build_error_names_the_escape_hatch` 테스트(`install.rs:939`)는 새 문구 "`pii_mode` to `off`"를 단언합니다.

## 참고 사항 (코드 변경 불필요)

1. `install.rs:188`의 "so `pii_mode` `full` would be enforced by someone else's configuration"은 두 인라인 코드가 연달아 붙어 읽기가 조금 어색합니다. "so a `pii_mode` of `full` would be …" 정도가 자연스럽습니다. 의미에는 문제가 없으므로 선택 사항입니다.
2. `install.rs:440` 함수 문서의 "The host aborts its boot."는 그대로 남아 있습니다. 운영자용 메시지가 아니라 부팅 시점 호스트를 서술하는 내부 문서이고, 바로 앞 문장이 "Returning `Ok` anyway would serve turns while …"로 계약을 먼저 말하고 있어서 문제로 보지 않습니다.

## 검증 실행 결과

merge-base `0721ca2692` 기준 현재 워킹 트리에서 실행했고, 구현자 보고와 일치합니다.

| 명령 | 결과 |
|---|---|
| `cargo test -p tinicore --features guardrails,sensitive,test-fixtures --lib -- guardrails::install` | 30 passed |
| `cargo test -p tinicore --features guardrails,sensitive,test-fixtures --lib -- turn_scope_handoff` | 2 passed (memorize, reflect), 5회 반복 모두 통과 |
| `cargo test -p tinicore --features guardrails,sensitive,test-fixtures --test gateway_turn_scope` | 1 passed |
| `cargo test -p tinicore --features guardrails,sensitive,test-fixtures --test guardrails_turn_scope_test` | 8 passed |
| `cargo test -p tinicli --features guardrails --lib -- guardrails` | 3 passed |
| `cargo clippy -p tinicore --features guardrails,sensitive,test-fixtures --lib --tests` | 린트 경고 없음 |
| `cargo clippy -p tinicli --features guardrails --lib` | 린트 경고 없음 |
| `audit_core_layer_deps.py` / `audit_core_product_leak.py` / `audit_core_crate_name_leak.py` (각 `--self-test` 포함) | 3종 모두 clean |

## 인계 시 참고 사항

- 남은 지적은 없습니다. 참고 사항 1은 반영하려면 문자열 한 곳만 바꾸면 되고, 넣지 않아도 됩니다.
- r1 지적 1(forward 캐시)은 r2 판정대로 코드 변경 없이 종결되었고, `Cache::clear_count()` 관측은 하지 않았습니다. 필수는 아닙니다.
- 브랜치는 현재 `origin/main`(`0721ca2692`) 위에 리베이스된 상태이며, 로컬 커밋 2개만 있고 push와 PR은 하지 않았습니다. push와 PR은 각각 별도 지시가 있을 때만 진행합니다.
