# ARGO #3413 턴 재빌드 브랜치 재리뷰 결과 (2026-09-15, r2)

이전 리뷰(`260915_ARGO_review-3413-turn-rebuilds.md`)의 지적 3건에 대한 구현자 처리 결과를 검증하고, amend된 첫 커밋을 다시 읽은 결과입니다.

## 리뷰 대상

- 레포: `~/Works/ARGO`
- 브랜치: `dev/byungchul.so/guardrails-turn-rebuilds`
- 범위: `origin/main...dev/byungchul.so/guardrails-turn-rebuilds` (로컬 커밋 2개, push·PR 없음)
- merge-base: `c873b9ca82` (현재 `origin/main`은 `0721ca2692`로 #3412 머지 1건만큼 앞서 있고, 이 브랜치의 변경 파일 17개와 겹치는 파일은 없습니다. 아래 검증은 merge-base 기준입니다.)
- 관련 이슈: #3413

### 커밋

| 해시 | 제목 | 이전 리뷰 이후 |
|---|---|---|
| `8bd284ccd4` | perf(guardrails): build the PII engine once per turn and once at boot (#3413) | amend됨 (아래 참고) |
| `68bd35e427` | perf(guardrails): compile each chunk's NFAs once per engine build (#3413) | 변경 없음 (확인함) |

### amend된 차이 (`9878a76895` → `HEAD`)

`git diff 9878a76895 HEAD`로 대조했고, 구현자 설명과 일치합니다. 3개 파일 20줄 추가·11줄 삭제이며, `recognizer.rs`는 손대지 않았습니다.

- `tinicli/src/guardrails/pii.rs`: `install_pii` 래퍼가 에러 문자열 끝에 ` (config.toml)`을 덧붙임.
- `tinicore/src/agent/loop_/wrap_up.rs`: memorize 가드에 시간 상한을 두지 않는 이유를 주석으로 명시.
- `tinicore/src/guardrails/install.rs`: `LayerBuild` 메시지에서 `in config.toml` 제거, 모듈 문서·함수 문서의 `ARGO_GUARDRAIL_DENY_INPUT`을 `install_guardrails_from_env` 기준 문구로 교체, 엔진 수명 서술을 "턴의 사후 작업까지 끝나면 해제"로 수정.

## 결론

동작을 깨뜨리는 정합성 버그는 이번에도 없습니다. 이전 지적 3건 중 1번은 코드 변경 없이 종결해도 되고, 2번은 정책(시간 상한 없음)은 타당하지만 "턴의 진짜 끝"이라는 새 문서 서술이 실제 코드와 어긋나는 지점이 하나 있으며, 3번은 파일 이름은 제거되었으나 같은 부류의 문구가 한 단계 아래에 남아 있습니다. 새로 보고하는 지적은 4건이고, 그중 1건(reflect 훅)은 이 이슈가 없애려던 재빌드가 특정 호스트에서 한 번 남는 것이라서 PR 전에 처리하는 편이 좋겠습니다.

## 이전 지적별 검증 결과

### 1. `recognizer.rs:746` forward 캐시 감소 → 코드 변경 없이 종결 가능

구현자의 배제 논리는 "캐시 용량이 원인인가"에 대해서는 빈틈이 없습니다. 더 나아가 구조적으로 보면 이 커밋은 실행되는 DFA 자체를 바꾸지 않으므로, 실제 스캔 회귀는 있을 수 없습니다. 근거는 regex-automata 0.4.14 소스에서 직접 확인했습니다.

- `hybrid::dfa::Builder::syntax()`는 내부 `thompson::Compiler`에 그대로 전달되고(`hybrid/dfa.rs:4147`), `build_many`는 `WhichCaptures::None`을 강제한 뒤 `build_from_nfa`를 호출합니다(`hybrid/dfa.rs:4021-4036`). 따라서 기존 코드가 내부적으로 만들던 forward NFA와 새 `compile_chunk_nfas`의 forward NFA는 동일하고, reverse도 `reverse(true)` + `None`으로 동일합니다.
- `minimum_cache_capacity`는 `nfa.states().len()`에 비례합니다(`hybrid/dfa.rs:4344-4346`). 기존 측정은 capture 상태가 붙은 NFA로 쟀으므로 DFA가 실제로 쓰지 않는 상태 수만큼 부풀려져 있었고, 37KB→32KB는 구현자 설명대로 측정값이 정확해진 것입니다.
- 결국 두 빌드의 차이는 `cache_capacity` 인자 하나뿐이고, 그것을 112KB로 강제해도 dense 수치가 그대로였다면 남는 설명은 측정 잡음이나 바이너리 배치 차이입니다. 번갈아 4회 측정으로는 4%를 잡음과 구분할 검정력이 없습니다.

남은 제안은 "재측정"이 아니라 "직접 관측"입니다. `hybrid::dfa::Cache::clear_count()`(`hybrid/dfa.rs:2013`)가 캐시 clear 횟수를 그대로 돌려주므로, dense 텍스트 스캔 후 이 값이 변경 전후 모두 0이면 용량 논쟁은 구조적으로 끝납니다. 이는 시간 측정보다 강한 근거이고 비용도 작습니다. 코드 변경은 필요 없습니다.

부수 확인: 기존 `measure_chunk_cache_caps`에 있던 빈 청크 방어(`if chunk_strs.is_empty()` → 64KB 폴백)가 새 코드에는 없는데, `pattern_strs.chunks(chunk_size)`(`recognizer.rs:235`)는 빈 슬라이스를 내지 않으므로 도달 불가능한 경로가 제거된 것입니다. 지적 사항이 아닙니다.

### 2. `wrap_up.rs:267` memorize 가드 시간 상한 → 정책은 타당, 문서 서술은 한 곳 어긋남

시간 상한을 두지 않는 결정 자체는 반대할 근거가 없습니다. memorize와 intervention check가 스캔을 하는 이상 그 전에 엔진을 놓으면 재빌드가 그대로 생기고, 훅이 안 끝나는 것은 훅의 버그라는 논리도 맞습니다. `wrap_up.rs` 주석과 커밋 메시지도 이 결정을 정확히 기록하고 있습니다.

다만 "memorize는 턴의 마지막 작업이고 그것이 턴의 진짜 끝"이라는 서술, 그리고 `install.rs:44-46`의 "detached post-turn tasks (memorize, intervention check — they scan too)"라는 열거는 실제 코드와 다릅니다. 사후 detached task는 셋이고, 셋째인 `spawn_post_task_reflect`는 가드를 받지 않습니다. 상세는 아래 새 지적 1번에 적었습니다.

수명 서술에서 한 가지 더 확인한 점은 문제는 아니지만 인계 시 알아 둘 만합니다. `turn_guard()`는 등록된 모든 슬롯을 프로세스 전역으로 pin하므로, 게이트웨이처럼 턴이 동시에 여러 개 돌면 엔진은 "이 턴"이 아니라 "겹치는 모든 턴의 사후 작업"이 끝날 때 해제됩니다. 문서의 "the turn's work"는 단일 턴 기준의 근사이고, 동시성 환경에서는 더 오래 살 뿐 더 짧게 살지는 않으므로 안전한 방향입니다.

### 3. `install.rs:174` Core에 CLI 전용 문구 → 파일 이름은 제거됨, 형식 가정은 남음

`config.toml`과 `ARGO_GUARDRAIL_DENY_INPUT`은 확실히 제거되었고, `install_guardrails_from_env`는 `tinicore/src/agent/guardrails.rs:1152`에 있는 Core 함수이므로 대체 문구는 적절합니다. Core 감사 스크립트 3종도 통과합니다.

그러나 "파일 이름"만 빠졌고 "파일 형식"은 남아 있습니다. `[pii_filter_labels]` 대괄호 표기는 TOML 테이블 문법이고, `pii_filter_labels.{layer}`는 TOML 점 경로입니다. 이 문구는 문서뿐 아니라 운영자용 에러 문자열에도 들어가서 `LayerBuild { detail }`을 통해 비 TOML 호스트의 운영자에게 그대로 전달됩니다. 감사 스크립트의 토큰 집합은 브랜드·페르소나 이름(`argo`, `siri`, `alexa`, `bixby`, `galaxy`, `samsung`)뿐이라 이 부류는 잡지 못합니다. 상세는 새 지적 3번입니다.

또한 amend에서 추가된 tinicli 래퍼의 ` (config.toml)` 접미사가 에러 3종 전부에 붙어서, 설정 오류가 아닌 에러에도 설정 파일을 가리키게 되었습니다. 새 지적 2번입니다.

## 새 지적 사항

| # | 위치 | 판정 | 심각도 | 요약 |
|---|---|---|---|---|
| 1 | `tinicore/src/agent/loop_/wrap_up.rs:434`, `tinicore/src/guardrails/install.rs:44` | CONFIRMED | 낮음~중간 | 셋째 사후 task `spawn_post_task_reflect`는 가드를 받지 않아 argo-pc·tiniffi에서 reflect가 발화하는 턴마다 재빌드 1회가 남고, 새 문서 서술("턴의 진짜 끝")이 이를 빠뜨림 |
| 2 | `tinicli/src/guardrails/pii.rs:75` | CONFIRMED | 낮음 | ` (config.toml)` 접미사가 `GuardrailMerge`·`MaskingSlotTaken`에도 붙어 "not a configuration error"라는 본문과 모순 |
| 3 | `tinicore/src/guardrails/install.rs:213,253,262` 및 필드 문서 | CONFIRMED | 낮음 | 운영자용 에러 문자열에 TOML 문법(`[pii_filter_labels]`, `pii_filter_labels.{layer}`)이 남아 있음, 감사 스크립트가 잡지 못하는 유형 |
| 4 | `tinicore/src/guardrails/install.rs:174,186` | PLAUSIBLE | 낮음 | "the process will not start", "Refusing to start"가 부팅 중단 호스트를 가정하는데, 같은 파일의 `layer_build_failure` 문서는 "a later reconfiguration"이 이 경로에 올 수 있다고 적음 |

### 1. `spawn_post_task_reflect`에 가드 인계 없음 (`wrap_up.rs:434`, `install.rs:44`)

`agent_loop`는 `loop_.rs:1479`에서 가드를 잡고 함수 반환 시 놓습니다. 그 안에서 사후 detached task 셋을 띄웁니다: memorize(`loop_.rs:6825`), intervention check(`loop_.rs:6830`), post-task reflect(`loop_.rs:6977`). 앞의 둘은 이번 커밋에서 `turn_guard()`를 받아 task 안으로 옮기지만, 셋째는 받지 않고 `JoinHandle`도 버려집니다("the loop must never await reflection").

reflect 훅은 LLM 작업을 합니다. argo-pc의 `PcPostTaskHook::draft_skill`(`argo-pc/rust-backend/src/self_evolving.rs:490`)은 `run_subagent`를 호출하고, 그 구현(`self_evolving.rs:280-`)은 `AgentLoopConfig`를 만들어 중첩 `agent_loop`를 돌립니다. tiniffi의 `AndroidPostTaskHook`(`tiniffi/src/self_evolving_maintenance.rs:1228`)도 문서상 "async LLM work (drafting)"를 합니다. 중첩 루프는 자기 가드를 잡으므로 그 안에서는 1회 빌드지만, 바깥 루프의 가드와 memorize·intervention 가드가 이미 놓인 시점이면 그 1회가 곧 이 이슈가 없애려던 재빌드입니다. 발화 조건(훅이 배선됨 + 자연 완료 + 정책 통과)이 붙어 있어 매 턴은 아니지만, 발화하는 턴에서는 턴당 빌드가 1이 아니라 2입니다.

tinicli는 `post_task_reflect: None`이라 벤치와 테스트에서 보이지 않습니다. 배선하는 호스트는 `argo-pc/rust-backend/src/bridge.rs:17707`과 `tiniffi/src/lib.rs:27526`입니다.

문서 쪽 영향: `install.rs:44-46`의 "released once the turn's work, including its detached post-turn tasks (memorize, intervention check — they scan too), has finished"는 셋 중 둘만 열거하고, `wrap_up.rs` 주석의 "memorize is the turn's own last piece of work"는 순서상으로도 reflect가 더 뒤에 띄워지므로 정확하지 않습니다.

제안: 다른 두 곳과 같은 3줄(`let turn_scope = turn_guard();` → `async move { let _turn_scope = turn_scope; … }`)을 `spawn_post_task_reflect`의 바깥 spawn에 넣고, 문서 열거에 reflect를 추가합니다. 시간 상한 없음 정책은 그대로 두면 됩니다. 이것을 이 PR에 넣을지 후속으로 뺄지는 사용자 결정입니다만, 커밋 메시지의 "Turn (2-3 -> 1)" 주장이 이 호스트들에서는 성립하지 않으므로 최소한 메시지에는 반영하는 편이 좋겠습니다.

### 2. ` (config.toml)` 접미사가 에러 3종 전부에 붙음 (`tinicli/src/guardrails/pii.rs:75`)

`.map_err(|e| format!("{e} (config.toml)"))`는 `GuardrailsInstallError`의 세 변형 모두에 적용됩니다. `GuardrailMerge`의 본문은 "This is a boot-ordering bug, not a configuration error — report it rather than working around it."인데 그 뒤에 `(config.toml)`이 붙고, `MaskingSlotTaken`도 설정 파일로 고칠 수 있는 오류가 아닙니다. 이전 코드(`c873b9ca82`의 `tinicli/src/guardrails/pii.rs:343`)는 `LayerBuild` 메시지 안에서만 `config.toml`을 언급했으므로, 이 amend는 CLI 사용자에게 "이전과 같은 안내"가 아니라 두 경로에서는 잘못된 안내를 추가한 것입니다.

제안: `LayerBuild`에만 접미사를 붙이도록 `match`로 분기하거나, 접미사 대신 `LayerBuild`의 "set `pii_mode = \"off\"`" 문장 뒤에 CLI 쪽에서 "in config.toml"을 이어 붙이는 형태로 바꿉니다.

### 3. TOML 문법이 운영자용 에러 문자열에 남아 있음 (`install.rs:213,253,262`)

- `check_filter_label_layers`(`install.rs:213`): `"unrecognized layer key(s) {unknown:?} in [pii_filter_labels] — valid keys are …"`
- `override_kinds_for_layer`(`install.rs:253`): `"unrecognized PII label {label_str:?} in pii_filter_labels.{layer}"`
- 같은 함수(`install.rs:262`): `"PII label {label_str:?} in pii_filter_labels.{layer} has no recognizer — …"` (경고 문자열)
- `PiiConfig` 필드 문서(`install.rs:85,90`): `` (`[pii_demask_tool_args]`) ``, `` (`[pii_filter_labels]`) ``

앞의 셋은 `LayerBuild { detail }`과 `GuardrailsInstall::warnings`를 통해 호스트가 그대로 운영자에게 보여 주는 문자열입니다. 대괄호와 점 경로는 TOML의 표기이고, JSON이나 프로그램 API로 설정을 넘기는 호스트(tiniffi 등)에서는 존재하지 않는 표기입니다. `config.toml`이 파일 이름이었다면 이것은 파일 형식이라서 같은 부류의 한 단계 아래이며, 감사 스크립트가 잡지 못하는 유형이라는 점도 같습니다.

한편 `pii_mode`, `pii_filter_labels`, `pii_demask_tool_args`라는 키 이름 자체는 `PiiConfig`의 필드 문서에서 Core의 어휘로 정의되어 있으므로 문제가 아닙니다. 제안: 대괄호와 점 경로만 빼고 `pii_filter_labels` 키 이름과 층 이름으로 표현합니다(예: `"… in pii_filter_labels (layer {layer})"`). 심각도 판단은 사용자 몫입니다.

그 밖에 `install.rs:4`의 "a host (tinicli, argot, …)"와 `install.rs:10`의 "This code lived in `tinicli::guardrails::pii`"는 Core 문서 안에서 상위 호스트 이름을 부르는 문구입니다. 후자는 이력 설명이라 남겨도 되지만, 전자는 예시일 뿐이므로 빼도 의미가 줄지 않습니다. crate-name 감사 스크립트는 베이스라인 대비 증가만 잡으므로 통과했습니다.

### 4. "process will not start" 계열 문구의 호스트 가정 (`install.rs:174,186`)

`LayerBuild`의 "`pii_mode` is set, so this configuration cannot be enforced and the process will not start"와 `MaskingSlotTaken`의 "Refusing to start"는 호스트가 부팅을 중단한다는 전제를 담고 있습니다. 같은 파일의 `layer_build_failure` 문서(`install.rs:409`)는 "for hosts that have a logger installed by the time a later reconfiguration could hit this"라고 적어 재설정 경로를 예상하고 있어서, 그 경로에서는 메시지가 사실과 다릅니다. 라이브러리 호스트(tiniffi)는 프로세스 시작 여부를 결정할 수 없고 앱에 에러를 돌려줄 뿐이기도 합니다. 모듈 문서의 계약("A host must not serve turns after receiving one")을 그대로 쓰면 어느 호스트에서도 참입니다. 낮은 심각도이고, 3번과 함께 처리하면 됩니다.

## 검증 실행 결과

모두 merge-base `c873b9ca82` 기준 현재 워킹 트리에서 실행했습니다.

| 명령 | 결과 |
|---|---|
| `cargo test -p tinicore --features guardrails,sensitive,test-fixtures --lib -- guardrails::install` | 30 passed |
| `cargo test -p tinicore --features guardrails,sensitive,test-fixtures --lib -- turn_scope_handoff` | 1 passed |
| `cargo test -p tinicore --features guardrails,sensitive,test-fixtures --test gateway_turn_scope` | 1 passed |
| `cargo test -p tinicore --features guardrails,sensitive,test-fixtures --test guardrails_turn_scope_test` | 8 passed |
| `cargo test -p tinicli --features guardrails --lib -- guardrails` | 3 passed |
| `cargo clippy -p tinicore --features guardrails,sensitive,test-fixtures --lib --tests` | 린트 경고 없음 (출력된 warning은 스킬 번들러 build script 메시지뿐) |
| `cargo clippy -p tinicli --features guardrails --lib` | 린트 경고 없음 (동일) |
| `audit_core_layer_deps.py` / `audit_core_product_leak.py` / `audit_core_crate_name_leak.py` (각 `--self-test` 포함) | 3종 모두 clean |

참고: `tinicore/tests/guardrails/turn_scope_test.rs`의 바이너리 이름은 `guardrails_turn_scope_test`입니다(`tinicore/Cargo.toml:2040`). 구현자 검증 명령에는 이 바이너리와 `gateway_turn_scope`가 빠져 있었는데, 둘 다 통과했습니다.

## 인계 시 참고 사항

- 새 지적 4건은 모두 미처리 상태입니다. 1번은 코드 3줄과 문서 수정, 2번은 `match` 분기, 3·4번은 문자열 수정이며, 처리 여부와 이 PR 포함 여부는 사용자 결정이 필요합니다.
- 이전 지적 1번은 코드 변경 없이 종결해도 됩니다. 원하면 `Cache::clear_count()` 관측 한 번으로 근거를 보강할 수 있습니다.
- 브랜치는 로컬 커밋만 있고 push와 PR은 아직 하지 않았습니다. push와 PR은 각각 별도 지시가 있을 때만 진행합니다.
- 브랜치가 `origin/main`보다 1 머지(#3412) 뒤에 있지만 겹치는 파일은 없으므로 리베이스는 선택 사항입니다.
