# argo-tizen: `[safety.pii.filter_labels]` 레이어별 PII 라벨 override 이식 계획

## Context

ARGO PR #3392(`guardrails: PII 마스킹 계층 정비`)는 tinicli 에 `[pii_filter_labels]` 설정을
추가했다. 운영자가 레이어(`input` / `output` / `default`)마다 탐지할 PII 라벨을 좁힐 수 있고,
`credential` 은 항상 포함되며, 오타는 부팅을 거부한다. 같은 기능을 argo-tizen 의
`argot-daemon` 에도 넣기로 했다.

이 계획은 **tini sync 가 끝난 상태**를 전제로 한다. 즉 `tini/tinicore` 에는 이미
`PiiSpanDetector::try_from_filter` / `for_kinds` 가 있고 `from_filter` 는 없으며,
`install_guardrails` 는 `InstallStatus { fully_merged }` 를 돌려준다. sync 자체가 깨뜨리는
`crates/argot-daemon/src/guardrails/pii.rs` 의 컴파일 오류(`from_filter` ×3, `install_guardrails`
반환형)는 이 이식 안에서 함께 해소된다.

ARGO 와 다르게 가는 결정 두 가지(사용자 확정):
- 설정 필드는 **타입으로 받는다** (`BTreeMap<PiiFilterLayer, Vec<PiiLabel>>`). 키·라벨 오타는
  serde 단계에서 `ConfigError::Parse` 로 거부된다. argo-tizen 이 `pii_mode` 오타를 처리하는
  관례(`unrecognized_pii_mode_is_rejected`)와 같다. tinicli 의 문자열 검증 함수
  (`check_filter_label_layers`, 라벨 문자열 대조)는 옮기지 않는다.
- 대시보드 패치 API 에는 **필드로 모델링하지 않고** 섹션 description 에만 언급한다
  (`demask_tool_args` 와 같은 처리).

argo-tizen 의 판단 로직(어느 모드에서 무엇을 막는지, boot 이 `Degraded` 를 fatal 로 다루는 것,
Ollama 티어 등)은 건드리지 않는다.

## 참고: ARGO 쪽 원본

- 설정 필드: `tinicli/src/config.rs:138` `pii_filter_labels`
- 빌드: `tinicli/src/guardrails/pii.rs` — `override_kinds_for_layer` (186), `build_layer_detector`
  (224), `build_pii_for_turn` (268)
- tinicore API: `PiiSpanDetector::for_kinds(name, &[SensitiveKind])`,
  `PiiSpanDetector::try_from_filter(name, PiiFilter)`, `shared_layer_filter(layer)`,
  `PiiLabel::ALL` / `as_str()` (`tinicore-traits/src/sensitive.rs:36`, serde `snake_case`)

## 변경 파일

### 1. `crates/argot-config/src/lib.rs` — 설정 스키마

`PiiSettings` (559행 근처) 에 필드 추가. 구조체가 이미 `#[serde(default)]` 이고 `is_empty` 가
`Default` 와의 `PartialEq` 라서 필드만 추가하면 저장 시 생략·로드 시 기본값이 자동으로 된다.

```rust
/// Per-layer narrowing of the PII recognizer set. Absent key = that layer
/// keeps the embedded YAML's built-in set; empty list = `credential` only.
/// `credential` is always detected and cannot be listed or removed.
/// `email` / `address` are accepted but have no recognizer (warned at boot).
/// A key or label the build does not know fails config load (serde), so a
/// policy this build cannot enforce never reaches boot.
pub filter_labels: BTreeMap<PiiFilterLayer, Vec<PiiLabel>>,
```

새 enum, 같은 파일 `PiiMode` 옆:

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum PiiFilterLayer { Input, Output, Default }
impl PiiFilterLayer { pub const fn as_str(self) -> &'static str { … } }   // "input" | "output" | "default"
```

`PiiLabel` 은 `tinicore_traits::sensitive::PiiLabel` 을 그대로 쓴다 (argot-config 는 이미
`tinicore-traits` 에 의존). `BTreeMap` 키로 쓰려면 `Ord` 가 필요하므로 `PiiFilterLayer` 에
derive 한다.

TOML 모양:

```toml
[safety.pii]
mode = "full"

[safety.pii.filter_labels]
input   = ["card", "national_id"]
output  = []
default = ["phone"]
```

`PiiSettings` doc 의 "boot-frozen" 설명에 `filter_labels` 도 재시작 시 반영된다고 한 줄 추가.
`reload.rs` 의 `"safety" => NeedsRestart` 는 최상위 키 단위라 변경 없음.

### 2. `crates/argot-config/src/patch.rs` — 대시보드 섹션 설명 (325행 근처)

`safety_pii` 의 `description` 문자열에 `demask_tool_args` 와 같은 문장으로 `filter_labels` 를
덧붙인다: "config.toml 에서만 설정하는 전문가용 레이어별 override, 대시보드에 노출하지 않음".
`fields` 는 변경 없음.

### 3. `crates/argot-daemon/src/guardrails/pii.rs` — 빌드 경로

**시그니처**

```rust
fn build_pii(mode, demask_tool_args, filter_labels: &BTreeMap<PiiFilterLayer, Vec<PiiLabel>>)
    -> (Option<GuardrailSet>, Option<SensitiveMasking>)
pub(crate) fn install_pii(mode, demask_tool_args, filter_labels: BTreeMap<PiiFilterLayer, Vec<PiiLabel>>)
    -> PiiInstall
```

`guardrails/mod.rs:66` 의 `pub fn install_pii` 재수출도 같은 시그니처로.

**새 헬퍼 두 개** (ARGO 의 `override_kinds_for_layer` + `build_layer_detector` 에 대응, 검증은 뺌)

```rust
/// Labels for one layer → the `SensitiveKind` list `for_kinds` takes.
/// `Credential` first, always: the operator narrows PII, never credentials.
fn override_kinds(layer: PiiFilterLayer, labels: &[PiiLabel]) -> Vec<SensitiveKind> {
    let mut kinds = vec![SensitiveKind::Credential];
    for label in labels {
        if matches!(label, PiiLabel::Email | PiiLabel::Address) {
            tracing::warn!(layer = layer.as_str(), label = label.as_str(),
                "pii: label has no recognizer in the embedded config — it will not detect anything");
        }
        kinds.push(SensitiveKind::Pii(*label));
    }
    kinds
}

/// Override path when the layer key is present, built-in layer otherwise.
/// Both come from the shared engine — see `pii_regex_engine_guard.rs`.
fn build_layer_detector(layer: PiiFilterLayer, filter_labels: &BTreeMap<…>) -> Result<PiiSpanDetector, PiiError> {
    let name = format!("guardrails:{}", layer.as_str());
    if let Some(labels) = filter_labels.get(&layer) {
        return PiiSpanDetector::for_kinds(name, &override_kinds(layer, labels));
    }
    let filter = shared_layer_filter(layer.as_str())?;
    PiiSpanDetector::try_from_filter(name, filter)
}
```

**`build_pii` 본문**: 기존의 `shared_layer_filter(...)` `match` + `from_filter(...)` 세 쌍을
`build_layer_detector(PiiFilterLayer::Input, filter_labels)` 등 세 호출로 교체. 실패 처리는
기존 모양 유지 — `input` 실패는 `tracing::error!` 후 `(None, None)`, `default`/`output` 실패는
`(Some(set), None)`. `block_only` 에서도 세 레이어를 모두 빌드하는 현재 순서는 그대로 둔다
(ARGO 와 같은 "모드를 올려도 설정이 이미 유효" 원칙).

**`install_pii`**: `install_guardrails(set)` → `install_guardrails(set).fully_merged`. `false` 를
`Degraded { input_active: false }` 로 보내는 판단은 그대로. 로그 문구는 "slot already installed"
→ "a guardrail layer was dropped while merging into the process-global set". 156~164행의
`OnceLock`/first-wins doc 은 accumulate 서술로 교체.

**`use`**: `argot_config::{PiiFilterLayer, PiiMode}`, `tinicore_traits::sensitive::PiiLabel` 추가.
`shared_layer_filter` 는 계속 쓰므로 유지.

### 4. `crates/argot-daemon/src/boot/mod.rs:416` — 배선

```rust
let installed = crate::guardrails::install_pii(pii.mode, pii.demask_tool_args.clone(), pii.filter_labels.clone());
```

`bail!` 메시지와 `info!` 는 변경 없음. 검증은 이미 config 로드에서 끝났으므로 boot 에 새
분기는 없다.

### 5. `docs/book/src/reference/config-schema.md` — 운영자 문서 (435~470행 `## [safety.pii]`)

키 표에 `filter_labels` 행 추가 (`Type: table of layer → label list`, `Default: (none)`,
`Applies: restart`), TOML 예시에 `[safety.pii.filter_labels]` 블록, 규칙 네 줄:
`credential` 항상 포함 / 키 생략 vs 빈 목록 / `email`·`address` 는 인식기 없음 / 알 수 없는
키·라벨은 config 로드 실패. 유효 라벨 8개를 나열한다.

### 6. 테스트

**`argot-config/src/lib.rs` `mod tests`** (기존 `enabled_pii_settings_round_trip_through_save` 를
본떠서):
- `filter_labels_round_trip_through_save` — 세 레이어 설정 후 `save` → `load_from` 동일
- `unrecognized_filter_label_is_rejected` — `input = ["crad"]` → `load_from` 은 `Err`
- `unrecognized_filter_layer_key_is_rejected` — `inpt = ["card"]` → `Err`
- `save_omits_safety_pii_when_default` 가 여전히 통과하는지 (필드 추가로 깨지지 않음)

**`argot-daemon/src/guardrails/pii.rs` `mod tests`** (기존 8개 옆):
- `override_prepends_credential` — `["card"]` → `[Credential, Pii(Card)]`
- `empty_override_is_credential_only`
- `absent_layer_key_uses_the_built_in_set` — `build_layer_detector` 가 `kinds()` 에 `Card` 외의
  종류도 포함
- `email_label_warns_and_is_kept`
- 기존 8개 테스트는 `install_pii`/`build_pii` 시그니처 변경에 맞춰 `BTreeMap::new()` 인자 추가

**`argot-daemon/tests/guardrails_global_install.rs:191`** — `install_pii(PiiMode::Full,
BTreeMap::new())` 에 세 번째 인자 `BTreeMap::new()` 추가. 이 파일은 "바이너리에서 유일한
설치자" 전제를 단언하므로 테스트를 더 넣지 않는다.

**`tests/pii_regex_engine_guard.rs`** — `build_filters_with_params` 만 금지하므로 변경 없음.

## 검증

```bash
cd /Users/byungchulso/Works/argo-tizen
cargo fmt --all -- --check
cargo clippy -p argot-config -p argot-daemon --all-targets -- -D warnings
cargo test -p argot-config pii                 # 라운드트립 + 오타 거부
cargo test -p argot-daemon guardrails          # 단위 + guardrails_global_install + pii_regex_engine_guard
```

수동 확인 (daemon 실행):
1. `[safety.pii.filter_labels] input = ["card"]` 로 부팅 → 로그 `pii: install complete`, 카드번호
   입력은 차단되고 전화번호 입력은 통과(입력 레이어가 `card`+`credential` 로 좁혀짐).
2. `input = ["crad"]` → daemon 이 config 로드 단계에서 `ConfigError::Parse` 로 시작 실패, 메시지에
   `crad` 와 허용 값 목록이 보임.
3. `default = ["email"]` → 부팅 로그에 `label has no recognizer` warn 한 줄, 부팅은 성공.
4. 필드를 지우고 저장(`save`) 하면 `config.toml` 에 `[safety.pii.filter_labels]` 가 남지 않음.

## 하지 않는 것

- `tini/` 아래 파일 수정 (읽기 전용, sync 로만 갱신)
- `build_only` 에서 `output`/`default` 레이어 빌드 생략 (ARGO 와 같은 이유로 유지)
- Ollama 티어, transport, `prompt_guard` 등 argo 로직
- 대시보드 UI 필드 (설명만)
