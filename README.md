# FastAPI Backend Store: навантажений backend магазину

Цей проєкт показує, як backend магазину обробляє багато одночасних покупок одного товару. У системі є FastAPI API, PostgreSQL, Redis, RabbitMQ, Locust, Redis Commander, RabbitMQ Management UI і невеликий frontend для ручної перевірки.

Головна навчальна ідея: товар не має продаватися “в мінус”, навіть якщо багато користувачів одночасно натискають купити.

## Чого навчає цей проєкт

Проєкт навчає запускати backend-стенд через Docker, працювати з FastAPI endpoint-ами, перевіряти стан PostgreSQL, Redis і RabbitMQ, запускати RPS-тести через Locust і читати результати навантаження.

Викладач дав саме такий тип завдання, бо тут є реальна backend-проблема: одночасний доступ до обмеженого ресурсу. У нашому випадку ресурс — це `stock` товару в базі.

## Архітектура

| Частина | Для чого потрібна |
| --- | --- |
| FastAPI | Приймає HTTP-запити: покупка, перегляд товару, healthcheck |
| PostgreSQL | Зберігає товар і залишок `stock` |
| Redis | Зберігає швидкі навчальні значення: лічильник успішних покупок і останню покупку |
| RabbitMQ | Зберігає події успішних покупок у черзі `purchase_events` |
| Redis Commander | Дає подивитися ключі Redis у браузері |
| RabbitMQ Management UI | Дає подивитися черги RabbitMQ у браузері |
| Locust | Генерує навантаження і показує RPS, latency, failures |
| Frontend | Дає вручну купити товар, скинути залишок і запустити простий браузерний RPS-тест |
| Nginx | Приймає зовнішні HTTP-запити на `127.0.0.1:8000` і проксіює їх у FastAPI |

## Що було оптимізовано в коді

Початково майже вся FastAPI-логіка була в одному файлі `app/main.py`: схеми, endpoint-и, SQL-запити, middleware, startup/shutdown і бізнес-логіка покупки. Це працювало, але для production-підходу такий файл швидко стає важко підтримувати.

Після оптимізації `main.py` став коротким:

```python
from app.core.app_factory import create_app

app = create_app()
```

Тепер код розділений за відповідальністю:

| Папка або файл | Для чого |
| --- | --- |
| `app/api/routes/` | HTTP endpoint-и FastAPI |
| `app/schemas/` | Pydantic input/output моделі |
| `app/repositories/` | SQL-запити до PostgreSQL |
| `app/services/` | Бізнес-логіка покупки |
| `app/core/` | Створення застосунку і lifecycle startup/shutdown |
| `app/middleware/` | CORS і frontend cache-control |
| `nginx/default.conf` | Reverse proxy перед API |

`nginx/default.conf` — це конфіг Nginx, який каже: приймай запити з браузера на порті `8000` і передавай їх усередину Docker-мережі в сервіс `api:8000`. У production часто роблять саме так: зовнішній клієнт не ходить напряму в uvicorn-процес, а заходить через reverse proxy.

Що стало краще:

- `main.py` більше не перевантажений.
- Роути можна читати окремо від SQL.
- SQL-логіка винесена в repository-шар.
- Бізнес-логіка покупки винесена в service-шар.
- Middleware не змішаний з endpoint-ами.
- Startup/shutdown підключення до PostgreSQL, Redis і RabbitMQ винесені в `lifespan`.
- Redis/RabbitMQ-подія після покупки запускається як background task, тому відповідь `/purchase` не чекає зайву інтеграційну роботу.

Важливе рішення: саме списання `stock` залишилось синхронним відносно HTTP-запиту. Це правильно для цього завдання, бо відповідь `{"status": "success"}` має означати, що товар уже реально списаний у PostgreSQL. RabbitMQ тут використовується для події після успішної покупки, а не як заміна атомарного SQL-оновлення.

## Що було оптимізовано в Docker

Зовнішній порт `8000` тепер належить Nginx:

```text
Browser / Locust / curl -> Nginx :8000 -> FastAPI api:8000
```

FastAPI більше не відкриває порт напряму назовні, а доступний усередині docker compose мережі.

Кількість uvicorn worker-ів винесена в `.env`:

```env
API_WORKERS=5
```

У `Dockerfile` це використовується так:

```text
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${API_WORKERS}
```

Що стало краще:

- можна тестувати `API_WORKERS=2`, `API_WORKERS=4`, `API_WORKERS=5` без зміни Dockerfile;
- кілька worker-процесів краще використовують CPU;
- Nginx дає більш production-like вхідну точку;
- `api` має healthcheck, тому Nginx і Locust стартують тільки після готовності FastAPI.

Обмеження: збільшувати worker-и нескінченно не можна. Кожен worker відкриває власний pool до PostgreSQL і власні підключення до Redis/RabbitMQ. Якщо worker-ів забагато, вузьким місцем стане вже база або CPU.

## Що ще можна оптимізувати пізніше

Можливі наступні кроки:

- додати окремий consumer для RabbitMQ, який буде читати `purchase_events`;
- винести важкі післяпокупкові дії в Celery або окремий worker-сервіс;
- додати метрики Prometheus/Grafana;
- оптимізувати PostgreSQL під реальні запити й індекси;
- розглядати partitioning тільки тоді, коли зʼявиться велика таблиця історії покупок, а не для маленької таблиці `products`;
- для реального горизонтального масштабування запускати кілька API-контейнерів і налаштовувати Nginx upstream під кілька backend-ів.

## Як працює покупка

Endpoint:

```text
POST /purchase
```

Приклад input:

```json
{
  "user_id": 12345,
  "product_id": 42,
  "purchased_count": 1
}
```

Головний SQL-запит:

```sql
UPDATE products
SET stock = stock - $1
WHERE product_id = $2
  AND stock >= $1
RETURNING product_id
```

Цей запит важливий, бо перевірка залишку і списання виконуються однією атомарною операцією. Якщо товару вистачає, PostgreSQL списує залишок. Якщо товару не вистачає, залишок не змінюється, а API повертає `409 Conflict`.

Після успішної покупки API також:

- збільшує Redis-ключ `store:purchases:success`;
- записує останню покупку в Redis-ключ `store:purchases:last`;
- публікує подію покупки в RabbitMQ queue `purchase_events`.

## Запуск проєкту

Спочатку відкрий Docker Desktop і дочекайся, поки Docker Engine запуститься.

Перейди в папку проєкту:

```powershell
cd D:\VSCode_Python_Projects_26\fastapi_backend_store_6
```

Зібрати образи:

```powershell
docker compose build
```

Запустити всі сервіси у фоні:

```powershell
docker compose up -d
```

Перевірити стан контейнерів:

```powershell
docker compose ps
```

Очікувано мають працювати:

- `api`;
- `postgres`;
- `redis`;
- `redis-commander`;
- `rabbitmq`;
- `locust`.

## Адреси сервісів

| Сервіс | Адреса | Що там робити |
| --- | --- | --- |
| Frontend | http://127.0.0.1:8000/frontend/ | Купити товар, скинути залишок, запустити браузерний RPS-тест |
| Swagger API docs | http://127.0.0.1:8000/docs | Подивитися і протестувати endpoint-и |
| Healthcheck | http://127.0.0.1:8000/health | Перевірити, що API живий |
| Dependencies | http://127.0.0.1:8000/system/dependencies | Перевірити Redis і RabbitMQ |
| Locust | http://127.0.0.1:8089 | Запустити графічний RPS-тест |
| Redis Commander | http://127.0.0.1:8081 | Подивитися ключі Redis |
| RabbitMQ UI | http://127.0.0.1:15672 | Подивитися черги RabbitMQ |

RabbitMQ login:

```text
guest / guest
```

## Перевірка після запуску

Перевірити API:

```powershell
curl http://127.0.0.1:8000/health
```

Очікувано:

```json
{"status":"ok"}
```

Перевірити Redis і RabbitMQ:

```powershell
curl http://127.0.0.1:8000/system/dependencies
```

Приклад відповіді:

```json
{
  "redis": {
    "connected": true,
    "successful_purchases_recorded": 105295,
    "last_purchase": {
      "user_id": 105295,
      "product_id": 42,
      "purchased_count": 1,
      "created_at": "2026-05-18T14:22:15.357034+00:00"
    }
  },
  "rabbitmq": {
    "connected": true,
    "queue": "purchase_events",
    "messages_ready": 20000,
    "consumers": 0
  }
}
```

## Робота з frontend

Відкрий:

```text
http://127.0.0.1:8000/frontend/
```

![Frontend RPS](docs/screenshots/frontend-rps.png)

Frontend у цьому проєкті написаний на звичайних `HTML + CSS + JavaScript`. Вона потрібна не як production UI, а як навчальна панель, щоб бачити покупку, залишок і простий браузерний RPS-тест.

У верхньому блоці показано `API workers`. Це кількість uvicorn worker-процесів у контейнері API. Їх не можна змінити кнопкою на сторінці, бо це налаштування Docker-запуску. Щоб змінити worker-и:

```powershell
# у .env змінити API_WORKERS, наприклад API_WORKERS=5
docker compose up --build -d
```

Більше worker-ів може підняти RPS, але також збільшує кількість підключень до PostgreSQL, Redis і RabbitMQ. Тому для локального тесту 5 worker-ів — контрольований максимум.

На сторінці worker-и тільки показуються. Кнопки “змінити worker-и” немає, бо worker-и створюються при старті контейнера. Тобто це не runtime-поле форми, а Docker-налаштування.

### Найпростіший правильний сценарій через frontend

1. Відкрий `http://127.0.0.1:8000/frontend/`.
2. У полі `Новий залишок` постав `20000`.
3. Натисни `Скинути залишок`.
4. Натисни `Оновити залишок` і переконайся, що видно `20000`.
5. Натисни пресет `Безпечний тест`.
6. Натисни `Запустити RPS-тест`.
7. Подивись `Успішно`, `409 Conflict`, `Timeout/Error`, `Dropped`, `Фактичний RPS`.

Для перевірки автоматичної зупинки:

1. У полі `Новий залишок` постав `5`.
2. Натисни `Скинути залишок`.
3. Запусти будь-який RPS-тест.
4. Тест має швидко зупинитися після появи `409 Conflict`.

Це означає, що товар закінчився, API правильно заборонив покупку понад залишок, а тест зупинився.

### Ручна перевірка

Поля:

- `User ID` — id користувача. Для тесту можна залишати будь-яке додатне число.
- `Product ID` — id товару. У цьому проєкті основний тестовий товар має `product_id = 42`.
- `Purchased count` — скільки одиниць товару купити за один запит.

Кнопки:

- `Купити` — виконує `POST /purchase`.
- `Оновити залишок` — виконує `GET /products/42`.
- `Скинути залишок` — виконує `POST /products/42/reset`.

Перед RPS-тестом корисно поставити великий залишок, наприклад:

```text
Новий залишок = 20000
```

Якщо залишок буде малий, тест швидко почне отримувати `409 Conflict`, бо товар закінчиться.

### RPS-тест у frontend

Frontend RPS-тест має тільки три головні поля:

- `RPS` — скільки запитів на секунду браузер намагається створити.
- `Тривалість, сек` — скільки секунд триватиме тест.
- `Конкурентність` — скільки запитів можуть одночасно очікувати відповідь.

Тест бере `Product ID` з блоку ручної перевірки і списує по `1` одиниці за запит. Timeout у браузерному тесті фіксований: `5000 ms`.

Пресети:

| Пресет | Значення | Коли використовувати |
| --- | --- | --- |
| Безпечний тест | `50 RPS`, `10 сек`, `concurrency 10` | перша перевірка |
| Середній тест | `100 RPS`, `10 сек`, `concurrency 25` | нормальна навчальна перевірка |
| Сильний тест | `300 RPS`, `15 сек`, `concurrency 50` | коли Docker і API стабільно працюють |

Не починай з `1000 RPS` у браузері. Браузер не є професійним генератором навантаження, тому він може не встигати створювати всі запити. Для `1000 RPS` краще використовувати Locust або `tests/load_test.py`.

Метрики:

- `Статус` — `idle`, `running`, `draining`, `finished`, `stopped`.
- `Заплановано` — скільки запитів браузер спробував створити.
- `Завершено` — скільки запитів уже завершилися.
- `Успішно` — скільки покупок отримали `200 OK`.
- `409 Conflict` — скільки покупок не пройшли через нестачу товару.
- `Timeout/Error` — скільки запитів завершилися timeout або іншою помилкою.
- `Dropped` — скільки запитів браузер не зміг відправити через власні обмеження.
- `Фактичний RPS` — реальна швидкість завершених запитів.
- `In-flight` — скільки запитів зараз очікують відповідь.

Як читати твій приклад:

```text
RPS = 1000
Тривалість = 5
Конкурентність = 50
Dropped = 4674
Фактичний RPS = 59
```

Це означає: я попросила браузер створити приблизно `5000` запитів за 5 секунд, але браузер зміг реально відправити тільки частину. `Dropped` — це не обовʼязково помилка backend. Це означає, що саме браузерний генератор не встиг подати таке навантаження.

Чому тест іноді завершується за 1-2 секунди:

- залишок товару був малий;
- перші запити швидко списали весь `stock`;
- наступний запит отримав `409 Conflict`;
- frontend зупинив тест, бо далі перевіряти покупки вже немає сенсу.

Якщо хочеш, щоб тест тривав повні `10` або `15` секунд, перед запуском постав великий залишок: `20000`, `50000` або більше.

Якщо хочеш побачити стабільний результат у frontend, починай так:

```text
RPS = 50 або 100
Тривалість = 10
Конкурентність = 10 або 25
Новий залишок = 20000
```

Frontend-тест зручний для навчання, але точніший benchmark краще робити через Locust.

## Locust у браузері

Відкрий:

```text
http://127.0.0.1:8089
```

Якщо ти змінювала `tests/locustfile.py`, перезапусти Locust, щоб браузерний UI підхопив новий код:

```powershell
docker compose restart locust
```

Сам тест запускається в браузері кнопкою `Start swarming`.

Якщо після `docker compose restart locust` у терміналі майже нічого не відбувається, це нормально. Для перевірки стану виконай:

```powershell
docker compose ps locust
```

Якщо бачиш `Up`, відкрий або онови сторінку:

```text
http://127.0.0.1:8089
```

Для тесту можна ввести:

```text
Number of users = 100
Ramp up = 20
Host = http://api:8000
```

Потім натисни `Start swarming`.

Поля Locust UI:

| Поле | Що вводити | Для чого |
| --- | --- | --- |
| Number of users | `10`, `50`, `100` | скільки віртуальних користувачів створити |
| Ramp up | `5`, `10`, `20` | як швидко додавати користувачів за секунду |
| Host | `http://api:8000` | адреса API всередині Docker-мережі |

Як працювати правильно:

1. Скинь залишок товару на велике число, якщо хочеш довгий тест.
2. Відкрий Locust UI.
3. Введи `Number of users`, `Ramp up`, `Host`.
4. Натисни `Start swarming`.
5. Дивись вкладки `Statistics` і `Charts`.
6. Натисни `Stop`, якщо хочеш завершити тест вручну.

Якщо ти поставив `stock = 5`, Locust зупиниться дуже швидко. Це очікувано: товар закінчився майже одразу. Для графіків і нормального RPS-тесту став `stock = 20000` або `50000`.

Якщо Locust у браузері “ніби один раз запустився, а потім не працює”:

1. Перевір, чи тест не залишився у стані `STOPPED`.
2. Натисни `NEW`, якщо хочеш почати новий запуск з чистої форми.
3. Постав великий `stock`, якщо хочеш довший тест.
4. Натисни `Start swarming` ще раз.
5. Якщо ти змінюеш `locustfile.py`, виконай `docker compose restart locust` і онови сторінку браузера.

Locust не зупиняється тільки тому, що `stock` малий, якщо у коді сценарію не написано таку логіку. У цьому проєкті логіка вже додана: перший `409 Conflict` позначається як `/purchase [out_of_stock_409]`, після чого тест зупиняється.

![Locust Charts](docs/screenshots/locust-charts.png)

У поточному сценарії Locust покупки розділені на два зрозумілі рядки статистики:

- `/purchase [success]` — успішні покупки з HTTP `200`;
- `/purchase [out_of_stock_409]` — товар закінчився, API повернув HTTP `409 Conflict`.

Коли Locust вперше отримує `409 Conflict`, тест автоматично зупиняється. Це зроблено спеціально для навчальної перевірки: якщо товар закінчився, далі навантажувати endpoint покупками вже не має сенсу, бо система правильно захищає склад від відʼємного залишку.


### Що означають графіки Locust

`Total Requests per Second`:

- зелена лінія `RPS` показує, скільки запитів на секунду обробляється;
- червона лінія `Failures/s` показує, скільки помилок за секунду;
- якщо червона лінія біля нуля, тест проходить без помилок.

`Response Times (ms)`:

- `50th percentile` — типовий час відповіді для половини запитів;
- `95th percentile` — 95% запитів були не повільніші за це значення;
- якщо 95th percentile різко росте, система починає відповідати повільніше під навантаженням.

`Number of Users`:

- показує, скільки віртуальних користувачів Locust зараз створив;
- на скріншоті видно, що кількість користувачів дійшла до 100 і трималась стабільно.

`Status STOPPED` означає, що тест уже завершено, а графіки показують результат останнього запуску.

## Locust у терміналі

Команда, яку було запущено:

```powershell
docker compose run --rm -T locust -f /mnt/locust/locustfile.py --host http://api:8000 --headless -u 100 -r 20 -t 30s --only-summary
```

Для короткої перевірки автоматичної зупинки, коли товар закінчився:

```powershell
$body = @{ stock = 5 } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/products/42/reset" -Method Post -ContentType "application/json" -Body $body
docker compose run --rm -T locust -f /mnt/locust/locustfile.py --host http://api:8000 --headless -u 10 -r 10 -t 30s --only-summary
```

Очікувана ознака правильного результату:

```text
Stock is depleted: received 409 Conflict. Stopping Locust test.
POST /purchase [out_of_stock_409]
```

Навіть якщо в команді стоїть `-t 30s`, тест має завершитися раніше, бо товар закінчився.

Для нормального RPS-тесту через Locust headless:

```powershell
$body = @{ stock = 50000 } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/products/42/reset" -Method Post -ContentType "application/json" -Body $body
docker compose run --rm -T locust -f /mnt/locust/locustfile.py --host http://api:8000 --headless -u 100 -r 20 -t 30s --only-summary
```

У цьому режимі результат друкується в терміналі, бо використовується `--headless`.

Що означають параметри:

| Параметр | Значення |
| --- | --- |
| `--rm` | видалити тимчасовий контейнер Locust після завершення |
| `-T` | не відкривати інтерактивний pseudo-TTY |
| `-f /mnt/locust/locustfile.py` | файл сценарію Locust |
| `--host http://api:8000` | тестувати API всередині docker compose мережі |
| `--headless` | запуск без браузерного UI |
| `-u 100` | 100 віртуальних користувачів |
| `-r 20` | додавати 20 користувачів за секунду |
| `-t 30s` | тест триває 30 секунд |
| `--only-summary` | показати тільки фінальну таблицю |

### Твій результат Locust

```text
Type     Name                          # reqs   # fails   Avg   Min   Max   Med   req/s
GET      /products/{product_id}          1465   0(0.00%)   109     8   410   100    49.18
POST     /purchase                      14734   0(0.00%)   132     7   517   120   494.62
GET      /system/dependencies            1482   0(0.00%)   155    12   815   140    49.75
Aggregated                              17681   0(0.00%)   132     7   815   120   593.55
```

Пояснення:

- `# reqs` — скільки запитів зробив Locust.
- `# fails` — скільки запитів завершилися помилкою.
- `Avg` — середній час відповіді в мілісекундах.
- `Min` — найшвидша відповідь.
- `Max` — найповільніша відповідь.
- `Med` — медіана, типовий час відповіді.
- `req/s` — requests per second.

Найважливіший результат:

```text
Aggregated: 17681 requests, 0 failures, 593.55 req/s
```

Це означає, що за 30 секунд сценарій виконав `17681` HTTP-запит, помилок не було, а загальна швидкість була приблизно `593.55 RPS`.

Для основного endpoint:

```text
POST /purchase: 14734 requests, 0 failures, 494.62 req/s
```

Це означає, що саме покупки проходили зі швидкістю приблизно `495 RPS`, без помилок.

### Percentiles

```text
POST /purchase:
50%  = 120 ms
95%  = 250 ms
99%  = 380 ms
100% = 520 ms
```

Це означає:

- половина покупок відповідала до `120 ms`;
- 95% покупок відповідали до `250 ms`;
- 99% покупок відповідали до `380 ms`;
- найповільніша покупка відповідала приблизно `520 ms`.

### CPU warning

Locust показав:

```text
CPU usage above 90%!
```

Це означає, що машина, яка генерує навантаження, була сильно завантажена. Через це результати можуть бути обмежені не тільки FastAPI/PostgreSQL, а ще й можливостями комп’ютера або Docker Desktop.

Навчальний висновок: якщо CPU генератора навантаження вище 90%, то для дуже точного benchmark треба запускати Locust distributed або на окремій машині. Для навчального проєкту цей результат достатній: `0% failures` і майже `495 RPS` для покупок.

## Redis Commander

Відкрий:

```text
http://127.0.0.1:8081
```

![Redis Commander](docs/screenshots/redis-commander-last-purchase.png)

На скріншоті видно ключ:

```text
store:purchases:last
```

Що означають поля:

- `Key: store:purchases:last` — ключ Redis, у якому збережено останню успішну покупку.
- `TTL: -1` — ключ не має автоматичного часу видалення.
- `Type: String` — значення збережено як Redis string.
- JSON у полі значення — дані останньої покупки.

Приклад:

```json
{
  "user_id": 105295,
  "product_id": 42,
  "purchased_count": 1,
  "created_at": "2026-05-18T14:22:15.357034+00:00"
}
```

Що це доводить:

- API після успішної покупки реально записує дані в Redis.
- Redis можна використовувати для швидких лічильників, кешу або короткого стану системи.
- `store:purchases:last` допомагає швидко побачити, яка покупка була останньою.

Другий важливий ключ:

```text
store:purchases:success
```

Це лічильник успішних покупок. Він збільшується після кожного успішного `POST /purchase`.

## RabbitMQ Management UI

Відкрий:

```text
http://127.0.0.1:15672
```

Логін:

```text
guest / guest
```

![RabbitMQ Queue](docs/screenshots/rabbitmq-queue.png)

На скріншоті відкрита вкладка `Queues and Streams`.

Що означають поля:

| Поле | Значення для проєкту |
| --- | --- |
| `Virtual host /` | Стандартний простір RabbitMQ |
| `Name purchase_events` | Черга, куди API записує події успішних покупок |
| `Type classic` | Звичайна класична RabbitMQ queue |
| `Features D` | Durable queue, черга переживає перезапуск RabbitMQ |
| `State running` | Черга активна і працює |
| `Ready 20,000` | 20 000 повідомлень лежать у черзі й готові до читання |
| `Unacked 0` | Немає повідомлень, які consumer взяв, але ще не підтвердив |
| `Total 20,000` | Усього в черзі 20 000 повідомлень |
| `incoming 0.00/s` | Зараз нові повідомлення не надходять |
| `deliver / get 0.00/s` | Зараз ніхто не читає повідомлення |
| `ack 0.00/s` | Зараз ніхто не підтверджує обробку повідомлень |

Висновок по RabbitMQ:

API успішно створює події покупок і складає їх у чергу `purchase_events`. Оскільки в проєкті немає окремого consumer-сервісу, повідомлення накопичуються в `Ready`. Це нормально для навчального стенду: ми бачимо, що producer працює.

У production зазвичай додають consumer, який читає такі події і робить додаткову роботу: надсилає email, пише аналітику, оновлює CRM або формує чек.

## Консольний Python RPS-тест

Окрім Locust, є тест:

```powershell
python tests\load_test.py --base-url http://127.0.0.1:8000 --rps 500 --duration 15 --concurrency 50 --timeout 5
```

Перед першим запуском встанови залежності саме в активне virtual environment:

```powershell
python -m pip install -r tests\requirements.txt
```

Важливо: `load_test.py` не запускається через `pytest`. Це окремий скрипт. Правильний запуск:

```powershell
python tests\load_test.py --base-url http://127.0.0.1:8000 --rps 500 --duration 15 --concurrency 50 --timeout 5
```

`pytest` у цьому проєкті запускає тільки unit/sanity-тести:

```powershell
python -m pip install -r tests\requirements.txt
python -m pytest
```

Якщо бачиш `ModuleNotFoundError: No module named 'httpx'`, це означає, що залежності для тестів не встановлені в активний Python. Виконай:

```powershell
python -m pip install -r tests\requirements.txt
```

Перед тестом бажано скинути залишок:

```powershell
$body = @{ stock = 20000 } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/products/42/reset" -Method Post -ContentType "application/json" -Body $body
```

Цей тест корисний, коли треба швидко перевірити API без Locust UI.

## Корисні команди керування проєктом

### Запуск

```powershell
docker compose build
docker compose up -d
docker compose ps
```

### Перезапуск після змін у коді

```powershell
docker compose up --build -d
```

### Подивитися логи

Усі сервіси:

```powershell
docker compose logs --tail=80
```

Тільки API:

```powershell
docker compose logs --tail=80 api
```

API, Redis і RabbitMQ:

```powershell
docker compose logs --tail=80 api redis rabbitmq
```

### Зупинити проєкт без видалення даних

```powershell
docker compose down
```

Це зупиняє контейнери, але volume з PostgreSQL, Redis і RabbitMQ залишаються.

### Повністю зупинити і очистити дані

```powershell
docker compose down -v
```

Це видаляє volumes:

- `postgres_data`;
- `redis_data`;
- `rabbitmq_data`.

Після цього при наступному запуску база PostgreSQL створиться заново з `db/init.sql`.

### Зупинити тільки один сервіс

```powershell
docker compose stop locust
docker compose stop redis-commander
docker compose stop rabbitmq
```

### Запустити тільки один сервіс назад

```powershell
docker compose up -d locust
docker compose up -d redis-commander
docker compose up -d rabbitmq
```

### Перезапустити API

```powershell
docker compose restart api
```

### Перевірити health API

```powershell
curl http://127.0.0.1:8000/health
```

### Перевірити залежності API

```powershell
curl http://127.0.0.1:8000/system/dependencies
```

### Подивитися товар

```powershell
curl http://127.0.0.1:8000/products/42
```

### Скинути залишок товару

```powershell
$body = @{ stock = 20000 } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/products/42/reset" -Method Post -ContentType "application/json" -Body $body
```

### Зайти в PostgreSQL

```powershell
docker compose exec postgres psql -U store_user -d store_db
```

Подивитися товари:

```sql
SELECT * FROM products ORDER BY product_id;
```

### Перевірити Redis через CLI

```powershell
docker compose exec redis redis-cli ping
docker compose exec redis redis-cli keys "store:*"
docker compose exec redis redis-cli get store:purchases:success
docker compose exec redis redis-cli get store:purchases:last
```

Очистити Redis:

```powershell
docker compose exec redis redis-cli FLUSHDB
```

### Перевірити RabbitMQ container

```powershell
docker compose exec rabbitmq rabbitmq-diagnostics ping
docker compose exec rabbitmq rabbitmqctl list_queues name messages_ready messages_unacknowledged consumers
```

Очистити чергу `purchase_events`:

```powershell
docker compose exec rabbitmq rabbitmqctl purge_queue purchase_events
```

### Запустити Locust headless

```powershell
docker compose run --rm -T locust -f /mnt/locust/locustfile.py --host http://api:8000 --headless -u 100 -r 20 -t 30s --only-summary
```

### Зупинити завислий тест

У терміналі натисни:

```text
Ctrl + C
```

Якщо після цього залишився тимчасовий контейнер:

```powershell
docker compose ps -a
docker compose down
```

## Коли щось не працює

1. Перевір, що Docker Desktop запущений.
2. Перевір контейнери:

```powershell
docker compose ps
```

3. Перевір API:

```powershell
curl http://127.0.0.1:8000/health
```

4. Перевір Redis і RabbitMQ:

```powershell
curl http://127.0.0.1:8000/system/dependencies
```

5. Подивись логи:

```powershell
docker compose logs --tail=80 api redis rabbitmq
```

6. Якщо треба повністю почати заново:

```powershell
docker compose down -v
docker compose up --build -d
```

## Навчальний висновок

Цей проєкт показав повний шлях backend-розробника: написати API, підключити базу, запустити все через Docker, додати Redis і RabbitMQ, перевірити систему через frontend і Locust, а потім правильно прочитати результати.

Головні висновки:

- PostgreSQL відповідає за коректний залишок товару.
- FastAPI приймає покупки і повертає зрозумілі HTTP-відповіді.
- Redis швидко показує лічильники і останню покупку.
- RabbitMQ накопичує події покупок для майбутньої обробки.
- Locust показує, скільки RPS витримує система і як росте latency.
- `0% failures` у твоєму Locust-тесті означає, що API стабільно відповідав під заданим навантаженням.
- Попередження CPU вище 90% означає, що навантаження вже впирається у ресурси комп’ютера.
- Найважливіше: після навантаження `stock` не має ставати від’ємним.

Завдяки цьому проєкту я навчилась не тільки запускати backend, а й аналізувати його поведінку під навантаженням: дивитися RPS, latency, failures, черги RabbitMQ, ключі Redis і робити технічний висновок по роботі системи.
