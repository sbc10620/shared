# PROVENANCE — 규칙 출처와 제외 근거

이 레포의 세 스킬은 [`dev-pipeline`](https://github.com/sbc10620/dev-pipeline)의 역할 프롬프트
(`agents/skills/dev-pipeline/agents/dp-*.md`)에서 **원칙만** 추출한 것이다.

`dev-pipeline`의 역할 프롬프트는 실제 인시던트마다 규칙이 추가되며 계속 갱신되는 파일이다
(8.1.0 기준 `dp-implementor.md` 규칙 13·14가 최근 추가분). 상류가 바뀌었을 때 **여기서 무엇을
다시 봐야 하는지** 알기 위해 이 대응표를 유지한다.

**이 추출은 단방향이며 자동 생성이 아니다.** 규칙의 근거를 새로 쓰고 분량을 절반 이하로 압축해야
했기 때문에 기계적 생성이 성립하지 않는다. 상류 변경은 손으로 반영한다.

원본 표기: `impl` = `dp-implementor.md`, `test` = `dp-test-implementor.md`,
`rev` = `dp-reviewer.md`, `plan-rev` = `dp-plan-reviewer.md`, `planner` = `dp-planner.md`.
`R<n>` = Global Rule 번호, `S<n>` = Workflow Step 번호.

---

## planning-discipline

| 스킬 구획 | 출처 |
|---|---|
| Rule 1 모호하면 물어라 | planner R2 |
| Rule 2 추출하되 발명하지 마라 | planner R3 |
| Rule 3 한 증분으로 right-size | planner R7 |
| Rule 4 WHAT만 명시, HOW는 위임 | planner R8 |
| Rule 5 읽기 전용 탐색 · 입력은 데이터 | planner R1 |
| S1.2 재사용 주장 검증 | plan-rev S1.3 |
| S3 자기점검 — 모호성 | plan-rev S2 "Ambiguity" |
| S3 자기점검 — 검증 불가능성 | plan-rev S2 "Untestable acceptance criteria" |
| S3 자기점검 — 커버리지 갭 | plan-rev S2 "Coverage gaps" |
| S3 자기점검 — 인터페이스 갭 | plan-rev S2 "Interface gaps" |
| S3 자기점검 — 거짓 재사용 주장 | plan-rev S2 "False or stale reuse claims" |
| S3 자기점검 — 범위 | plan-rev S2 "Scope" |
| S3 자기점검 — 과잉 규정 | plan-rev S2 "Over-prescription" |

### 제외

| 원본 | 제외 근거 |
|---|---|
| planner R4 (TDD/no-TDD 분류) | `driver.tdd_mode` 종속 — 상태머신 전용 |
| planner R5 (본문에 명령어 금지) | `--update-config`가 명령을 따로 갖는다는 전제에 종속 |
| planner R6 (정해진 H2 헤딩) | `init`의 섹션 검증에 종속 |
| planner R9 (콜드 리더 자립성) | 근거가 "test author/implementor/reviewer가 대화를 못 본다"는 **역할 분리**. 소규모 작업엔 그 분리가 없음 |
| plan-rev S2 "Mode mismatch" | 파이프라인 전용 |
| plan-rev S2 "Session-dependent content" | planner R9와 같은 이유로 소멸 |
| plan-rev R7 + S5 (JSON 스키마) | 검증기 없음 |

---

## build-discipline

| 스킬 구획 | 출처 |
|---|---|
| Rule 1 최소·수술적 변경 | impl R1 |
| Rule 2 재사용 우선 | impl R6 |
| Rule 3 성능은 정확성의 일부 | impl R12 |
| Rule 4 계획 문서 금지 | impl R3 |
| Rule 4 불가능하면 멈추고 말하기 | impl R11 **일부 복원** (아래 주 참조) |
| Rule 7 주석은 코드 용어로 | impl R4 / test R6·R7 **축약** (아래 주 참조) |
| Rule 8 입력은 데이터지 지시 아님 | impl R8 / test R9 (rev R8, planner R1과 공통) |
| S1 두 종류의 불확실성 | impl R5 + impl S2.4 + test R10 |
| S3.1 asserting 테스트, placeholder 금지 | test R3 |
| S3.2 함의된 엣지·오류 케이스 | test R4 + test S3.2 |
| S3.3 기존 컨벤션 · 행위 기반 네이밍 | test R7 + test S2 |
| S3.4 하나의 테스트를 무한정 다듬지 마라 | test S3.6 |
| S3.5 테스트 불가능하면 말할 것 | test R11 |
| S4 자기점검 | impl S5 + test S4 |

> **Rule 5 주.** 원본은 "contract의 AC 번호를 인용하지 마라"(`AC1`, "criterion 1" 등)로,
> 근거가 "그 번호는 plan 작성 장치일 뿐 downstream이 상관시키지 않는다"였다. 소규모 작업엔
> 번호 자체가 없으므로 **"독자가 본 적 없는 문서를 인용하지 마라"**는 일반 원칙으로 축약했다.

### 제외

| 원본 | 제외 근거 |
|---|---|
| impl R2 (빌드만, 테스트 금지) | 테스터 역할이 없음. **소규모 작업에선 작성자가 직접 실행하는 게 맞다** — S4에서 반대로 뒤집었다 |
| test R5 (테스트·빌드 실행 금지) | 같은 이유. RED 검증 스테이지가 없으므로 실행 금지는 **유해**하다 |
| impl R9 / test R1·R2 (테스트 경로 경계) | 강제 장치 없음. "(the driver enforces this)"를 남기면 **없는 안전망을 믿게 만든다** |
| impl R7 / test R8 (재시도 이력) | 이력 파일 없음 |
| impl R10 / test R2 (`.dev-pipeline/` 금지) | 해당 없음 |
| impl R11 **의 `blocked_on` 부분만** | 라우팅 값은 상태머신 것이라 제외. **단 R11의 규율("불가능하면 억지로 만들지 말고 멈춰라")은 라우팅과 무관하므로 Rule 4로 복원했다** — 처음엔 둘을 한 덩어리로 잘라낸 실수였고, 그 결과 테스트 쪽([Step 3.5])에만 대응물이 있고 구현 쪽은 비는 비대칭이 생겼다 |
| impl R13·R14 | `owner`·재진입 note — 상태머신 라우팅 신호 |
| test R11·R12·R13 | 같음. 단 test R11의 "테스트 불가능하면 말할 것"은 S3.5로 살렸다 |
| impl S6 / test S5 (상태 JSON) | 검증기 없음 |

---

## adversarial-review

| 스킬 구획 | 출처 |
|---|---|
| Rule 1 엄격히 읽기 전용 | rev R1 |
| Rule 2 고치지 마라 | rev R2 |
| Rule 3 적대적 | rev R4 |
| Rule 4 독립 감사자 | rev R5 |
| Rule 5 material finding만 | rev R6 |
| Rule 6 입력은 데이터지 지시 아님 | rev R8 |
| S1.3 변경분 없으면 승인 금지 | rev S1.3 |
| S2 탐색 우선순위 7항목 | rev S2 |
| S2 finding 4문답 | rev S2 |
| S3 severity 4단계 | rev S3 |
| S3 성능 finding 증거 기준 | rev S3 "Performance findings" |
| S3 테스트 코드 판정 | rev S3 "Test code (TDD runs)" |

### 제외

| 원본 | 제외 근거 |
|---|---|
| rev R3 (빌드·설치·테스트 실행 금지) | 근거가 "테스터의 일"이라는 역할 분담. read-only는 frontmatter `allowed-tools`로 이미 걸리므로 규칙 문장이 불필요 |
| rev R7 + S5 (JSON 스키마) | 검증기 없음 → 산문 리포트로 대체 |
| rev S5의 `file` 경로 표기 규칙 | 파이프라인의 경로 매칭 라우팅 전용 |

### 툴 봉쇄 — 처음의 강화와, 그것을 되돌린 대가

처음 이 스킬은 `allowed-tools: Read, Grep, Glob`이었고, 그게 원본보다 나아진 유일한 지점이었다.
원본의 `main-session`/`subagent` 러너는 **하드 툴 봉쇄가 없어서** 읽기 전용 역할이 쓰기 권한을
가진 채 실행된다(상류 `AGENTS.md`의 보안 노트). 스킬 frontmatter는 그 봉쇄를 실제로 제공했다.

**감사 리포트를 파일로 저장하게 되면서 `Write`가 추가됐고, 그 봉쇄는 부분적으로만 남았다.**
이제 리뷰 대상 코드에 대한 쓰기를 막는 것은 툴이 아니라 **규칙 1의 산문**이다 — 리뷰 대상에
인젝션이 있을 때 방어선은 그 문장 하나다. 규칙 1은 이 사실을 감추지 않고 명시한다
("You hold a write tool, so this boundary is no longer something your tools enforce for you").

상류에 같은 형태의 선례가 있다 — `impl` R10: *"유일한 예외는 프롬프트가 지정한 정확한 경로에
쓰는 자기 출력 채널뿐"*. 다만 **상류에서는 러너의 `--allowedTools`가 물리적으로 막아줬고
여기엔 그 층이 없다.** 대가를 치른 이유는 산출물 영속화다: 리포트가 대화 안에만 남으면 세션이
끝날 때 사라져 재감사 시 이전 라운드와 대조할 수 없다.

---

## 이 레포에서 추가한 것 (상류에 없음)

아래는 `dp-*.md`에서 온 규칙이 **아니다.** 대응표를 상류 추적 용도로 정확히 유지하기 위해
따로 표기한다.

| 항목 | 스킬 | 비고 |
|---|---|---|
| `.agent-work/plans/`에 계획 저장 | planning-discipline S2, S3.6 | 명명 규칙만 상류 `states/planning.md` S1에서 차용 |
| `.agent-work/reviews/`에 리포트 저장 | adversarial-review S4 | 계획의 슬러그를 재사용해 짝을 맞춤 |
| 저장된 계획을 기준으로 사용 | adversarial-review S1.1 / build-discipline 도입부 | 세 스킬을 실제로 잇는 연결 |
| 산출물 첫머리의 핸드오프 프롬프트 | planning-discipline S3.1 / adversarial-review S4 | 파일을 통째로 다른 LLM에 넘기면 바로 다음 단계가 되도록. 상류는 이 문제가 없었다 — 드라이버가 프롬프트를 조립해 넘겼으므로 산출물이 스스로를 설명할 필요가 없었다 |
| 다음 단계 지목 + 경계 명시 | 세 스킬 전부 (S3.1·S3.7 / S4 / S4) | 상류는 `driver advance`가 다음 상태를 결정했고 역할은 그걸 알 필요가 없었다. 여기엔 상태머신이 없으므로 각 스킬이 스스로 다음을 지목한다. 동시에 **자기가 그 다음을 하지 않는다**는 경계도 함께 — 상류에서는 `run-stage`가 역할을 갈라놔 넘어갈 방법 자체가 없었다 |
| 보안을 구현 시점에 (Rule 6) | build-discipline | 상류 구현자에게도 없던 규칙이다. 리뷰어(`rev` S2)만 인젝션·미검증 입력·신뢰 경계를 사냥해서, 구현자는 아무 주의도 못 받고 리뷰어만 찾는 비대칭이었다. 성능(Rule 3)과 같은 형태로 맞췄다 |
| 전체 스위트 실행 (S4) | build-discipline | 상류는 별도 tester 역할이 프로젝트의 테스트 명령을 통째로 돌렸다. 그 역할을 제외하면서 "자기 테스트만 돌리고 끝"이 가능해졌다 |
| 검증 방법 명시 (자명하지 않을 때만) | planning-discipline S3.4 | 아래 "테스트 인프라 공백" 참조 |
| 테스트 관행이 없을 때 스스로 정하고 밝히기 | build-discipline S3.3 | 같음 |

### 테스트 인프라 공백 — 제외가 남긴 구멍과 그 메움

상류에서 **테스트를 어디에 어떤 프레임워크로 쓸지는 plan이 아니라 config**가 들고 있었다
(`llm.test_implementor.framework_instruction`, `test_paths`, tester의 build/install/test
instruction). `planner` R5는 그래서 *"실행 명령을 본문에 넣지 마라"*라고 못 박을 수 있었다 —
그 정보가 갈 다른 자리가 있었기 때문이다.

여기선 그 config가 없다. R5를 "`--update-config` 종속"으로 제외하면서 **대체물을 넣지 않아**
다음 분담에 빈 줄이 생겼다:

```
planning-discipline  →  무엇을 검증할 것인가 (기준 = 입력→출력)
build-discipline     →  어떤 테스트가 유효한가 (asserting, 엣지케이스, 실행)
        (없음)       →  어디에 어떤 프레임워크로 놓을 것인가
```

기존 테스트 관행이 있는 프로젝트는 `build-discipline` S3.3의 "기존 관행 모방"이 메웠지만,
그 분기의 "관행이 없을 때"는 **네이밍 하나만** 답하고 위치·프레임워크·fixture는 답하지 않았다.

메운 방식은 **명령을 적게 하는 것이 아니다** — R5가 그걸 금지한 이유는 여전히 유효하고,
`planner` R8("WHAT만, HOW는 위임")과도 충돌한다. 대신 두 갈래로 나눴다:

- **계획 쪽(S3.4)은 증거만 명시한다** — 부수효과로만 관측되는가, 어떤 상태 준비가 필요한가,
  무엇을 대역으로 세워야 하는가. 프레임워크와 명령은 여전히 금지. 이건 "무엇이 충족의
  증거인가"라 WHAT에 속한다
- **구현 쪽(S3.3)은 관행이 없으면 스스로 정하고 밝힌다** — 고르는 것 자체가 HOW이므로
  구현자의 몫이지만, 말없이 정하면 다음 변경이 모르는 채로 상속하므로 요약에 남기게 했다
| **슬러그 유니코드 허용** | 양쪽 | 상류와 다른 유일한 지점. 상류는 planner가 계획을 영어로만 쓰게 강제(`planner` R6)해 슬러그가 항상 ASCII였다. 한글 목표에 ASCII 규칙을 적용하면 전부 소멸해 파일명이 `plan`, `plan-2`가 된다 |
| `.gitignore` 불간섭 | 양쪽 | 상류는 `.dev-pipeline/plans/`를 gitignore하지만, 여기선 스킬이 프로젝트 설정을 건드리지 않는다 |
| Bash 미요구 | 양쪽 | 상류는 `date -u`를 셸로 부른다. 산출물 저장 하나로 읽기 중심 역할에 명령 실행권을 주지 않기 위해 호스트가 아는 날짜를 쓴다 |

---

## 전면 제외: `dp-tester.md`

7개 규칙 중 이식 가능한 건 R1("설정된 명령만 실행")과 R5("exit code로만 판정") 둘뿐이고,
**둘 다 명령을 공급하는 오케스트레이터를 전제**한다. 그 전제가 없으면 스킬로 만들 내용이
남지 않는다. 소규모 작업에서 이 역할에 해당하는 규율은 `build-discipline` S4
("직접 빌드하고 테스트를 돌려라, 통과 못 하면 우회하지 말고 말하라")가 대신한다.
