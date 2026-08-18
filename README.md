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
```

축은 세 스킬이 공유하는 **"검증 가능한 성공 기준"** 하나다. 기준이 없으면 `build-discipline`은
범위 이탈을 구분할 수 없고, `adversarial-review`는 판정 대상이 없어 일반 린팅으로 무너진다.
각각 단독으로도 쓸 수 있지만, 기준 없이 시작하면 뒤의 둘이 약해진다는 점은 알고 쓸 것.

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

스킬을 수정한 뒤에는 두 가지를 확인한다:

```bash
# 파이프라인 machinery / 특정 LLM 이름 누출 — 0건이어야 한다
grep -rniE 'driver|dev-pipeline|attempts\.md|blocked_on|contract_path|test_paths|run_dir|orchestrator|red_test|stage-input|\.dev-pipeline|claude|codex|gpt|gemini' .agents/skills/

# 분량 — 스킬당 60줄을 넘으면 압축 실패
wc -l .agents/skills/*/SKILL.md
```
