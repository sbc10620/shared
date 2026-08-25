# shared — common-LLM 작업 규율 스킬

소규모 작업에 쓰는 **LLM 비종속 작업 규율** 스킬 모음. [Agent Skills](https://agents.md) 표준
트리(`.agents/skills/<name>/SKILL.md`)라 Codex·Gemini CLI·Cursor 등이 이 레포를 열면 바로
인식하고, Claude Code는 `.claude/skills/`로 복사해 쓴다.

특정 모델이나 CLI에 묶인 내용은 어디에도 없다.

## 스킬

| 스킬 | 언제 | 툴 |
|---|---|---|
| **`planning-discipline`** | 착수 전, 요청을 **검증 가능한 성공 기준**으로 정리할 때 | `Read, Grep, Glob, Write` |
| **`build-discipline`** | 기준에 맞춰 코드와 테스트를 작성할 때 | 제한 없음 |
| **`adversarial-review`** | 변경이 끝난 뒤 감사할 때 | `Read, Grep, Glob` (읽기 전용) |

### 체인

```
planning-discipline  →  build-discipline  →  adversarial-review
   검증 가능한 기준        그 기준을 구현          그 기준 대비로 판정
         │                       │                       │
         ↓                    (읽음)                     ↓
 .agent-work/plans/  ─────────────┘        .agent-work/reviews/
```

축은 세 스킬이 공유하는 **"검증 가능한 성공 기준"** 하나다. 기준이 없으면 `build-discipline`은
범위 이탈을 구분할 수 없고, `adversarial-review`는 판정 대상이 없어 일반 린팅으로 무너진다.
각각 단독으로도 쓸 수 있지만, 기준 없이 시작하면 뒤의 둘이 약해진다는 점은 알고 쓸 것.

## 산출물

계획과 감사 리포트는 프로젝트 루트 기준으로 저장된다. 대화 안에만 남으면 세션이 끝날 때
기준이 사라져 체인이 실제로는 이어지지 않기 때문이다.

| 경로 | 내용 | 쓰는 주체 |
|---|---|---|
| `.agent-work/plans/` | 검증 가능한 성공 기준 | `planning-discipline` |
| `.agent-work/reviews/` | 감사 리포트 | `adversarial-review` |

파일명은 `<YYYYMMDD>-<slug>.md`. `<slug>`는 목표를 소문자화하고 문자·숫자가 아닌 연속을 `-`
하나로 접은 것으로, **문자는 어느 문자 체계든 보존**한다(한글 목표가 통째로 소멸하지 않도록).
경로가 이미 있으면 `-2`, `-3`을 붙이며, **감사는 판정 대상 계획의 슬러그를 재사용**하므로
`plans/`와 `reviews/`를 나란히 놓으면 파일명만으로 짝이 맞고 `-2`는 재감사 라운드가 된다.

```
.agent-work/plans/20260825-로그인-재시도-로직-추가.md
.agent-work/reviews/20260825-로그인-재시도-로직-추가.md      ← 1차 감사
.agent-work/reviews/20260825-로그인-재시도-로직-추가-2.md    ← 수정 후 재감사
```

**`.gitignore`는 스킬이 건드리지 않는다.** 이 파일들을 추적할지는 프로젝트마다 다른 판단이라
사용자가 직접 정한다.

## 설치

대상 프로젝트로 원하는 스킬 디렉터리를 복사한다.

```bash
# Agent Skills를 읽는 호스트 (Codex, Gemini CLI, Cursor, …)
mkdir -p <project>/.agents/skills
cp -R .agents/skills/<skill-name> <project>/.agents/skills/

# Claude Code — .agents/skills 를 아직 읽지 않으므로 별도 복사가 필요
mkdir -p <project>/.claude/skills
cp -R .agents/skills/<skill-name> <project>/.claude/skills/
```

## 출처

[`dev-pipeline`](https://github.com/sbc10620/dev-pipeline)의 역할 프롬프트
(`dp-implementor` / `dp-test-implementor` / `dp-reviewer` / `dp-plan-reviewer` / `dp-planner`)에서
**원칙만** 추출했다. 원본은 상태머신이 강제하는 파이프라인 안에서만 동작하고, 그 규칙의 상당수는
본질적 규율이 아니라 **역할 분담**이다 — 워크플로우를 버리면 근거가 사라지거나 문장이 거짓이 된다
("the driver enforces this"처럼 없는 안전망을 믿게 만드는 문장이 대표적).

그래서 이 스킬들은 원본의 복사본이 아니라, 이식 가능한 규칙만 골라 근거를 새로 쓰고 분량을 절반
이하로 압축한 **재작성**이다. 어떤 규칙이 어디서 왔고 무엇을 왜 버렸는지는
[`PROVENANCE.md`](./PROVENANCE.md)에 있다.

`dp-tester`는 전면 제외했다 — 명령을 공급하는 오케스트레이터가 없으면 남는 내용이 없다.

## 유지보수

상류 `dev-pipeline`의 역할 프롬프트는 인시던트마다 규칙이 추가되며 계속 갱신된다. 상류가 바뀌면
`PROVENANCE.md`의 대응표로 여기서 다시 볼 지점을 찾는다. **자동 생성이 아니므로 손으로 반영한다.**

**규칙은 셀 수 있게 유지한다.** 스킬당 규칙 8개 이하, 같은 말을 두 번 하지 않는다. 규칙이
늘어나면 줄을 압축하지 말고 **규칙을 잘라내거나 스킬을 쪼갠다** — 줄 수는 증상이지 원인이
아니다. 이 스킬들은 소규모 작업마다 로드되어 대화와 프롬프트 예산을 두고 경쟁하고, 규칙이
길어질수록 실제 준수율이 떨어진다.

스킬을 수정한 뒤에는 두 가지를 확인한다:

```bash
# 파이프라인 machinery / 특정 LLM 이름 누출 — 0건이어야 한다
grep -rniE 'driver|dev-pipeline|attempts\.md|blocked_on|contract_path|test_paths|run_dir|orchestrator|red_test|stage-input|\.dev-pipeline|claude|codex|gpt|gemini' .agents/skills/

# 규칙 수 — 스킬당 8개 이하 (줄 수는 참고용이지 합격 기준이 아니다)
grep -c '^[0-9]\+\. \*\*' .agents/skills/*/SKILL.md
```
