# 260910 ARGO 리뷰 대응 계획

## 배경 (Context)

`dev/byungchul.so/guardrails-refactor` 브랜치는 guardrails 설정과 masking 설정을 per-run 방식에서 프로세스 전역 방식으로 옮기고, 스캔 결과를 SHA-256 기반으로 재사용하는 캐시를 도입했습니다. 리뷰어는 `~/Works/shared/reviews/260910_ARGO_review.md` 에서 여덟 가지를 지적했습니다.

여덟 항목은 성격이 둘로 나뉩니다. 3·4·6·8번은 "이렇게 고치자"는 지시이므로 코드를 수정합니다. 1·2·5·7번은 "이대로 괜찮은가"라는 질문이므로, 먼저 근거를 갖춘 답을 제시하고 그 답이 요구할 때에만 코드를 고칩니다. 최종 목표는 리팩터링이 남긴 잔재를 정리하고, 로그가 실제 이상 상황만 알리도록 만드는 것입니다.

### 사전 작업 상태

- ARGO 워크트리는 이미 `dev/byungchul.so/guardrails-refactor` 에 있고, 원격과 0 커밋 차이이며, 변경된 파일이나 stash 가 없는 깨끗한 상태임을 확인했습니다. 따라서 별도의 체크아웃이나 정리 작업이 필요하지 않았습니다.
- `~/Works/shared` 는 `git fetch` 를 마쳤으나, 플랜 모드에서는 워킹 트리를 변경할 수 없으므로 `git pull` 은 하지 않았습니다. 리뷰 문서는 `git show origin/main:reviews/260910_ARGO_review.md` 로 읽었기 때문에, 현재 로컬 워킹 트리에는 아직 그 파일이 없습니다. 승인 이후에 fast-forward 로 반영하겠습니다.

---

## 관통하는 원칙: warn 을 언제 쓸 것인가

4번과 7번은 표면적으로 반대 방향을 가리킵니다. 4번은 warn 을 없애라고 하고, 7번은 warn 을 추가하라고 합니다. 두 지적을 하나의 기준으로 통합합니다. (결론적으로 7번은 warn 을 추가하는 대신 기존 warn 하나를 fail-closed 오류로 승격시키는데, 그 이유는 해당 항목에서 설명합니다.)

**warn 은 "당신의 설정이 잘못되었을 가능성이 높다"를 알릴 때만 사용합니다. "이 시스템은 이렇게 동작한다"를 설명하는 문장은 warn 이 아닙니다.**

이 기준을 적용하면 guardrails 계열의 `warn!` 은 세 부류로 나뉩니다.

| 부류 | 성격 | 처리 |
|---|---|---|
| (A) 설명·안내 | 조건이 사실상 정상 동작인데도 뜨는 문장 | 삭제하거나 `debug!` 로 강등 |
| (B) 정책 집행 감사(audit) | 차단이 실제로 일어났다는 기록 | 유지 |
| (C) 오설정·실패 | 환경 변수 파싱 실패, `Arc` 공유로 팩 미부착 등 | 유지 |

아래 4번 항목은 (A) 를 정리하는 작업입니다. 7번 항목은 (C) 중에서도 **설정한 정책을 아예 강제할 수 없는 상황**이라, warn 으로 알리고 넘어가는 대신 부팅을 중단시킵니다.

---

## 1번 — `LARGE_BATCH_WARN_BYTES` 는 여전히 필요한가

**답: 필요하지 않습니다. 상수와 두 검사 지점을 모두 삭제합니다.**

근거는 경고가 발생하는 시점과 캐시를 조회하는 시점의 선후 관계입니다.

- 메인 턴 경로인 `tinicore/src/agent/pii_masking.rs:1315` 의 경고는 `masking_scan_cache::checkpoint_for` 조회(`:1334`)보다 약 15줄 **앞**에서, 캐시 적중 여부와 무관하게 배치 전체 바이트를 기준으로 발화합니다. prefix 체크포인트가 적중하면 실제 DFA 스캔은 새로 붙은 tail 메시지에만 일어나는데, 경고는 누적 히스토리 전체를 스캔할 것처럼 보고합니다.
- 대화가 길어지면 `batch_bytes` 는 턴마다 단조 증가하므로, 한 번 64 KiB 를 넘긴 뒤에는 **매 턴 경고가 찍히지만 실제 비용은 캐시 덕분에 거의 늘지 않습니다.** 즉 이 경고는 "실제로 지불한 비용"이 아니라 "캐시가 없었다면 지불했을 비용"을 보고하고 있습니다.
- 이 상수를 검증하는 테스트는 저장소에 하나도 없습니다.

경고를 캐시 조회 뒤로 옮기고 실제 스캔 대상 바이트만 합산하는 대안도 있으나, 그렇게 만든 값은 형제 상수 `LARGE_SCAN_WARN_BYTES` 가 메시지 단위로 이미 보고하는 내용과 크게 겹칩니다. 관측 전용 코드를 정교하게 유지하는 비용이 이득보다 크다고 판단하여 삭제를 권합니다.

**수정 대상**

- `tinicore/src/agent/pii_masking.rs` — 상수 정의(`:1196`)와 doc 주석(`:1185~1195`), 메인 턴 검사(`:1307~1325`), background 검사(`:2062~2087`) 를 삭제합니다.
- 같은 파일의 내부 헬퍼 `content_text_len`(`:2043`) 은 이 배치 검사가 **유일한 호출자**임을 확인했습니다. 함께 삭제하면, 이 헬퍼가 실제 마스킹 `match` 문의 형태를 손으로 복제해 두어 `LlmContent` 변종 추가 시 두 곳을 함께 고쳐야 했던 구조적 드리프트 위험도 같이 사라집니다.
- `tinicore/src/guardrails/AGENTS.md:116` 과 `tinicore/examples/guardrails/scanning_benchmark.rs:178` 이 이 상수를 언급하므로 문서와 주석도 함께 정리합니다.
- 형제 상수 `LARGE_SCAN_WARN_BYTES` 쪽에서 이 상수를 역참조하는 doc 링크는 없음을 확인했으므로(`filter.rs` 에 매치 0건), 이 항목 때문에 `cargo doc` 이 깨지지는 않습니다.

---

## 2번 — chain bucket 이 3인데 충분한가

**답: 충분합니다. 코드 변경을 하지 않습니다.**

여기서 말하는 3은 `tinicore/src/agent/guardrail_scan_cache.rs:185` 와 `tinicore/src/agent/masking_scan_cache.rs:84` 의 `MAX_CHAINS` 이며, 검출기 체인 아이덴티티별로 캐시를 나누는 개수입니다.

근거는 세 가지입니다.

1. **정확도에는 영향이 없습니다.** 축출된 체인의 다음 조회는 콜드 미스가 되고, 콜드 미스는 전체 재스캔으로 폴백하여 캐시가 없을 때와 **완전히 동일한 출력**을 냅니다. 코드 주석이 "a pure cache-hit-rate cost, never a correctness one"이라고 명시합니다.
2. **정상 상태에서는 버킷 1개만 씁니다.** `install_guardrails_from_env` 는 체인을 하나만 설치하고, `resolve()` 는 이미 해소된 체인을 `Arc::clone` 할 뿐 호출마다 새로 만들지 않습니다. 따라서 단일 정책 호스트는 프로세스 전체에서 체인 아이덴티티를 정확히 하나만 유지합니다. 3은 서브에이전트나 테스트가 자기 체인을 설치하는 경우를 위한 여유입니다.
3. **한 턴 안에서 스래싱이 일어날 수 없습니다.** 한 턴은 체인 하나만 사용하므로, `MAX_CHAINS` 는 서로 다른 체인 사이에서만 작동합니다. 과거에 폐기된 "메시지별 LRU" 설계가 영구 0% 적중률을 만들었던 문제와는 구조가 다릅니다.

늘리지 않는 이유도 있습니다. `masking_scan_cache` 의 워스트케이스 메모리 산식이 `8 세션 × 3 체인 ≈ 5.4 MB` 이므로, 3을 키우면 상한이 선형으로 증가합니다. 얻는 것은 발생하지 않는 축출을 더 막는 일뿐입니다.

**범위 밖 후속 과제:** 축출 횟수를 세는 카운터를 넣으면 이 판단을 실측으로 확인할 수 있으나, 이번 대응에는 포함하지 않습니다.

---

## 3번 — background LLM 경로의 캐시 삭제

**지시대로 삭제합니다.**

먼저 사실 관계를 정리합니다. background 경로는 전역 캐시인 `masking_scan_cache` 와 `guardrail_scan_cache` 를 **애초에 사용하지 않습니다.** `EgressMask::begin()` 이 세션 인자를 받지 않고, 5-인자 래퍼 `mask_messages_for_cloud` 가 세션에 `None` 을 하드코딩하기 때문에 구조적으로 도달할 수 없습니다.

따라서 삭제 대상은 요청 단위 메모인 `EgressMask::scanned` 입니다. 이것은 한 요청 안에서 같은 텍스트가 여러 `LlmContent` 변종에 반복될 때만 이득을 주는데, 서로 다른 메시지가 대부분인 일반적인 배치에서는 적중이 드뭅니다.

**수정 대상: `tinicore/src/agent/pii_masking.rs`**

- 필드 `scanned`(`:1825`) 와 그 doc 주석, 상한 상수 `MAX_LOCAL_SCAN_ENTRIES`(`:1830`) 를 삭제합니다.
- `mask_text`(`:1938~1955`) 에서 `fingerprint` 조회와 삽입을 제거하고, 항상 `self.chain().detect_all(original).await` 를 수행하도록 단순화합니다. `hit` / `fresh` / `memoizable` 지역 변수가 함께 사라집니다.
- `EgressMask::begin()` 의 생성자에서 `scanned` 초기화를 제거합니다.

**주의: 이 변경은 순수한 성능 변경이 아닙니다.** 지금은 메모에 적중하면 `complete` 가 구조적으로 항상 `true` 이지만, 삭제하면 매번 `outcome.is_complete()` 를 새로 평가합니다. 따라서 한 요청 안에 동일한 텍스트가 두 번 있고 두 번째 스캔이 불완전하게 끝나는 상황에서는, `RedactionPolicy::FailClosed` 아래에서 `GATE_ERROR_PLACEHOLDER` 로 치환될 수 있습니다. 발생 가능성은 낮지만 동작 차이가 존재한다는 점을 리뷰어에게 함께 보고합니다.

**미리 밝혀 둘 부수 효과:** 이 삭제로 background 경로에서 `is_memoizable()` 을 확인하던 유일한 지점이 함께 사라집니다. 캐시가 없으면 걸러낼 대상도 없으므로 올바른 결과이지만, 리뷰어가 되물을 만한 지점이라 회신에 미리 적어 둡니다.

**함께 지우지 말아야 할 것:** 같은 구조체의 `_turn_scope` 필드는 요청 동안 검출기 엔진을 유지해 `mask_text` 마다 엔진을 다시 만들지 않게 하는 장치이며, 스캔 메모와 무관하므로 그대로 둡니다.

---

## 4번 — 조건 없이 뜨는 warn 정리

리뷰어가 지목한 문장은 `tinicore/src/agent/guardrails.rs:585` 의 `warn_input_history_gap_once` 입니다. 사실 이 함수는 `OnceLock` 래치로 **프로세스당 정확히 1회만** 출력되도록 이미 제한되어 있습니다. 다만 내용 자체가 "INPUT guardrail 은 이런 한계를 가진다"는 설계 설명이고 이상 상황이 아니므로, 위 원칙의 (A) 부류에 해당하여 삭제하는 편이 맞습니다.

**수정 대상 (부류 A 전체)**

| 위치 | 조치 | 이유 |
|---|---|---|
| `tinicore/src/agent/guardrails.rs:585` `warn_input_history_gap_once` | **삭제** | 순수한 설계 설명 |
| `tinicore/src/agent/loop_.rs:2002` | 호출 삭제 | 위 함수의 호출 지점 |
| `tinicore/src/agent/guardrails.rs:328` | 호출 삭제 | 위 함수의 호출 지점 |
| `tinicore/src/guardrails/filter.rs:209` | `debug!` 로 강등 | 실제 비용 신호를 담고 있어 진단에는 유용함 |
| `tinicore/src/agent/guardrails_builtin.rs:68` | `debug!` 로 강등 | 위와 같음 |
| `tinicore/src/agent/pii_masking.rs:1316`, `:2077` | 삭제 | 1번 항목에서 이미 삭제 대상 |

**리뷰어 제안에서 벗어난 부분:** 리뷰어는 "info 로 변경 또는 삭제"를 제시했으나, 위 두 건은 `info` 가 아니라 `debug` 로 낮추기를 권합니다. 두 메시지는 스캔이 일어날 때마다 발화하므로 `info` 로 두어도 여전히 잡음이 되지만, 실제로 지불한 스캔 비용을 담고 있어 완전히 지우기에는 아깝기 때문입니다. 이 선택을 회신에 명시합니다.

**보존해야 할 내용:** `guardrails.rs:545~585` 의 doc 주석에는 "래치를 `resolve` 가 아니라 실행 지점에 둔 이유"와 "전역 set 이 재적재 가능해지면 래치도 함께 초기화해야 한다"는 제약이 기록되어 있습니다. 함수를 지우더라도 뒤쪽 제약은 사라지면 안 되므로, 모듈 수준 doc 주석으로 옮깁니다.

**확인 완료:** 이 래치를 검증하는 테스트는 저장소에 없습니다. `warn_input_history_gap_once` 의 참조는 정의 한 건과 호출 두 건, 주석 한 건이 전부이므로, 삭제해도 깨지는 테스트가 없습니다.

**유지하는 항목:** 부류 (B) 인 `hook.rs:206`, `sensitive/guardrail.rs:153`, `pii_masking.rs:487` 과, 부류 (C) 인 `guardrails.rs` 의 `Arc` 공유·환경 변수 파싱 실패 계열, `recognizer.rs` 의 DFA 실패 계열, `tinicli/src/guardrails/pii.rs` 의 라벨 검증 계열은 그대로 둡니다.

---

## 5번 — argo-cli / tinicli 의 `AgentLoopConfig` 검토

**답: CLI 생성 지점도 a2a 경로도 이미 정리되어 있으므로 손댈 것이 없습니다. 리팩터링이 남긴 죽은 함수 하나만 삭제합니다.**

`argo-cli` 는 `tinicli::run_cli()` 를 호출하는 얇은 래퍼이며 `AgentLoopConfig` 를 직접 만들지 않습니다. `tinicli` 의 생성 지점 다섯 곳은 모두 `guardrails: None` 이고, `sensitive` 와 `reveal_override` 를 설정하는 곳은 한 군데도 없습니다.

| 위치 | 용도 | 상태 |
|---|---|---|
| `tinicli/src/repl.rs:296` | REPL 프로포저 템플릿 | `guardrails: None` |
| `tinicli/src/repl.rs:670` | REPL 본 턴 | `guardrails: None` |
| `tinicli/src/run_tui.rs:592` | TUI 본 턴 | 사후 대입으로 `None` |
| `tinicli/src/daemon.rs:1102` | cron `Llm` 액션 | `guardrails: None` |
| `tinicli/src/daemon.rs:1387` | cron `SpawnAgent` | `guardrails: None` |

전역은 `tinicli/src/cli_entry.rs` 의 부팅 경로에서 모든 턴 이전에 초기화됩니다. `:158` 이 `install_guardrails_from_env("ARGO")` 를, `:394` 가 `install_pii(...)` 를 호출하며, 둘 중 하나라도 실패하면 `:399` 가 프로세스를 종료합니다.

### a2a 경로 확인 결과

지시하신 대로 a2a 쪽도 함께 훑었습니다. 저장소 전체에서 `guardrails` / `sensitive` / `reveal_override` 를 per-run 으로 채우는 **프로덕션** 코드는 단 한 곳뿐이며, 그곳은 고쳐서는 안 되는 자리입니다.

| 위치 | 내용 | 판단 |
|---|---|---|
| `tinicore/src/protocols/a2a/served.rs:500` | `config.reveal_override = Some(RevealTo::NoOne)` | **유지해야 합니다** |
| `tiniffi/src/a2a_ingest.rs:179` | `..Default::default()` 로 세 필드 모두 `None` | 정상 |
| `argo-server/src/host_runtime/runner.rs:2025` | 동일 | 정상 |
| `argo-a2a` / `argo-a2a-delegation` | 프로덕션 생성 지점 없음(테스트만 존재) | 해당 없음 |

즉 **`guardrails` 와 `sensitive` 두 필드를 프로덕션에서 채우는 코드는 저장소 전체에 하나도 없습니다.** `guardrails = Some(...)` 이나 `sensitive = Some(...)` 이 나오는 자리는 전부 `#[cfg(test)]` 모듈이거나 `tinicore/tests/` 아래의 통합 테스트입니다. 하위 에이전트 설정을 만드는 `kind_executor.rs:268` 의 `build_kind_config` 도 `base.clone()` 으로 부모 값을 그대로 물려받을 뿐 두 필드를 직접 건드리지 않으므로, 부모가 `None` 이면 자식도 `None` 입니다.

`served.rs:500` 은 원격 피어에게 보내는 응답에서 루프의 마지막 demask 단계가 실제 PII 를 복원해 회선에 실어 보내는 일을 막는 장치입니다. 주석이 밝히듯 `config.sensitive.as_mut()` 로 쓰지 않고 최상위 필드인 `reveal_override` 를 쓰는 이유도, 호스트가 마스킹을 전역으로 설치한 경우 per-run 슬롯이 `None` 이라 쓰기가 그냥 흘러가 버리기 때문입니다. 즉 이 자리는 전역 전환이 덜 된 잔재가 아니라, **전역 전환을 전제로 일부러 설계된 예외**입니다.

### `guardrails: Some(...)` 의 대체 시맨틱

말씀하신 대로 이것은 올바른 동작입니다. `pick_layer`(`guardrails.rs:341`) 가 per-run 레이어로 전역 레이어를 합치지 않고 대체하는 것은 per-run 설정의 정의 그 자체이므로, 이 부분은 손대지 않습니다.

### 유일한 조치: `inherit_global_sensitive` 삭제

`tinicore/src/agent/pii_masking.rs:989` 의 이 함수는 전역 정책을 `config.sensitive` 에 복사해 넣는 구식 방식이며, 커밋 `cc95a4bb57` 이 `resolve_sensitive` 로 대체했습니다. 호출자가 하나도 없고 이미 `#[deprecated]` 가 붙어 있습니다. (앞선 조사에서 표시가 없다고 보고했으나 실제로는 붙어 있음을 직접 확인해 바로잡습니다.)

doc 주석은 "`config.sensitive` 가 제자리에서 채워지기를 기대하는 out-of-tree 호출자를 위해 남겨 둔다"고 적고 있으나, `tinicore` 는 레지스트리 버전으로 참조되지 않고 워크스페이스 안에서 path 의존성으로만 쓰이므로 out-of-tree 호출자가 존재할 수 없습니다. 따라서 지시하신 대로 삭제합니다.

**수정 대상: `tinicore/src/agent/pii_masking.rs`**

- `inherit_global_sensitive`(`:989`) 와 그 doc 주석, `#[deprecated]` 속성을 삭제합니다.
- `resolve_sensitive` 의 doc 주석이 이 함수를 참조한다면 함께 정리합니다.

형제 별칭인 `install_masking_policy`(`:541`), `global_masking_policy`(`:547`), `inherit_global_masking`(`:554`), `force_reveal_to`(`:971` 부근) 는 이번 리뷰의 지적 대상이 아니므로 그대로 둡니다.

---

## 6번 — `run_input_guardrails_with_text` 에 `None` 을 넘기기

**지시대로 수정합니다.**

리뷰어의 진단이 정확합니다. 두 프로덕션 호출 지점이 `global_guardrails()` 를 꺼내어 `per_run` 슬롯에 되먹이고 있는데, 함수는 내부(`guardrails.rs:320`)에서 똑같은 `global_guardrails()` 를 다시 조회합니다. 결과적으로 `resolve_against(Some(global), Some(global))` 이 되어 동작상 차이가 전혀 없는 사문(死文) 코드입니다. 함수의 doc 주석도 "per-run 체인이 아직 없으면 `None` 을 넘겨라, 이것이 일반적인 경우다"라고 이미 명시하고 있습니다.

**수정 대상**

- `tinicli/src/repl.rs:483~490` — `pii_global` 지역 변수와 이를 만드는 `#[cfg(feature = "guardrails")]` / `#[cfg(not(...))]` 분기 네 줄을 삭제하고, 인자를 `None` 으로 바꿉니다.
- `tinicli/src/run_tui.rs:461~469` — 위와 동일하게 처리합니다.

두 지점의 주석이 이미 "PII input guardrail 은 부팅 시 전역 슬롯에 설치된다"고 적어 놓고 바로 그 전역을 되먹이는 모순 상태이므로, 주석도 함께 정리합니다.

**부수 효과:** 이 변경으로 `cfg` 분기가 사라지면 `guardrails` feature 를 껐을 때와 켰을 때의 코드 경로가 하나로 합쳐집니다. 두 feature 조합 모두에서 빌드가 되는지 확인해야 합니다.

**함수 시그니처는 유지합니다.** `per_run` 파라미터 자체를 없애는 것은 리뷰어가 요구한 범위를 넘고, 진짜 per-run set 을 가진 외부 호스트가 나중에 생길 여지를 없애기 때문입니다.

---

## 7번 — `build_layer_detector` 의 fallback 경고

**답: 레이어 키 누락에 대한 fallback 은 유지합니다. 대신 `config.toml` 에 적은 label 을 실제로 쓸 수 없는 경우에만 `Err` 로 부팅을 중단합니다.**

### 왜 레이어 키 누락은 fallback 이 맞는가

`pii_filter_labels` 는 레이어별로 분리된 표이고, 각 호출은 자기 레이어 키만 조회합니다.

```rust
build_layer_detector("guardrails:input",   "input",   Some(&map))  // map.get("input")   만 봄
build_layer_detector("guardrails:output",  "output",  Some(&map))  // map.get("output")  만 봄
build_layer_detector("guardrails:default", "default", Some(&map))  // map.get("default") 만 봄
```

따라서 `input = ["card"]` 만 적으면 그 값은 `input` 레이어에만 적용되고, `output` 과 `default` 는 각자 `shared_layer_filter` 로 자기 레이어의 내장 필터를 씁니다. `input` 값을 물려받지 않습니다.

레이어 키를 적지 않은 것은 "이 레이어는 내장 기본값 그대로 두겠다"는 의미이며, `config.rs:120` 의 필드 주석("When a layer key is present ... instead of the YAML layer's default recognizer set")과 `override_no_layer_key_returns_none` 테스트가 이를 사양으로 규정하고 있습니다. 여기서 부팅을 막으면 `pii_filter_labels` 가 전부 아니면 전무인 표가 되어, 한 레이어만 조정하고 싶은 사용자가 나머지 둘까지 손으로 적어야 합니다.

### 무엇을 `Err` 로 바꾸는가

**`config.toml` 에 적은 label 을 이 빌드가 해석할 수 없는 경우**입니다. 지금은 `pii.rs:167` 이 경고 한 줄을 남기고 그 label 을 조용히 건너뜁니다.

```toml
[pii_filter_labels]
input = ["crad"]   # "card" 의 오타
```

이 설정으로 지금은 정상 부팅하며, `input` 레이어의 kinds 는 `[Credential]` 만 남습니다. 사용자는 카드번호가 차단되고 있다고 믿지만 실제로는 전혀 검사되지 않습니다. 적어 놓은 정책을 강제할 수 없는 상태이므로, 같은 파일이 이미 채택한 원칙("`Err` means the configured mode cannot be enforced, never 'off'")에 따라 부팅을 중단해야 합니다.

### 네 경로의 처리 방침

| 상황 | 현재 동작 | 변경 후 |
|---|---|---|
| 레이어 키 없음 | 내장 필터로 fallback | **그대로 유지** |
| 알 수 없는 label 문자열 (`"crad"`) | warn 후 건너뜀 | **`Err`** |
| recognizer 없는 유효 label (`Email`, `Address`) | warn 후 포함 | **그대로 유지** |
| `pii_filter_labels` 자체가 없음 | 내장 필터가 곧 정책 | **그대로 유지** |

### `config.toml` 형태별 동작 정리

"키가 없다"와 "키가 있고 비어 있다"는 겉보기에 비슷하지만 결과가 정반대일 수 있으므로, 표로 구분해 둡니다.

| `config.toml` | Rust 값 | `output` 레이어의 동작 |
|---|---|---|
| `[pii_filter_labels]` 섹션 자체가 없음 | `None` | 내장 필터 (fallback) |
| `[pii_filter_labels]` 만 쓰고 항목이 없음 | `Some({})` | 내장 필터 (fallback) |
| `input = ["card"]` 만 씀 | `Some({"input": [...]})` | 내장 필터 (fallback) |
| `output = []` | `Some({"output": []})` | **`Credential` 하나만 탐지** |

`output = []` 는 fallback 이 아닙니다. 키가 존재하므로 override 가 적용되고, 붙일 label 이 없어 `[Credential]` 만 남습니다. "이 레이어는 자격증명만 보고 나머지 PII 는 보지 마라"는 의도적인 축소 설정이며, `pii.rs:548` 의 `override_empty_list_has_only_credential` 이 이 동작을 검증합니다. 내장 필터는 보통 여러 종류의 PII 를 잡으므로, 두 경우의 탐지 범위는 정반대에 가깝습니다.

`Email` 과 `Address` 를 경고로 남기는 이유는 성격이 다르기 때문입니다. label 자체는 시스템이 이해하는 유효한 값이고, 단지 매칭할 패턴이 YAML 에 없을 뿐입니다. 사용자가 잘못 적은 것이 아니므로 부팅을 막을 근거가 약합니다.

### 수정 대상: `tinicli/src/guardrails/pii.rs:141`

`override_kinds_for_layer` 의 반환 타입을 `Option<Vec<SensitiveKind>>` 에서 `Result<Option<Vec<SensitiveKind>>, PiiError>` 로 바꿉니다. `Ok(None)` 은 "레이어 키 없음"으로 남아 fallback 을 그대로 유지하고, `Err` 는 "적은 label 을 해석할 수 없음"을 뜻합니다.

```rust
fn override_kinds_for_layer(
    layer: &str,
    filter_labels: &HashMap<String, Vec<String>>,
) -> Result<Option<Vec<SensitiveKind>>, PiiError> {
    // `Ok(None)`, not an error: omitting a layer key is the documented way to
    // leave that layer on its built-in filter (see `CliConfig::pii_filter_labels`).
    let Some(labels) = filter_labels.get(layer) else {
        return Ok(None);
    };
    let mut kinds = vec![SensitiveKind::Credential];
    for label_str in labels {
        // A label string this build cannot map is a policy the operator wrote
        // down and this process cannot enforce. Skipping it silently leaves a
        // turn unprotected while `config.toml` promises otherwise, so it fails
        // the build instead — same rule `build_pii_for_turn`'s doc states for
        // a mode that cannot be enforced.
        let Some(label) = PiiLabel::ALL.iter().find(|l| l.as_str() == label_str) else {
            return Err(PiiError::Config(format!(
                "unrecognized PII label {label_str:?} in pii_filter_labels.{layer}"
            )));
        };
        // Deliberate carve-out from the rule above: the label IS understood,
        // there is simply no recognizer for it in the YAML. Nothing was
        // mistyped, so this stays a warning.
        //
        // `log::warn!` + `eprintln!` as a pair: `install_pii` runs before
        // `log::set_logger`, so on the interactive path only the `eprintln!`
        // is actually visible.
        if matches!(label, PiiLabel::Email | PiiLabel::Address) {
            log::warn!(
                "[pii] PII label {label_str:?} in pii_filter_labels.{layer} has no recognizer — \
                 it will not detect anything"
            );
            eprintln!(
                "[pii] PII label {label_str:?} in pii_filter_labels.{layer} has no recognizer — \
                 it will not detect anything"
            );
        }
        kinds.push(SensitiveKind::Pii(*label));
    }
    Ok(Some(kinds))
}
```

`build_layer_detector` 는 구조를 그대로 두고 `?` 하나만 붙습니다.

```rust
fn build_layer_detector(
    name: &str,
    layer: &str,
    filter_labels: Option<&HashMap<String, Vec<String>>>,
) -> Result<PiiSpanDetector, PiiError> {
    if let Some(labels) = filter_labels {
        if let Some(kinds) = override_kinds_for_layer(layer, labels)? {
            return PiiSpanDetector::for_kinds(name, &kinds);
        }
    }
    let filter = shared_layer_filter(layer)?;
    PiiSpanDetector::try_from_filter(name, filter)
}
```

`PiiError::Config(String)` 는 `tinicore/src/guardrails/error.rs:14` 의 공개 변종이며, `tinicli` 가 이미 `PiiError` 를 import 하고 있으므로 그대로 쓸 수 있습니다.

### 오류 메시지 출력은 기존 경로가 이미 처리합니다

오류 경로에 별도의 `eprintln!` 을 넣지 않기를 권합니다. 넣으면 같은 내용이 두 번 나옵니다.

1. `build_pii_for_turn:246` 이 `map_err(|e| layer_build_failure("input", &e))` 로 감쌉니다.
2. `layer_build_failure`(`:288`) 가 `log::error!` 를 남기고 해결 방법까지 담은 문자열을 만듭니다.
3. `cli_entry.rs:399` 가 `eprintln!("[pii] refusing to start: {e}")` 를 출력하고 `exit(1)` 합니다.

최종 출력은 이렇게 됩니다.

```
[pii] refusing to start: PII filter build failed for the 'input' layer: config error: unrecognized PII label "crad" in pii_filter_labels.input
`pii_mode` is set, so this configuration cannot be enforced and the process will not start. Fix the PII configuration, or set `pii_mode = "off"` in config.toml to run without PII protection.
```

### 함께 고쳐야 할 테스트

반환 타입이 바뀌므로 `override_kinds_for_layer` 를 직접 호출하는 네 건이 영향을 받습니다. 그중 한 건은 의미가 뒤집힙니다.

| 위치 | 현재 내용 | 조치 |
|---|---|---|
| `pii.rs:527` `override_card_has_credential_and_card_not_phone` | `.expect("layer key exists")` | `Result` 에 맞게 언랩 단계를 하나 추가 |
| `pii.rs:548` `override_empty_list_has_only_credential` | 동일 | 동일 |
| `pii.rs:558` `override_invalid_label_skipped` | `"foo"` 가 건너뛰어지고 길이가 2라고 단언 | **의미가 뒤집힘** — `Err` 를 기대하도록 다시 쓰고 이름도 `override_invalid_label_is_rejected` 로 바꿉니다 |
| `pii.rs:571` `override_no_layer_key_returns_none` | `is_none()` 단언 | `Ok(None)` 을 기대하도록 언랩 단계만 조정하며, **의미는 그대로 유효합니다** |

`build_pii_for_turn` 을 호출하는 테스트들은 부분 표가 여전히 성공하므로 **수정할 필요가 없습니다.**

**새로 추가할 회귀 테스트 한 건**

```rust
/// A label string this build cannot map is a stated policy that would not be
/// enforced — it must fail the build rather than being skipped.
#[test]
fn unrecognized_label_fails_the_build() {
    let mut map = HashMap::new();
    map.insert("input".to_string(), vec!["crad".to_string()]);
    let err = build_pii_for_turn(PiiMode::Full, None, Some(&map))
        .expect_err("an unrecognized label must not build");
    assert!(err.contains("crad"), "the message must name the bad label: {err}");
}
```

### 함께 고쳐야 할 문서

- `override_kinds_for_layer`(`:130~140`) 의 doc 주석 — "Unrecognized strings are skipped with a `log::warn!` + `eprintln!`" 이 더 이상 사실이 아니므로 다시 씁니다. `Email` / `Address` 경고는 유지된다는 점은 그대로 둡니다.
- `tinicli/src/config.rs:119~125` 의 `pii_filter_labels` 필드 주석 — "Unrecognized label strings are skipped with a warning" 을 "부팅이 중단된다"로 고칩니다. 레이어 키를 생략하면 내장 필터를 쓴다는 기존 설명은 그대로 유지합니다.

### 동작 변경의 영향

label 에 오타가 있던 설정은 이 변경 이후 부팅에 실패합니다. 그런 설정은 원래 해당 label 에 대한 보호가 적용되지 않고 있었으므로, 조용히 넘어가는 것보다 실패로 드러나는 편이 낫습니다. 레이어 키를 일부만 적는 기존 사용 방식은 영향을 받지 않습니다.

### 참고: 세 레이어가 각각 무엇인지

| 레이어 | 만들어지는 것 | 하는 일 |
|---|---|---|
| `input` | `SensitiveGuardrail("pii.input")` | 사용자 입력에서 PII 를 찾으면 LLM 호출 자체를 차단합니다 |
| `default` | `SensitiveMasking::with_chain(default_chain)`, `outbound_roles(ALL)` | 클라우드로 나가는 메시지를 마스킹합니다 |
| `output` | `mask_llm_output(ASSISTANT_ONLY, output_chain)` | LLM 이 돌려준 답변을 마스킹합니다 |

**호출 빈도 확인:** 함수 이름이 `build_pii_for_turn` 이라 매 턴 호출되는 것처럼 보이지만, 실제 체인은 `cli_entry.rs:394` → `install_pii` → `build_pii_for_turn` 이며 **부팅 시 1회**입니다.

---

## 8번 — `from_filter` 삭제

**지시대로 삭제합니다. 이행할 호출자가 없어 작업이 단순합니다.**

저장소 전체(`target` 과 `.git` 제외, 모든 크레이트와 테스트 포함)를 검색한 결과 `from_filter` 의 매치는 정의 자체와 doc 링크 두 건뿐이며, **프로덕션에도 테스트에도 호출자가 0개**입니다. `try_from_filter` 로의 이행은 직전 커밋에서 이미 끝났습니다.

**수정 대상: `tinicore/src/guardrails/detector.rs`**

- `from_filter`(`:467~521`) 와 그 `#[deprecated]` 속성을 삭제합니다.
- `every_pii_kind`(`:139`) 를 함께 삭제합니다. 호출자가 `from_filter` 의 오류 분기(`:508`) 하나뿐임을 확인했습니다.
- `:137` 의 intra-doc 링크가 깨지므로 함께 정리합니다. 그 doc 주석이 설명하는 "빈 kinds 가 아니라 전체 kinds 를 주장해야 조용히 무방비인 턴을 막을 수 있다"는 방어 논리는 `try_from_filter` 가 오류를 전파하는 방식으로 이미 해결하므로 삭제해도 무방합니다.

**semver 우려는 없습니다.** `tinicore` 를 레지스트리 버전으로 참조하는 곳이 없고 워크스페이스 내부에서 path 의존성으로만 쓰이므로, `pub` API 삭제가 외부에 영향을 주지 않습니다.

---

## 9번 — `config.toml` 의 PII 설정 문서화 (리뷰 항목 외, 사용자 요청)

**현재 `~/.argo/config.toml` 의 PII 설정 세 개 중 하나만 문서화되어 있습니다.**

| 설정 | 문서 상태 |
|---|---|
| `pii_mode` | `tinicore/src/guardrails/AGENTS.md:101~107` 에 있음 |
| `pii_filter_labels` | **없음** — 모든 `.md` 에서 매치 0건 |
| `pii_demask_tool_args` | **없음** — `tinicore/CHANGELOG.md` 와 옛 plan 문서에만 언급 |

세 설정을 한자리에 모아 `AGENTS.md` 의 기존 `pii_mode` 블록(`:101`)을 확장합니다. 기존 `pii_mode` 내용은 그대로 살리고 소제목만 붙여 정리한 뒤, 나머지 두 설정을 이어서 씁니다.

환경 변수(`ARGO_GUARDRAIL_DENY_*`, `ARGO_GUARDRAIL_TOOL_PACK`, `ARGO_GUARDRAIL_EXFIL`)도 문서가 없으나, 지시하신 대로 이번 범위에서 제외합니다.

### 추가할 내용

````markdown
**Runtime configuration** — the three PII settings in `~/.argo/config.toml`.

#### `pii_mode` — enforcement level

```toml
pii_mode = "off"         # default — nothing installed
pii_mode = "block_only"  # input guardrail only
pii_mode = "full"        # input guardrail + outbound/output masking
```

#### `[pii_filter_labels]` — narrow what each layer detects

Optional. By default all three layers use the built-in recognizer set for
their layer; this table overrides that, per layer.

```toml
pii_mode = "full"

[pii_filter_labels]
input   = ["card", "national_id"]   # block only these in user input
output  = ["card"]                  # mask only these in the model's reply
default = ["card", "national_id"]   # mask only these on the way out
```

Valid label strings (`PiiLabel::as_str`): `phone`, `email`, `national_id`,
`address`, `card`, `passport`, `driver_license`, `bank_account`.

- **`Credential` is always detected**, on every layer, whatever you list
  here. There is no way to turn it off.
- **Omitting a layer key** leaves that layer on its built-in recognizer set.
  The table is per-layer, so `input = [...]` alone does not affect `output`
  or `default`.
- **An empty list** (`output = []`) is NOT the same as omitting the key: it
  narrows that layer to `Credential` only.
- **`email` and `address` are valid labels with no recognizer** in the
  embedded YAML. They are accepted and warned about, but detect nothing.
- **An unrecognized label string aborts the boot.** A policy this build
  cannot enforce is not silently downgraded — fix the typo, or drop the entry.

#### `[pii_demask_tool_args]` — restore real values for tool execution

Optional, and **only effective when `pii_mode = "full"`** — set under any
other mode, it is ignored with a boot warning. Names the arguments whose
real value a tool must receive even though masking is on.

```toml
pii_mode = "full"

[pii_demask_tool_args]
send_email  = ["to"]
gcal_create = ["attendee.email", "organizer"]
```

- **Keys are tool WIRE names**, matching `^[a-zA-Z0-9_-]{1,64}$`. A
  namespaced or aliased key can never match a real call; `install_pii`
  reports it at boot.
- **Values are dot-separated paths** into the call's JSON arguments. `.` is
  always a separator, so a flat key that itself contains a dot is
  unreachable — express the target as a nested path.
- **Only the executed copy is restored.** The stored transcript keeps
  placeholders, so nothing here puts PII at rest.
- ⚠ **A tool that also gates on human approval does not work here.** The
  per-turn vault does not survive the approval suspend/resume boundary
  (persisting it would put plaintext PII at rest), so the resumed call
  receives the literal `[SENS:PII:…]` placeholder and treats it as a real
  value. `install_pii` warns at boot on exactly this combination.
````

### 근거를 확인한 출처

| 문서에 쓰는 내용 | 확인한 코드 |
|---|---|
| 유효 label 여덟 개 | `tinicore-traits/src/sensitive.rs:97` `PiiLabel::as_str` |
| `Credential` 항상 포함 | `tinicli/src/guardrails/pii.rs:146` |
| 빈 목록은 `Credential` 만 | `pii.rs:548` `override_empty_list_has_only_credential` |
| wire name 규칙 | `pii_masking.rs:2649` `is_valid_wire_name` |
| 경로 구분자 제약 | `pii_masking.rs:2657~2665` |
| 승인 게이트 충돌 | `pii_masking.rs:753~767` |
| `full` 이 아니면 무시 | `pii.rs:232` |

### 함께 손봐야 할 이웃 문단

`AGENTS.md:109~119` 의 latency 문단이 `LARGE_BATCH_WARN_BYTES` 를 근거로 "64 KiB 를 넘으면 경고가 뜬다"고 설명합니다. 1번 항목이 그 상수를 삭제하므로 **마지막 문장을 고쳐야 합니다.** 스캔 비용 자체(~17.5 µs/byte)와 "size cap 이나 chunking 은 없다"는 설명은 여전히 유효하므로 남기고, 경고 관련 서술만 걷어냅니다.

---

## 작업 순서

의존 관계를 고려한 순서입니다.

1. **8번** — 독립적이고 삭제만 하므로 먼저 처리합니다.
2. **1번 + 3번** — 둘 다 `pii_masking.rs` 를 만지므로 함께 처리합니다. 1번이 background 배치 경고를 지우고, 3번이 그 아래 `mask_text` 를 단순화합니다.
3. **4번** — 1번에서 이미 지운 두 건을 제외한 나머지 warn 을 정리하고, doc 주석을 모듈 수준으로 옮깁니다.
4. **6번** — `repl.rs` 와 `run_tui.rs` 를 수정합니다.
5. **5번** — `inherit_global_sensitive` 삭제만 남았으므로 간단합니다.
6. **7번** — `override_kinds_for_layer` 의 반환 타입을 `Result<Option<..>, PiiError>` 로 바꾸어 오타 label 만 `Err` 로 만듭니다. 영향받는 테스트 네 건을 고치고, 회귀 테스트 한 건과 문서를 함께 갱신합니다.
7. **9번** — 1번과 7번이 모두 끝난 뒤 `AGENTS.md` 를 갱신합니다. 두 항목의 최종 동작이 확정되어야 문서가 정확해집니다.
8. **2번** — 코드 변경 없이 보고서에 답만 작성합니다.

---

## 검증

### 빌드

`target/` 디렉터리가 용량 확보를 위해 삭제된 상태이므로 **첫 빌드는 콜드 빌드이며 시간이 오래 걸립니다.** 이 점을 감안해 시간을 잡아야 합니다.

```
cargo build -p tinicore -p tinicli -p argo-cli
```

6번 항목이 `cfg` 분기를 제거하므로 feature 조합 양쪽을 확인합니다.

```
cargo check -p tinicli --features guardrails
cargo check -p tinicli --no-default-features
```

### 테스트

**반드시 디버그 모드로 실행합니다.** `--release` 로 lib 테스트를 돌리면 `debug_assert` 관련으로 13건이 실패하는데, 이는 정상 동작이며 이번 변경과 무관합니다.

```
cargo test -p tinicore --lib
cargo test -p tinicore --test guardrails
cargo test -p tinicore --test inbound_admission_e2e
cargo test -p tinicore --test inbound_admission_regression
cargo test -p tinicli --lib
```

`inbound_admission_*` 두 테스트는 6번 항목이 바꾸는 `run_input_guardrails_with_text` 를 직접 호출하므로 특히 중요합니다.

**단독으로는 통과하는데 전체 실행에서 실패하는 테스트가 나오면, 변경 자체보다 전역 상태 오염을 먼저 의심해야 합니다.** 이 경로들은 `install_guardrails`(Mutex 전역, 누적 방식)와 `install_sensitive_masking`(`OnceLock`, 최초 1회 승리)을 건드립니다.

### ratchet 테스트

6번이 `repl.rs` 와 `run_tui.rs` 를 수정하므로, `repl.rs:998` 과 `daemon.rs:2590` 의 소스 파싱 ratchet 이 여전히 통과하는지 확인합니다. 이 두 테스트는 해당 파일의 모든 `AgentLoopConfig` 리터럴이 `guardrails:` 를 설정하도록 강제합니다.

### 문서

8번이 intra-doc 링크를 건드리므로 문서 빌드를 확인합니다.

```
cargo doc -p tinicore --no-deps
```

### 로그 육안 확인

4번과 7번은 확인 방법이 서로 다르므로 나누어 실행합니다.

**4번 (선택 사항, API 키와 네트워크 필요):** 정상 설정 상태에서 한 턴을 돌려 `WARN` 레벨 출력이 남지 않는지 확인합니다.

```
RUST_LOG=warn cargo run -p argo-cli -- "안녕"
```

**7번 (LLM 호출 불필요):** `~/.argo/config.toml` 로 세 가지를 확인합니다.

1. `pii_filter_labels.input` 에 `"crad"` 같은 오타 label 을 넣고, 부팅이 **중단되고** 그 label 이름이 메시지에 나오는지 확인합니다.
2. `input` 만 적고 `output` / `default` 를 비워 둔 부분 표에서 **정상 부팅**하는지 확인합니다. 이 경로는 사양이므로 실패하면 안 됩니다.
3. `input = ["email"]` 처럼 recognizer 없는 유효 label 을 넣고, **경고만 나오고 부팅은 되는지** 확인합니다.

---

## 커밋

**아홉 항목을 커밋 하나에 모두 담습니다.** 위의 작업 순서는 구현 편의를 위한 진행 순서일 뿐이며, 중간 커밋을 만들지 않습니다.

저장소 관례(`feat(sensitive):`, `refactor(guardrails):` 같은 conventional commit)에 맞추어 다음 형태를 제안합니다.

```
refactor(guardrails): apply the 260910 review — drop dead code, quiet observational warns

- Delete LARGE_BATCH_WARN_BYTES and both batch-size checks: the scan cache
  made them report a cost that is no longer paid (review #1).
- Delete EgressMask::scanned, the request-local scan memo on the background
  egress path (review #3). Not purely a perf change — see the note below.
- Delete warn_input_history_gap_once and demote two per-scan cost warnings to
  debug!: neither reports a misconfiguration (review #4).
- Delete inherit_global_sensitive, a zero-caller deprecated helper the
  resolve_sensitive refactor replaced (review #5).
- Pass None for per_run at both run_input_guardrails_with_text call sites;
  they were feeding the global back into a slot the function re-reads
  (review #6).
- Reject an unrecognized pii_filter_labels label string instead of skipping
  it: a policy this build cannot enforce must not boot (review #7).
- Delete the deprecated PiiSpanDetector::from_filter and every_pii_kind,
  its only remaining user (review #8).
- Document pii_mode, pii_filter_labels and pii_demask_tool_args together in
  the guardrails AGENTS.md; only the first was documented before.

Behaviour notes for the reviewer:
- Removing the background scan memo re-evaluates completeness per scan, so a
  text repeated inside one request can now be scrubbed to
  GATE_ERROR_PLACEHOLDER under FailClosed where the memo made it complete by
  construction.
- A config.toml with a misspelled PII label no longer boots. Omitting a layer
  key is unchanged — that is the documented way to leave a layer on its
  built-in filter.
- MAX_CHAINS stays at 3 (review #2); the reasoning is in the review reply,
  not in code.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## 승인 이후의 후속 작업

- `~/Works/shared` 를 `origin/main` 으로 fast-forward 하여 리뷰 문서를 워킹 트리에 반영합니다.
- 관례에 따라 이 계획서를 `~/Works/shared/plans/` 에 날짜 접두사를 붙여 복사합니다. **커밋까지만 하고 push 는 하지 않습니다.**
- ARGO 작업도 마찬가지로 **커밋 하나까지만 진행합니다. push 와 PR 생성은 모두 별도 지시가 있을 때까지 하지 않습니다.**
- 리뷰어에게 회신할 때 다음 네 가지를 명시합니다. 2번은 코드를 바꾸지 않고 근거로 답한다는 점, 3번은 순수한 성능 변경이 아니라 미세한 동작 차이가 있다는 점, 4번의 두 건은 제안받은 `info` 가 아니라 `debug` 로 낮춘다는 점, **7번은 fallback 을 그대로 두는 대신, `config.toml` 에 적은 label 을 해석할 수 없는 경우만 부팅 중단으로 바꿨다는 점**입니다. 레이어 키를 일부만 적는 사용 방식은 사양이므로 영향이 없고, label 에 오타가 있던 설정만 실패하게 됩니다.
