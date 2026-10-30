# ARGO 다국어 PII 브랜치의 가드레일 메모리 절감 항목 실측

작성일: 2026-10-30

## 1. 요약

- **목표는 다국어 브랜치의 PSS를 다국어 이전(base)에 맞추는 것이었습니다.** 설치 직후 PSS를 비교하면 다국어 브랜치가 base보다 **+307 KB** 큽니다. live heap은 두 브랜치가 같으므로, 차이의 대부분은 바이너리가 커진 몫입니다.
- **가드레일 코드 항목만으로는 이 차이를 0으로 만들 수 없었습니다.** 후보 11개를 모은 합본을 적용하면 차이가 **+115 KB**로 줄어듭니다. 이 합본에는 나중에 제외를 권한 checkpoint 꺼내기 항목도 들어 있습니다.
- **1 MB 안팎 이상을 줄인 것은 세 가지뿐이었습니다.** 셋 다 스레드나 링커와 관련된 것입니다.
  - 작은 텍스트(16 KB 이하)를 별도 스레드 없이 바로 스캔하는 변경은 Pss_Anon을 200턴 뒤 −1.5 MB, 1000턴 뒤 −6.5 MB 줄였습니다. 가드레일 코드를 바꾸는 항목 가운데 효과가 큰 것은 이것 하나입니다.
  - glibc arena를 1개로 제한(`GLIBC_TUNABLES=glibc.malloc.arena_max=1`)하면 Pss_Anon이 200턴 뒤 −1.1 MB, 1000턴 뒤 −6.3 MB 줄었습니다. 코드가 아니라 프로세스 설정입니다.
  - lld 링커에 RELR(`-z pack-relative-relocs`)을 쓰면 설치 직후 Pss_File이 −784 KB 줄었습니다. 코드가 아니라 링커 설정입니다.
- **나머지 항목은 live heap을 수십 KB 줄였거나, 할당량이나 바이너리만 줄였거나, 노이즈 안에 있었습니다.**
  - reverse DFA 지연 생성: −71~−105 KB
  - 운전면허 패턴 제외: −52~−58 KB
  - DFA 캐시 비율 1.5: −42 KB
  - PatternMeta 축소: 약 −15 KB
  - Aho-Corasick dense 설정: 약 −15 KB
  - 마스킹 결과 일괄 복사 줄이기: 턴당 할당량 −7.3 %. 대신 peak heap이 늘었습니다.
  - 빌드할 때 나라 선택과 YAML 주석 제거: 바이너리 −231 KB, −72 KB. PSS 효과는 작았습니다.
- **엔진 미리 데우기는 오히려 메모리를 늘렸습니다.** 캐시 상한 축소도 대화 여러 개를 번갈아 쓰는 경우에는 오히려 악화되었습니다.
- **실제 argot daemon(argo-tizen v0.6.18)은 오래 돌려도 PSS가 끝없이 늘지 않았습니다.** 첫 100턴에 PSS가 +3 MB 오르는데, 가드레일을 꺼도 거의 같게 오르므로 가드레일 몫이 아닙니다. 그 뒤 약 1,200턴부터 ±60 KB 안에 머뭅니다. 가드레일 몫은 100턴 이후 PSS +0.33~0.66 MB로, 늘지 않고 이 범위에서 오르내립니다.

## 2. 배경

- **비교 대상**
  - base: 194cf3b3a7 `fix(guardrails): no PII recognizer reports a match inside a UUID`. 다국어 작업 이전 커밋이며, kr·us 규칙이 파일 하나에 들어 있습니다.
  - 다국어 브랜치: `dev/byungchul.so/multilingual-support`의 65395de87f `refactor(guardrails): keep each country's PII files in one directory`. 13개국 규칙이 나라별 디렉터리로 나뉘어 있고, 실행할 때 나라를 고릅니다.
- **2026-10-28 baseline 측정의 결론**
  - kr·us만 고르면 두 브랜치의 live heap이 같았습니다.
  - PSS는 다국어 브랜치가 더 크며, 200턴 뒤 기준으로 약 +332 KB였습니다.
  - 차이의 원인은 바이너리 섹션이 커진 몫으로 판단했습니다(`.rodata`, `.rela.dyn`, `.data.rel.ro`, `.text`).
- **이 문서의 범위**
  - 차이를 줄이고 가드레일 몫 자체도 줄이기 위한 후보 항목을 임시로 구현했습니다. 실제 커밋 후보가 아니라 측정용 구현입니다.
  - 그 구현을 같은 방법으로 측정한 결과를 정리합니다.
  - 측정용이므로 코드 리뷰는 거치지 않았습니다.

## 3. 측정 방법

### 3.1 측정 도구

- **bench:** `tinicore/examples/guardrails/bench_idle_after_turns.rs`
  - `install_guardrails_from_config`로 가드레일을 모두 설치합니다. PII는 `full`이고, tool output 검사와 내장 prompt guard 규칙도 켭니다.
  - 그 뒤 실제 `agent_loop` 턴을 N번 돌립니다. 모델은 미리 짜 둔 가짜 모델(`ScriptedToolThenEcho`)입니다.
    - 첫 응답은 tool을 한 번 호출하며, tool 결과에는 전화번호와 HTML 주석이 들어 있습니다.
    - 두 번째 응답은 tool 결과를 그대로 돌려줍니다.
    - 대화 하나에 턴마다 사용자 메시지와 답을 쌓으므로 대화가 계속 길어집니다.
- **임시 측정 도구 커밋:** 44a413b529 `tmp(bench): report Pss_Anon/Pss_File, turn allocation volume and round-robin conversations`. 다국어 브랜치 65395de87f 위에 얹었고, 모든 항목 브랜치가 이 커밋 위에 있습니다.
  - `examples/guardrails/common.rs`
    - 할당 카운터(`CountingAllocator`)가 할당 총량과 횟수(`ALLOC_BYTES`, `ALLOC_COUNT`), peak live heap(`PEAK_LIVE`)을 함께 셉니다.
    - `read_pss_split()`이 `/proc/self/smaps_rollup`에서 `Pss`, `Pss_Anon`, `Pss_File`을 읽습니다.
  - `examples/guardrails/bench_idle_after_turns.rs`
    - 시점마다 `METRIC point=… live=… pss=… anon=… file=…` 한 줄을 출력합니다.
    - 턴을 다 돈 뒤 `ALLOC bytes=… count=… peak=… turns=… conversations=…` 한 줄을 출력합니다.
    - `--conversations N`을 추가했습니다. 대화 N개를 번갈아 씁니다(대화 ID `bench-conversation-{k}`).
- **base에도 같은 도구를 얹었습니다.** base의 bench에는 `--countries` 옵션이 없습니다. 그래서 같은 변경을 손으로 옮긴 사본을 base 트리에 덮어썼습니다.

### 3.2 환경과 조건

- **환경:** Mac 위의 Ubuntu 24.04 aarch64 VM, glibc 2.39, 4 vCPU
  - TV(32비트 armv7, Tizen glibc)와 아키텍처가 다르므로 절대값은 TV와 다릅니다.
- **빌드:** `cargo build -p tinicore --example bench_idle_after_turns --release --features guardrails,sensitive,test-fixtures`
- **실행:** `--pin on --countries us,kr --turns <200|1000> --settle 12`
  - 가드레일은 항상 켰습니다.
  - base에는 `--countries`를 넘기지 않았습니다. 이 커밋은 kr·us 규칙만 갖고 있습니다.
- **반복:** 200턴 측정은 9회, 1000턴 측정은 3회 돌려 중앙값을 썼습니다.
  - 측정은 한 번에 프로세스 하나씩만 돌렸습니다. 동시에 돌리면 공유하는 바이너리 페이지가 프로세스끼리 나뉘어 Pss_File이 틀어집니다.
  - 반복할 때마다 모든 구성을 한 바퀴씩 돌렸습니다. 시간에 따른 변화가 특정 구성에만 몰리지 않게 하려는 것입니다.

### 3.3 시점과 지표

- **시점**
  - 설치 직후: 가드레일 설치와 prompt guard 컴파일이 끝나자마자 대기 없이 잽니다. bench의 12초 대기는 설치 전 시점 앞에 있습니다.
  - 200턴 뒤 / 1000턴 뒤: 마지막 턴 뒤 12초를 기다리고 잽니다. tokio가 놀고 있는 blocking 스레드를 10초 뒤에 정리하므로 12초를 기다립니다.
  - trim 뒤: 위 측정 직후 `malloc_trim(0)`을 부르고 잽니다. 운영 환경에서는 일어나지 않으므로, 돌려받을 수 있는 양의 상한으로만 봅니다.
- **지표**
  - live heap: bench의 할당 카운터가 센, 프로그램이 들고 있는 바이트입니다.
  - Pss_Anon: heap, 해제했지만 glibc가 돌려주지 않은 arena 메모리, 스레드 스택, 재배치된 `.data.rel.ro`가 여기에 잡힙니다.
  - Pss_File: 바이너리를 매핑한 페이지 가운데 실제로 읽은 몫입니다(`.text`, `.rodata`, 시작할 때 읽는 `.rela.dyn` 등).
  - 턴당 할당량: 턴을 도는 동안 요청한 할당 크기의 합(realloc의 새 크기 포함)을 턴 수로 나눈 값입니다. 상주 메모리가 아니라 할당 부담을 나타냅니다.
  - peak heap: 턴을 도는 동안 live heap이 가장 높았던 값입니다.

### 3.4 노이즈 기준

| 대조 구성 | 결과 | 뜻 |
| --- | --- | --- |
| 같은 바이너리를 다시 측정 | 설치 직후 PSS +4 KB, 200턴 뒤 −56 KB, 1000턴 뒤 **−1,064 KB** | 턴을 돈 뒤의 PSS는 arena 때문에 측정마다 크게 흔들립니다. |
| 코드는 같고 컴파일 옵션만 다르게 빌드 | 섹션 크기는 같은데 설치 직후 Pss_File **+140 KB** | 빌드 배치가 바뀌면 Pss_File이 움직입니다. |

- 설치 직후 PSS는 측정마다 수십 KB 안에서 움직여 믿을 만합니다.
- Pss_File은 코드 변화 없이도 +140~+172 KB 움직였습니다(이 표의 대조군과 5장의 lld 대조군). 이 문서는 이 정도 차이를 빌드 배치 노이즈로 봅니다.
- live heap도 측정마다 거의 같아서 믿을 만합니다.
- 바이너리를 바꾸는 항목은 ELF 섹션 크기를 주 지표로, Pss_File을 보조 지표로 봅니다.
- 같은 소스를 두 번 빌드하면 바이너리 해시가 같았습니다. 따라서 같은 소스라면 빌드할 때마다 생기는 배치 차이는 없습니다.

### 3.5 항목별 바이너리를 만든 방법

- **패치 준비:** 항목마다 측정 도구 커밋 위에 브랜치를 하나씩 만들었습니다(`items/*`). 브랜치마다 `git diff 44a413b529 items/<항목>` 패치를 뽑았습니다.
- **VM 소스 트리:** 측정 도구 커밋 상태의 트리를 git 저장소로 만들어 두었습니다.
- **빌드 순서:** 항목마다 다음을 반복했습니다.
  1. `git apply --check`로 패치가 적용되는지 확인합니다.
  2. 패치를 적용하고 빌드합니다.
  3. `git checkout -f . && git clean -fd`로 트리를 되돌립니다.
  4. 트리에 변경이 남았으면 중단합니다.
- **빌드 확인:** 항목 바이너리의 해시가 기준 바이너리와 같으면 빌드가 건너뛰어진 것으로 보고 중단하게 했습니다. 실제로 그런 경우는 없었습니다.
- **ELF 섹션 크기:** `size -A`로 읽었습니다.

## 4. 항목별 상세

모든 수치는 "다국어 브랜치 + 측정 도구"(44a413b529)와 비교한 차이입니다. 음수가 감소이고, 단위는 KB(1024 바이트)입니다. 각 항목의 SHA는 그 항목 브랜치의 끝 커밋입니다.

### 4.1 가드레일 코드 항목

#### 빈 스캔 결과에 빈 `Arc` 하나를 공유 (`items/a1-empty-arc`, b68b0a8749)

- **바꾼 곳:** `tinicore/src/agent/masking_scan_cache.rs`, `tinicore/src/agent/pii_masking.rs`
  - `masking_scan_cache`에 `pub(crate) fn memo(spans: &[SensitiveSpan]) -> Arc<[SensitiveSpan]>`를 추가했습니다.
    - 결과가 비어 있으면 `OnceLock`에 둔 프로세스 전역의 빈 slice를 `Arc::clone`해서 돌려줍니다.
    - 비어 있지 않으면 지금처럼 `Arc::from`입니다.
  - `pii_masking.rs`의 두 곳에서 `None => Arc::from(spans)`를 `memo(spans)` 호출로 바꿨습니다.
    - `mask_messages_for_cloud_in_session`: LLM 입력 마스킹
    - `mask_llm_output_in_session`: LLM 출력 마스킹
  - slot 메모리를 설명하는 주석도 함께 고쳤습니다.
- **기대한 효과:** PII가 없는 메시지마다 생기던 빈 `Arc` 헤더(16 B 블록)가 사라집니다.
- **결과**
  - live heap: 설치 직후 0, 200턴 뒤 −2 KB, 1000턴 뒤 −12 KB
  - 턴당 할당량: 변화 없음
- **판정:** 효과가 미미합니다.
- **테스트:** 빈 결과끼리 같은 slice를 공유하고, 결과가 있으면 따로 할당하는지 확인하는 단위 테스트 1개를 추가했습니다.

#### PatternMeta 축소 (`items/a2-patternmeta`, 4f34133ffd)

- **바꾼 곳:** `tinicore/src/guardrails/engine/recognizer.rs`
  - `PatternMeta.layers`를 `Vec<String>`에서 `Arc<[String]>`로 바꿨습니다.
  - `PatternMeta.boundary_check_reject_before/after`를 `Option<String>`에서 `Option<Arc<str>>`로 바꿨습니다.
  - 이 두 값은 엔진을 한 번 빌드하는 동안 새 구조체 `MetaInterner`가 공유시킵니다.
    - `MetaInterner`는 `HashMap<Vec<String>, Arc<[String]>>`와 `HashMap<String, Arc<str>>`로 이루어져 있습니다.
    - 그래서 값이 같은 recognizer끼리는 하나의 할당을 같이 씁니다.
  - `PatternMeta.context_words`를 `Vec<ContextWord>`에서 새 구조체 `ContextWords`로 바꿨습니다.
    - `ContextWords`는 `text: Box<str>`와 `words: Box<[(u32, u32, Option<CharClass>, Option<CharClass>)]>`를 갖습니다.
    - 모든 단어를 소문자로 바꿔 문자열 하나에 이어 붙이고, 단어마다 범위와 경계 class를 기록합니다.
    - 그래서 단어마다 하던 할당이 recognizer마다 2개로 줄어듭니다.
  - 문맥어 검색 함수 `context_word_found(&str, &ContextWord)`를 `word_found(window, lower, before, after)`로 바꿨습니다. 테스트가 쓰는 원래 형태는 `#[cfg(test)]` 래퍼로 남겼습니다.
  - `passes_boundary_check`가 받는 인자를 `&Option<String>`에서 `Option<&str>`로 바꿨습니다.
- **기대한 효과:** recognizer마다 반복되는 문자열 할당이 줄어듭니다.
- **결과**
  - live heap: 설치 직후 −15 KB, 200턴 뒤 −16 KB, 1000턴 뒤 −14 KB
  - 바이너리: +8 KB(`.text` +6.8 KB)
- **판정:** 약 −15 KB의 효과가 있습니다.
- **주의:** 원래 계획은 layer를 `u64` 비트마스크로, reject 집합을 `[u64; 4]`로 바꾸는 것이었습니다. 임시 구현은 그보다 작은 범위인 공유만 했습니다.

#### 운전면허 패턴을 DFA chunk에서 제외 (`items/a3-licence-out`, 40977277e2)

- **바꾼 곳:** `tinicore/src/guardrails/pii/countries/kr/rules.yaml`
  - `kr_driver_license` recognizer 블록 전체를 지우고, 측정용이라는 주석을 남겼습니다.
  - 지운 정규식에는 지역명(서울, 부산, …) alternation이 들어 있습니다. 그래서 DFA chunk에 한글 바이트 class가 많이 생깁니다.
- **기대한 효과:** 한글 alternation이 만드는 NFA·DFA 상태와 캐시가 줄어듭니다.
- **결과**
  - live heap: 설치 직후 −12 KB, 200턴 뒤 −58 KB, 1000턴 뒤 −52 KB
  - 턴당 할당량: −0.01 %
- **판정:** 탐지를 잃는 변경입니다. 이 수치는 운전면허를 hand-written detector로 다시 구현할 때 넘어야 할 기준으로 씁니다.
- **테스트:** 운전면허를 찾는 filter 테스트 2개가 의도한 대로 실패합니다.

#### reverse DFA를 첫 매치 때 생성 (`items/b1-lazy-reverse`, 62452821ce)

- **바꾼 곳:** `tinicore/src/guardrails/engine/recognizer.rs`
  - `DfaChunk`의 `rev: Arc<DFA>`와 `cache_rev: Mutex<dfa::Cache>`를 `rev: Mutex<LazyRev>` 하나로 바꿨습니다.
  - `enum LazyRev`의 상태는 세 가지입니다.
    - `Pending { patterns: Box<[Box<str>]>, cap }`: 아직 만들지 않았고, 다시 만들 때 쓸 패턴 문자열을 들고 있습니다.
    - `Built { dfa, cache }`: 만들어 둔 상태입니다.
    - `Failed`: 만들다 실패한 상태입니다.
  - `build_dfa_chunks`
    - 빌드할 때 reverse DFA를 한 번 만들고 바로 버립니다. 잘못된 패턴이 지금처럼 빌드 오류가 되게 하려는 것입니다.
    - chunk에는 `Pending`을 넣습니다.
  - `DfaChunkEngine::scan_raw`
    - forward 검색 결과가 비면 reverse 단계를 건너뜁니다.
    - 결과가 있으면 그때 `build_reverse()`로 reverse NFA와 DFA를 만들어 `Built`로 바꿉니다.
    - 실패하면 `warn!`을 남기고 `Failed`로 바꾼 뒤 그 chunk의 매치를 버립니다.
  - reverse DFA 설정은 `reverse_dfa_config()` 함수 하나로 모았습니다.
- **기대한 효과:** 매치가 한 번도 없는 chunk는 reverse DFA와 그 캐시를 들고 있지 않습니다.
- **결과**
  - live heap: 설치 직후 **−105 KB**, 200턴 뒤 **−71 KB**, 1000턴 뒤 **−72 KB**
  - 바이너리: +18 KB
- **판정:** 상한값입니다.
  - bench가 보내는 PII는 KR 전화번호(Aho-Corasick)뿐이고, HTML 주석은 prompt injection 검사 대상입니다. 그래서 DFA chunk에서 매치가 거의 나오지 않습니다. 그래서 reverse DFA를 거의 만들지 않았고, 절약이 크게 보입니다.
  - 계획에 적은 진행 조건이 있습니다. 실제와 비슷한 PII 텍스트를 스캔한 뒤에도 엔진당 순절약이 20 KB 이상이어야 진행합니다. 이 조건은 아직 확인하지 않았습니다.
  - pin off이면 빌드 비용이 늘어납니다. 빌드할 때 한 번, 첫 매치 때 또 한 번 reverse를 컴파일하기 때문입니다.
- **테스트:** 기존 테스트가 통과했습니다.

#### DFA 캐시 비율 3.0 → 1.5 (`items/b2-cache-ratio`, a48a7afc7b)

- **바꾼 곳:** `tinicore/src/guardrails/engine/recognizer.rs`의 `const CACHE_MARGIN_RATIO: f64`를 3.0에서 1.5로 바꿨습니다.
  - chunk마다 lazy DFA 캐시의 상한은 최소 필요량에 이 비율을 곱한 값입니다.
- **기대한 효과:** 캐시가 자랄 수 있는 상한이 절반으로 줄어듭니다.
- **결과**
  - live heap: 설치 직후 0, 200턴 뒤 **−42 KB**, 1000턴 뒤 **−42 KB**
  - 턴당 할당량: +0.15 %(1000턴), 할당 횟수 +0.8 %(200턴)
- **판정:** 캐시가 자주 비워지는 징후가 있습니다. 속도를 측정해야 판정할 수 있습니다.
  - 이 비율은 원래 성능 절벽을 피하려고 정한 값입니다. 그 원인으로 문서에 적힌 `facebook_oauth_2_0`은 이제 hand-written입니다.

#### Aho-Corasick dense 설정 (`items/c9-ac-dense`, 6d5e7eab2a)

- **바꾼 곳:** `tinicore/src/guardrails/pii/handwritten/aho_corasick_detector/mod.rs`
  - `AhoCorasickBuilder`에 `.dense_depth(1)`을 추가했습니다. 기본값은 2입니다.
- **기대한 효과:** 상태 전이를 촘촘한 표로 두는 깊이가 줄어 automaton이 작아집니다.
- **결과**
  - live heap: 설치 직후 −15 KB, 200턴 뒤 −17 KB, 1000턴 뒤 −13 KB
  - 바이너리: +8 KB
- **판정:** 약 −15 KB의 효과가 있습니다. 속도 영향은 측정하지 않았습니다.

#### 작은 텍스트(16 KB 이하)를 별도 스레드 없이 바로 스캔 (`items/c3-inline-scan`, 525bfb1347)

- **바꾼 곳:** 아래 세 곳에서 `text.len() <= 16 * 1024`이면 `tokio::task::spawn_blocking` 대신 현재 스레드에서 바로 스캔합니다. 더 긴 텍스트는 지금처럼 blocking 스레드로 보냅니다.
  - `tinicore/src/guardrails/pii/detector.rs`: `PiiSpanDetector::detect`가 `filter.analyze_with_meta`를 바로 부릅니다.
  - `tinicore/src/guardrails/prompt_injection/detector.rs`: `PromptInjectionDetector::detect`가 `filter.analyze_keep_nested`를 바로 부릅니다.
  - `tinicore/src/agent/prompt_guard.rs`: `evaluate_off_thread`가 `evaluate(&guard, &text)`를 바로 부릅니다.
- **기대한 효과:** 스캔이 남기는 할당이 blocking 스레드마다 생기는 glibc arena에 흩어지지 않습니다.
- **결과**
  - live heap: 변화 없음
  - Pss_Anon: 200턴 뒤 **−1,540 KB**, 1000턴 뒤 **−6,488 KB**
  - trim 뒤 PSS: 200턴 뒤 −904 KB, 1000턴 뒤 −3,300 KB
- **판정:** 가드레일 코드 항목 가운데 PSS를 가장 크게 줄였습니다.
  - 대신 스캔이 async worker 스레드를 잡고 있게 됩니다. 16 KB 스캔에 걸리는 시간을 `bench_scan`으로 확인한 뒤에 채택해야 합니다.
  - 줄어드는 양은 할당하는 스레드 수에 달려 있습니다. 그래서 TV daemon에서는 크기가 다를 수 있습니다. 6장의 argot 측정에서는 `malloc_trim`으로 돌아오는 양이 40~80 KB뿐이었습니다.

#### 마스킹 결과 일괄 복사 줄이기 (`items/c1-batch-copy`, 3d32739621)

- **바꾼 곳:** `tinicore/src/agent/pii_masking.rs`, `tinicore/src/types/message.rs`
  - `mask_messages_for_cloud_in_session`: 마스킹된 메시지가 처음 나오면 결과 `Vec`을 만듭니다.
    - 원래는 `messages[..i].to_vec()`로 만들었습니다.
    - 이를 `Vec::with_capacity(messages.len())` + `extend_from_slice`로 바꿔 한 번에 필요한 크기를 잡습니다.
  - 마스킹된 메시지를 만드는 방식도 바꿨습니다.
    - 원래는 `msg.clone()`으로 원문까지 복제한 뒤 `sanitize_text_content`로 덮어썼습니다.
    - 이를 새 함수 `ChatMessage::clone_with_sanitized_text(&self, sanitized: String)`로 바꿨습니다. 이 함수는 텍스트가 아닌 부분만 복제하고 새 텍스트를 넣습니다.
  - `sanitize_text_content`: 새 텍스트를 `clone`하지 않고 `pending.take()`로 옮겨 넣습니다.
- **기대한 효과:** 턴마다 하던 대화 기록 복사와 원문 복제가 줄어듭니다.
- **결과**
  - 턴당 할당량: **−7.3 %** (1000턴 기준 −719 KB)
  - live heap: 변화 없음
  - peak heap: **+119 KB(200턴), +719 KB(1000턴)**
  - Pss_Anon: 200턴 뒤 +332 KB로 노이즈보다 큽니다. 1000턴 뒤 +1,008 KB는 노이즈(약 ±1 MB) 범위입니다.
- **판정:** 할당량은 줄었지만 peak heap이 늘었습니다. 원인은 확인하지 않았습니다.
  - 할당량 감소의 일부는 결과 `Vec`이 자라면서 하던 realloc이 사라진 몫일 수 있습니다. 턴당 할당량은 realloc의 새 크기도 더하기 때문입니다.

#### 검사할 텍스트를 복사하지 않고 빌림 (`items/c5-text-cow`, b042a3464e)

- **바꾼 곳:**
  - `tinicore/src/agent/loop_.rs`: 입력 가드레일 검사의 `texts_to_check`를 `Vec<String>`(`m.text()`)에서 `Vec<Cow<str>>`(`m.text_cow()`)로 바꿨습니다.
  - `tinicore/src/agent/guardrail_scan_cache.rs`: `verify_prefix`가 `&[String]` 대신 `&[S] where S: AsRef<str>`를 받도록 바꿨습니다.
  - `tinicore/src/agent/pii_masking.rs`: `mask_llm_output_in_session`의 `msg.text_cow().into_owned()`에서 `into_owned()`를 뺐습니다.
- **기대한 효과:** 턴마다 대화 기록의 텍스트를 복사하던 몫이 줄어듭니다.
- **결과**
  - 턴당 할당량: −0.7 %(200턴), −0.8 %(1000턴)
  - live heap: 변화 없음
- **판정:** 미미합니다.

#### checkpoint를 복제하지 않고 꺼내기 (`items/c7-checkpoint-take`, 6494aa38c8)

- **바꾼 곳:** `tinicore/src/agent/masking_scan_cache.rs`의 `checkpoint_for`
  - 원래는 `bucket.sessions.get(session_key)?.clone()`으로 checkpoint를 복제했습니다.
  - 이를 `bucket.sessions.remove(session_key)?`로 꺼내도록 바꿨습니다. 다음 `record_checkpoint`가 새 checkpoint를 다시 넣습니다.
  - 그 다음 줄의 `bucket.session_order.touch(session_key.to_string())`도 지웠습니다. 그래서 읽기만 해서는 LRU 순서가 갱신되지 않습니다.
- **기대한 효과:** 턴마다 slot 배열 전체를 복제하던 몫이 사라집니다.
- **결과**
  - 턴당 할당량: −0.4 %
  - live heap: 변화 없음
- **판정:** 제외를 권합니다. 동작이 바뀌는 변경입니다.
  - checkpoint를 꺼낸 뒤 기록하지 않고 끝나는 호출이 있으면, 다음 호출은 전체를 다시 스캔합니다.
  - 이 브랜치의 커밋 메시지에는 `checkpoint_for`를 두 번 읽는 테스트 4개가 실패한다고 기록했습니다. 합본에서는 lib 테스트 2개가 실패했습니다. 두 수가 다른 이유는 확인하지 않았습니다.

#### prompt guard 캐시 키를 SHA-256으로 (`items/c10-guard-key`, 3e329315c9)

- **바꾼 곳:** `tinicore/src/agent/prompt_guard.rs`
  - `COMPILED_GUARD_CACHE`가 들고 있던 `(PromptGuardConfig, Arc<CompiledGuard>)`를 `([u8; 32], Arc<CompiledGuard>)`로 바꿨습니다.
  - 키는 새 함수 `config_key()`가 만듭니다. `serde_json::to_vec(config)`의 SHA-256입니다.
  - `compile_cached`는 설정을 복사해 비교하지 않고 키를 비교합니다.
- **기대한 효과:** 규칙 목록 사본을 들고 있지 않습니다.
- **결과**
  - live heap: −2~−3 KB
  - 턴당 할당량: +0.1 %(1000턴), +0.3 %(200턴). `compile_cached`를 부를 때마다 설정을 직렬화하기 때문입니다.
- **판정:** 미미합니다.

#### 세션 키 문자열 할당 줄이기 (`items/c6-session-keys`, c8a496d49c)

- **바꾼 곳:** `tinicore/src/agent/guardrail_scan_cache.rs`, `tinicore/src/agent/masking_scan_cache.rs`
  - `Lru<String>`에 `touch_str(&str)`를 추가했습니다. 이미 있는 키는 새 `String`을 만들지 않고 뒤로 옮깁니다.
  - `checkpoint_for`와 `record_checkpoint`에서 `touch(session_key.to_string())`를 `touch_str(session_key)`로 바꿨습니다.
  - 이미 있는 세션이면 `get_mut`으로 값만 바꿉니다. 그래서 키를 새로 할당하지 않습니다.
- **결과:** 대화 1개와 5개 모두 변화가 없었습니다.
- **판정:** 효과가 없습니다.

#### 스캔할 때마다 하던 할당 줄이기 (`items/c8-scan-allocs`, 64608d3347)

- **바꾼 곳:** `tinicore/src/guardrails/engine/filter.rs`
  - `PatternFilter.active`를 `ActiveFilter`에서 `Arc<ActiveFilter>`로 바꿨습니다. 필터를 복제할 때 layer 이름이나 type 목록을 복사하지 않습니다.
  - `ActiveFilter::keeps(meta)`를 추가했습니다.
  - `analyze`는 스캔마다 pid 표(`keep_table`)를 만들지 않고, 매치마다 `keeps`로 거릅니다.
- **결과:** live heap과 할당량 모두 변화가 없었습니다.
- **판정:** 효과가 없습니다.

#### 캐시 상한 축소 (`items/b3-cache-caps`, cd7f304ac5)

- **바꾼 곳:**
  - `tinicore/src/agent/guardrail_scan_cache.rs`: `MAX_CHAINS` 3 → 1, `MAX_SESSIONS_PER_CHAIN` 128 → 3
  - `tinicore/src/agent/masking_scan_cache.rs`: `MAX_CHAINS` 3 → 2, `MAX_SESSIONS_PER_CHAIN` 8 → 3
- **결과 (대화 1개):** 변화가 없었습니다. 대화가 하나뿐이면 상한에 닿지 않습니다.
- **결과 (대화 5개를 번갈아 사용, `--conversations 5`):** 같은 부하로 돌린 기준과 비교했습니다.

| 구성 | live heap 200턴 / 1000턴 | 턴당 할당량 200턴 / 1000턴 | PSS 1000턴 뒤 |
| --- | --- | --- | --- |
| 기준(대화 5개) | 1,039 / 2,081 KB | 735 / 2,286 KB | 14,234 KB |
| 캐시 상한 축소 | −12 / −67 KB | **+28 % / +48 %** | **+1,268 KB**(모두 Pss_Anon) |
| 세션 키 할당 줄이기 | +3 / −1 KB | 변화 없음 | −16 KB |

- **판정:** 대화가 여러 개면 악화됩니다.
  - 두 캐시 모두 세션을 3개로 제한했으므로, 5개 대화를 번갈아 쓰면 캐시가 계속 빗나갑니다. 그래서 스캔을 다시 하고 할당이 늘어납니다.
  - 두 캐시의 상한을 함께 바꿨으므로, 증가가 어느 캐시에서 왔는지는 이 측정으로 나눌 수 없습니다.

#### 설치할 때 엔진 미리 데우기 (`items/c2-prewarm`, c481902c1f)

- **바꾼 곳:** `tinicore/src/guardrails/install.rs`
  - `install_guardrails_from_config` 끝에서, `pin_engines`가 켜져 있으면 `prewarm_pinned_engines()`를 부릅니다.
  - 이 함수는 고정된 예문 3개(영어 PII, 한국어 PII, 숫자열과 HTML 주석)를 두 엔진으로 스캔합니다.
    - PII 엔진: `pii::shared_layer_filter("default")`
    - prompt injection 엔진: `prompt_injection::shared::slot().acquire()`
- **기대한 효과:** DFA 캐시가 설치 스레드에서 미리 자라, 턴 도중에 흩어져 자라지 않습니다.
- **결과**
  - live heap: 설치 직후 **+155 KB**, 200턴 뒤 +34 KB, 1000턴 뒤 +36 KB
- **판정:** 메모리가 오히려 늘었습니다. 제외합니다.

#### 후보 11개 합본 (`items/zz-all-safe`, a3c97523ca)

- **구성:** 아래 11개 항목을 차례로 얹었습니다.
  - 빈 `Arc` 공유, PatternMeta 축소, FixedShape, YAML 주석 제거
  - 일괄 복사 줄이기, 텍스트 빌림, 세션 키, 스캔 할당
  - Aho-Corasick dense, guard 캐시 키, checkpoint 꺼내기
- **충돌 해결:** checkpoint 꺼내기와 세션 키가 같은 줄을 고쳐서 충돌했습니다. `remove`를 쓰는 쪽으로 손으로 합쳤습니다.
- **결과**
  - live heap: 설치 직후 **−32 KB**, 200턴 뒤 **−35 KB**, 1000턴 뒤 **−46 KB**
  - 턴당 할당량: **−7.9 %(200턴), −8.4 %(1000턴)**
  - peak heap: +68 KB(200턴), +602 KB(1000턴). 일괄 복사 항목에서 온 것입니다.
  - 설치 직후 PSS: −192 KB. base와의 차이가 +307 KB에서 +115 KB로 줄었습니다.
  - 바이너리: −68 KB
- **판정:** 지표에 따라 개별 항목의 합과 맞기도 하고 다르기도 합니다.
  - 합과 맞는 지표: 설치 직후 live heap(항목 합 −31.7 KB, 합본 −32.3 KB), 1000턴 턴당 할당량(둘 다 −826 KB)
  - 합과 다른 지표: 바이너리(항목 합 약 −28 KB, 합본 −68 KB), 설치 직후 PSS(항목 합 +100 KB, 합본 −192 KB). PSS와 바이너리는 빌드 배치에 따라 움직이기 때문입니다.
  - 합본에는 제외를 권한 checkpoint 꺼내기 항목이 들어 있습니다. 위 수치에도 그 몫이 포함됩니다.
- **테스트:** lib 테스트 1065개가 통과했고, 2개가 실패했습니다. 실패한 2개는 checkpoint 꺼내기 항목에서 예상한 실패입니다.

### 4.2 바이너리를 바꾸는 항목

#### 빌드할 때 나라 선택: common·kr·us만 (`items/a6-build-krus`, cfb844c0f4)

- **바꾼 곳:**
  - `tinicore/src/guardrails/pii/countries/mod.rs`: `common`, `kr`, `us` 외의 `mod` 선언을 지웠습니다.
  - `tinicore/src/guardrails/pii/rules.rs`: `PiiCountry::rules()`에서 나머지 나라는 빈 규칙 `CountryRules::new("recognizers: {}\n")`을 돌려주도록 바꿨습니다.
  - 실제로 쓸 때는 Cargo feature로 나라를 고르는 방식이 될 것입니다. 이번 구현은 측정용으로 코드에서 바로 지웠습니다.
- **결과**
  - 바이너리: **−231 KB**
  - 설치 직후 Pss_File −52 KB, PSS −100 KB
  - 200턴 뒤 Pss_File −192 KB
- **판정:** 바이너리는 크게 줄지만 PSS 효과는 노이즈 근처입니다.
  - 고르지 않은 나라의 코드와 규칙 데이터는 실행 중에 읽히지 않으므로 원래 페이지로 잡히지 않습니다.
  - 다만 relocation 데이터는 시작할 때 처리되므로 줄어듭니다. `.data.rel.ro` −48 KB, `.rela.dyn` −69 KB가 줄었고, 설치 직후 Pss_Anon −48 KB가 이와 맞습니다.
  - 200턴 뒤 Pss_File −192 KB는 빌드 배치 노이즈(+140~+172 KB)를 조금 넘습니다.

#### 내장 YAML에서 주석 줄 제거 (`items/a5-yaml`, ba91304f0c)

- **바꾼 곳:**
  - `tinicore/build.rs`에 `strip_guardrail_rule_comments()`를 추가했습니다.
    - 대상: `pii/countries/*/rules.yaml`과 `prompt_injection/config/rules.yaml`
    - 줄 전체가 주석인 줄을 빈 줄로 바꿔 `OUT_DIR/guardrails/…`에 씁니다. 빈 줄로 남기면 YAML 오류의 줄 번호가 원본과 같게 유지됩니다.
    - 줄 끝 주석은 그대로 둡니다. scalar 안의 `#`과 구별하려면 YAML 파서가 필요하기 때문입니다.
    - `pii/countries` 디렉터리, 나라별 `rules.yaml`, prompt injection의 `rules.yaml`에 `cargo:rerun-if-changed`를 출력합니다.
  - `common`과 각 나라의 `countries/<code>/mod.rs`에서 `include_str!("rules.yaml")`을, `prompt_injection/mod.rs`에서 `include_str!("config/rules.yaml")`을 `include_str!(concat!(env!("OUT_DIR"), "/guardrails/…/rules.yaml"))`로 바꿨습니다.
  - 동치 테스트 2개를 추가했습니다(`pii/mod.rs`, `prompt_injection/mod.rs`). 원본과 사본을 각각 `serde_yaml::Value`로 파싱해 같은지, 사본에 주석 줄이 남지 않았는지 확인합니다.
- **결과**
  - 바이너리: `.rodata` **−72 KB**
  - 설치 직후 Pss_File −60 KB
  - live heap: 변화 없음
- **판정:** 바이너리만 줄어듭니다.
- **덧붙임:** 원래 계획에는 YAML을 압축해 넣는 시험도 있었습니다. 이번 회차에서는 만들지 않았습니다.

#### FixedShape 표에서 함수 포인터 제거 (`items/a4-fixedshape`, a0ef425230)

- **바꾼 곳:**
  - `tinicore/src/guardrails/pii/handwritten/fixed_shape_detector/mod.rs`
    - `struct Class([u64; 4])`를 추가했습니다. 256비트 바이트 집합이며, `has(b)`가 비트 하나를 조회합니다.
    - 매크로 `cls!(pred)`를 추가했습니다. `const fn(u8) -> bool` predicate로 컴파일 시점에 `Class`를 계산합니다.
    - `enum Seg`를 `Run(fn(u8) -> bool, usize)` / `Opt(fn(u8) -> bool)`에서 `Run(Class, u8)` / `Opt(Class)`로 바꿨습니다.
    - `segment_ends`와 `first_two_byte_sets`가 함수 호출 대신 비트 조회를 하도록 고쳤습니다.
  - `fixed_shape_detector/preds.rs`
    - 모든 predicate를 `const fn`으로 바꿨습니다.
    - `RangeInclusive::contains`는 `const fn`이 아니어서 `matches!`로 바꿨습니다.
    - slice `contains`의 `const fn` 대체로 `in_set`을 추가했습니다.
  - 12개 나라의 `countries/<code>/shaped.rs`
    - `Run(digit, 2)` 형태를 모두 `Run(cls!(digit), 2)` 형태로 바꿨습니다.
    - 나라별 predicate도 `const fn`으로 바꿨습니다.
- **기대한 효과:** 함수 포인터 약 2,300개에 딸린 load-time relocation이 사라집니다. relocation이 없어지면 `.rela.dyn`과 `.data.rel.ro`가 줄어듭니다.
- **결과**
  - 바이너리: −6 KB
    - `.rodata` +88 KB
    - `.data.rel.ro` −36 KB, `.rela.dyn` −54 KB
  - 설치 직후 Pss_File −64 KB, PSS −100 KB. 노이즈 안입니다.
- **판정:** 임시 구현이 계획과 달라서 효과가 상쇄되었습니다.
  - 임시 구현은 segment마다 32 B짜리 `Class`를 직접 넣었습니다. 그래서 `.rodata`가 늘었습니다.
  - 계획은 segment에 클래스 id만 두고, 클래스별 256비트 표는 따로 한 번만 두는 것이었습니다. 계획대로 하면 relocation 절약을 대부분 지킬 수 있을 것입니다.
  - 이전 회차(가드레일을 끈 시작 시점)에서는 이 항목만 PSS를 −148 KB 줄였습니다. 이번 결과와 함께 다시 확인해야 합니다.

### 4.3 링커와 프로세스 설정

#### lld 링커 + RELR

- **바꾼 곳:** 코드는 바꾸지 않았습니다. 빌드할 때 `RUSTFLAGS`만 바꿨습니다.
  - lld만 적용: `-C link-arg=-B<rustlib>/bin/gcc-ld -C link-arg=-fuse-ld=lld`
    - `<rustlib>`은 툴체인의 `lib/rustlib/aarch64-unknown-linux-gnu`입니다.
  - lld + RELR: 위에 `-C link-arg=-Wl,-z,pack-relative-relocs`를 더했습니다.
  - VM의 기본 링커(BFD ld 2.42)는 aarch64에서 `-z pack-relative-relocs`를 무시합니다(`warning: -z pack-relative-relocs ignored`). 그래서 Rust 툴체인에 들어 있는 lld를 썼습니다.
- **결과**

| 구성 | `.rela.dyn` | RELR 표 | 바이너리 | 설치 직후 Pss_File / PSS | 200턴 뒤 PSS |
| --- | --- | --- | --- | --- | --- |
| lld만 적용 | 818 KB | 없음 | 0 | +167 / +172 KB | +28 KB |
| lld + RELR | **1 KB** | 10 KB | **−807 KB** | **−784 / −780 KB** | −493 KB |

- **판정:** 가장 큰 효과입니다.
  - lld만 적용한 결과는 빌드 배치 노이즈 범위입니다. 따라서 RELR의 효과가 링커를 바꾼 효과는 아닙니다.
  - 설치 직후 PSS가 7,438 KB로 base(7,901 KB)보다 작아집니다. 하지만 base에 같은 설정을 적용해도 같은 만큼 줄어들 것이므로, 다국어 때문에 생긴 차이를 메우는 수단은 아닙니다.
- **확인할 점**
  - 실행하는 기기의 glibc가 2.36 이상이어야 RELR을 읽을 수 있습니다.
  - armv7은 REL 항목이 8 B라서 절약이 aarch64보다 작습니다.
  - argo-tizen 빌드 설정에서 다룰 일입니다.

#### glibc arena 1개로 제한 (`arena_max=1`)

- **바꾼 곳:** 코드는 바꾸지 않았습니다. 실행할 때 `GLIBC_TUNABLES=glibc.malloc.arena_max=1`을 줬습니다.
- **결과**
  - Pss_Anon: 200턴 뒤 **−1,136 KB**, 1000턴 뒤 **−6,280 KB**
  - trim 뒤 PSS: 200턴 뒤 −896 KB, 1000턴 뒤 −2,584 KB
  - live heap과 할당량: 변화 없음
- **판정:** 큰 효과가 있지만, 가드레일 코드가 아니라 호스트 쪽 설정입니다.
  - 호스트가 `main`에서 `mallopt(M_ARENA_MAX, 1)`을 부르는 방식으로도 같은 효과를 낼 수 있습니다.
  - 모든 스레드가 arena 하나를 나눠 쓰므로 할당 경합이 늘 수 있습니다. 측정하지 않았습니다.

## 5. 전체 결과 표

- 숫자는 대부분 "다국어 브랜치 + 측정 도구"와 비교한 차이입니다. 첫 줄만 절대값입니다.
- 음수가 감소이고, 단위는 KB입니다.
- 턴당 할당량은 1000턴 기준입니다.

| 분류 | 구성 | live heap 설치 직후 / 200턴 뒤 / 1000턴 뒤 | Pss_Anon 200턴 뒤 / 1000턴 뒤 | 설치 직후 Pss_File / PSS | 턴당 할당량 | 바이너리 크기 | 판정 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 기준 | 다국어 브랜치 + 측정 도구 (절대값) | 377 / 1,008 / 1,948 | 5,664 / 15,928 | 6,464 / 8,208 | 9,874 | 12,951 | 비교 기준 |
| 기준 | 다국어 이전 base | +1 / +1 / +7 | −84 / +444 | −244 / **−307** | 0 % | −305 | 목표 차이 |
| 노이즈 | 같은 바이너리를 다시 측정 | 0 / −1 / −1 | −56 / **−1,064** | 0 / +4 | 0 % | 0 | 턴 뒤 PSS 노이즈 |
| 노이즈 | 컴파일 옵션만 다르게 빌드 | 0 / 0 / +3 | +24 / +4 | **+140** / +140 | 0 % | 0 | Pss_File 노이즈 |
| 가드레일 코드 | reverse DFA를 첫 매치 때 생성 | **−105 / −71 / −72** | +76 / +556 | +68 / +32 | 0 % | +18 | 상한값, 재확인 필요 |
| 가드레일 코드 | 운전면허 패턴을 DFA chunk에서 제외 | −12 / **−58 / −52** | −36 / +300 | 0 / −16 | 0 % | 0 | 탐지 손실, 기준값 |
| 가드레일 코드 | DFA 캐시 비율 3.0 → 1.5 | 0 / **−42 / −42** | −56 / +560 | 0 / 0 | +0.15 % | 0 | 속도 확인 필요 |
| 가드레일 코드 | PatternMeta 축소 | −15 / −16 / −14 | −36 / +460 | +16 / −16 | 0 % | +8 | 약 −15 KB |
| 가드레일 코드 | Aho-Corasick dense 설정 | −15 / −17 / −13 | −16 / +412 | +60 / +52 | 0 % | +8 | 약 −15 KB |
| 가드레일 코드 | 작은 텍스트를 바로 스캔 | 0 / 0 / +3 | **−1,540 / −6,488** | +124 / +124 | 0 % | +17 | 큰 효과, 지연 확인 필요 |
| 가드레일 코드 | 마스킹 결과 일괄 복사 줄이기 | 0 / 0 / +3 | +332 / +1,008 | +60 / +64 | **−7.3 %** | +12 | peak +719 KB |
| 가드레일 코드 | 검사할 텍스트를 빌림 | 0 / +1 / −3 | −36 / +304 | 0 / +4 | −0.8 % | 0 | 미미 |
| 가드레일 코드 | checkpoint를 꺼내기 | 0 / −1 / +2 | −48 / +64 | 0 / +4 | −0.4 % | 0 | 제외 권장 |
| 가드레일 코드 | prompt guard 캐시 키 SHA-256 | −3 / −2 / −3 | +40 / +520 | +76 / +84 | +0.1 % | +9 | 미미 |
| 가드레일 코드 | 빈 `Arc` 공유 | 0 / −2 / −12 | −24 / +564 | 0 / 0 | 0 % | 0 | 미미 |
| 가드레일 코드 | 세션 키 할당 줄이기 | 0 / −1 / +2 | −28 / +552 | +60 / +64 | 0 % | +8 | 효과 없음 |
| 가드레일 코드 | 스캔 할당 줄이기 | 0 / +1 / −1 | −32 / +336 | −4 / +4 | 0 % | +4 | 효과 없음 |
| 가드레일 코드 | 캐시 상한 축소 | 0 / +1 / −1 | +4 / +812 | 0 / 0 | 0 % | 0 | 대화 여러 개에서 악화 |
| 가드레일 코드 | 설치할 때 엔진 미리 데우기 | **+155** / +34 / +36 | −8 / +556 | +56 / +132 | 0 % | +5 | 악화, 제외 |
| 가드레일 코드 | 후보 11개 합본(checkpoint 꺼내기 포함) | **−32 / −35 / −46** | +244 / +1,864 | −109 / **−192** | **−8.4 %** | −68 | base 차이 +115 KB |
| 바이너리 | 빌드할 때 나라 선택 | 0 / 0 / −1 | −64 / +448 | −52 / −100 | 0 % | **−231** | PSS 효과 작음 |
| 바이너리 | 내장 YAML 주석 제거 | 0 / −2 / +3 | −20 / +740 | −60 / −60 | 0 % | −72 | 바이너리만 |
| 바이너리 | FixedShape 함수 포인터 제거 | 0 / 0 / +3 | −152 / +756 | −64 / −100 | 0 % | −6 | 구현 형태 문제 |
| 링커 | lld만 적용 | 0 / +1 / +3 | −12 / +496 | +167 / +172 | 0 % | 0 | 대조군 |
| 링커 | lld + RELR | 0 / +1 / 0 | −60 / +828 | **−784 / −780** | 0 % | **−807** | 가장 큰 효과 |
| 프로세스 설정 | `arena_max=1` | 0 / +1 / −1 | **−1,136 / −6,280** | 0 / −16 | 0 % | 0 | 큰 효과, 호스트 설정 |

- **표를 읽을 때 주의할 점**
  - 1000턴 뒤 Pss_Anon은 같은 바이너리도 약 1 MB씩 흔들립니다. 그래서 이 열에서 ±1 MB 이내의 차이는 판단에 쓰지 않습니다.
  - lld 두 줄은 따로 돌린 측정입니다. 그때 함께 돌린 기준과 비교한 값입니다.

## 6. 턴 수에 따른 변화

### 6.1 bench를 100턴마다 측정

- **실행 방법:** `--turns 1000 --every 100 --settle 12`로 한 프로세스 안에서 100턴마다 값을 읽었습니다.
  - 가드레일 켬은 `--pin on --countries us,kr`이고, 가드레일 끔은 `--guardrails off`입니다.
- **주의:** 중간 지점은 턴을 돌리는 도중에 대기 없이 읽은 값이라 idle이 아닙니다. idle 상태에서 잰 것은 설치 직후, 1000턴 + 12초 대기 뒤, `malloc_trim` 뒤뿐입니다.
- PSS 칸의 두 숫자는 두 번 실행한 결과입니다.

| 시점 | live heap 켬 | live heap 끔 | PSS 켬 | PSS 끔 | PSS 바로 스캔 | PSS `arena_max=1` |
| --- | --- | --- | --- | --- | --- | --- |
| 설치 직후 | 378 | 61 | 8,214 / 8,214 | 5,243 / 5,239 | 8,255 | 8,194 |
| 100턴 | 872 | 414 | 11,392 / 11,484 | 9,725 / 9,709 | 11,613 | 10,980 |
| 200턴 | 1,016 | 533 | 12,752 / 14,208 | 10,805 / 10,701 | 12,925 | 11,968 |
| 400턴 | 1,273 | 772 | 17,772 / 16,832 | 12,533 / 12,641 | 14,625 | 12,676 |
| 600턴 | 1,672 | 1,139 | 20,192 / 20,080 | 13,145 / 14,629 | 15,305 | 13,976 |
| 800턴 | 1,810 | 1,250 | 23,292 / 22,900 | 16,373 / 17,197 | 16,321 | 16,000 |
| 1000턴 + 12초 대기 | 1,945 | 1,361 | 27,188 / 29,460 | 17,805 / 22,461 | 19,297 | 18,672 |
| 그 뒤 `malloc_trim` | 1,945 | 1,361 | 19,432 / 17,304 | 12,605 / 13,625 | 15,089 | 14,264 |

- **live heap은 가드레일을 끄고 켜는 것과 상관없이 거의 같은 기울기로 늘어납니다.** bench가 대화 기록을 계속 쌓기 때문입니다.
  - 300턴과 600턴에서 크게 한 번씩 뛰는 것도 두 경우가 같습니다. 대화 기록 `Vec`이 용량을 두 배로 늘리며 다시 할당하는 자리로 보입니다.
- **가드레일 몫의 live heap은 거의 늘지 않습니다.** 켬과 끔의 차이가 200턴 뒤 483 KB, 1000턴 뒤 584 KB입니다. 설치 직후의 317 KB를 빼면 200턴 이후 100턴마다 약 13 KB씩 늘어납니다. masking 캐시가 메시지마다 slot을 하나씩 두기 때문으로 보이지만, 확인하지는 않았습니다.
- **가드레일 몫의 PSS는 계속 벌어집니다.**
  - 켬과 끔의 차이가 200턴 뒤 1.9~3.5 MB, 1000턴 뒤 7.0~9.4 MB입니다(같은 회차끼리 비교).
  - 같은 시점의 live heap 차이는 0.6 MB뿐이므로, 나머지는 glibc가 해제하고도 돌려주지 않은 메모리입니다.
  - 바로 스캔하거나 `arena_max=1`을 쓰면 가드레일을 끈 경우와 비슷한 수준으로 내려옵니다.

### 6.2 argot daemon을 2000턴 측정

- **대상:** argo-tizen origin/main 3a32d2e92(v0.6.18)의 `argot` daemon을 VM에서 release로 빌드했습니다.
  - 가드레일 설정은 출시 상태 그대로이며, `pin_engines`가 켜져 있습니다.
- **VM에서만 바꾼 것**
  - `--features argot-host-tv/test-util`로 빌드해 테스트 계정 파일(`ARGOT_ACCOUNT_IDENTITY_FIXTURE`)을 읽게 했습니다. 이 기능이 없으면 모든 턴이 "TV account identity is not ready"로 거부됩니다.
  - `crates/argot-daemon/src/resource_limits.rs`의 `requests_per_minute`를 10에서 1,000,000으로 바꿨습니다. 그대로 두면 분당 11번째 턴부터 거부됩니다.
- **턴 형태:** argo-tizen-e2e의 mock LLM을 상대로 턴마다 새 대화를 엽니다.
  - 각 턴에는 전화번호(PII 검사)와 `bash_run` 도구 호출(tool output 검사)이 들어 있습니다.
  - 2000턴 모두 성공했습니다.
- **측정 방법:** 100턴마다 25초를 기다린 뒤 idle 상태에서 쟀습니다.
  - 부팅 직후 값만 5초를 기다린 뒤 쟀습니다.
  - live heap은 gdb로 `malloc_stats()`를 불러 얻은 glibc의 in-use 바이트입니다.
  - 가드레일 켬과 끔을 차례로 1회씩 돌렸습니다.

| 시점 | PSS 켬 | PSS 끔 | 차이 | Pss_Anon 켬 / 끔 | Pss_File 켬 / 끔 | live heap 켬 / 끔 |
| --- | --- | --- | --- | --- | --- | --- |
| 부팅 직후 | 17,735 | 17,303 | +432 | 5,492 / 5,264 | 12,243 / 12,039 | 3,491 / 3,244 |
| 100턴 | 20,970 | 20,350 | +620 | 8,536 / 7,900 | 12,434 / 12,450 | 4,866 / 4,290 |
| 200턴 | 21,122 | 20,626 | +496 | 8,688 / 8,176 | 12,434 / 12,450 | 4,955 / 4,339 |
| 400턴 | 21,246 | 20,878 | +368 | 8,812 / 8,428 | 12,434 / 12,450 | 5,014 / 4,424 |
| 600턴 | 21,346 | 20,874 | +472 | 8,912 / 8,424 | 12,434 / 12,450 | 5,079 / 4,490 |
| 800턴 | 21,470 | 20,846 | +624 | 9,036 / 8,396 | 12,434 / 12,450 | 5,094 / 4,488 |
| 1000턴 | 21,462 | 20,806 | +656 | 9,028 / 8,356 | 12,434 / 12,450 | 5,116 / 4,498 |
| 1200턴 | 21,526 | 21,026 | +500 | 9,092 / 8,576 | 12,434 / 12,450 | 5,137 / 4,517 |
| 1400턴 | 21,566 | 20,946 | +620 | 9,132 / 8,496 | 12,434 / 12,450 | 5,156 / 4,529 |
| 1600턴 | 21,558 | 20,974 | +584 | 9,124 / 8,524 | 12,434 / 12,450 | 5,174 / 4,561 |
| 1800턴 | 21,550 | 20,994 | +556 | 9,116 / 8,544 | 12,434 / 12,450 | 5,234 / 4,612 |
| 2000턴 | 21,530 | 21,074 | +456 | 9,096 / 8,624 | 12,434 / 12,450 | 5,236 / 4,630 |
| 그 뒤 `malloc_trim` | 21,490 | 20,994 | +496 | 9,056 / 8,544 | 12,434 / 12,450 | 5,236 / 4,627 |

- **첫 100턴이 증가의 대부분입니다.** 가드레일 켬은 +3,235 KB, 끔은 +3,047 KB가 올라 거의 같습니다.
- **200턴 이후에는 천천히 늘다가 멈춥니다.**
  - 가드레일 켬 기준으로 200턴에서 1,200턴 사이에 +404 KB(약 2 %)가 더 늘었습니다.
  - 1,200턴부터 2,000턴까지는 21,458~21,566 KB 사이에 머뭅니다.
  - 가드레일을 끈 경우도 같은 모양입니다.
- **가드레일 몫은 100턴부터 늘지 않습니다.** 100턴마다 잰 값 전체(표에 없는 지점 포함)에서 PSS 차이는 +332~+656 KB, live heap 차이는 +576~+632 KB 사이를 오르내립니다.
  - 따라서 턴마다 새 대화를 여는 이 형태에서는 구성끼리 비교하는 측정이 200턴이면 충분합니다.
  - 대화 하나가 계속 길어지는 6.1의 bench에서는 켬과 끔의 PSS 차이가 1000턴까지 계속 벌어졌으므로, 이 결론을 그대로 옮길 수 없습니다.
- **live heap은 두 경우 모두 100턴마다 약 20 KB씩 늘어납니다.** 가드레일과 상관없는 daemon 쪽 증가입니다. 턴마다 새 대화를 만들기 때문에 대화별 상태가 쌓이는 것으로 보이지만, 원인은 확인하지 않았습니다.
- **`malloc_trim`으로 돌아오는 양은 40~80 KB뿐입니다.** bench에서는 arena가 수 MB를 잡고 있었지만, 실제 daemon에서는 그런 몫이 거의 없습니다.
- **한계**
  - VM은 64비트라 TV(32비트)와 절대값이 다릅니다.
  - 대화 하나를 길게 이어 가는 경우는 재지 않았습니다.
  - 구성마다 1회만 돌렸으므로, 100 KB 이하의 차이는 노이즈와 구별하기 어렵습니다.

## 7. 측정하지 않은 후보와 이유

- **vault 구조 변경:** 보안에 민감하고 변경 범위가 커서 제외했습니다.
- **나머지 relocation 표:** 검증기 표(`&'static dyn Validator`), Aho-Corasick 표, `CARD_BRANDS`가 남아 있습니다. 남은 양이 작아 효과가 작을 것으로 보았습니다.
- **YAML 압축:** 이번 회차에서는 만들지 않았습니다.
- **기각된 항목:** 사용자 결정으로 제외한 항목은 측정하지 않았습니다.

## 8. 남은 결정과 후속 작업

- **작은 텍스트를 바로 스캔:** 16 KB 스캔의 지연을 `bench_scan`으로 측정한 뒤 채택 여부를 정합니다.
- **lld + RELR:** argo-tizen 빌드 설정에서 검토합니다. TV의 glibc 버전 확인이 먼저입니다.
- **`arena_max=1`:** 호스트 쪽 설정으로 검토합니다. 할당 경합을 확인해야 합니다.
- **reverse DFA 지연 생성:** 실제와 비슷한 PII 텍스트로 순절약을 다시 잽니다. pin off일 때의 빌드 비용도 함께 잽니다.
- **DFA 캐시 비율 1.5:** 속도를 측정합니다.
- **운전면허:** hand-written detector로 다시 구현하고, live heap −52~−58 KB와 비교합니다.
- **FixedShape:** 계획대로 클래스 id와 별도의 표로 다시 구현해 relocation 절약을 확인합니다.
- **일괄 복사 줄이기:** peak heap이 늘어난 원인을 확인합니다.
- **제외할 항목:** 엔진 미리 데우기, checkpoint 꺼내기, 지금 값의 캐시 상한 축소

## 부록 A. 브랜치

모두 `~/Works/ARGO-multilingual-memory-opt` worktree의 로컬 브랜치이며, 원격에 push하지 않았습니다.

| 브랜치 | 끝 커밋 | 내용 |
| --- | --- | --- |
| `dev/byungchul.so/multilingual-memory-opt` | 44a413b529 | 다국어 브랜치 + 임시 측정 도구 |
| `items/a1-empty-arc` | b68b0a8749 | 빈 `Arc` 공유 |
| `items/a2-patternmeta` | 4f34133ffd | PatternMeta 축소 |
| `items/a3-licence-out` | 40977277e2 | 운전면허 패턴 제외 |
| `items/a4-fixedshape` | a0ef425230 | FixedShape 함수 포인터 제거 |
| `items/a5-yaml` | ba91304f0c | 내장 YAML 주석 제거 |
| `items/a6-build-krus` | cfb844c0f4 | 빌드할 때 나라 선택 |
| `items/b1-lazy-reverse` | 62452821ce | reverse DFA 지연 생성 |
| `items/b2-cache-ratio` | a48a7afc7b | DFA 캐시 비율 1.5 |
| `items/b3-cache-caps` | cd7f304ac5 | 캐시 상한 축소 |
| `items/c1-batch-copy` | 3d32739621 | 마스킹 결과 일괄 복사 줄이기 |
| `items/c2-prewarm` | c481902c1f | 엔진 미리 데우기 |
| `items/c3-inline-scan` | 525bfb1347 | 작은 텍스트를 바로 스캔 |
| `items/c5-text-cow` | b042a3464e | 검사할 텍스트를 빌림 |
| `items/c6-session-keys` | c8a496d49c | 세션 키 할당 줄이기 |
| `items/c7-checkpoint-take` | 6494aa38c8 | checkpoint 꺼내기 |
| `items/c8-scan-allocs` | 64608d3347 | 스캔 할당 줄이기 |
| `items/c9-ac-dense` | 6d5e7eab2a | Aho-Corasick dense 설정 |
| `items/c10-guard-key` | 3e329315c9 | prompt guard 캐시 키 |
| `items/zz-all-safe` | a3c97523ca | 후보 11개 합본(checkpoint 꺼내기 포함) |
| `exp/multilingual-memory-opt-experiments-20261029` | bd981833a5 | 이전 회차 커밋 6개(측정 도구 1개 + 실험 5개) |

## 부록 B. 결과 파일과 재현

- **bench 항목 측정** (Mac 사본: `~/Works/VM/probe/results-2026-10-30/items/`)
  - 요약: `summary-t200.txt`, `summary-t1000.txt`, `summary-x200.txt`(lld), `summary-x1000.txt`(lld)
  - 실행별 원본: `runs/<t200|t1000|x200|x1000>-<구성>-<회차>.txt`
  - 바이너리 섹션 크기: `size-<구성>.txt`, 해시: `sha-<구성>.txt`
  - 100턴마다 측정: `every/`
  - 스크립트: `items_build.sh`(빌드), `items_run.sh`(실행), `items_lld.sh`(lld 변형), `items_summary.py`(요약)
- **argot 측정** (`~/Works/VM/probe/converge/`)
  - 측정 스크립트: `converge_probe.py`, 실행 순서: `run.sh`
  - 결과: `results/<on-1|off-1>.idle.jsonl`(100턴마다 idle 값), `results/<…>.turns.jsonl`(턴마다 값)
- **VM:** `~/Works/VM`, 접속은 `ssh -F ~/Works/VM/ssh_config memvm`입니다.
