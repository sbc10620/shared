# dev-cycle-lite 스킬 계획

## 배경

- LLM 토큰을 많이 쓸 수 없는 환경에서도 dev-cycle 과 같은 흐름으로 개발하려고 한다.
- dev-cycle 의 흐름(테스트 먼저, 영향 범위 검증, 범위 리뷰, 사용자 결정, PR 전 전체 검사)은 그대로 두고, 토큰을 많이 쓰는 부분만 줄인 `dev-cycle-lite` 스킬을 만든다.
- dev-cycle 과 dev-cycle-code-review 는 고치지 않는다.

## 토큰을 많이 쓰는 곳과 lite 의 대응

| 영역 | dev-cycle | dev-cycle-lite | 절감 정도 |
| --- | --- | --- | --- |
| 리뷰 1회차 | 내장 리뷰 스킬 우선, high(관점 6개를 서브에이전트로 병렬 실행) | `dev-cycle-code-review` medium 으로 고정(한 번에 검토, 추가 서브에이전트 없음) | 큼 |
| 리뷰 2회차 이후 | 매 라운드 전체 범위를 medium 으로 다시 검토, 구현 코드를 고치면 계속 반복 | 2회차는 수정 diff 만 검토, 3회차부터는 사용자가 결정 | 큼 |
| 계획 검토 | 읽기 전용 서브에이전트가 한 번 검토 | 기본은 생략하고 오케스트레이터가 체크리스트로 직접 확인, 큰 계획일 때만 실행을 제안 | 중간 |
| 테스트 작성 | 별도 에이전트가 spec 만 보고 작성 | 구현자가 구현 전에 spec 에서 기대값을 먼저 적음 | 중간 |
| 도구 출력 | 규칙 없음 | 빌드·테스트 출력은 결과 줄과 실패 이름만 컨텍스트에 남김 | 중간 (Rust 전체 suite 에서 큼) |
| 스킬 문서 | `SKILL.md` 23 KB + 참조 문서 | `SKILL.md` 10 KB 이하, dev-cycle `SKILL.md` 는 읽지 않음 | 약 3천 토큰 |
| 프로필 | 전체를 읽음(ARGO 24 KB) | 필요한 절만 읽음, 속도·메모리 측정 절은 계획에 있을 때만 | 약 1천 토큰 |
| 리뷰 보고 표 | 모든 지적을 한 행씩 | "고칠 결함"만 행으로, 나머지는 분류별로 한 줄 | 작음 |
| 마일스톤 규칙·10단계(프로필 갱신) | 있음 | 뺌 | 작음 |

## 그대로 두는 것

- 리뷰 서브에이전트의 모델은 세션 모델을 그대로 쓴다.
- 리뷰 프롬프트에는 설계 원칙 14개를 지금처럼 모두 넣는다.
- PR 직전 검사(9단계)는 dev-cycle 과 같다. 프로필이 PR 전으로 미룬 회귀 비교, 전체 suite, 전체 e2e, 점검 목록을 실행한다. 속도·메모리 측정은 지금 프로필처럼 계획에 있을 때만 실행한다.
- worktree 규칙, 편집 전 baseline, `git stash` 금지, 수정은 관련 커밋에 amend, 동작을 바꾼 수정은 낡은 문서·주석을 찾아 함께 고침, push·PR·댓글은 각각 지시를 기다림.
- 리뷰 결과를 보고한 뒤 사용자가 고칠 항목을 고를 때까지 기다린다.
- PR 대응 댓글(ai-review-triage 등 다른 스킬)은 영향을 받지 않는다. 모든 항목을 적는 규칙은 그대로다.

## 파일 구성

- 원본: `~/.agents/skills/dev-cycle-lite/SKILL.md` 한 파일만 만든다. `~/.claude/skills` 는 `~/.agents/skills` 의 심볼릭 링크이므로 Claude Code 에서도 바로 보인다.
- 함께 쓰는 파일(상대 경로로 참조):
  - 프로필: `../dev-cycle/profiles/<repo>.md` 와 그 `scripts/`
  - 설계 원칙: `../dev-cycle/references/design-principles.md`
  - 프로필이 없을 때: `../dev-cycle/references/profile-guide.md` 의 "Without a profile" 절만 읽음
  - 리뷰: `dev-cycle-code-review` 스킬(설치된 그대로)
- shared 사본: `~/Works/shared/skills/dev-cycle-lite/SKILL.md`. shared 에는 `skills/dev-cycle` 이 이미 있으므로 상대 경로가 그대로 맞는다. 프로필 스크립트가 shared 사본에 없는 것은 dev-cycle 과 같다.
- 스킬 본문은 영어로 쓴다(전역 규칙). 사용자 보고는 한국어다.
- lite 는 dev-cycle 의 `SKILL.md` 를 읽지 않는다. 따라서 아래에서 "dev-cycle 과 같다"고 적은 규칙도 lite 의 `SKILL.md` 에 짧게 풀어 쓴다. 처음 읽는 에이전트가 다른 파일 없이 따를 수 있어야 하기 때문이다. 그래서 크기 목표는 6 KB 가 아니라 10 KB 이하로 잡는다.

## frontmatter 초안

```yaml
---
name: dev-cycle-lite
description: "Token-light variant of the dev-cycle skill, same flow and profiles: the implementer writes the spec-derived tests before the code, verification runs only what the change affects with tool output cut to result lines, one dev-cycle-code-review round at medium over the whole range, then a second round over the fix diff only when a fix touched the implementation, a third only if the user asks, and the same pre-PR checks. Use ONLY when the user or an instruction file (CLAUDE.md, AGENTS.md) names dev-cycle-lite or asks for the lite cycle ('dev-cycle-lite', 'lite 로', '경량 사이클'). Otherwise use dev-cycle."
user-invocable: true
---
```

- description 은 큰따옴표로 감싸고 `yaml.safe_load` 로 검사한다(콜론 때문에 파싱이 실패한 적이 있음).
- dev-cycle 의 description 은 고치지 않는다. lite 는 이름을 댈 때만 실행된다.

## SKILL.md 단계별 내용

### 1. 프로필 찾기

- 프로필을 찾는 방법은 dev-cycle 과 같다(`origin` remote 의 저장소 이름).
- 프로필은 시점에 맞는 절만 읽는다. 절 하나를 읽는 명령을 스킬에 적는다.

  ```bash
  preamble() { awk '/^## /{exit} 1' "$1"; }
  section()  { awk -v h="## $2" 'index($0,"## ")==1{p=(index($0,h)==1)} p' "$1"; }
  ```

  | 시점 | 읽는 절 |
  | --- | --- |
  | 시작할 때 | 머리말(`preamble`), Commands, Path → affected checks, Check cost and shared builds, When each check runs, Tests, Pitfalls |
  | 편집 전 | Baselines (항상 읽음: 프로필이 경로에 따라 baseline 을 요구할 수 있고, 편집 뒤에는 되돌릴 수 없음) |
  | PR 전 | Pre-PR checklist |
  | 계획이 이름을 댈 때만 | Speed check, Memory check 같은 측정 절 |

- `section` 이 아무것도 출력하지 않으면(절 이름이 바뀐 경우) 프로필 전체를 읽는다.
- Pitfalls 는 크지만 읽는다. 함정에 한 번 빠지면 그 실패를 다루는 데 더 많은 토큰이 든다.
- 프로필이 없으면 `profile-guide.md` 의 "Without a profile" 절만 읽고 저장소에서 명령을 찾는다. 그 절의 마지막 문장("step 10 에서 프로필 초안이 된다")은 lite 에서 적용하지 않는다고 스킬에 적는다. 끝날 때 프로필 초안은 만들지 않고, "프로필 없음, 사용한 명령: …" 한 줄만 보고한다.

### 2. 첫 편집 전

- worktree·브랜치·시작 커밋 규칙과 baseline 규칙은 dev-cycle 과 같다. 스킬에는 다음 규칙을 짧게 풀어 적는다.
  - 계획에 worktree, 브랜치, 시작 커밋을 적는다. 기본 위치는 `<main checkout>/.worktrees/<repo>-<topic>` 이다.
  - 프로필이나 계획이 요구하는 baseline 은 첫 편집 전에 시작 커밋에서 받고, 빌드와 실행이 끝날 때까지 기다린다.
  - `git stash` 를 쓰지 않는다. 작업을 잠시 치울 때는 임시 커밋을 쓴다.
- 계획 검토 서브에이전트는 기본으로 실행하지 않는다. 대신 오케스트레이터가 계획을 보여 주기 전에 직접 확인한다.
  - 계획이 이름을 댄 파일·함수·설정 값이 실제로 있는지 `git grep` 으로 확인한다.
  - 커밋마다 spec 이 기대값을 정할 만큼 구체적인지 확인한다.
  - 바뀌는 경로마다 프로필이 요구하는 검사가 계획에 있는지 확인한다.
  - 계획을 보여 줄 때 "직접 확인함: …" 한 줄을 붙인다.
- 다음 중 하나면 서브에이전트 계획 검토를 실행할지 사용자에게 묻는다.
  - 계획한 커밋이 4개 이상이다.
  - 공개 API, 설정 형식, 저장 형식처럼 다른 저장소나 사용자가 기대는 형식을 바꾼다.
  - 사용자가 요청한다.

### 3. 테스트 먼저 (구현자가 작성)

- 커밋마다 구현을 시작하기 전에, 새 동작의 기대값을 spec 에서 먼저 적는다. 형식은 (입력, 기대 결과, 근거가 된 spec 문장) 목록이다.
- 그 목록으로 테스트를 쓰고, 실패하는 것을 확인한 다음 구현한다.
- 테스트를 쓰는 동안에는 구현을 상상하지 않는다. 기대값의 근거는 spec 문장뿐이다.
- 구현과 테스트가 어긋나면 어느 쪽도 혼자 고치지 않는다. 테스트, 근거 spec 문장, 코드의 실제 동작을 보고하고 사용자 결정을 기다린다. dev-cycle 4단계와 같은 규칙이다.
- spec 이 없는 변경(리팩터링, 성능 변경)이나 사소한 변경은 이 단계를 건너뛰고 한 줄로 보고한다.

### 4. 구현

- 커밋하기 전에 `design-principles.md` 로 이번 커밋이 추가하거나 확장한 구조를 점검한다. 이 파일은 세션에서 한 번만 읽는다.

### 5. 영향 범위 검증

- 영향 범위를 정하는 방법과 검사 순서(formatter·linter → audit → 영향받는 테스트 → 경로별 추가 검사 → 해당 e2e 한 suite)는 dev-cycle 과 같다.
- **도구 출력 규칙**(lite 에서 새로 추가):
  - 빌드는 quiet 옵션으로 실행한다(`cargo ... -q`, `npm --silent` 등).
  - 테스트 출력은 파일로 저장하고, 컨텍스트에는 결과 줄과 실패 이름만 가져온다.

    ```bash
    log="${TMPDIR:-/tmp}/dcl-$(basename "$PWD")-test.log"
    cargo test -q ... >"$log" 2>&1; echo "exit=$?"
    grep -E '^test result|^---- |^    [A-Za-z0-9_:]+$|panicked|^error(\[|:)' "$log" | head -60
    ```

    `cargo test -q` 는 실패한 테스트를 진행 줄에 `F` 로만 표시한다. 그래서 실패 이름은 `---- <name> stdout ----` 줄과 마지막 `failures:` 목록에서 가져온다.
  - 실패했을 때만 실패한 테스트 주변을 `grep -A` 나 `sed -n` 으로 좁혀서 읽는다. 로그 전체를 읽지 않는다.
  - 로그 파일 이름에는 worktree 이름을 넣는다. 다른 세션이 같은 파일을 쓰지 않게 하기 위해서다.
- 진행 보고에는 결과 줄 원문, 실패 테스트 이름, spec 테스트를 바꿨는지("no test edits" 또는 diff 와 이유)를 적는다.
- dev-cycle 5단계의 다음 규칙도 풀어 적는다.
  - 실행할 수 없는 단계(e2e 없음, linter 없음)는 건너뛰되 반드시 한 줄로 보고한다. 조용히 건너뛰지 않는다.
  - 실패한 검사가 있으면 원인을 찾아 고칠 때까지 다음으로 가지 않는다. 이 일은 오케스트레이터가 하고, 사용자를 기다리지 않는다.
  - 리뷰 전에 사용자를 기다리는 경우는 두 가지뿐이다. spec 테스트와 구현이 어긋날 때, 그리고 회귀 비교에서 계획이 허용하지 않은 차이가 나올 때다.

### 6. 리뷰

- 계획한 커밋을 모두 만든 뒤, 읽기 전용 서브에이전트가 `dev-cycle-code-review` 를 **medium** 으로 실행한다. 모델은 지정하지 않는다(세션 모델을 이어받음).
- 내장 리뷰 스킬(`/code-review` 등)은 쓰지 않는다. 내장 스킬은 medium 에서 에이전트를 몇 개 쓰는지 알 수 없어서 비용을 예측할 수 없기 때문이다.
- `dev-cycle-code-review` 가 실행되지 않으면 같은 서브에이전트가 직접 검토하고, 첫 줄에 `manual review — dev-cycle-code-review failed: <reason>` 을 적는다.
- 프롬프트 형식은 dev-cycle 과 같다. 첫 줄은 `medium <base SHA>..<head SHA> — Report findings only, no edits.` 이고, 그다음 줄부터 설계 원칙 14개(원칙 이름 + "Look for" 칸), 사용자의 규칙, 이전 라운드 블록을 넣는다.
- 프롬프트에는 worktree 경로를 적고, 커밋은 `HEAD` 가 아니라 SHA 로 적는다. 서브에이전트는 다른 디렉터리에서 시작할 수 있기 때문이다.
- 리뷰어 보고의 첫 줄(방법 줄)이 `dev-cycle-code-review, medium (…)` 이 아니고 이유도 없으면, 그 보고는 쓰지 않고 리뷰를 다시 실행한다.

**회차별 범위**

| 회차 | 언제 | 리뷰 범위 | 보는 것 |
| --- | --- | --- | --- |
| 1회차 | 계획한 커밋을 모두 만든 뒤 | `<base>..<head>` 전체 | 정확성 + 설계 원칙 |
| 2회차 | 1회차 수정이 구현 코드를 건드렸을 때만 | 1회차 리뷰 때의 head 와 수정 후 head 의 차이 | (a) 고친 항목이 실제로 고쳐졌는가, (b) 수정 diff 가 바꾼 줄과 그 직접 호출부에 새 결함이 없는가. 설계 원칙은 수정 diff 에만 적용 |
| 3회차 이후 | 2회차 수정이 구현 코드를 건드렸고, 사용자가 실행하라고 할 때만 | 직전 회차 head 와 수정 후 head 의 차이 | 2회차와 같음 |

- 2회차 범위의 구현 방법: `dev-cycle-code-review` 에 range 로 `<1회차 head SHA>..<수정 후 head SHA>` 를 넘긴다. 첫 줄의 `<base SHA>` 자리에 1회차 head SHA 가 들어간다. 이 스킬의 "Later rounds" 규칙은 "넘겨받은 range 전체를 다시 본다"이므로, range 자체를 수정 diff 로 넘기면 스킬을 고치지 않고도 범위가 좁아진다.
  - `git diff A..B` 는 두 트리의 차이, 곧 수정 내용만 보여 준다. 반면 amend 로 이력이 바뀌었으면 `git log A..B` 에 다시 쓰인 커밋이 나온다. 그러면 리뷰어가 커밋 메시지에서 기능 전체의 의도를 읽고, 바뀌지 않은 코드에 대해 "동작이 빠졌다"고 지적할 수 있다.
  - 그래서 프롬프트에 다음 줄을 넣는다: "The range is the fix diff between two heads. git log may list rewritten commits; ignore them and the commit count. The intent of this round is the findings marked `fixed in` below. Judge by git diff."
  - 1회차 head SHA 는 수정 전에 기록해 둔다. 수정 중에 base 가 바뀌는 rebase 를 했다면 이 방법을 쓸 수 없다. 이때는 1회차 head 도 같은 base 로 옮긴 SHA 를 쓰고, 그렇게 할 수 없으면 `<base>..<head>` 전체를 medium 으로 리뷰한다.
  - 이전 라운드 블록에는 `fixed in` 항목과 사용자 결정을 넣는다. `not fixed`·`not applicable` 항목은 다시 꺼내지 말라는 표시로 넣는다. 블록의 "Changed this round" 줄은 range 와 같아도 그대로 적는다.
- 지적이 정말 맞는지 코드와 대조하는 방법은 dev-cycle 6단계와 같다. 스킬에는 네 줄로 줄여 적는다.

**종료 조건**

- 한 회차에 고칠 것이 없거나, 수정이 문서·테스트뿐이면 리뷰를 끝낸다. "테스트"의 뜻은 dev-cycle 과 같다(테스트용으로만 빌드·실행되는 코드).
- 2회차 수정이 구현 코드를 건드렸으면, 영향 범위를 검증한 뒤 3회차를 실행할지 사용자에게 묻는다. 사용자가 실행하지 않기로 하면 리뷰를 끝낸다.

### 7. 보고 후 대기

```
방법: <리뷰어의 방법 줄>
결론: 고칠 결함 <n>건 / 사실이지만 동작 영향 없음 <n>건 / 해당 없음·이미 처리됨 <n>건

| # | 지적 | 확인 결과 (CONFIRMED/PLAUSIBLE, 한 줄) | 수정안 |
| --- | --- | --- | --- |
(고칠 결함만)

사실이지만 동작 영향 없음: R1#3 문서 문구, R1#5 로그 단계, …
해당 없음·이미 처리됨: R1#2 이미 상위에서 검사함, …
```

- 세 분류 이름은 dev-cycle 과 같다. 기호만 쓰지 않고 이름을 쓴다. 분류 기준도 스킬에 풀어 적는다.
  - 고칠 결함: 코드에서 재현할 수 있는 런타임 결함, 또는 조용히 건너뛰는 검사.
  - 사실이지만 동작 영향 없음: 사실이지만 동작에 영향이 없는 것(문서 문구, 로그 단계, 테스트 일관성, 호출되지 않는 경로의 검사). 설계 지적은 "설계:"로 시작한다.
  - 해당 없음·이미 처리됨: 전제가 틀렸거나, 코드가 이미 처리하거나, 변경 범위 밖이거나, 이전 회차에서 답한 것.
- 표 밖의 항목도 번호와 짧은 이름을 남긴다. 사용자는 어느 분류에서든 고칠 항목을 고를 수 있고, 자세한 내용을 물어볼 수 있다.
- 보고한 뒤 멈추고, 사용자가 고를 때까지 수정하지 않는다.

### 8. 수정

- dev-cycle 8단계와 같다. 스킬에는 다음 규칙을 풀어 적는다.
  - 수정은 관련 커밋에 바로 넣는다(HEAD 면 `--amend`, 아니면 `--fixup` 후 `git rebase --autosquash <commit>^`). `fixup!` 커밋을 남기지 않는다.
  - 고치기 전에 설계 원칙으로 수정이 추가하는 구조를 점검한다.
  - 동작을 바꾼 수정은 옛 동작을 적은 주석, 문서, 오류 메시지, 테스트 이름을 저장소 전체에서 찾아 같이 고친다.
  - 백그라운드 검사가 트리를 쓰고 있으면 이력을 다시 쓰지 않고 기다린다. amend 전 SHA 는 기록해 둔다(2회차 리뷰 범위에 필요).
- spec 이 정한 동작을 바꾸는 수정은 구현자가 3단계 방식으로 기대값을 먼저 다시 적는다.
- 수정한 뒤에는 5단계(수정의 영향 범위만)로 검증하고, 6단계의 회차 규칙에 따라 다음 회차로 가거나 끝낸다.

### 9. PR 전 (한 번)

- dev-cycle 9단계와 같다. 도구 출력 규칙(5단계)을 여기에도 적용한다. 스킬에는 다음 규칙을 풀어 적는다.
  - 실행하는 것: 프로필이 PR 전으로 미룬 느린 검사, 전체 suite(baseline 이 있으면 테스트별 결과 비교), 전체 e2e, 프로필의 Pre-PR checklist.
  - base 에서 통과하던 테스트가 실패하면 결함이다. 원인을 찾아 고친다. base 에서도 실패하는 테스트나, 다시 돌리면 통과하는 flaky 테스트는 보고만 한다.
  - 계획이 허용하지 않은 차이(회귀 비교, 사라지거나 새로 생긴 테스트)가 나오면 멈추고 사용자가 정한다. 허용하면 계획의 허용 차이에 적는다. 측정값은 프로필 규칙을 따른다.
- 9단계에서 구현 코드를 고쳤으면 리뷰를 다시 연다. 이 리뷰는 2회차와 같은 모양(수정 diff 만, medium)이고, 회차 번호는 이어서 센다. 3회차 이후 규칙(사용자가 정함)도 그대로 적용한다. 리뷰가 끝나면 9단계를 새 HEAD 에서 다시 실행한다.
- 9단계 수정이 문서·테스트뿐이면 리뷰를 다시 열지 않는다. 영향 범위만 검증하고 9단계를 다시 실행한다.
- 이력 재작성 뒤의 규칙(트리가 같으면 다시 돌리지 않음, 다르면 바뀐 파일이 요구하는 검사만)은 dev-cycle 과 같다.
- push, PR, 댓글은 각각 지시를 기다린다.

### 뺀 것

- 마일스톤 규칙: 계획이 마일스톤으로 나눠야 할 만큼 크면 사용자에게 알리기만 한다. dev-cycle 로 바꾸는 것은 사용자가 그렇게 말할 때뿐이다. 지시 파일이 lite 를 지정한 환경에서 스스로 dev-cycle 로 바꾸면 high 리뷰와 내장 리뷰 스킬이 실행되기 때문이다.
- 10단계(프로필 갱신): 프로필이 틀렸거나 도구를 고쳐 썼으면 끝날 때 한 줄로 보고만 한다. 고치는 일은 dev-cycle 에서 한다.
- 역할 표와 helper 프롬프트를 보여 주는 규칙: 남은 helper 는 리뷰어 하나뿐이므로 6단계에 같이 적는다.

## 토큰이 제한된 환경에서 쓰는 방법

- 그 환경에 `dev-cycle`, `dev-cycle-lite`, `dev-cycle-code-review` 세 스킬을 설치한다. shared 사본을 복사하면 된다.
- 그 환경의 전역 지시 파일에서 개발 사이클 줄만 바꾼다.
  - Claude Code: `~/.claude/CLAUDE.md`
  - Codex: `~/.codex/AGENTS.md`
  - 바꿀 문장:

    ```
    - For a code change headed for a PR, follow the `dev-cycle-lite` skill from planning on.
    ```

- 이 Mac 의 `~/.claude/CLAUDE.md` 는 바꾸지 않는다.

## 작업 순서

1. `~/.agents/skills/dev-cycle-lite/SKILL.md` 를 쓴다. 크기는 10 KB 이하를 목표로 한다.
2. frontmatter 를 `yaml.safe_load` 로 검사한다.
3. 읽기 전용 서브에이전트에게 한 번 검토를 맡긴다. 검토 기준은 아래와 같다.
   - 이 계획의 결정과 어긋나는 곳이 있는가
   - `dev-cycle-code-review` 의 입력 형식·"Later rounds" 규칙과 맞는가
   - 상대 경로와 프로필 절 이름이 실제 파일과 맞는가
   - 처음 읽는 에이전트가 헷갈릴 만한 문장이 있는가
4. 검토 결과를 보고하고, 고칠 항목을 정한 뒤 반영한다.
5. shared 사본(`~/Works/shared/skills/dev-cycle-lite/`)을 만들고 commit·push 한다.
6. 메모리에 dev-cycle-lite 항목을 추가한다.

## 확인할 점

- 프로필 절 이름이 바뀌면 lite 의 절 목록도 바꿔야 한다. 그 전까지는 1단계의 "절을 찾지 못하면 전체를 읽는다" 규칙이 막아 준다.
- 구현자가 테스트를 함께 쓰므로, 테스트가 구현을 따라가는 위험은 dev-cycle 보다 크다. 이 위험은 "기대값의 근거는 spec 문장뿐"이라는 규칙과, 리뷰어가 tests 관점(테스트가 실패할 수 없는 경우)을 보는 것으로 줄인다.
