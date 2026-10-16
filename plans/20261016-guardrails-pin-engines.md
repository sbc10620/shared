# 가드레일 메모리 개선 (ARGO tinicore) 구현 계획

## Context

- argo-tizen 이슈 #1652(F5)는 가드레일 엔진을 턴마다 다시 빌드하는 churn(도구 턴당 6.0 MB / 62.3k 블록)과 `demask_pattern` churn을 지적한다. TV에서는 엔진을 상주시킨 쪽이 idle PSS가 더 낮았다.
- 이슈 #1652 댓글로 다섯 가지 변경을 약속했다. 모두 ARGO의 tinicore 수정이고, 머지 뒤 argo-tizen이 sync한다.
- 사용자 결정: PR 하나에 커밋 5개(약속한 다섯 가지; prompt guard 규칙의 YAML 중복 검사는 커밋 1의 등록 검사에 포함), pin 설정은 `GuardrailsConfig.pin_engines`(tinicli는 기본값 한 줄만 추가), demask는 실제 토큰과 LLM이 바꿔 쓰는 형태(대소문자, 공백) 기준으로 단순하게, comment_directive 창은 800 **문자**(ClawKeeper 원본과 같게).
- 작업 위치: `~/Works/ARGO`에서 origin/main(`077da95088`) 기준 새 worktree `~/Works/ARGO-guardrails-pin`, 브랜치 `dev/byungchul.so/guardrails-pin-engines`. 로컬 커밋까지만 하고 push/PR은 별도 지시를 기다린다.
- 진행은 dev-cycle(`~/.agents/skills/dev-cycle`, 프로필 `profiles/ARGO.md`)을 따른다.
  - 커밋마다: 명세 → 테스트 에이전트(명세만 받음)가 새 동작의 테스트 작성 → 구현 → 영향 테스트 실행.
  - 다섯 커밋을 모두 구현한 뒤 한 번에: e2e 스위트 → `/code-review`(서브에이전트, high, 전체 범위) → 보고 후 결정 대기 → 수정(관련 커밋에 amend) → 재리뷰. 수정이 문서뿐이거나 없을 때 종료.

## 시작 전 (기준선)

- worktree를 만든 직후, 수정 전에 `profiles/ARGO/scripts/regress_tests.sh <base-dir>`로 077da95088의 전체 테스트 결과를 받아 둔다. 테스트가 추가·이름 변경되므로 PR 직전 `compare_tests.py`의 기준이 된다.
- PII 규칙·엔진은 바꾸지 않으므로 matching regression은 돌리지 않는다.

## 커밋 1: prompt injection 엔진을 하나로 (prompt guard와 tool output이 항상 같은 엔진)

**명세**
- 프로세스에 prompt injection 엔진(`TurnSlot<PatternEngine>`)은 항상 하나다. prompt guard와 tool output guardrail은 언제나 이 엔진을 스캔하고, 스캔 전에 공유 여부를 따지지 않는다.
- 엔진에 들어가는 규칙:
  - 내장 규칙 파일(`rules.yaml`)의 모든 규칙(entity = 규칙 id)
  - host가 tool output에 추가한 `ToolOutputRule`(layer `tool_output`, 지금처럼 내장 id와 겹치면 install 실패)
  - prompt guard 규칙(host가 `CoreConfig.prompt_guard`로 넘기는 `PromptGuardRule` 목록, layer `prompt_guard`). YAML은 바꾸지 않고, 빌드할 때 메모리에서 만드는 `EngineConfig`에만 넣는다.
    - YAML 규칙과 id·pattern이 같은 규칙(예: argot가 넘기는 내장 7개 사본)은 YAML 규칙이 이미 있으므로 따로 넣지 않는다.
    - 나머지 host 규칙(예: argot의 위조 태그 규칙, product 규칙)은 엔진 안에서도 id 그대로 넣는다. 이미 등록된 host 규칙과 id·패턴이 같으면 한 번만 들어간다(argot의 위조 태그 규칙은 tool output 추가 규칙과 prompt guard 규칙 양쪽에 같은 패턴으로 등록되므로 한 항목이 두 layer에 걸림).
- **등록 검사(하나의 규칙)**: 새로 등록하는 규칙의 id가 엔진에 이미 있는 규칙(YAML 규칙 또는 등록된 host 규칙)과 같은데 패턴이 다르면, 등록(prompt guard는 compile, tool output은 install) 때 오류로 거부한다.
  - 지금 prompt guard의 `check_unique_ids`(`agent/prompt_guard.rs:173`)는 자기 목록 안의 중복만 보고 YAML과는 비교하지 않는다. tool output의 `check_added_rules`(`tool_output.rs:77-103`)는 YAML과도 비교한다. 이 검사가 둘을 같은 규칙으로 맞춘다. 자기 목록 안의 중복 검사는 그대로 둔다.
  - id·패턴이 같으면 허용한다. 이 비교에서 action은 보지 않는다(argot는 warn/block 모드에서 action만 바꾼 사본을 넘기고, action은 각 layer가 엔진 밖의 표에서 따로 적용함).
  - YAML의 handwritten 규칙(`base64_decoded_to_shell`, 커밋 5 뒤의 `comment_directive`)은 정규식 패턴이 없으므로 그 id를 쓰는 규칙은 거부한다.
  - 오류 메시지는 규칙 id만 알려 주고, 패턴 내용은 지금처럼 로그나 메시지에 넣지 않는다.
  - argot와 tinicli는 이 경우에 걸리지 않으므로 동작이 바뀌지 않는다. `gateway_prompt_guard_gate.rs`의 `block_rule()`(YAML id `ignore_prior`에 다른 pattern)은 id를 바꾼다.
  - YAML 파싱 결과는 상주시키지 않는다. 등록 함수 안에서 파싱해 이 검사와 커밋 2의 판정에 함께 쓰고 버린다. 등록은 설정이 바뀔 때만 일어나므로(보통 부팅 때 한 번) 턴마다 생기는 비용은 없다.
- 각 layer는 자기 규칙만 본다: prompt guard는 자기 규칙의 entity 목록으로, tool output은 지금처럼 `tool_output` layer로 걸러 본다. 그래서 prompt guard host 규칙은 tool output 결과에 나타나지 않는다.
- prompt guard의 판정(Block/Warn/Sanitize와 재스캔, 규칙 순서, 보고되는 rule id는 선언한 id)은 지금과 같다.
- tool output이 꺼져 있어도 prompt guard는 같은 엔진(내장 규칙 + prompt guard host 규칙)을 쓴다. 그래서 이 구성에서는 엔진이 지금(7패턴)보다 커진다(내장 12패턴 + handwritten detector).

**구현**
- 엔진 소유: 운영 코드에는 전역 슬롯 하나와 host 규칙 저장소 하나만 둔다(PII `pii/shared.rs` `shared_slot()`과 같은 모양). 테스트를 위해 운영 코드 구조를 바꾸지 않는다. `sensitive` feature로 막힌 모듈(`install`, `detector`) 밖에 둔다.
- 테스트 격리는 테스트 쪽에서 한다: 전역 엔진을 건드리는 lib 테스트는 `#[serial]`로 묶고(기존 `prompt_guard.rs` 테스트의 선례), 테스트 전용(`#[cfg(test)]`) 초기화 함수로 각 테스트 시작 때 등록된 host 규칙을 비우고 엔진을 무효화한다. 그래서 같은 id를 다른 패턴으로 쓰는 기존 테스트(`blk`, `zwsp`, `r` 등)를 고치지 않아도 된다. 통합 테스트는 바이너리마다 프로세스가 따로이므로 같은 바이너리 안에서만 이렇게 묶는다. 커스텀 YAML로 만드는 테스트 전용 생성자(`ToolOutputEngine::from_yaml`, `#[cfg(test)]`)는 지금처럼 자기 슬롯을 쓴다.
- 규칙 등록: install(`prompt_injection/install.rs`)은 tool output 추가 규칙을, `compile`(`agent/prompt_guard.rs:271-298`)은 prompt guard host 규칙을 등록한다. 꺼진 layer의 규칙은 등록하지 않고, 모든 검사를 통과한 뒤에만 등록한다. 등록은 누적만 한다. 다른 설정으로 컴파일된 guard가 아직 쓰이는 동안 그 규칙이 사라지면 조용히 통과되기 때문이다.
- 동시성: 등록은 전용 mutex 안에서 "검증 → 반영"을 한 번에 한다(동시에 두 설정이 들어와도 합친 집합이 검증됨). 슬롯의 빌드 함수는 그 시점 규칙 집합의 불변 스냅샷(`Arc`)을 읽는다. 반영한 뒤 저장소 잠금 없이 슬롯을 무효화한다.
- 무효화: `sensitive/turn_scope.rs`의 `TurnSlot`에 함수를 추가해 `pinned`와 `live`를 모두 끊는다. 진행 중인 스캔은 자기가 쥔 `Arc`로 끝까지 가지만, 다음 `acquire`는 반드시 새로 빌드한다(`live`가 남으면 새 규칙이 빠진 옛 엔진이 넘어가 통과될 수 있음).
- `ToolOutputEngine`(`tool_output.rs`)은 이 전역 슬롯을 쓰는 view가 되고, `CompiledGuard`(`prompt_guard.rs:128-139`)는 `PatternFilter::new(전역 슬롯, ActiveFilter::PiiTypes(entity 목록), AUDIT_TAG)`(`engine/filter.rs:47-55, 104`)를 쓴다. prompt guard 쪽은 `#[cfg(feature = "guardrails")]` seam으로 연결하고, `guardrails` feature가 없으면 지금처럼 자기 엔진을 만든다(내장 규칙 파일이 없는 빌드).
- 문서: "자기 엔진" 문장들(`AGENTS.md:284-285, 310, 331-334, 993`, `tool_output.rs:8-11`, `prompt_guard.rs:5-6, 46-58, 136-137, 294-295, 442-445`, `mod.rs:8-22`, `guardrails/mod.rs:15-23`, `prompt_injection/install.rs:4-15, 101-108`, `guardrails/install.rs:187-196`, `bench_prompt_guard_memory.rs:75`, `rules.yaml:46-47`). inbound 스캔에서도 base64 handwritten detector가 돌고 결과만 걸러진다는 점을 적는다.

**테스트**
- 테스트 에이전트(명세만): 등록 검사의 거부·허용 경우(YAML id + 다른 패턴, host 규칙끼리 같은 id + 다른 패턴, handwritten id는 거부 / YAML 사본·action만 다른 사본·같은 id와 패턴은 허용), 두 layer가 한 턴에 엔진을 한 번만 빌드함, 내장 규칙 7개와 host 규칙의 판정이 지금과 같음, prompt guard host 규칙이 tool output 결과에 나타나지 않음, 컴파일 순서(install 전/후)와 관계없이 같은 결과. 전역 상태를 되돌릴 수 없으므로 통합 테스트는 자체 `[[test]]` 바이너리로 둔다.
- 기존 테스트 유지 확인: `a_host_rule_cannot_shadow_a_baseline_rule`(`prompt_guard.rs:1311`)은 그대로 통과해야 한다. `prompt_guard.rs`의 build count·cache 테스트(:1207, 1232, 1463~1560)는 전역 슬롯 기준으로 기대값이 바뀔 수 있다. 바뀌는 테스트는 모두 보고한다.
- 구현자: 규칙 저장소와 등록 helper 단위 테스트. 엔진 크기는 패턴 수 대신 규칙 수(`pattern_count() == 13` 류)로 확인한다(커밋 5에서 regex/handwritten 구성이 바뀜).

## 커밋 2: 알려진 규칙의 부팅 검증 빌드 생략

**명세** (PR #1641의 `unverified_rules` / `build_added`를 ARGO로 옮기되, 커밋 1의 단일 엔진에 맞춘다)
- 규칙을 등록할 때(install의 tool output 추가 규칙, `compile`의 prompt guard 규칙) 새로 들어가는 규칙이 없으면 검증 빌드를 하지 않는다. 예: prompt guard 규칙이 모두 내장 규칙과 같을 때, tool output 추가 규칙이 없을 때.
- 새 규칙이 있으면 지금처럼 버리는 빌드로 검증하되, 새 규칙만이 아니라 **엔진에 들어갈 전체 규칙**(내장 + 등록된 규칙 + 새 규칙)으로 빌드한다. "하나씩은 빌드되지만 합치면 안 되는" 실패를 놓치지 않기 위해서다(`prompt_guard.rs:230-235`, `tool_output.rs:60-65`). 실패하면 지금처럼 문제 규칙을 이름으로 알려 준다.
- 내장 규칙과 같은지 판정할 때 YAML 파싱 결과는 상주시키지 않는다. 등록 함수 안에서 파싱해 쓰고 버리며, 커밋 1의 등록 검사와 같은 파싱 한 번을 함께 쓴다. 그래서 PR #1641처럼 부팅 때 파싱이 한 번 더 생기는 것(+132 KiB churn)은 남지만, 상주 메모리는 늘지 않는다.
- 잘못된 패턴은 지금처럼 부팅(compile/install) 때 실패한다.

**구현**: `prompt_guard.rs:288`, `tool_output.rs:185`의 검증 분기를 커밋 1의 등록 함수로 옮긴다. 관련 문서(`prompt_guard.rs:41-45, 119-122, 243-246`, `tool_output.rs:128-131, 183-184`, `guardrails/install.rs:180-182`, `mod.rs:331-335`).

**테스트**
- 테스트 에이전트: 내장 규칙만 있을 때 검증 빌드가 없음, 잘못된 추가 규칙·사용자 규칙은 여전히 실패, 합쳐서만 실패하는 경우.
- 기존 테스트 유지 확인: `an_added_rule_with_a_bad_pattern_is_named`, `added_rules_reach_the_guardrail_and_a_bad_one_fails_the_install`, `bad_regex_is_config_error_not_panic`(unit/e2e), `rules_that_do_not_compile_fail_the_request`, `engine_is_built_once_per_turn_once_the_slot_is_registered`(`Some(0)`).
- 내장 규칙이 컴파일된다는 보장: `mod.rs:440` `every_rule_pattern_compiles`에 더해 prompt_guard 7개 집합의 빌드 테스트(구현자).

## 커밋 3: `GuardrailsConfig.pin_engines`

**명세**
- `pin_engines: bool`, 기본값 false. true면 `install_guardrails_from_config`가 무엇이든 빌드하기 전에 `turn_scope::pin_for_process()`(`sensitive/turn_scope.rs:113-118`)를 부른다.
- pin 상태에서 tool output layer가 켜져 있으면 install이 prompt injection 엔진도 바로 빌드해서 상주시킨다. 꺼져 있으면 미리 빌드하지 않는다(아무도 안 쓰는 엔진이 상주하지 않게). 나중에 compile이 새 host 규칙을 등록하면 그 빌드는 무효화되고 다음 스캔에서 다시 빌드·상주한다.
- "pin이면 버리는 검증 빌드 대신 엔진을 바로 빌드해 상주"하는 분기는 커밋 1의 공용 등록 함수에 두어, install과 compile 모두에 적용한다. 그래서 pin 상태에서는 버리는 빌드가 없다.
- 결과: 부팅 뒤 PII 엔진과 prompt injection 엔진(prompt guard와 tool output이 함께 씀)이 상주하고, 이후 턴에서 다시 빌드하지 않는다. 나중에 등록으로 규칙이 바뀌면(커밋 1의 무효화) 그때 한 번 다시 빌드해서 다시 상주한다.
- false면 동작이 지금과 같다. tinicore 기본값은 false이고 argot가 켠다(제품별 기본값).

**구현**: `guardrails/install.rs`(`GuardrailsConfig` 42-50, 설치 순서 183~), 공용 등록 함수(pin이면 `acquire`), 문서(`install.rs:145-149`, `turn_scope.rs:91-93`, `GuardrailsInstallError::PromptInjection`의 "엔진 빌드 실패를 잡는다"는 설명과 tinicli `cli_entry.rs`의 해당 분기 주석). tinicli `cli_entry.rs:436-443`의 struct 리터럴에 `pin_engines: false` 한 줄(동작 변경 없음).

**테스트**: 테스트 에이전트가 자체 `[[test]]` 바이너리(플래그를 되돌릴 수 없음)로 pin true일 때 상주·재빌드 없음·공유를 확인한다. 기존 `tests/guardrails/turn_scope_test.rs:285`(false일 때 상주 없음)는 그대로 통과해야 한다.

## 커밋 4: demask 정규식 → byte scan (실제 토큰과 LLM이 바꿔 쓰는 형태 기준)

**명세** (`tinicore/src/sensitive/redaction.rs`, 지금 `demask_pattern` 959-985)
- 기준은 마스킹이 실제로 만드는 토큰 `[SENS:PII:<LABEL>:<counter>:<nonce>]`(label은 고정 영문 대문자, counter는 ASCII 숫자, nonce는 소문자 hex 12자; `try_mint`, `fresh_nonce`)과, LLM이 다시 쓸 때 흔히 바꾸는 형태(대소문자, 끼어든 공백)다. 기존 테스트가 확인하는 것도 이 범위다.
- 받아들이는 것: `SENS`·`PII`·label·nonce는 ASCII 대소문자 구분 없음, 각 자리 사이와 nonce 글자 사이의 공백은 `char::is_whitespace`(NBSP, U+3000, `\x0B` 포함), counter는 ASCII 숫자, label `[A-Za-z0-9_-]+`, nonce는 hex 정확히 12자. 가장 왼쪽 우선·겹치지 않음, 실패한 후보 뒤에는 그 시작 다음의 `[`부터 다시 찾음, 일방향 `[SENS:PII:PHONE]`은 매치하지 않음.
- 지금 정규식과 달라지는 것은 `(?i)`의 Unicode 대응(`ſ`, Kelvin 기호 `K`)과 비ASCII 숫자 counter뿐이다. 이런 토큰은 마스킹이 만들지 않고 대부분 지금도 복원되지 않는다. 이 차이는 문서에 적는다.
- `canonical_token` 규칙(label ASCII 대문자, counter 그대로, nonce 공백 제거 후 소문자)과 Cow 동작(매치가 하나라도 있으면 Owned, 없으면 Borrowed)도 그대로다. `egress.rs`의 `content_was_corrected`가 이 동작에 기대기 때문이다.
- 할당 없음: 스캔 자체와 `contains_placeholder`는 할당하지 않는다. 정규식 컴파일과 스레드별 cache가 사라진다.

**구현**: `demask_pattern`을 걷어내고 `contains_placeholder`(1002), `demask_inner`(1090), `collect_tokens`(1153), 테스트 `label_matcher_is_wider_than_todays_labels`(1712)를 스캐너로 바꾼다. 정규식을 언급하는 주석(redaction.rs 42-46, 397-412, 1259-1264, pii_masking.rs 2679-2682, 2697-2699, 2975-2988, 3030, `sensitive/mod.rs:43-44`)을 고친다.

**테스트**
- 테스트 에이전트: 지금 테스트가 없는 경우들(끝나지 않은 `[SENS:PII:` 반복, nonce 11·13자와 12자 안의 비hex, 0으로 시작하는 counter, 슬롯 안의 NBSP·U+3000·U+2028·`\x0B`, 토큰 안의 `\n`, 비ASCII 숫자 counter는 매치하지 않음, 실패 후보 뒤 재탐색 `[SENS:PII:EMAIL:1:[SENS:PII:EMAIL:1:<nonce>]`, 모르는 토큰만 있을 때 Owned).
- 구현자: 지금 정규식과 스캐너를 고정 입력 목록으로 비교하는 동등성 테스트(선례 `card_detector.rs`의 regex 비교). 목록에서는 의도한 차이(`ſ`, `K`, 비ASCII 숫자)를 뺀다. 무작위 대량 비교는 CI 밖에서 한 번만 돌리고 결과를 커밋 메시지에 남긴다.
- 기존 테스트 유지: redaction.rs의 whitespace·case·nonce 테스트들, pii_masking.rs 3836, 4023, 4117, `sensitive_slim.rs:521`, `pii_masking_e2e.rs`, `pii_masking_egress_e2e.rs`(스트림 청크 분할).

## 커밋 5: comment_directive → handwritten detector (창 800 문자)

**명세** (`prompt_injection/config/rules.yaml:184-208`)
- 규칙 id·action(block)·label(comment_directive)·layer(tool_output)는 그대로이고, `HandWrittenRecognizer`로 바뀐다.
- 여는 표시 `<!--`, `/*`, `#`+공백*+`maintainer-note`(ASCII `\b` 양쪽), 그 뒤 **800 문자 이내**에 트리거 `also`+공백+(run|dump|cat|read|show|exfil), `please`+공백+(include|always|verify), `~/.ssh/`, `~/.aws/`. 대소문자 무시는 ASCII, 줄바꿈 포함, 공백은 ASCII 공백·U+00A0·U+3000(규칙 파일의 WS).
- 매치는 지금 엔진과 같은 방식으로 낸다: 트리거마다 (조건을 만족하는 **가장 이른** 여는 표시의 시작, 트리거 끝)을 원시 매치로 내고, 시작점별 가장 긴 매치 선택과 겹침 제거는 엔진의 정리 단계(`validate_and_collapse`)에 맡긴다.
- 창의 정의: 여는 표시의 끝에서 트리거의 시작까지 800 문자 이하(트리거 자체는 창 밖으로 나가도 됨). 공백에는 `\x0B`도 포함한다. 알고리즘은 텍스트 길이에 비례해야 하며, 여는 표시마다 800자를 다시 훑지 않는다.
- 의도한 차이는 하나뿐이다: 창을 바이트가 아닌 문자로 센다. 그래서 `<!-- ` + 한글 300자 + ` please include …`가 새로 잡힌다. ASCII 텍스트에서는 결과가 지금과 같다.

**구현**: detector는 `prompt_injection/handwritten/` 안에 `base64_shell_detector.rs`와 나란히 선언하고, `prompt_injection::extensions()`(`mod.rs:388-393`)의 handwritten builder를 통해 engine extension으로 붙인다. `build_handwritten_detectors`(`handwritten/mod.rs:22-42`)가 entity_type으로 매핑하고, pid는 `handled`에 들어간 순서대로 붙인다(설정이 `HashMap` 순서로 들어오므로). layer가 `tool_output`이므로 prompt guard의 필터에는 걸리지 않는다. rules.yaml의 KNOWN GAP 주석(189-200)과 낡은 경로(212), `mod.rs`의 출처 설명(47-52, 76-82, 141, "9개를 그대로 옮김"), `AGENTS.md`(351-363, Known gaps)를 고친다.

**테스트**
- 테스트 에이전트: 한글 300자 케이스, 800·801 문자 경계, 세 여는 표시와 트리거 조합, 공백 변형, 대소문자, TODO 주석 통과.
- 기존 테스트 유지: `mod.rs:654, 737, 453, 501`, `detector.rs:600, 616, 634, 673, 741`(span이 `also` 앞에서 시작해 겹쳐야 함).
- 구현자: 지금 정규식과의 비교 테스트(ASCII 고정 목록은 같아야 하고, 비ASCII 창 차이만 허용). 목록에 여는 표시가 이어지거나 겹친 경우를 넣는다. 무작위 대량 비교는 CI 밖에서 한 번.
- 효과 확인(로컬만, 숫자는 커밋 메시지·이슈에 넣지 않음): tool output 엔진의 NFA·최소 cache 감소.

## 검증 (프로필 기준)

- **커밋마다 구현한 직후**: `cargo fmt --all -- --check`, clippy(`-p tinicore --features guardrails,sensitive,test-fixtures --all-targets`, 커밋 3은 `-p tinicli` 두 lane도), 그 커밋이 건드린 모듈의 테스트(디버그). 범위: lib `-- prompt_injection prompt_guard guardrails turn_scope sensitive`, `--test prompt_guard_e2e --test prompt_injection_install_e2e --test gateway_prompt_guard_gate --test sensitive_slim --test pii_masking_e2e --test pii_masking_egress_e2e`, `--test guardrails_turn_scope_test`, `--test guardrail_layers_e2e`, 새 `[[test]]` 바이너리 가운데 해당하는 것. install을 건드리는 커밋(1·2·3)은 `--test guardrails_country_install_test`도, tinicli를 건드리는 커밋 3은 `cargo test -p tinicli --lib`를 `guardrails` 켜고/끄고 둘 다 돌린다.
- **feature 경계 검사**(새 seam이 `guardrails` feature에 걸치므로, 커밋 1·4 뒤): `cargo test -p tinicore --no-default-features --lib`, `cargo clippy -p tinicore --features test-fixtures --all-targets`, `cargo check -p tinicore --features guardrails --all-targets`(sensitive 없이).
- **다섯 커밋을 모두 구현한 뒤 한 번**: `argo-e2e` 스킬(release, guardrails 켬)의 prompt guard·tool output·PII masking 스위트, 그다음 전체 범위(`077da95088..HEAD`)에 대한 `/code-review` 루프. 리뷰 수정 라운드마다 그 수정이 영향을 주는 테스트만 다시 돌린다.
- **PR 직전 최종 HEAD에서 한 번**: `regress_tests.sh` + `compare_tests.py`(기준선 대비 새 실패 없음, 추가·변경 테스트 명시), argo-e2e 전체 스펙, Core 감사 4종, 입력 처리 변경(커밋 4·5)이므로 panic 감사 3종, 브랜치 작업 상태 메모리 갱신.

## 머지 뒤 후속 (argo-tizen, 이번 PR 범위 밖)

- **sync 전에 먼저**: argot의 `GuardrailsConfig` 리터럴(`crates/argot-daemon/src/guardrails/mod.rs`)도 필드를 모두 나열하므로, 이 PR이 머지되기 전에 argot에 `..Default::default()`를 넣어 둔다. 그렇지 않으면 sync하는 순간 argot가 컴파일되지 않는다.
- `tini/` sync, argot `guardrails_config`에 `pin_engines` 배선.
- argot 설정 키(예: `[safety] pin_engines`, 기본 켬)와 `SafetyConfig::is_empty`·`patch.rs` describe·`default_config.toml` 반영.
- PR #1641에는 `tini/` 가드레일 수정을 빼고 sync로 받도록 알린다.
- TV에서 idle PSS 재측정. 측정용 worktree `~/Works/argo-tizen-memprobe`의 로컬 hack은 정리 대상이다.

## 이슈 #1652 댓글 정정

댓글 5번 항목의 "내장 규칙은 한 번만 파싱하므로 재파싱 문제가 생기지 않는다"는 이 결정과 맞지 않는다. 승인 뒤 "파싱 결과는 상주시키지 않고, compile 때 한 번 파싱해 쓰고 버린다"로 고친다.

## 계획 문서 공유

승인 뒤 이 계획을 `~/Works/shared/plans/20261016-guardrails-pin-engines.md`로 옮겨 commit·push한다(공유 문서 관례).
