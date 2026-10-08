# Полный гайд по лабораторной "Replicated Counter Service"

> Весь код проекта уже написан и **проверен** (10/10 pytest проходят, quorum 3/3→2/3→1/3
> работает, benchmark считает, Lamport-логи генерируются). Этот файл — пошаговая
> инструкция на русском: что делать, какие команды вводить, что они значат и как
> подготовиться к защите. Весь код и текст, который видит преподаватель, — на английском.

Содержание:
- ЧАСТЬ 0–6 — установка, проект, venv, Git/GitHub
- ЧАСТЬ 7 — структура проекта
- ЧАСТЬ 8–12 — proto, генерация, clocks, server, client (как они работают)
- ЧАСТЬ 13–17 — проверка Part A (one replica, idempotency, concurrency)
- ЧАСТЬ 18–20 — три replicas, quorum, stale read
- ЧАСТЬ 21 — Lamport trace
- ЧАСТЬ 22–25 — pytest, failure injection, benchmark, evidence
- ЧАСТЬ 26 — report (готовый шаблон — файл `report.md`)
- ЧАСТЬ 27–29 — reflection, git commits, финальный чеклист
- ЧАСТЬ 30 — подготовка к Midterm Defense (+20 вопросов)
- ЧАСТЬ 31 — частые ошибки

---

## ЧАСТЬ 0 — Что установить ⏱ 15–30 мин

Скачай и установи:
1. **Python 3.9+** — https://www.python.org/downloads/ (при установке поставь галочку *Add Python to PATH*).
2. **Visual Studio Code** — https://code.visualstudio.com/
3. **Python extension** для VS Code (Microsoft) — через боковую панель Extensions.
4. **Git for Windows** — https://git-scm.com/download/win

Через pip (позже сами) ставятся `grpcio`, `grpcio-tools`, `pytest` — отдельно качать не надо.

Проверка в терминале:
```powershell
python --version
git --version
```
Если `python` не работает, но работает `py` — используй везде `py` вместо `python` (напр. `py -m venv .venv`).

## ЧАСТЬ 1 — VS Code и PowerShell ⏱ 2 мин
Открой VS Code → меню **Terminal → New Terminal**. Внизу появится строка вида `PS C:\Users\...>`.
`PS` = PowerShell, это и есть терминал, куда вводим команды.

## ЧАСТЬ 2 — Папка проекта ⏱ 3 мин
Распакуй присланный архив `dcc-assignment2` на Desktop. Затем в VS Code:
**File → Open Folder → выбери `dcc-assignment2`**. Снова открой Terminal → New Terminal
(теперь терминал уже внутри папки проекта).

Если создаёшь с нуля:
```powershell
cd Desktop
mkdir dcc-assignment2
cd dcc-assignment2
```

## ЧАСТЬ 3 — Virtual environment ⏱ 3 мин
venv — это изолированная «коробка» с библиотеками только для этого проекта.
```powershell
python -m venv .venv
.venv\Scripts\activate
```
После активации слева в строке терминала появится `(.venv)`.

**Если ошибка `running scripts is disabled on this system`** — PowerShell запрещает запуск скриптов.
Безопасное решение (только для текущего пользователя):
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```
Нажми `Y`, потом снова `.venv\Scripts\activate`.

## ЧАСТЬ 4 — Установка библиотек ⏱ 3 мин
```powershell
pip install grpcio grpcio-tools pytest
python -m grpc_tools.protoc --version
```
Последняя команда должна вывести строку вида `libprotoc 3x.x` — значит gRPC-инструменты работают.

## ЧАСТЬ 5–6 — Git и GitHub ⏱ 10 мин
Преподаватель пока не дал GitHub Classroom, поэтому создаём свой **приватный** репозиторий.

Сначала один раз настрой имя/почту (на английском):
```powershell
git config --global user.name "YOUR NAME"
git config --global user.email "YOUR EMAIL"
```
Файл `.gitignore` уже есть в проекте (игнорирует `.venv`, `__pycache__`, логи).

На сайте: github.com → войти → **New repository** → имя `dcc-assignment2` → **Private** →
**НЕ** ставить галочки README/.gitignore/license (репозиторий должен быть пустым) → **Create repository** →
скопировать HTTPS-ссылку.

Далее в терминале:
```powershell
git init
git add .
git commit -m "Initial project setup"
git branch -M main
git remote add origin REPOSITORY_URL
git push -u origin main
```
Простыми словами:
- `git status` — показывает, какие файлы изменились;
- `git add .` — помечает все изменения для сохранения;
- `git commit -m "..."` — сохраняет снимок (checkpoint) в истории;
- `git push` — отправляет историю на GitHub.
Все commit-сообщения — на английском.

## ЧАСТЬ 7 — Структура проекта
Смотри README.md — там дерево файлов. Коротко: `counter.proto` (интерфейс),
`clocks.py` (логические часы), `server.py` (одна replica), `client.py` (клиент с retry и quorum),
`tests/` (тесты и benchmark), `logs/` (логи для Lamport-анализа).

---

## ЧАСТЬ 8 — counter.proto (интерфейс)
Это описание «контракта» сервиса на языке Protocol Buffers: какие есть методы (`Increment`, `Get`)
и какие поля в сообщениях. Поле `lamport_time = 4` добавлено в каждый request/reply для Part B.
Файл уже готов. После любого изменения proto нужно заново генерировать stubs (Часть 9).

**Что запомнить для защиты:** proto — это язык-независимое описание API; `int64`, `string`, `uint64` —
типы полей; числа (`= 1`, `= 2`) — это **field numbers**, по ним кодируются данные в бинарном виде.

## ЧАСТЬ 9 — Генерация counter_pb2 файлов
```powershell
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. counter.proto
```
Создаются `counter_pb2.py` (классы сообщений) и `counter_pb2_grpc.py` (классы сервиса/стаба).
**Руками их не редактировать.** Если изменишь proto — запусти команду снова.

## ЧАСТЬ 10 — clocks.py (Lamport clock)
`LamportClock` — простой счётчик с `threading.Lock`:
- `tick()` → `value = value + 1` (перед локальным событием: send / apply);
- `receive(received)` → `value = max(value, received) + 1` (при приёме сообщения).

Зачем: у разных машин нет общих точных физических часов, поэтому по времени «на стене»
нельзя сказать, какое событие было раньше. Логический счётчик даёт правило:
**если A произошло-до B, то L(A) < L(B)**. `Lock` нужен, потому что часы трогают несколько потоков
одновременно — без него два потока могли бы прочитать и записать `value` «вперемешку».

## ЧАСТЬ 11 — server.py (одна replica)
Одна replica = один процесс со своим состоянием: `values` (counter_id → число),
`seen` (idempotency_key → результат, для дедупликации), свои Lamport-часы.
Сервер использует `ThreadPoolExecutor(max_workers=8)` — обрабатывает клиентов параллельно.

**Критично:** проверка `idempotency_key` и изменение counter делаются под **одним и тем же** `self._lock`.
Иначе два одновременных retry с одинаковым ключом могли бы оба пройти проверку и прибавить delta дважды.

Логика `Increment`: обновить часы от присланного `lamport_time` (RECV) → при необходимости применить
fault/delay → войти в lock → если ключ уже в `seen`, вернуть сохранённый результат с `was_duplicate=True`
(delta НЕ прибавляется) → иначе прибавить delta, сохранить значение и ключ (APPLY), сделать SEND → вернуть ответ.

Флаги: `--port`, `--name`, `--fault {delay-first,drop-after-recv}`, `--delay-ms N`.
`create_server(port=0, ...)` — хелпер: при `port=0` ОС выдаёт свободный (ephemeral) порт; это
используют тесты, чтобы не конфликтовать с 50051–50053. Логи можно отключать (`log_enabled=False`)
для тестов и benchmark.

**Для защиты:** state у каждой replica свой (нет shared state); dedup-проверка и мутация под одним lock;
fault-инъекция сделана через флаги (детерминированно).

## ЧАСТЬ 12 — client.py (клиент)
Класс `CounterClient`. Методы: `increment_single` (одна replica, с retry), `quorum_increment`
(шлёт всем replicas параллельно, коммит при majority), `get` (читает с любой доступной replica),
`close`. Default replicas: `127.0.0.1:50051/50052/50053`.

- Каждый RPC с дедлайном `timeout=2.0`.
- Один **idempotency_key = uuid.uuid4()** на одну логическую операцию; при retry — **тот же** ключ.
- Retry **только** на `DEADLINE_EXCEEDED` и `UNAVAILABLE`, максимум 3 раза (итого до 4 попыток),
  backoff `0.2 / 0.4 / 0.8` сек.
- Lamport: перед каждым SEND → `tick()`; при RECV → `receive(reply.lamport_time)`.

CLI: `incr <counter> --by N [--key K]`, `get <counter>`, `scenario client-1|2|3`, флаги `--replicas`, `--name`.

**Для защиты:** majority = `len(replicas)//2 + 1` (для 3 → 2); один ключ на всю логическую операцию и на все
replicas; retry переиспользует ключ — поэтому повтор безопасен.

---

## ЧАСТЬ 13 — Part A, одна replica ⏱ 5 мин
```powershell
# Terminal 1
python server.py --port 50051 --name replica-A
# Terminal 2 (не забудь активировать .venv в каждом новом терминале)
python client.py --replicas 127.0.0.1:50051 incr likes:post-42 --by 5
python client.py --replicas 127.0.0.1:50051 get likes:post-42
```
Ожидаем `value=5`. Проверили: клиент→сервер по gRPC, Increment применил +5, Get прочитал значение.
**Git:** после этого — `git add . && git commit -m "Implement counter server and client"`.

## ЧАСТЬ 14 — Idempotency ⏱ 3 мин
```powershell
python client.py --replicas 127.0.0.1:50051 incr x --by 5 --key demo-key
python client.py --replicas 127.0.0.1:50051 incr x --by 5 --key demo-key
```
Первый раз: `value=5, duplicate: no`. Второй раз: `value=5, duplicate: yes` — counter НЕ стал 10,
потому что сервер по ключу `demo-key` понял, что операция уже выполнялась, и вернул сохранённый результат.

## ЧАСТЬ 15 — Concurrency ⏱ авто (в тестах)
Проверяется тестом `test_concurrent_increments_exact`: два потока по 1000 increments одного counter → ровно **2000**.
- **race condition** — когда два потока одновременно делают «прочитать→прибавить→записать», и одно обновление теряется.
- Без `Lock` финал может быть, например, 1997.
- `Lock` делает «прочитать+прибавить+записать» одной неделимой операцией → ровно 2000.

## ЧАСТЬ 16 — Три replicas ⏱ 5 мин
Запусти в трёх терминалах `server.py` на портах 50051/50052/50053 (имена replica-A/B/C).
В четвёртом — клиент без `--replicas` (берёт все три по умолчанию). Каждый Increment уходит всем трём
параллельно (`ThreadPoolExecutor`). У каждой replica свои `values`, `seen`, `LamportClock` — никакого общего состояния.

## ЧАСТЬ 17 — Quorum ⏱ 5 мин
Majority для 3 replicas = 2.
- 3/3 → `OK committed (acked 3/3)`
- останови одну (Ctrl+C) → 2/3 → `OK committed (acked 2/3)`
- останови вторую → 1/3 → `FAILED not committed (acked 1/3)`

**Anomaly (важно для защиты):** при 1/3 клиент говорит «не закоммичено», НО единственная живая replica
могла уже применить изменение локально (partial write). Проверено: после FAILED `get` с этой replica
показывает применённое значение. Это НЕ полноценный consensus. Raft это чинит через: **leader**,
**replicated log**, **commit index**, **recovery/catch-up** (реализовывать Raft не нужно).

## ЧАСТЬ 18/20 — Get и stale read
`Get` читает с любой одной доступной replica. Если одна replica пропустила записи (была недоступна),
её значение может быть устаревшим (stale). Это в Known Limitations.

## ЧАСТЬ 21 — Lamport trace ⏱ 10 мин
```powershell
# сначала очисти старые логи
Remove-Item logs\*.log -ErrorAction SilentlyContinue
# Terminal 1
python server.py --port 50051 --name replica-A
# Terminals 2,3,4 — запусти быстро друг за другом
python client.py --name client-1 --replicas 127.0.0.1:50051 scenario client-1
python client.py --name client-2 --replicas 127.0.0.1:50051 scenario client-2
python client.py --name client-3 --replicas 127.0.0.1:50051 scenario client-3
```
Логи появятся в `logs\`. Открой их, выбери ~30 полезных строк и сохрани как `logs\trace_excerpt.txt`
(шаблон такого файла уже есть — замени на СВОИ реальные значения).

По реальному трейсу в report нужно найти (правило разбора — ниже в report):
- 2 пары причинно-связанных событий (цепочка local → message → ...);
- 1 пару concurrent-событий;
- почему разные Lamport-значения не доказывают причинность;
- ограничение Lamport + что добавляют vector clocks.

**Не выдумывай Lamport-значения — бери из своего запуска.**

---

## ЧАСТЬ 22 — pytest ⏱ 2 мин
```powershell
pytest -v
```
Ожидаемый формат вывода — строки `PASSED`. 10 тестов (8 обязательных + 2 доп. failure-сценария).
Реальный вывод вставишь в report (там стоит `[PASTE REAL PYTEST OUTPUT HERE]`).

Обязательные 8 имён: `test_increment_applies_delta`, `test_duplicate_key_not_reapplied`,
`test_concurrent_increments_exact`, `test_get_missing_counter`, `test_retry_after_timeout_is_safe`,
`test_majority_commit_two_acks`, `test_no_commit_below_majority`, `test_replicas_converge`.

## ЧАСТЬ 23/24 — Failure injection
Три сценария автоматизированы в `tests/test_failures.py`:
1. **Replica failure** → `test_majority_commit_two_acks` (2 из 3 живы → commit).
2. **Duplicate request** → `test_duplicate_request_moves_value_once` (тот же ключ дважды → value один раз, `was_duplicate=True`).
3. **Timeout + retry** → `test_timeout_then_retry_commits_once` (replica с `--fault delay-first` задерживает первый запрос дольше дедлайна; retry с тем же ключом → counter меняется один раз).
Плюс `test_no_commit_below_majority` показывает partial-write anomaly.

## ЧАСТЬ 25 — Benchmark ⏱ 2–5 мин
```powershell
python tests\perf_benchmark.py
```
Benchmark сам поднимает ephemeral servers, гоняет **2000 логических** Increment на каждую из 4 конфигураций,
печатает median и p95 (мс). Логирование на время benchmark выключено. Реальные числа вставишь в report.
- **median** — «типичная» задержка (половина запросов быстрее, половина медленнее);
- **p95** — 95% запросов быстрее этого значения (видно «хвост» медленных запросов);
- p95 считается как элемент отсортированного списка на позиции `ceil(0.95*n)` (в коде — zero-based индекс).

## ЧАСТЬ 25b — Какие evidence сохранить
**REQUIRED (обязательно):**
- Git history (несколько commit'ов) — `git log --oneline`;
- вывод `pytest -v` (все PASSED);
- файлы в `logs/` + `trace_excerpt.txt` с реальными строками;
- вывод benchmark (median/p95 по 4 конфигурациям);
- заполненный report.pdf (таблицы с реальными результатами);
- README.md.

**OPTIONAL (для подстраховки, скриншоты не требуются заданием, но полезны):**
- скриншот `pytest -v` с PASSED;
- скриншот трёх работающих replicas + успешный quorum;
- скриншот вывода benchmark.

---

## ЧАСТЬ 26 — Report
Готовый шаблон — отдельный файл **`report.md`** в этом проекте. Открой его, вставь свои реальные
результаты вместо меток `[PASTE REAL ... HERE]`, затем экспортируй в PDF
(в VS Code: расширение «Markdown PDF», правый клик → *Markdown PDF: Export (pdf)*; либо через Word/Google Docs).
Сохрани как `report.pdf` в корне проекта.

## ЧАСТЬ 27 — Reflection answers
Они включены в `report.md` (раздел Reflection Questions) — короткие ответы на английском.
Ниже в этом гайде (Часть 30) те же идеи объяснены по-русски, чтобы ты мог их пересказать устно.

## ЧАСТЬ 28 — Git commits (incremental history)
Делай коммиты по ходу, а не один в конце. Пример последовательности:
```
Initial project setup
Add gRPC counter interface
Implement counter server
Implement client retries and idempotency
Add Lamport clock instrumentation
Add quorum replication
Add automated tests
Add failure injection tests
Add performance benchmark
Add Lamport trace evidence
Complete README and report
```
После крупного этапа:
```powershell
git status
git add .
git commit -m "..."
git push
```
В конце — `git log --oneline` (должно быть несколько строк, а не один коммит).

## ЧАСТЬ 29 — Финальный чеклист
Пройди по чеклисту из задания (раздел 39). Главное: pytest зелёный; quorum 3/3, 2/3, 1/3 проверены;
есть реальные логи и trace_excerpt; benchmark с реальными числами; report.pdf заполнен; несколько коммитов запушены.

---

## ЧАСТЬ 30 — Подготовка к Midterm Defense (кратко, по-русски)

- **RPC** — вызов функции на другой машине, как будто локальной. **gRPC** — реализация RPC от Google поверх HTTP/2.
  **Protocol Buffers** — язык описания сообщений/сервисов и бинарный формат (компактнее JSON).
- **counter.proto** — контракт API. **counter_pb2.py** — классы сообщений, **counter_pb2_grpc.py** — классы сервиса/стаба (генерируются).
- **server** принимает RPC и хранит состояние; **client** шлёт RPC. **Increment** меняет counter, **Get** читает.
- **idempotency** — свойство «повтор не меняет результат». **idempotency_key** — уникальный id операции; retry
  с ТЕМ ЖЕ ключом → сервер понимает, что это повтор, и не применяет delta снова. Новый ключ на retry сломал бы это (counter вырос бы дважды).
- **deadline** — макс. время ожидания ответа. **DEADLINE_EXCEEDED** — не успел; **UNAVAILABLE** — сервер недоступен.
  Эти ошибки временные → их ретраим. **exponential backoff** (0.2/0.4/0.8) — паузы между retry растут, чтобы не долбить сервер.
- **concurrency** — одновременная работа потоков. **thread** — поток. **ThreadPoolExecutor** — пул потоков.
  **race condition** — потеря обновления при одновременном read-modify-write. **Lock** делает участок неделимым →
  2×1000 даёт ровно 2000. Dedup-проверка и мутация под одним lock — иначе два retry с одним ключом оба применятся.
- **Lamport time** — логический счётчик. `tick()` = +1 перед локальным событием; `receive()` = `max(local,received)+1`.
  **happened-before**: A→B если A локально раньше B, или A — это send, а B — соответствующий receive, или по цепочке.
  **concurrent events** — между которыми нет такой цепочки. `L(A)<L(B)` НЕ значит A→B (события разных процессов могут быть concurrent).
  **vector clock** — вектор счётчиков по одному на процесс; умеет точно определять concurrency (чего Lamport не может).
- **replica** — копия сервиса. Три replicas → терпим отказ одной. **quorum/majority** = 2 из 3.
  Одна упала → 2/3, всё ещё commit. Две упали → majority невозможен → не commit. При 1/3 одна replica могла
  применить локально (partial write). Это **не Raft**: нет leader/лога/commit index/recovery.
- **Get** может вернуть stale данные, если читаем с отставшей replica.
- **median / p95** — см. Часть 25. **quorum медленнее**, т.к. ждём несколько replicas (ответ по самой медленной из нужных),
  плюс сетевые RPC и параллельные потоки.
- После рестарта replica теряет state (всё in-memory). Чтобы пережить рестарт без потери коммитов — нужно
  **durable storage** (запись на диск) + журнал/лог → это ведёт к настоящему consensus (Raft).

### 20 вероятных вопросов на защите
Формат: **Q** — вопрос; *(проверяет)* — что хотят услышать; **A (EN)** — короткий ответ вслух.

1. **Q: Where is idempotency implemented?** *(понимаешь ли дедуп)*
   **A:** In `server.py`: the `seen` dict maps each idempotency_key to its stored result; if the key is already there I return the stored value with `was_duplicate=True` without applying the delta.
2. **Q: Where is the shared-state lock?** *(где критическая секция)*
   **A:** `self._lock` in `CounterServicer.Increment` — the dedup check and the counter mutation are inside the same `with self._lock` block.
3. **Q: Where is the retry logic?** **A:** In `client.py`, `_increment_on_stub`: up to 3 retries on DEADLINE_EXCEEDED/UNAVAILABLE with 0.2/0.4/0.8s backoff.
4. **Q: Where do you reuse the same idempotency key?** **A:** The key is generated once per logical operation in `quorum_increment`/`increment_single` and passed into every retry and every replica.
5. **Q: Where is quorum calculated?** **A:** `majority()` returns `len(replicas)//2 + 1`; `quorum_increment` commits when acks ≥ majority.
6. **Q: Why is quorum equal to 2?** **A:** Majority of 3 is 2, so any two replicas overlap on at least one — that tolerates one crash while preserving committed writes.
7. **Q: Where is Lamport receive implemented?** **A:** `clocks.py`, `receive()` = `max(local, received) + 1`, called on every RECV.
8. **Q: Where do you update the clock before SEND?** **A:** `tick()` (+1) is called right before building each outgoing message.
9. **Q: How do you know concurrency is correct?** **A:** `test_concurrent_increments_exact` runs 2×1000 increments and asserts the counter is exactly 2000.
10. **Q: How did you test 2000 increments?** **A:** Two threads, 1000 each, unique keys, single replica; final Get must equal 2000.
11. **Q: How do you simulate timeout?** **A:** `--fault delay-first` delays the first request past the client deadline; the client times out and retries.
12. **Q: How do you simulate replica failure?** **A:** The client points at a dead address (no server), or a replica is stopped; it returns UNAVAILABLE and is not counted as an ack.
13. **Q: Why can one replica be inconsistent?** **A:** Writes go to replicas independently; a replica that was down misses writes until it gets new ones, so a single-replica Get can be stale.
14. **Q: What happens if all replicas restart?** **A:** State is in-memory, so all counters and the dedup store are lost — committed writes are not durable.
15. **Q: Why is this not a consensus algorithm?** **A:** No leader, no replicated log, no commit index, no recovery — just independent majority acks, so a sub-majority write can partially apply.
16. **Q: Why is the quorum benchmark slower?** **A:** A logical op waits for a majority of parallel RPCs, so its latency is bounded by the slower acks plus extra network/thread overhead.
17. **Q: What does `was_duplicate` mean?** **A:** The server already applied this idempotency_key, so it returned the stored result instead of applying the delta again.
18. **Q: What is the partial-write anomaly?** **A:** With only 1/3 acks the client reports failure, yet that one replica already applied the write locally.
19. **Q: Why max(local, received)+1 on receive?** **A:** It guarantees the receive event's clock is strictly greater than the send event's, preserving happened-before across processes.
20. **Q: What would you change to survive restarts?** **A:** Persist counter state and the idempotency store to disk (a write-ahead log), which is the first step toward a real replicated log / Raft.

---

## ЧАСТЬ 31 — Частые ошибки

| Симптом | Причина | Что сделать |
|---|---|---|
| `python is not recognized` | Python не в PATH | Переустанови с галочкой *Add to PATH*, или используй `py` |
| `py` работает, `python` нет | только launcher | Везде используй `py` (напр. `py -m venv .venv`) |
| `git is not recognized` | Git не установлен/не в PATH | Установи Git for Windows, перезапусти терминал |
| `.venv cannot activate` / `running scripts is disabled` | политика PowerShell | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` |
| `ModuleNotFoundError: grpc` | не установлен grpcio / venv не активен | активируй `.venv`, затем `pip install grpcio grpcio-tools pytest` |
| `ModuleNotFoundError: pytest` | pytest не установлен | `pip install pytest` |
| `ModuleNotFoundError: counter_pb2` | не сгенерированы stubs | запусти команду protoc из Части 9 |
| `ModuleNotFoundError: server` (в тестах) | запуск не из корня | запускай `pytest` из папки `dcc-assignment2` (conftest.py сам добавляет корень в путь) |
| protoc generation fails | старый pip | `python -m pip install --upgrade pip`, повтори |
| wrong current folder | ты не в папке проекта | `cd` в `dcc-assignment2` |
| `Address already in use` / `port already occupied` | порт занят старым сервером | закрой старый сервер; в тестах это не бывает (ephemeral порты) |
| `UNAVAILABLE` / `connection refused` | сервер не запущен / не тот порт | запусти `server.py` на нужном порту до клиента |
| server стартует, но client не коннектится | разные адреса/порты | проверь `--replicas` и `--port` |
| pytest collection/import error | неверный путь импорта | запускай из корня проекта; не переименовывай файлы |
| pytest hangs | завис сервер в фикстуре | Ctrl+C; убедись, что не запущены лишние серверы вручную |
| concurrency test fails (<2000) | убрали Lock | верни `with self._lock` вокруг проверки+мутации |
| timeout test flaky | дедлайн ≈ задержке | держи `timeout=0.5` и `--delay-ms 1500` (запас) |
| `Git remote origin already exists` | remote уже добавлен | `git remote set-url origin URL` |
| `Git authentication failed` | нужен токен | используй Personal Access Token вместо пароля |
| `Git push rejected` | на GitHub есть коммиты | `git pull --rebase origin main`, потом `git push` |
| `nothing to commit` | нет изменений | это норм; сначала измени/добавь файлы |
| `repository not found` | неверный URL/нет доступа | проверь ссылку origin и права на репозиторий |

---

## Если просто хочешь сделать всё по порядку (roadmap)
1. Установи/проверь инструменты (Python, VS Code, Git).
2. Открой папку проекта в VS Code.
3. Создай GitHub-репозиторий.
4. (proto уже есть) при изменении — перегенерируй stubs.
5. Сгенерируй `counter_pb2*` (Часть 9).
6. (clocks/server/client уже написаны) — просто прочти, чтобы понимать.
7–8. Запусти одну replica и клиент (Часть 13).
9. Проверь idempotency (Часть 14).
10. Запусти `pytest -v` — должно быть 10 PASSED (это и concurrency 2000).
11. Подними три replicas (Часть 16).
12. Проверь quorum 3/3 → 2/3 → 1/3 (Часть 17).
13. Сгенерируй Lamport-логи и `trace_excerpt.txt` (Часть 21).
14. Запусти failure-тесты (входят в `pytest`).
15. Запусти benchmark (Часть 25), запиши реальные median/p95.
16. Заполни `report.md` реальными результатами → экспортируй `report.pdf`.
17. Сделай несколько git-коммитов и финальный push.
18. Повтори вопросы для защиты (Часть 30).
