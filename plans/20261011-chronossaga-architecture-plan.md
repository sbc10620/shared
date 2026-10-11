# ChronosSaga 구조 설계안

- 작성일: 2026-10-11
- 대상: `~/Works/ChronosSaga` (아직 코드 없음, 빈 git 저장소만 생성됨)
- 범위: 확장 가능한 전체 구조, 사용자가 직접 쓰는 스테이지 편집기, 렌더링 기준, 단계별 개발 순서

## 1. 결론

- 프로젝트를 **정적 라이브러리 5개와 실행 파일 2개**로 나눈다.
  - 라이브러리: `core`(게임 규칙), `content`(데이터 파일 읽기·검증), `engine`(플랫폼·Vulkan), `engine_imgui`(편집기 UI 연결), `battle`(전투 화면)
  - 실행 파일: `game`(게임 본편), `editor`(스테이지 편집기)
- **게임 규칙(`core`)은 그래픽과 파일 입출력을 전혀 모르는 순수 C++ 코드로 작성한다.** AI, 트리거, 세이브, 리플레이, 편집기의 테스트 플레이가 모두 같은 규칙 코드를 재사용한다.
- **전투 화면(`battle`)은 게임 실행 파일 안이 아니라, 게임과 편집기가 함께 링크하는 라이브러리에 둔다.** 그래야 편집기가 편집 중인 스테이지를 파일로 저장하지 않고도 바로 테스트 플레이할 수 있다.
- **스테이지 파일은 사용자가 만들고 공유하는 공개 형식이므로, 처음부터 버전 번호, 검증기, 패키지 형식을 갖춘다.**
- 확장성은 "데이터 추가"와 "문자열 ID 등록부(registry)"로 확보한다. ECS, DLL 플러그인, Lua 스크립트는 처음에는 도입하지 않는다.

## 2. 의존 방향

```
          ┌──────────┐                 ┌──────────┐
          │   game   │                 │  editor  │            ← 실행 파일
          └──┬───┬───┘                 └─┬───┬──┬─┘
             │   └────────┐   ┌─────────┘   │  │
             │            ▼   ▼             │  ▼
             │         ┌──────────┐         │ ┌──────────────┐
             │         │  battle  │         │ │ engine_imgui │ Dear ImGui 연결
             │         └─┬──────┬─┘         │ └──────┬───────┘
             ▼           │      │           ▼        │
          ┌──────────┐◀──┘      └──▶┌──────────┐◀────┘
          │ content  │              │  engine  │  플랫폼, Vulkan, 에셋, 입력, 오디오, 폰트
          └────┬─────┘              └──────────┘
               ▼
          ┌──────────┐
          │   core   │  순수 게임 규칙 + 데이터 정의 구조체 (의존성 0)
          └──────────┘
```

`game` 과 `editor` 는 `core`, `content`, `engine`, `battle` 에 모두 의존한다. 그림에서는 선이 겹치지 않도록 일부 화살표를 생략했다.

| 라이브러리 | 의존해도 되는 대상 | 의존하면 안 되는 대상 |
|---|---|---|
| `core` | C++ 표준 라이브러리만 | 나머지 전부 (파일, 그래픽, JSON 포함) |
| `content` | `core`, JSON 라이브러리 | `engine`, SDL, Vulkan |
| `engine` | SDL3, Vulkan, VMA, 이미지·폰트·오디오 라이브러리 | `core`, `content` (게임 규칙을 모르는 범용 계층) |
| `engine_imgui` | `engine`, Dear ImGui | `core`, `content` |
| `battle` | `core`, `content`, `engine` | ImGui, `editor` 전용 코드 |
| `game` | 위 전부 (`engine_imgui` 제외) | `editor` |
| `editor` | 위 전부 | `game` |

- `engine` 이 `core` 를 모르도록 유지하면, 렌더러를 교체하거나 다른 플랫폼으로 옮길 때 게임 규칙을 건드릴 필요가 없다.
- ImGui의 Vulkan·SDL3 백엔드는 Vulkan 장치와 SDL 창을 직접 다뤄야 한다. 그래서 ImGui 연결 코드는 `editor` 가 아니라 `engine` 쪽의 별도 라이브러리(`engine_imgui`)에 둔다. 이렇게 하면 Vulkan 객체가 `engine` 계열 밖으로 나가지 않는다.

## 3. 디렉터리 구조

```
ChronosSaga/
├── CMakeLists.txt
├── CMakePresets.json          # macOS / Windows / Linux 빌드 설정
├── vcpkg.json                 # 외부 라이브러리 목록 (Vulkan SDK 는 시스템 설치)
├── libs/
│   ├── core/                  # chronos_core
│   │   ├── include/chronos/core/
│   │   │   ├── ids.hpp            # UnitId, ClassId 같은 강타입 ID
│   │   │   ├── defs.hpp           # ClassDef, WeaponDef, TerrainDef, ItemDef (데이터 정의 구조체)
│   │   │   ├── database.hpp       # 정의 묶음 + ID 별칭 표
│   │   │   ├── map.hpp            # 격자, 지형
│   │   │   ├── unit.hpp           # 유닛 상태(능력치, HP, 소지품)
│   │   │   ├── roster.hpp         # 캠페인 동안 유지되는 아군 명단
│   │   │   ├── battle_setup.hpp   # 전투 시작 조건 (맵, 배치, 트리거, 승패 조건)
│   │   │   ├── battle_state.hpp   # 한 전투의 전체 상태 (복사·저장 가능)
│   │   │   ├── actions.hpp        # Move, Attack, Wait, UseItem, EndTurn
│   │   │   ├── events.hpp         # UnitMoved, Attacked, UnitDefeated, DialogueRequested ...
│   │   │   ├── rules.hpp          # Action 검증·적용 → Event 목록
│   │   │   ├── triggers.hpp       # 트리거 조건·행동 평가
│   │   │   ├── move_range.hpp     # 이동 범위 (Dijkstra)
│   │   │   ├── combat.hpp         # 명중·필살·추격·무기 상성
│   │   │   ├── rng.hpp            # 시드 고정 난수 (상태 안에 저장)
│   │   │   ├── skills.hpp         # 스킬 효과 등록부
│   │   │   ├── ai.hpp             # AI 성향 등록부 + 상태 → Action 결정
│   │   │   └── builtins.hpp       # register_builtin_skills(), register_builtin_ai() ...
│   │   ├── src/
│   │   └── tests/
│   ├── content/               # chronos_content
│   │   ├── include/chronos/content/
│   │   │   ├── database_io.hpp    # classes.json 등 → core::Database
│   │   │   ├── stage.hpp          # 스테이지 문서 구조체 (편집기가 수정하는 대상)
│   │   │   ├── stage_io.hpp       # 스테이지 JSON 읽기·쓰기
│   │   │   ├── to_setup.hpp       # 스테이지 문서 + 명단 → core::BattleSetup
│   │   │   ├── package.hpp        # 스테이지 패키지 매니페스트
│   │   │   ├── migrate.hpp        # 구버전 → 신버전 변환
│   │   │   ├── validate.hpp       # 게임·편집기 공용 검증기
│   │   │   └── content_roots.hpp  # 기본 콘텐츠·사용자 콘텐츠 경로 묶음 (앱이 전달)
│   │   ├── src/
│   │   └── tests/
│   ├── engine/                # chronos_engine
│   │   ├── include/chronos/engine/
│   │   │   ├── platform/          # 창, 이벤트 루프, 사용자 데이터 경로
│   │   │   ├── input/             # 키·패드·마우스 → 추상 입력 동작
│   │   │   ├── gfx/               # Vulkan 장치, 스왑체인, 프레임 관리
│   │   │   ├── render/            # 스프라이트 배치, 타일맵, 텍스트, 카메라
│   │   │   ├── text/              # 폰트 래스터화, 동적 글리프 아틀라스 (한글 대응)
│   │   │   ├── assets/            # 텍스처 아틀라스, 셰이더 로딩
│   │   │   ├── audio/
│   │   │   └── scene.hpp          # 화면 스택 (타이틀, 전투, 메뉴)
│   │   └── src/
│   ├── engine_imgui/          # chronos_engine_imgui (편집기 전용)
│   └── battle/                # chronos_battle
│       ├── include/chronos/battle/
│       │   ├── battle_scene.hpp   # 전투 화면 (메모리 안의 BattleSetup 으로 시작 가능)
│       │   ├── player_input.hpp   # 커서·메뉴 조작 → Action
│       │   ├── presentation.hpp   # Event → 이동·전투·대화 연출 대기열
│       │   └── ui/                # 유닛 정보창, 행동 메뉴, 전투 예측창
│       └── src/
├── apps/
│   ├── game/                  # 타이틀, 챕터 진행, 명단 관리, 세이브
│   └── editor/                # 스테이지 편집기
├── shaders/                   # GLSL, 빌드 시 glslc 로 SPIR-V 생성
├── assets/                    # 도트 그림, 폰트, 효과음 (기본 콘텐츠)
├── content/                   # 기본 게임 데이터 (JSON)
│   ├── manifest.json          # 기본 콘텐츠 버전
│   ├── classes.json
│   ├── weapons.json
│   ├── terrain.json
│   ├── tilesets/
│   ├── dialogue/
│   └── stages/
└── docs/
```

### 3.1 콘텐츠 경로

- 사용자가 만든 스테이지는 설치 폴더가 아니라 사용자 데이터 폴더(예: macOS `~/Library/Application Support/ChronosSaga/user_content/`)에 저장한다. 기본 콘텐츠와 사용자 콘텐츠를 분리해야 게임 업데이트가 사용자 작업물을 덮어쓰지 않는다.
- 사용자 데이터 폴더의 실제 위치는 플랫폼마다 다르므로 `engine::platform` 이 구한다. 앱(`game`, `editor`)은 이 경로를 `content::ContentRoots` 에 담아 `content` 에 넘긴다. 그래서 `content` 는 `engine` 에 의존하지 않는다.
- 게임과 편집기는 같은 사용자 콘텐츠 폴더를 읽고 쓴다. 그래서 편집기에서 저장한 스테이지가 게임의 "사용자 스테이지" 목록에 바로 나타난다.

## 4. 게임 규칙 코어 (`core`)

### 4.1 데이터 정의는 `core`, 파일 읽기는 `content`

- 전투 계산과 이동 비용 계산에는 클래스·무기·지형의 수치가 필요하다. 그래서 정의 구조체(`ClassDef`, `WeaponDef`, `TerrainDef`)와 정의 묶음(`Database`)은 `core` 에 둔다.
- `content` 는 JSON을 읽고 검증해서 이 구조체를 채우는 역할만 한다.
- 스테이지 문서(`content::Stage`)를 전투 시작 조건(`core::BattleSetup`)으로 바꾸는 작업은 `content::to_setup` 이 맡는다. 이때 캠페인 명단(`core::Roster`)을 함께 받아서 출격 슬롯에 아군을 배치한다.
- `core::BattleState` 는 `BattleSetup` 으로부터만 만들어진다. 테스트 코드는 JSON 없이 `BattleSetup` 을 직접 조립해서 규칙을 검증할 수 있다.

### 4.2 상태는 복사 가능한 순수 데이터로 만든다

- `BattleState` 는 맵, 유닛 목록, 현재 턴, 진영, 트리거 진행 상태, 난수 상태를 모두 담는다.
- 유닛끼리는 포인터가 아니라 `UnitId` 로 참조한다. 증원으로 새로 생기는 유닛의 ID도 `BattleState` 안의 카운터로 순서대로 발급한다.
- 그래서 상태 전체를 복사하거나 저장할 수 있다. AI는 상태를 복사해서 "이 행동을 하면 어떻게 될까"를 미리 계산할 수 있다.
- 난수 생성기의 상태도 `BattleState` 안에 저장한다. 같은 콘텐츠, 같은 시드, 같은 행동 목록이면 결과가 항상 같다. 세이브와 리플레이에는 기본 콘텐츠 버전(또는 해시)을 함께 기록해서, 데이터가 바뀐 뒤에 옛 리플레이를 틀리게 재생하는 일을 막는다.

### 4.3 Action → 검증 → 적용 → Event

```
플레이어 입력 (battle::player_input) ─┐
                                      ├─▶ Action ─▶ rules::validate ─▶ rules::apply ─▶ Event 목록 ─▶ 연출 대기열
AI (core::ai)                       ──┘                (거부 사유 반환)     (상태 변경,          (battle::presentation)
                                                                             트리거 평가 포함)
```

- 플레이어와 AI는 똑같이 `Action` 을 만든다. 규칙 코드는 행동을 누가 만들었는지 구분하지 않는다.
- AI의 판단 로직은 결정적이어야 리플레이가 맞으므로 `core` 에 둔다. `battle` 은 적 턴에 `core::ai` 를 호출하기만 한다.
- `apply` 는 상태를 바꾼 뒤 `Event` 목록을 돌려준다. 트리거도 이 단계에서 평가된다. 예를 들어 "3턴 시작 시 증원"이면 `UnitSpawned` 이벤트가 나온다.
- 대화 같은 연출은 규칙 코드가 직접 실행하지 않고 `DialogueRequested` 이벤트로 요청한다. 화면 쪽이 이 이벤트를 받아 대화창을 띄운다.
- 규칙 코드는 애니메이션을 기다리지 않는다. 상태는 즉시 바뀌고, 연출은 그 뒤를 따라간다.

### 4.4 확장 지점

| 추가하려는 것 | 방법 | 필요한 C++ 작업 |
|---|---|---|
| 새 클래스, 무기, 아이템 | `content/*.json` 에 항목 추가 | 없음 |
| 새 지형 종류 | `terrain.json` 에 이동 비용·회피·방어 보정 추가 | 없음 |
| 새 스킬 | 전투 계산 단계(명중 계산, 피해 계산 등)에 끼어드는 함수를 문자열 ID로 등록 | 효과 1개당 함수 1개 |
| 새 AI 성향 | `AiBehavior` 인터페이스 구현을 문자열 ID로 등록 (돌격형, 대기형, 거점 방어형) | 성향 1개당 클래스 1개 |
| 새 트리거 조건·행동, 승리 조건 | 조건·행동 종류를 등록 | 종류 1개당 함수 1개 |

- 스킬과 AI를 문자열 ID 등록부로 관리하면, 데이터 파일과 스테이지 파일은 `"skill": "vantage"` 처럼 ID만 적으면 된다. 편집기도 등록부 목록을 읽어서 선택지를 자동으로 만든다.
- 등록은 정적 초기화(전역 객체 생성자)로 하지 않고, `register_builtin_skills()` 같은 명시적 함수 호출로 한다. 정적 라이브러리에서는 아무도 참조하지 않는 오브젝트 파일을 링커가 빼 버리기 때문에, 정적 초기화 방식을 쓰면 등록부가 비어 있을 수 있다. 게임과 편집기는 같은 등록 함수를 호출해서 목록이 항상 같도록 한다.

## 5. 스테이지 데이터와 사용자 편집 (`content`)

### 5.1 지형과 그림을 분리한다

- **그림 레이어**: 타일셋에서 고른 타일. 화면에 보이는 모습만 정한다.
- **지형 레이어**: 평지, 숲, 산, 물, 벽 같은 규칙상의 지형. 이동 비용과 회피 보정을 정한다.
- 타일셋의 각 타일에는 기본 지형이 지정되어 있다. 편집기에서 타일을 칠하면 지형도 자동으로 채워진다.
- 필요하면 특정 칸의 지형만 따로 덮어쓸 수 있다. 예를 들어 "숲처럼 보이지만 실제로는 평지"인 칸을 만들 수 있다.
- 타일셋의 타일도 문자열 ID(`"grass"`, `"grass_flower"`)를 가진다. 스테이지 파일은 맨 앞에 "이 스테이지가 쓰는 타일 ID 목록(`tile_palette`)"을 적고, 칸마다 그 목록의 번호를 적는다. 타일셋에 타일을 추가하거나 순서를 바꿔도 기존 스테이지가 깨지지 않으면서, 파일 크기는 작게 유지된다.

### 5.2 스테이지 파일 예시

좌표는 모두 `"pos": [x, y]` 형식으로 통일한다.

```json
{
  "format_version": 1,
  "id": "ch01_border_fort",
  "name": "국경 요새",
  "requires": { "base_content": ">=0.1" },
  "size": { "width": 24, "height": 16 },
  "tileset": "grassland",
  "tile_palette": ["grass", "grass_flower", "forest", "fort_wall"],
  "layers": {
    "tiles": [0, 0, 2, 2, "..."],
    "terrain_overrides": [{ "pos": [5, 7], "terrain": "plain" }]
  },
  "deploy": {
    "required": ["alm"],
    "slots": [[2, 13], [3, 13], [2, 14], [3, 14]]
  },
  "units": [
    { "id": "bandit_a", "class": "brigand", "team": "enemy", "level": 2,
      "pos": [18, 4], "ai": "charge", "items": ["iron_axe"] },
    { "id": "guest_kay", "kind": "guest", "class": "archer", "team": "player",
      "level": 3, "pos": [4, 12], "items": ["iron_bow"] }
  ],
  "victory": { "type": "defeat_all" },
  "defeat": { "type": "unit_defeated", "unit": "alm" },
  "triggers": [
    {
      "when": { "type": "turn_start", "turn": 3, "team": "player" },
      "do": [
        { "type": "dialogue", "script": "ch01_reinforce" },
        { "type": "spawn", "unit": { "class": "brigand", "team": "enemy", "pos": [23, 8], "ai": "charge" } }
      ]
    }
  ]
}
```

- `deploy` 는 캠페인 명단에서 데려오는 아군의 출격 위치이다. `required` 에 적힌 캐릭터는 반드시 출격한다.
- `units` 는 이 스테이지에만 등장하는 고정 유닛(적, 일시 합류 아군)이다.
- 이렇게 나누면 캠페인에서 레벨·소지품·사망 여부가 이어지는 아군과, 스테이지마다 새로 정의되는 유닛을 함께 다룰 수 있다. 단독으로 플레이하는 사용자 스테이지는 `deploy` 대신 미리 정한 아군을 `units` 에 넣으면 된다.

### 5.3 스테이지 패키지

다른 사람과 공유하는 단위는 스테이지 파일 하나가 아니라 **패키지 폴더**이다.

```
user_content/packages/border_fort_pack/
├── package.json        # 패키지 ID, 버전, 작성자, 필요한 기본 콘텐츠 버전, 포함 스테이지 목록
├── stages/ch01_border_fort.json
├── dialogue/ch01_reinforce.json
└── tilesets/           # 선택: 사용자 정의 타일셋 (도트 그림 + 타일 정의)
```

- 게임은 `user_content/packages/` 아래의 패키지를 찾아 목록을 만든다.
- 패키지 안의 ID는 패키지 ID를 앞에 붙여 구분한다(예: `border_fort_pack:ch01_reinforce`). 그래서 서로 다른 패키지끼리, 그리고 기본 콘텐츠와 ID가 충돌하지 않는다.

### 5.4 공개 형식으로서 지켜야 할 규칙

- **모든 데이터 파일에 `format_version`**: 스테이지뿐 아니라 타일셋, 대화, 패키지 매니페스트에도 버전 번호를 둔다. 형식이 바뀌면 번호를 올리고, `migrate` 가 구버전 파일을 한 단계씩 신버전으로 변환한다.
- **ID는 문자열**: 클래스, 무기, 유닛, 타일은 배열 번호가 아니라 문자열로 참조한다.
- **ID 변경 정책**: 기본 콘텐츠에서 ID의 이름을 바꾸거나 항목을 없앨 때는 `Database` 의 별칭 표에 "옛 ID → 새 ID"를 남긴다. 기본 게임을 업데이트해도 사용자 스테이지가 깨지지 않게 하려는 조치이다.
- **검증기는 하나만 둔다**: 게임과 편집기가 같은 `validate` 를 쓴다. 편집기는 오류를 목록으로 보여 주고, 게임은 같은 오류를 근거로 로딩을 거부한다.
- **신뢰할 수 없는 파일로 취급한다**: 다른 사람이 공유한 패키지는 크기 제한, 범위 검사, 존재하지 않는 ID 검사를 통과해야 한다. 잘못된 파일 때문에 게임이 멈추면 안 되고, 오류 메시지를 보여 주어야 한다.
- **트리거는 선언형으로 시작한다**: "조건 → 행동" 데이터만 지원한다. 나중에 Lua 같은 스크립트를 넣더라도, 사용자끼리 패키지를 공유하는 구조이므로 파일 접근과 무한 루프를 막는 격리 환경이 필요하다.

## 6. 렌더링 (`engine`)

### 6.1 이미 정한 기준

- 도트 기준 해상도는 **640×360**, 타일은 **32×32 도트**이다.
- 배율은 `max(1, floor(min(화면 너비 / 640, 화면 높이 / 360)))` 로 정한 정수이다. 1080p는 3배, 1440p는 4배, 4K는 6배가 된다. 창이 640×360보다 작아도 배율은 1 아래로 내려가지 않는다.
- 화면 크기는 창의 논리 크기가 아니라 **실제 픽셀 크기**(SDL3 `SDL_GetWindowSizeInPixels`)로 계산한다. macOS Retina 화면에서는 두 값이 2배 차이가 난다.
- 16:9가 아닌 화면에서는 배율을 유지하고 남는 영역에 맵을 더 보여 준다. 검은 띠를 쓰지 않는다.
  - UI(유닛 정보창, 지형 정보창)는 화면 모서리를 기준으로 배치하므로, 화면 비율이 달라도 위치가 어긋나지 않는다.
  - 맵이 화면보다 작으면 맵을 화면 가운데에 놓고 바깥은 배경색으로 채운다.
- 640×360 오프스크린 버퍼에 그린 뒤 확대하는 방식은 쓰지 않는다. 실제 해상도에서 직접 그리고, 도트 그림만 정수배 + nearest 필터로 키운다. 그래서 카메라 스크롤과 유닛 이동이 화면 픽셀 단위로 부드럽게 움직인다.
  - 카메라 위치는 화면 픽셀 단위로 반올림한다. 그래야 도트 경계가 흔들리지 않는다.
  - 텍스처 아틀라스의 그림 사이에는 여백을 두어서, 확대 시 옆 그림의 색이 번져 들어오지 않게 한다.
- UI 글자는 도트 배율과 관계없이 실제 해상도 폰트로 그린다. 한글 음절은 수천 자이므로 미리 전부 굽지 않고, 화면에 처음 나오는 글자를 그때그때 아틀라스에 추가하는 동적 글리프 아틀라스를 쓴다.

### 6.2 게임 코드는 Vulkan을 직접 다루지 않는다

```
battle / game 코드
    │  draw list 제출: sprite(아틀라스 ID, 위치, 반전, 색상), tilemap, text
    ▼
engine::render   (스프라이트 배치, 정렬, 카메라 변환)
    │
    ▼
engine::gfx      (Vulkan 1.3: dynamic rendering, synchronization2, VMA, 프레임 2개 겹침)
    ▲
    │  "추가 UI 패스" 연결점
engine_imgui     (편집기만 사용)
```

- 게임 코드는 "무엇을 어디에 그릴지"만 목록으로 넘긴다.
- Vulkan 객체(파이프라인, 디스크립터, 버퍼)는 `engine` 과 `engine_imgui` 밖으로 나오지 않는다.
- 편집기의 ImGui 화면은 같은 프레임의 마지막 단계에서 그린다. ImGui의 Vulkan 백엔드는 dynamic rendering을 지원하므로, `engine` 은 "추가 UI 패스"를 끼울 수 있는 연결점만 제공하면 된다.
- macOS에서는 MoltenVK를 통해 실행된다. 이를 위해 `engine::gfx` 안에서 다음을 처리한다.
  - 인스턴스 생성 시 `VK_KHR_portability_enumeration` 확장을 켜고, `VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR` 플래그를 설정한다. 플래그가 없으면 Vulkan 로더가 MoltenVK 장치를 보여 주지 않는다.
  - 장치가 `VK_KHR_portability_subset` 을 제공하면 장치 생성 시 켠다.

## 7. 스테이지 편집기 (`editor`)

### 7.1 형태

- 게임과 별도의 실행 파일로 만든다. `core`, `content`, `engine`, `battle`, `engine_imgui` 를 링크한다.
- 1차 버전의 UI는 Dear ImGui로 만든다. 개발 속도가 빠르고, 타일 팔레트·속성 창·목록 같은 편집기 화면에 잘 맞는다.
- 플레이어에게 배포할 때는 한글 글리프 범위, 고해상도 화면 배율, 언어 설정을 ImGui에 추가로 설정해야 한다. ImGui의 기본 모양이 일반 사용자에게 충분한지는 M5 결과를 보고 판단한다(11장).

### 7.2 기능 (1차 목표 순서)

1. 새 스테이지 만들기, 열기, 저장하기 (패키지 단위)
2. 타일 칠하기: 붓, 사각형 채우기, 영역 채우기, 지우개
3. 지형 덮어쓰기 표시 모드
4. 유닛 배치: 클래스, 레벨, 진영, 소지품, AI 성향 지정, 출격 슬롯 지정
5. 승리·패배 조건 지정
6. 검증 결과 패널: 오류를 클릭하면 해당 칸으로 이동
7. **테스트 플레이**: 편집 중인 스테이지를 저장하지 않고 `battle` 화면으로 바로 실행
8. 트리거 편집기: 조건과 행동을 목록에서 골라 조합

### 7.3 실행 취소는 게임 규칙과 별도로 만든다

- 편집기의 실행 취소(undo/redo)는 **스테이지 문서를 수정하는 명령 스택**이다. 예: `PaintTiles`, `PlaceUnit`, `EditTrigger`.
- 게임의 `Action` 은 **전투 상태를 바꾸는 규칙 명령**이다.
- 두 개념은 이름이 비슷하지만 대상과 목적이 다르므로 섞지 않는다.

## 8. 외부 라이브러리

| 용도 | 추천 | 비고 |
|---|---|---|
| 창·입력 | **SDL3** | 게임패드 지원과 Steam Deck 대응이 GLFW보다 좋다. 결정 필요 |
| Vulkan 메모리 | VMA | 사실상 표준 |
| 수학 | GLM | |
| JSON | nlohmann/json | 데이터·스테이지 파일 |
| 이미지 | stb_image | PNG 로딩 |
| 폰트 | FreeType | 한글 동적 글리프 아틀라스 |
| 오디오 | SDL3 audio 또는 miniaudio | SDL3를 쓰면 SDL3 audio로 시작 |
| 편집기 UI | Dear ImGui | Vulkan·SDL3 백엔드 사용 |
| 테스트 | doctest | `core`, `content` 단위 테스트 |
| 의존성 관리 | **vcpkg manifest** | Windows를 포함한 세 플랫폼에서 같은 버전의 라이브러리를 받기 위해 사용. Vulkan SDK만 시스템에 설치 |

현재 Mac에는 Homebrew로 Vulkan 도구(MoltenVK, 검증 레이어, `glslc`)가 설치되어 있다. 라이브러리는 vcpkg로 옮기더라도, Vulkan 런타임과 셰이더 컴파일러는 계속 시스템 설치본을 쓴다.

## 9. 처음에는 만들지 않는 것

| 항목 | 미루는 이유 |
|---|---|
| ECS (EnTT 등) | 유닛 수십 개 규모의 턴제 게임에는 단순 구조체와 ID로 충분하다 |
| DLL 플러그인 | 데이터 추가와 등록부만으로 확장 요구를 대부분 처리할 수 있다 |
| Lua 스크립트 | 선언형 트리거로 먼저 필요한 기능을 확인하고, 부족할 때 격리 환경과 함께 도입한다 |
| 렌더러 추상화 (Metal, DX12 백엔드) | Vulkan 하나로 Windows·Linux·macOS를 지원할 수 있다. `engine` 경계만 지키면 나중에 추가할 수 있다 |
| 네트워크 대전 | 결정적 규칙 구조(4.2)를 지키면 나중에 행동 목록 동기화 방식으로 붙일 수 있다 |

## 10. 개발 단계

| 단계 | 내용 | 완료 기준 |
|---|---|---|
| M0 | CMake 골격, 창, Vulkan 초기화, 화면 지우기 | 검증 레이어 오류 0건으로 창이 뜬다 |
| M1 | 스프라이트 배치, 타일맵, 정수 배율 카메라, 한글 텍스트 | 32px 타일 맵이 1080p·1440p·4K에서 정수배로 표시되고 한글이 선명하게 나온다 |
| M2 | `core` 맵·이동 범위 + 커서·선택·이동 | 이동 범위가 표시되고 유닛이 이동한다, 이동 범위 단위 테스트 통과 |
| M3 | 전투 계산, 턴 교대, 단순 AI | 아군 2명 대 적 2명으로 한 판을 끝까지 할 수 있다 |
| M4 | JSON 데이터·스테이지 로딩, 검증기, 버전 변환 틀, 패키지 탐색 | 패키지만 바꿔서 다른 맵을 플레이할 수 있다 |
| M5 | 편집기 v0: 타일 칠하기, 유닛 배치, 저장·열기, 테스트 플레이 | 편집기에서 만든 스테이지를 바로 플레이할 수 있다 |
| M6 | 트리거, 대화, 승패 조건 | 3턴째 증원과 대화가 나오는 스테이지를 편집기로 만들 수 있다 |
| M7 | 캠페인 명단, 출격 준비 화면, 세이브 | 두 챕터를 이어서 플레이하면 레벨과 사망 여부가 이어진다 |

## 11. 결정이 필요한 사항

| 항목 | 추천 | 대안 |
|---|---|---|
| 창·입력 라이브러리 | SDL3 | GLFW (더 단순하지만 게임패드·오디오 지원이 약함) |
| 의존성 관리 | vcpkg manifest | FetchContent (별도 도구가 필요 없지만, 라이브러리 수가 늘면 CMake 설정이 복잡해짐) |
| 편집기 형태 | 별도 실행 파일 | 게임 안의 편집 모드 (배포는 단순하지만 게임 코드와 편집 코드가 섞임) |
| 편집기 UI | 1차는 Dear ImGui, 일반 사용자 배포 전에 재검토 | 처음부터 게임과 같은 도트 스타일 UI (완성도는 높지만 개발량이 매우 큼) |
| 데이터 형식 | JSON | TOML·YAML (사람이 손으로 쓰기는 편하지만 편집기가 저장하는 구조에는 이점이 적음) |
| 사용자 편집 범위 | 1차는 스테이지·대화·타일셋 | 클래스·무기 정의까지 사용자 편집 허용 (밸런스 검증 범위가 커짐) |
