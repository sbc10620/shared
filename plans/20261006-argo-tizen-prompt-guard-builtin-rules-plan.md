# argo-tizen prompt guard: tinicore 내장 규칙으로 전환

- 작성일: 2026-10-06
- 상태: 사용자 승인
- 대상 저장소: `AGENTIC/argo-tizen` (`main` `99b883eb`, ARGO `8ead9197ca`까지 tinisync)
- 서브에이전트 검토(코드 대조) 결과를 반영함
## Context

- argo-tizen(`main` `99b883eb`)은 ARGO `8ead9197ca`(PR #3464)까지 tinisync되어, tinicore의 `builtin_user_input_prompt_injection_rules()`를 쓸 수 있다.
- 지금 argot은 baseline 규칙 3개를 자체 상수로 들고 있고, `[safety.prompt_guard] mode = off|warn|block`이 모든 규칙의 action을 일괄로 정한다.
- 사용자 결정(2026-10-06):
  - mode를 `off | on | warn | block` 네 가지로 하고 의미를 문서에 명시한다. `on`은 tinicore가 규칙마다 정한 action을 그대로 쓰고, `warn`/`block`은 모든 규칙을 그 action으로 덮어쓴다.
  - argot 자체 규칙은 위조 태그 2개(`argot_context_forgery`, `turn_context_forgery`)만 남기고, baseline 3개는 tinicore 내장 7개로 바꾼다.
  - 내장 규칙과 action은 별도 처리 없이 설정값을 그대로 따른다. 오탐 대응용 예외, 테스트, 문서 주의 문구는 넣지 않는다. 내장 규칙 자체는 나중에 ARGO 쪽에서 고칠 수 있다.
  - argo-tizen에는 config.toml 규칙 배선을 하지 않는다.
- 원칙: 수정 최소화. `tini/`(tinisync 소유)는 건드리지 않는다. tool output 레이어(`argot-daemon/src/guardrails/mod.rs:52`)와 PII는 바꾸지 않는다.

## mode 의미와 검사 경로별 구성

| mode | loop 안 검사 (`CoreConfig.prompt_guard`) | 저장 전 원문 검사 |
| --- | --- | --- |
| `off` | 없음 | 없음 |
| `on` (신규) | 내장 7개(내장 action: block 6, warn 1) + 제품 규칙(block) | 내장 중 block 6개 + 제품 규칙 + 위조 2개, 모두 block |
| `warn` | 내장 7개 + 제품 규칙, 모두 warn | 위조 2개, warn (지금과 같음) |
| `block` | 내장 7개 + 제품 규칙, 모두 block | 내장 7개 + 제품 규칙 + 위조 2개, 모두 block (지금과 같은 구조) |

- `on`에서 warn 규칙을 저장 전 검사에서 빼는 이유: warn 이벤트가 두 번 나가지 않게 하려는 것이다. `warn` 모드가 이미 같은 원칙을 따른다.
- 겹치는 id 3개는 tinicore 패턴이 argot 패턴을 포함한다(공백에 NBSP와 U+3000을 더 받음). 서브에이전트 검토로 확인했다.

## 수정 파일

1. `crates/argot-config/src/lib.rs`
   - `PromptGuardMode`(547행)에 `On`을 `Off` 다음에 추가하고, 네 변형의 doc 주석에 위 의미를 적는다.
   - `PromptGuardSettings` doc(529, 532~533행)의 "off/warn/block", "baseline" 표현도 고친다.
   - 테스트(3025~3085행 근처): `mode = "on"` 파싱과 저장·재로드 왕복.
2. `crates/argot-config/src/patch.rs`
   - 333행 `values`를 `["off", "on", "warn", "block"]`으로, 335~338행 설명을 새 의미로 바꾼다("baseline" 표현 포함).
   - 1732행 테스트 기대값.
3. `crates/argot-daemon/src/agent_config.rs`
   - `CORE_PROMPT_GUARD_BASELINE_RULES`(87행) 삭제.
   - 내장 규칙 helper: `tinicore::guardrails::builtin_user_input_prompt_injection_rules()`를 부르고 `expect`로 처리한다. 이 함수의 `Err`는 내장 YAML이 깨진 결함 빌드에서만 나고, 호출 지점인 `build_runtime_context`(context_builder.rs:106)는 `Result`를 돌려주지 않기 때문이다.
   - `prompt_guard_config_for_mode`(303행)와 `pre_persist_prompt_guard_config_for_mode`(359행)를 위 표대로 고친다. 기존 `prompt_guard_config` helper(321행)는 덮어쓰기 경로에서 계속 쓴다.
   - `RAW_PROMPT_GUARD_RULES`(102행) 주변과 위 함수들의 doc에서 "baseline"이 가리키는 대상을 tinicore 내장 규칙으로 고친다.
4. `crates/argot-host/src/lib.rs` 422행 `GuardRule` doc
   - `on`에서는 block으로 동작한다는 점을 적는다.
   - 내장 id와 같은 id를 쓰면 생기는 일을 적는다. `on`/`block`에서는 부팅이 실패하고, `warn`에서는 매 턴 loop 안 compile이 실패한다.
5. 테스트 (`agent_config.rs` 816~1050행, `turn/mod.rs`)
   - 상수를 참조하는 테스트는 내장 규칙 수(7) 기준으로 바꾼다. 모드 목록을 도는 루프(832~834, 862~864, 933~935행)에 `On`을 더한다.
   - 신규 단위 테스트:
     - `on`의 loop 구성에서 `invisible_payload`만 warn이다.
     - `on`의 저장 전 구성에 `invisible_payload`가 없고, block 내장 6개와 위조 2개가 있다.
   - 신규 turn 테스트 `run_turn_prompt_guard_on_*`:
     - injection은 저장 전에 거부된다.
     - ZWJ 이모지 메시지는 저장되고 provider에 도달한다.
   - 기존 `run_turn_prompt_guard_*`와 `prompt_guard_baseline_blocks_injection_not_product_talk`는 수정하지 않고 실행만 한다.
6. 문서
   - `docs/book/src/reference/config-schema.md` 431~446행: 네 값의 의미와 내장 규칙의 출처를 적는다.
   - `crates/argot-config/src/default_config.toml` 77~81행: 값 목록과 각 값의 의미.
   - `project/wiki/.../references/argot-config/config.md` 66행: 행 전체(경로 구성, 테스트 이름 포함)를 새 구성에 맞춘다.
   - `docs/book/po/ko.po`: 원문이 바뀌어 번역이 stale 상태가 된다. 저장소에 재생성 절차가 있으면 따르고, 없으면 PR 설명에 적는다.
7. 공유 계획서 `~/Works/shared/plans/20261006-argo-tizen-prompt-guard-builtin-rules-plan.md`
   - 서브에이전트 검토 결과와 위 결정을 반영해 고친 뒤 commit·push한다(공유 문서 관례).

## 기존 기기 동작 변화 (문서와 PR 설명에 적을 것)

- `warn`·`block`의 규칙이 3개에서 7개로 늘어 탐지 범위가 넓어진다.
- 같은 문장이 여러 규칙에 걸리면 warn 이벤트가 늘 수 있다. 예를 들어 "ignore previous instructions"는 이제 `ignore_prior`가 먼저 보고된다.
- `off`(기본값)를 쓰는 기기는 변화가 없다.

## 검증

- `cargo test -p argot-config`
- `cargo test -p argot-daemon agent_config`, `cargo test -p argot-daemon prompt_guard`, `cargo test -p argot-daemon run_turn_prompt_guard`
- `cargo clippy -p argot-config -p argot-daemon -p argot-host --all-targets -- -D warnings`
- 최종 HEAD에서 저장소 preflight를 한 번 실행한다(e2e `chat/prompt_guard_block_mode` 포함).
- `/code-review high` 서브에이전트 리뷰 → 수정 → 재리뷰를 반복한다. 수정할 것이 문서뿐이거나 없을 때 멈춘다.

## 진행 방식

- 브랜치: `main`(`99b883eb`)에서 `dev/byungchul.so/prompt-guard-tinicore-builtin`을 만든다.
- 커밋 1개로 만든다. 메시지 예: `feat(safety): add prompt_guard mode "on" over tinicore's built-in rules`
- push와 PR은 별도 지시가 있을 때만 한다.
- ARGO 규칙 표 삭제는 별도 작업으로 남긴다. 지원 종료 키 처리 방식과 feature 없는 빌드의 처리 방식은 결정을 기다리고 있다.
