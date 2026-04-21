<div align="center">

<a id="top"></a>

# AI-Assisted Application Configuration

**Dil &nbsp;·&nbsp; Language:** [**English**](#english) &nbsp;|&nbsp; [**Türkçe**](#turkce)

[![](https://img.shields.io/badge/stack-Flask-0d1117?logo=flask)](https://flask.palletsprojects.com/) [![](https://img.shields.io/badge/LLM-Ollama-0d1117?logo=ollama)](https://ollama.com/) [![](https://img.shields.io/badge/orchestration-Docker%20Compose-0d1117?logo=docker)](https://docs.docker.com/compose/) [![](https://img.shields.io/badge/validation-JSON%20Schema-0d1117)](https://json-schema.org/)

**Repo:** [github.com/memirutku/peakIntern](https://github.com/memirutku/peakIntern)

</div>

---

<a id="english"></a>

## English

**Natural language → validated config updates.** A small **Python microservice** stack that maps plain-English instructions to changes in JSON configuration, with **JSON Schema** validation and a **local LLM via Ollama** (no cloud models).

Originally built as a **case assignment for a Peak Games internship application**; published to demonstrate work with **Flask**, **Docker Compose**, **Ollama**, and **schema-driven configuration**.

---

### What you can ask for

Examples the bot understands:

- “set tournament service memory to 1024mb”
- “set GAME_NAME env to toyblast for matchmaking service”
- “lower cpu limit of chat service to %80”

The **bot** infers which app (`chat`, `tournament`, `matchmaking`) you mean, loads that app’s **schema** and **current values**, asks the LLM for an updated values document, validates it against the schema, and returns the result.

---

### Stack (short)

| Area        | Choices                                                         |
| ----------- | --------------------------------------------------------------- |
| Services    | Flask apps: `schema-server`, `values-server`, `bot-server`   |
| LLM         | Local **Ollama**; model configurable (default `llama3.2`)      |
| Validation  | **jsonschema** on LLM output                                    |
| Ops         | Docker per service, internal Docker network, `restart: unless-stopped` |
| Quality     | Per-request logging, health endpoints, retries on bad LLM output |

For **model choice, prompts, and trade-offs**, see [`INTERN.md`](./INTERN.md).

---

### Architecture

Three services, one responsibility each:

| Service           | Role                                                                         |
| ----------------- | ---------------------------------------------------------------------------- |
| **schema-server** | Serves JSON Schema per `app_name` (`GET /{app_name}`)                        |
| **values-server** | Serves current values JSON per `app_name` (`GET /{app_name}`)               |
| **bot-server**    | Public API: NL in → validated updated JSON out (`POST /message`)            |

Only **bot-server** exposes a host port (**5003**). Schema and values are reached from the bot over the Compose network.

---

### Request flow

1. Client posts `{ "input": "…" }` to **bot-server** `POST /message`.
2. Bot calls Ollama to determine the **target application name**.
3. Bot fetches **schema** and **values** from the other two services.
4. Bot calls Ollama again with schema + values + user text; expects **only** updated values JSON.
5. Bot validates against the schema, applies changes (with retries when output is invalid), returns JSON.

---

### Quick start

**Prerequisites**

- **Docker** with Compose v2 (`docker compose`)
- **Ollama** on the host with a pulled model, e.g.:

```bash
ollama pull llama3.2
```

**Run** (from the repo root):

```bash
docker compose up --build -d
```

**Configure Ollama (optional)** — Compose passes through environment (see `docker-compose.yml`):

| Variable             | Default                              | Meaning                          |
| -------------------- | ------------------------------------ | -------------------------------- |
| `OLLAMA_URL`         | `http://host.docker.internal:11434`  | Ollama API (host machine)         |
| `LLM_MODEL`          | `llama3.2`                          | Model name in Ollama              |
| `OLLAMA_NUM_PREDICT` | `4096`                              | Max tokens for completion         |

`extra_hosts: host.docker.internal:host-gateway` is set so the bot container can reach Ollama on Linux as well as macOS/Windows.

**Try it**

```bash
curl -X POST http://localhost:5003/message \
  -H "Content-Type: application/json" \
  -d '{"input": "set tournament service memory to 1024mb"}'
```

More examples:

```bash
curl -X POST http://localhost:5003/message \
  -H "Content-Type: application/json" \
  -d '{"input": "set GAME_NAME env to toyblast for matchmaking service"}'

curl -X POST http://localhost:5003/message \
  -H "Content-Type: application/json" \
  -d '{"input": "lower cpu limit of chat service to %80"}'
```

---

### HTTP API (reference)

**Bot service (host)**

| Method | Path       | Body                                  | Success                    |
| ------ | ---------- | ------------------------------------- | -------------------------- |
| `POST` | `/message` | `{ "input": "<natural language>" }` | `200` + updated values JSON |

**Schema & values (in-network; optional host exposure)** — Both expose `GET /health` and `GET /{app_name}` (e.g. `tournament`, `chat`, `matchmaking`). In the default Compose file, **ports 5001/5002 are not mapped** to the host—use `docker compose exec` or temporarily uncomment `ports` in `docker-compose.yml` for debugging.

---

### Repository layout

```text
├── bot-server/          # Flask, Ollama client, orchestration
├── schema-server/       # Serves *.schema.json
├── values-server/       # Serves *.value.json
├── data/
│   ├── schemas/         # chat, matchmaking, tournament schemas
│   └── values/          # current values per app
├── docker-compose.yml
├── INTERN.md            # Design decisions and deep dive
└── README.md
```

---

### Case requirements (summary)

The original brief asked for: all services in **Python**, **only local** LLM via **Ollama**, outputs **validated** against each app’s **JSON Schema**, and everything runnable with **`docker compose up`**. This repository implements that; extended reasoning lives in **`INTERN.md`**.

**[↑ Back to top](#top)**

---

<a id="turkce"></a>

## Türkçe

**Doğal dil → şemayla doğrulanmış yapılandırma güncellemeleri.** Düz İngilizce yönergeleri JSON yapılandırma değişikliklerine eşleyen küçük bir **Python mikro servis** yığını: **JSON Schema** doğrulaması ve **Ollama üzerinden yerel LLM** (bulut modelleri yok).

Başlangıçta **Peak Games staj başvurusu vaka çalışması** olarak hazırlandı; **Flask**, **Docker Compose**, **Ollama** ve **şemaya dayalı yapılandırma** ile çalışmayı göstermek için yayımlandı.

---

### Ne isteyebilirsiniz?

Botun anladığı örnekler:

- “set tournament service memory to 1024mb”
- “set GAME_NAME env to toyblast for matchmaking service”
- “lower cpu limit of chat service to %80”

**Bot**, hangi uygulamayı (`chat`, `tournament`, `matchmaking`) kastettiğinizi çıkarır, o uygulamanın **şemasını** ve **güncel değerlerini** yükler, LLM’den güncellenmiş değer belgesi ister, şemaya göre doğrular ve sonucu döner.

---

### Kısa yığın (stack)

| Alan        | Tercihler                                                                 |
| ----------- | ------------------------------------------------------------------------- |
| Servisler   | Flask: `schema-server`, `values-server`, `bot-server`                     |
| LLM         | Yerel **Ollama**; model yapılandırılabilir (varsayılan `llama3.2`)         |
| Doğrulama   | LLM çıktısında **jsonschema**                                             |
| Operasyon   | Servis başına Docker, iç Docker ağı, `restart: unless-stopped`            |
| Kalite      | İstek başına loglama, sağlık uç noktaları, hatalı LLM çıktısında yeniden deneme |

**Model seçimi, istemler ve ödünleşimler** için bkz. [`INTERN.md`](./INTERN.md).

---

### Mimari

Üç servis, her biri tek sorumluluk:

| Servis            | Rol                                                                          |
| ----------------- | ---------------------------------------------------------------------------- |
| **schema-server** | `app_name` başına JSON Schema sunar (`GET /{app_name}`)                      |
| **values-server** | `app_name` başına güncel değer JSON’u sunar (`GET /{app_name}`)             |
| **bot-server**    | Genel API: doğal dil girişi → doğrulanmış güncel JSON çıkışı (`POST /message`) |

Yalnızca **bot-server** host’ta port açar (**5003**). Şema ve değerler, bot tarafından Compose ağı üzerinden erişilir.

---

### İstek akışı

1. İstemci **bot-server** `POST /message` adresine `{ "input": "…" }` gönderir.
2. Bot, **hedef uygulama adını** belirlemek için Ollama’yı çağırır.
3. Bot diğer iki servisten **şema** ve **değerleri** alır.
4. Bot, şema + değerler + kullanıcı metniyle Ollama’yı tekrar çağırır; yanıtta **yalnızca** güncellenmiş değer JSON’u beklenir.
5. Bot çıktıyı şemaya göre doğrular, (geçersiz çıktıda yeniden denemelerle) değişiklikleri uygular, JSON döner.

---

### Hızlı başlangıç

**Gereksinimler**

- Compose v2 ile **Docker** (`docker compose`)
- Model çekilmiş **Ollama** (host’ta), ör.:

```bash
ollama pull llama3.2
```

**Çalıştırma** (depo kökünden):

```bash
docker compose up --build -d
```

**Ollama yapılandırması (isteğe bağlı)** — Compose ortam değişkenlerini geçirir (ayrıntı `docker-compose.yml`):

| Değişken              | Varsayılan                           | Anlamı                           |
| --------------------- | ------------------------------------ | -------------------------------- |
| `OLLAMA_URL`          | `http://host.docker.internal:11434`  | Ollama API (host makine)         |
| `LLM_MODEL`           | `llama3.2`                          | Ollama’daki model adı            |
| `OLLAMA_NUM_PREDICT`  | `4096`                              | Tamamlama için maksimum token    |

`extra_hosts: host.docker.internal:host-gateway` sayesinde bot konteyneri Ollama’ya Linux’ta da macOS/Windows’taki gibi ulaşabilir.

**Deneme**

```bash
curl -X POST http://localhost:5003/message \
  -H "Content-Type: application/json" \
  -d '{"input": "set tournament service memory to 1024mb"}'
```

Diğer örnekler:

```bash
curl -X POST http://localhost:5003/message \
  -H "Content-Type: application/json" \
  -d '{"input": "set GAME_NAME env to toyblast for matchmaking service"}'

curl -X POST http://localhost:5003/message \
  -H "Content-Type: application/json" \
  -d '{"input": "lower cpu limit of chat service to %80"}'
```

---

### HTTP API (özet)

**Bot servisi (host)**

| Metod  | Yol        | Gövde                                 | Başarı                     |
| ------ | ---------- | ------------------------------------- | -------------------------- |
| `POST` | `/message` | `{ "input": "<doğal dil metni>" }`   | `200` + güncellenmiş değer JSON’u |

**Şema ve değerler (ağ içi; host’a açma isteğe bağlı)** — İkisi de `GET /health` ve `GET /{app_name}` sunar (ör. `tournament`, `chat`, `matchmaking`). Varsayılan Compose’ta **5001/5002 portları host’a map edilmez**—hata ayıklama için `docker compose exec` kullanın veya `docker-compose.yml` içinde `ports` satırlarını geçici açın.

---

### Depo yapısı

```text
├── bot-server/          # Flask, Ollama istemcisi, orkestrasyon
├── schema-server/       # *.schema.json sunar
├── values-server/       # *.value.json sunar
├── data/
│   ├── schemas/         # chat, matchmaking, tournament şemaları
│   └── values/          # uygulama başına güncel değerler
├── docker-compose.yml
├── INTERN.md            # Tasarım kararları ve ayrıntılı anlatım
└── README.md
```

---

### Vaka gereksinimleri (özet)

Orijinal özet: tüm servisler **Python**, LLM yalnızca **Ollama** ile **yerel**, çıktılar her uygulamanın **JSON Schema**’sına göre **doğrulanmış** ve her şey **`docker compose up`** ile çalışır. Bu depo bunu uygular; genişletilmiş açıklamalar **`INTERN.md`** dosyasındadır.

**[↑ Başa dön](#top)**
