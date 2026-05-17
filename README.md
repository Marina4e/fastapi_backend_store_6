# FastAPI Backend Store

Це навчальний backend-проєкт магазину на **FastAPI + PostgreSQL + Docker**.

Головна ідея: є товар з обмеженим залишком на складі. Багато користувачів одночасно намагаються купити цей товар через один endpoint `POST /purchase`. Сервіс має працювати так, щоб товар не продавався “в мінус”.

## Для чого це завдання

Викладач, найімовірніше, хоче перевірити не просто знання FastAPI, а розуміння кількох важливих речей:

1. Як створити backend API.
2. Як підключити PostgreSQL.
3. Як запускати застосунок і базу через Docker.
4. Як працювати з `.env` налаштуваннями.
5. Як правильно змінювати дані в базі при одночасних запитах.
6. Як протестувати API під навантаженням.
7. Як пояснити іншій людині запуск і перевірку проєкту через README.

Найважливіша частина тут — **одночасні покупки одного товару**.

Якщо зробити код неправильно, може статись така ситуація:

1. На складі є `1` одиниця товару.
2. Два користувачі одночасно бачать, що товар ще є.
3. Обидва купують.
4. У результаті система продала `2` одиниці, хоча на складі була тільки `1`.

Це називається проблемою конкурентності. У цьому проєкті вона вирішена через атомарний SQL-запит у PostgreSQL.

## Що реалізовано

- FastAPI застосунок.
- Endpoint `POST /purchase`.
- PostgreSQL база даних.
- Dockerfile для API.
- `docker-compose.yml` для запуску API та PostgreSQL.
- `.env` файл з налаштуваннями.
- Таблиця `products`.
- Стартові товари через `db/init.sql`.
- Endpoint для перегляду товару.
- Endpoint для скидання залишку товару перед тестами.
- Простий frontend для ручної перевірки.
- RPS-тест прямо з frontend.
- Окремий Python load-test скрипт `tests/load_test.py`.

## Структура проєкту

```text
.
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── db.py
│   └── main.py
├── db/
│   └── init.sql
├── frontend/
│   ├── index.html
│   ├── script.js
│   └── styles.css
├── tests/
│   ├── load_test.py
│   └── requirements.txt
├── .env
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Як працює база даних

У базі є таблиця `products`:

```sql
CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY,
    stock INTEGER NOT NULL CHECK (stock >= 0),
    description TEXT NOT NULL
);
```

Поля:

- `product_id` — id товару.
- `stock` — кількість товару на складі.
- `description` — опис товару.

Стартові товари створюються у файлі `db/init.sql`.

Головний тестовий товар:

```text
product_id = 42
stock = 10000
description = Demo product for concurrent purchase testing
```

## Як працює покупка

Endpoint:

```text
POST /purchase
```

Input:

```json
{
  "user_id": 12345,
  "product_id": 42,
  "purchased_count": 2
}
```

Успішна відповідь:

```json
{
  "status": "success"
}
```

У коді покупка виконується одним SQL-запитом:

```sql
UPDATE products
SET stock = stock - $1
WHERE product_id = $2
  AND stock >= $1
RETURNING product_id
```

Що це означає простими словами:

1. PostgreSQL знаходить товар по `product_id`.
2. Перевіряє, що `stock >= purchased_count`.
3. Якщо товару вистачає, одразу зменшує `stock`.
4. Якщо товару не вистачає, нічого не списує.

Цей запит атомарний. Тобто перевірка залишку і списання виконуються як одна неподільна дія.

Саме тому при одночасних запитах склад не піде нижче нуля.

## HTTP відповіді

`200 OK`:

```json
{
  "status": "success"
}
```

Це означає, що покупка пройшла успішно.

`409 Conflict`:

```json
{
  "detail": "Not enough stock"
}
```

Це не помилка коду. Це нормальна бізнес-відповідь: товар закінчився або його недостатньо.

`404 Not Found`:

```json
{
  "detail": "Product not found"
}
```

Це означає, що товару з таким `product_id` немає.

## Порядок запуску проєкту

### 1. Запустити Docker Desktop

Спочатку відкрий Docker Desktop.

Дочекайся, поки Docker повністю запуститься. Якщо Docker Engine не запущений, команди `docker compose` не працюватимуть.

### 2. Відкрити PowerShell у папці проєкту

```powershell
cd D:\VSCode_Python_Projects_26\fastapi_backend_store_6
```

### 3. Запустити API і PostgreSQL

Рекомендований запуск:

```powershell
docker compose up --build -d
```

Що означає команда:

- `docker compose` — запускає сервіси з `docker-compose.yml`.
- `up` — підняти контейнери.
- `--build` — перед запуском зібрати Docker-образ API.
- `-d` — запустити у фоні, щоб термінал не був зайнятий логами.

### 4. Перевірити, що контейнери працюють

```powershell
docker compose ps
```

Ти маєш побачити два сервіси:

- `api`
- `postgres`

У PostgreSQL має бути статус `healthy`.

### 5. Перевірити health endpoint

```powershell
curl http://127.0.0.1:8000/health
```

Очікувана відповідь:

```json
{"status":"ok"}
```

Якщо це працює, значить API підключився до бази.

## Як користуватись frontend

Відкрий у браузері:

```text
http://127.0.0.1:8000/
```

На сторінці є дві частини:

1. Ручна перевірка покупки.
2. RPS-тест з браузера.

### Ручна перевірка

Поля:

- `User ID` — id користувача. Можна залишити `12345`.
- `Product ID` — id товару. Для тесту використовуй `42`.
- `Purchased count` — скільки одиниць купити.

Кнопки:

- `Купити` — відправляє запит на `POST /purchase`.
- `Оновити залишок` — показує поточний залишок товару.
- `Скинути залишок` — встановлює новий `stock` для товару.

Порядок ручної перевірки:

1. Відкрий `http://127.0.0.1:8000/`.
2. Переконайся, що статус зверху `online`.
3. Натисни `Оновити залишок`.
4. Натисни `Купити`.
5. Знову натисни `Оновити залишок`.
6. Перевір, що `stock` зменшився.

### Скидання залишку перед тестами

Перед кожним RPS-тестом краще скидати залишок.

Наприклад:

1. У полі `Новий залишок` введи `20000`.
2. Натисни `Скинути залишок`.
3. Натисни `Оновити залишок`.
4. Переконайся, що `stock` став `20000`.

Це потрібно тому, що кожен тест реально купує товар і зменшує залишок у базі.

Якщо не скинути залишок, наступний тест може показати багато `409 Conflict`, бо товар уже закінчився.

## Як запускати RPS-тест через frontend

У блоці `RPS-тест з браузера` є поля:

- `RPS` — скільки запитів на секунду frontend буде намагатися створити.
- `Тривалість, сек` — скільки секунд триватиме тест.
- `Конкурентність` — скільки запитів можуть одночасно чекати відповіді.
- `Product ID` — товар для тесту, зазвичай `42`.
- `Purchased count` — скільки одиниць списувати за один запит.
- `Timeout, мс` — скільки чекати відповідь на один запит.

Рекомендований навчальний порядок:

1. Скинь залишок на `20000`.
2. Постав:

```text
RPS = 100
Тривалість = 5
Конкурентність = 50
Product ID = 42
Purchased count = 1
Timeout = 2000
```

3. Натисни `Запустити RPS-тест`.
4. Подивись на лічильники.
5. Якщо все стабільно, поступово піднімай `RPS`: `200`, `500`, `1000`.

Не починай одразу з великих значень, якщо ти вчишся. Краще бачити, як система поводиться поступово.

### Що показують метрики у frontend

- `Статус` — стан тесту: `idle`, `running`, `draining`, `finished`, `stopped`.
- `Заплановано` — скільки запитів frontend спробував створити.
- `Завершено` — скільки запитів уже отримали відповідь або помилку.
- `Успішно` — кількість відповідей `200 OK`.
- `409 Conflict` — кількість відповідей, де товару вже не вистачило.
- `Timeout/Error` — таймаути або інші помилки.
- `Dropped` — запити, які браузер хотів створити, але не відправив, бо ліміт `Конкурентність` уже був зайнятий.
- `Фактичний RPS` — приблизна кількість завершених запитів за секунду.
- `In-flight` — скільки запитів прямо зараз очікують відповідь.

### Як читати результат frontend RPS-тесту

Приклад:

```json
{
  "status": "finished",
  "elapsed_seconds": 5.22,
  "scheduled_requests": 1124,
  "completed_requests": 1124,
  "successful_purchases": 1124,
  "stock_conflicts": 0,
  "timeout_or_other_errors": 0,
  "dropped_by_browser": 3874,
  "in_flight": 0,
  "actual_rps": 215.3,
  "target": {
    "rps": 1000,
    "duration": 5,
    "concurrency": 50,
    "product_id": 42,
    "purchased_count": 1,
    "timeout_ms": 2000
  }
}
```

Що тут важливо:

- `target.rps = 1000` означає, що браузер намагався створити 1000 запитів за секунду.
- `duration = 5` означає, що тест мав тривати 5 секунд.
- Теоретична ціль: приблизно `1000 * 5 = 5000` запитів.
- `scheduled_requests` — скільки запитів браузер реально зміг відправити в API.
- `completed_requests` — скільки відправлених запитів завершились відповіддю або помилкою.
- `successful_purchases` — скільки покупок реально пройшло.
- `dropped_by_browser` — скільки запитів браузер не відправив, бо вже було забагато активних запитів.

Якщо `dropped_by_browser` велике, це не означає, що backend точно впав. Це означає, що браузерний тестер не зміг створити таку кількість запитів з заданою `Конкурентність`.

Для `RPS = 1000`, `duration = 5`, `concurrency = 50` браузеру складно чесно створити всі 5000 запитів, бо він тримає тільки 50 активних запитів одночасно. Якщо відповіді не встигають повертатися дуже швидко, наступні запити не відправляються і потрапляють у `Dropped`.

### Важливе про frontend RPS-тест

Frontend-тест з браузера потрібен для навчання і швидкої перевірки.

Він зручний, бо ти бачиш усе на екрані. Але браузер не є ідеальним інструментом для точного benchmark. Для більш серйозної перевірки використовуй Python-скрипт `tests/load_test.py`.

## Як запускати Python load-test

Спочатку API і PostgreSQL вже мають працювати через Docker:

```powershell
docker compose up --build -d
```

Потім у PowerShell активуй virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r tests\requirements.txt
```

Перед тестом скинь залишок:

```powershell
$body = @{ stock = 20000 } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/products/42/reset" -Method Post -ContentType "application/json" -Body $body
```

Запусти стабільний навчальний тест. Для домашньої машини краще почати не з `1000 RPS`, а з `300-500 RPS` і довшої тривалості:

```powershell
python tests\load_test.py --base-url http://127.0.0.1:8000 --rps 500 --duration 15 --concurrency 50 --timeout 5
```

Чому так:

- `--duration 15` дає більш спокійний і чесний результат, ніж 5 секунд.
- `--concurrency 50` не перевантажує Windows/Docker надто різко.
- `--timeout 5` дає backend більше часу відповісти під навантаженням.

Якщо комп'ютер починає сильно гальмувати, зменш параметри:

```powershell
python tests\load_test.py --base-url http://127.0.0.1:8000 --rps 200 --duration 15 --concurrency 30 --timeout 5
```

Якщо все стабільно, поступово піднімай:

```powershell
python tests\load_test.py --base-url http://127.0.0.1:8000 --rps 750 --duration 20 --concurrency 100 --timeout 5
```

Для спроби `1000 RPS`:

```powershell
python tests\load_test.py --base-url http://127.0.0.1:8000 --rps 1000 --duration 20 --concurrency 100 --timeout 5
```

## Як порівняти frontend RPS-тест і Python load-test

Щоб порівняння було чесним, використовуй однакові параметри.

### 1. Запусти Docker

```powershell
docker compose up --build -d
```

### 2. Скинь залишок перед frontend-тестом

У frontend постав `Новий залишок = 20000` і натисни `Скинути залишок`.

Або через PowerShell:

```powershell
$body = @{ stock = 20000 } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/products/42/reset" -Method Post -ContentType "application/json" -Body $body
```

### 3. Запусти frontend-тест

Наприклад:

```text
RPS = 1000
Тривалість = 5
Конкурентність = 50
Product ID = 42
Purchased count = 1
Timeout = 2000
```

Запиши такі значення:

- `successful_purchases`
- `stock_conflicts`
- `timeout_or_other_errors`
- `dropped_by_browser`
- `actual_rps`

### 4. Знову скинь залишок перед Python-тестом

Це обов'язково. Інакше Python-тест стартуватиме вже після списання товару frontend-тестом.

```powershell
$body = @{ stock = 20000 } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/products/42/reset" -Method Post -ContentType "application/json" -Body $body
```

### 5. Запусти Python-тест з подібними параметрами

```powershell
python tests\load_test.py --base-url http://127.0.0.1:8000 --rps 1000 --duration 5 --concurrency 50 --timeout 5
```

### 6. Порівняй результати

У frontend:

- `successful_purchases` відповідає успішним покупкам.
- `stock_conflicts` відповідає `409 Conflict`.
- `timeout_or_other_errors` відповідає помилкам запитів.
- `dropped_by_browser` показує, що браузер не зміг відправити частину запитів.

У Python:

- `Successful purchases` відповідає успішним покупкам.
- `Stock conflicts` відповідає `409 Conflict`.
- `Timeouts` відповідає таймаутам.
- `Other errors` відповідає іншим помилкам.
- `Dropped by load tester` відповідає запитам, які тестер не зміг поставити або дочекатися через власні обмеження.
- `Completed RPS` краще використовувати для порівняння з `actual_rps` у frontend.

Python-скрипт зазвичай точніший для benchmark, бо він не залежить від обмежень браузера, вкладки, рендера сторінки і JavaScript event loop. Frontend-тест корисний для навчання: він показує процес на екрані і допомагає зрозуміти, що відбувається.

## Що означає результат Python load-test

Приклад:

```text
Load test summary
========================================================
Status:                  FINISHED
Base URL:                http://127.0.0.1:8000
Endpoint:                POST /purchase
Product ID:              42
Purchased count:         1
--------------------------------------------------------
Target RPS:              500.00
Requested duration:      15.00s
Real duration:           15.42s
Target requests:         7500
Scheduled requests:      7501
Sent to API:             7480
Completed requests:      7480
Dropped by tester:       21 (0.28%)
--------------------------------------------------------
Successful purchases:    7480
Stock conflicts 409:     0
Timeouts:                0
Other errors:            0
Error rate:              0.00%
--------------------------------------------------------
Actual RPS:              485.08
Sent RPS:                485.08
Success RPS:             485.08
Average latency:         85.33 ms
P95 latency:             180.10 ms
HTTP status codes:
  200: 7480
```

Пояснення:

- `Status` — тест завершився сам або був зупинений через `Ctrl+C`.
- `Target RPS` — яку швидкість скрипт намагався створити.
- `Requested duration` — скільки секунд ми попросили генерувати навантаження.
- `Real duration` — скільки реально працював скрипт.
- `Target requests` — теоретична кількість запитів: `RPS * duration`.
- `Scheduled requests` — скільки запитів скрипт хотів створити.
- `Sent to API` — скільки запитів реально пішло в API.
- `Completed requests` — скільки запитів завершились відповіддю або помилкою.
- `Dropped by tester` — запити, які тестер не зміг відправити або дочекатися через власні обмеження.
- `Successful purchases` — успішні покупки.
- `Stock conflicts` — товару не вистачило, HTTP `409`.
- `Timeouts` — клієнт не дочекався відповіді.
- `Other errors` — інші помилки.
- `Error rate` — відсоток неуспішних завершених запитів.
- `Actual RPS` — скільки запитів реально завершувалось за секунду.
- `Sent RPS` — скільки запитів реально відправлялось за секунду.
- `Success RPS` — скільки успішних покупок було за секунду.
- `Average latency` — середній час відповіді API.
- `P95 latency` — 95% відповідей були швидші або рівні цьому значенню.

Якщо натиснути `Ctrl+C`, нова версія скрипта не повинна показувати великий traceback. Вона має надрукувати частковий підсумок і написати `Status: INTERRUPTED BY USER`.

## Чому тест може показувати різні результати

Це нормально.

Причини:

1. Кожен тест змінює базу і зменшує `stock`.
2. Якщо не скидати залишок, наступний тест отримає більше `409 Conflict`.
3. Docker Desktop використовує ресурси твого комп'ютера.
4. PostgreSQL блокує один і той самий ряд товару при оновленні.
5. Windows, браузер, VS Code і Docker можуть одночасно боротись за CPU та RAM.
6. `1000 RPS` на один товар — це важкий сценарій, бо всі запити оновлюють один ряд у базі.

## Чому термінал може “злітати” або поводитись дивно

Якщо запускати Docker так:

```powershell
docker compose up --build
```

контейнери пишуть логи прямо в цей термінал.

При навантажувальному тесті логів і активності стає багато. VS Code PowerShell terminal може перезапустити language service або закрити сесію.

Краще запускати так:

```powershell
docker compose up --build -d
```

Тоді Docker працює у фоні.

Логи дивись окремо тільки коли потрібно:

```powershell
docker compose logs --tail=80 api postgres
```

## Як перевірити базу напряму

Подивитись товари:

```powershell
docker compose exec postgres psql -U store_user -d store_db -c "SELECT * FROM products ORDER BY product_id;"
```

Скинути базу повністю:

```powershell
docker compose down -v
docker compose up --build -d
```

Команда `down -v` видаляє volume PostgreSQL. Після наступного запуску файл `db/init.sql` виконається заново.

## Що було зроблено при створенні проєкту

1. Створено папку `app` для FastAPI коду.
2. Додано `app/config.py` для читання `.env`.
3. Додано `app/db.py` для підключення до PostgreSQL через async pool.
4. Додано `app/main.py` з endpoint-ами.
5. Реалізовано `POST /purchase`.
6. Додано атомарне SQL-списання товару.
7. Додано `GET /products/{product_id}` для перегляду товару.
8. Додано `POST /products/{product_id}/reset` для скидання залишку.
9. Додано `GET /health`.
10. Створено `db/init.sql`.
11. Створено `Dockerfile`.
12. Створено `docker-compose.yml`.
13. Створено `.env` і `.env.example`.
14. Створено frontend для ручної перевірки.
15. Додано RPS-тест у frontend.
16. Створено Python load-test `tests/load_test.py`.
17. Описано запуск і перевірку в README.

## Короткий чекліст для здачі

1. Docker Desktop запущений.
2. Виконано:

```powershell
docker compose up --build -d
```

3. Перевірено:

```powershell
curl http://127.0.0.1:8000/health
```

4. Відкрито frontend:

```text
http://127.0.0.1:8000/
```

5. Через frontend зроблено ручну покупку.
6. Через frontend скинуто залишок.
7. Через frontend запущено невеликий RPS-тест.
8. Через Python-скрипт запущено окремий load-test.
9. Після тесту перевірено залишок товару.

## Якщо щось зависає

Не треба чекати 10 хвилин.

Якщо тест або термінал поводиться дивно:

1. Зупини тест кнопкою `Зупинити тест` у frontend або `Ctrl+C` у PowerShell.
2. Перевір контейнери:

```powershell
docker compose ps
```

3. Перевір health:

```powershell
curl http://127.0.0.1:8000/health
```

4. Подивись короткі логи:

```powershell
docker compose logs --tail=80 api postgres
```

5. Якщо треба, перезапусти:

```powershell
docker compose down
docker compose up --build -d
```

Для навчання краще починати з малих значень `RPS = 100`, `duration = 5`, `concurrency = 50`, а потім поступово збільшувати.
