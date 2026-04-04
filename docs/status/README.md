# Status Audit

Этот каталог нужен для простой вещи: чтобы не спорить о состоянии проекта по памяти. Здесь лежит снимок текущей готовности относительно `MASTER_SPEC.md`, список оставшихся gap'ов и machine-readable статус по фазам, слоям и operational path.

Когда проект большой, очень легко попасть в режим “вроде почти всё есть”. Обычно именно в этот момент выясняется, что “почти” сидит в самых дорогих местах: release-hardening, vendor adapters, optimizer и прочих радостях жизни.

## Что здесь лежит

- `implementation_status.yaml` — машинно-читаемый снимок состояния проекта;
- `spec_gap_audit.md` — человеческий аудит по фазам, инвариантам и хвостам до полного DoD.
- `lego_progress.yaml` — статус по backlog-эпикам `E00..E26`;
- `lego_progress.md` — человеческий комментарий к backlog progress.

## Как этим пользоваться

- перед новой фазой смотреть `spec_gap_audit.md`, чтобы не делать вид, что хвостов нет;
- перед релизным прогоном смотреть `implementation_status.yaml`, чтобы быстро увидеть открытые риски и временные упрощения;
- перед обновлением roadmap синхронизировать этот каталог с [implementation_notes.md](/E:/projecttype/docs/implementation_notes.md) и [release_checklist.md](/E:/projecttype/docs/release_checklist.md).

## Что здесь принципиально важно

- статус должен быть честным, а не мотивационным;
- временные упрощения должны перечисляться явно;
- machine-readable и prose-слой не должны противоречить друг другу.

## Как проверять

Для этих артефактов есть smoke-проверка в `tests/integration/test_status_audit_artifacts.py`.
