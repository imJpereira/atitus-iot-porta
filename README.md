# atitus-iot-porta

Stack e convenções em [AGENTS.md](AGENTS.md).

## Como rodar

Pré-requisitos: [uv](https://docs.astral.sh/uv/) e Python 3.14+.

```bash
git clone https://github.com/imJpereira/atitus-iot-porta.git
cd atitus-iot-porta
```

### 1. Backend + frontend (computador/servidor)

1. Instale as dependências:

   ```bash
   uv sync
   ```

2. Copie o exemplo de variáveis e defina `PI_API_KEY` e `SECRET_KEY` (o Flask não lê o `.env` sozinho; exporte no shell):

   ```bash
   cp .env.example .env
   export PI_API_KEY=minha-chave SECRET_KEY=outra-chave
   ```

3. Crie o usuário administrador (pede a senha; ou use `ADMIN_PASSWORD`):

   ```bash
   uv run flask --app api create-admin admin
   ```

4. Suba a aplicação:

   ```bash
   uv run flask --app api run --debug
   ```

5. Abra <http://127.0.0.1:5000> e faça login com o usuário criado.

O banco SQLite é criado em `data/app.db`. Testes: `uv run pytest`.

### 2. Raspberry Pi (controle de acesso)

1. Monte o circuito conforme [Hardware](#hardware-raspberry-pi) e habilite o SPI (`sudo raspi-config` → *Interface Options* → *SPI*).
2. Instale as dependências da Pi:

   ```bash
   uv sync --group rasp
   ```

3. Configure o `.env` com `API_BASE_URL` (URL do backend) e `PI_API_KEY` **igual** ao do backend.
4. Teste o hardware e inicie o controle de acesso:

   ```bash
   uv run python rasp/test_hardware.py
   uv run python -m rasp.access
   ```

5. No frontend, cadastre colaboradores e vincule a tag RFID de cada um.

Rotas administrativas (`/api/employees`, `GET /api/events*`, `/api/export/*`) exigem login em `POST /api/auth/login`; a Raspberry Pi usa só `X-API-Key`.

## Tag RFID

- `rfid_tag` é opcional e única. Vincule, troque ou remova com `PATCH /api/employees/<id>`; `null` desvincula.
- Ao salvar, a tag é normalizada com `strip().upper()` (`" aa:bb "` vira `"AA:BB"`). Qualquer string não vazia vale; não há regex.
- Tag já usada por outro colaborador responde 409 `{"error": "rfid_tag already exists", "owner": {"id", "name", "registration_id"}}`.
- `GET /api/sync/employees` (chave da Pi) lista só colaboradores com tag, inclusive inativos; a Pi decide por `is_active` e `has_room_access`. Tag trocada ou removida some da lista.

## Cache Local de Colaboradores (Raspberry Pi)

- Na inicialização, a Pi consulta `GET /api/sync/employees` e salva o cache em `data/employees_cache.json` no formato `{"updated_at": "<ISO-8601 UTC>", "employees": [...]}`.
- Com conexão ativa, o cache é atualizado periodicamente no intervalo definido por `CACHE_SYNC_INTERVAL_SECONDS` (padrão `60` segundos); falhas de rede durante a atualização mantêm o cache anterior intacto.
- Se a Pi iniciar sem conexão e existir `data/employees_cache.json`, ela carrega o arquivo local e valida os crachás normalmente.
- **Comportamento sem cache:** se a Pi iniciar sem conexão e não houver cache local, o estado é registrado em log e toda tag lida é negada (`acesso_negado`, LED amarelo + buzzer e aviso de cache indisponível), tentando reconectar a cada leitura/ciclo.

## Fila Local de Eventos Offline e Sincronização (Raspberry Pi)

- O feedback de LED e buzzer é emitido imediatamente após a leitura da tag, sem depender da resposta do backend.
- Se o envio a `POST /api/events` falhar por falta de conexão, o evento é gravado na fila local persistente em `data/events_queue.json` (escrita atômica com `fsync` + `os.replace`, resistente a queda de energia e reinicializações).
- Cada item da fila preserva `id` (UUID v4), `type`, `rfid_tag`, `timestamp` original da leitura em UTC (`Z`) e `source` (`raspberry_pi`), na ordem cronológica de ocorrência.
- **Limite e aviso de fila cheia:** configurável via `EVENT_QUEUE_MAX_SIZE` (padrão `1000` eventos). Quando a quantidade de eventos pendentes atinge ou ultrapassa esse limite, o sistema registra um aviso (`WARNING`) no log indicando o total acumulado e o limite configurado — **nenhum evento antigo ou novo é descartado**.
- **Sincronização automática ao reconectar:** quando há eventos na fila local, a Pi tenta reenviá-los automaticamente em ordem cronológica (FIFO) para `POST /api/events/batch` em lotes configuráveis por `EVENT_SYNC_BATCH_SIZE` (padrão `50`) e respeitando o intervalo entre tentativas `EVENT_SYNC_INTERVAL_SECONDS` (padrão `10` segundos).
- **Confirmação incremental e idempotência:** cada lote confirmado pelo backend é imediatamente removido de `data/events_queue.json`; se a conexão cair no meio do envio, apenas os lotes não confirmados permanecem na fila para nova tentativa. Caso um evento já tenha sido recebido anteriormente, o backend ignora duplicatas pelo UUID (`INSERT OR IGNORE`).
- **Operação contínua:** no loop principal do leitor (`run_access_loop`), o reenvio processa um lote por ciclo (`on_tick`), permitindo que novas leituras de crachá continuem sendo atendidas imediatamente durante a sincronização.

## Limitações do MVP

- **Relógio da Raspberry Pi (sem bateria RTC):** a Raspberry Pi não possui módulo RTC dedicado por padrão; se o dispositivo reiniciar totalmente sem acesso à rede (sem sincronização NTP), os timestamps dos eventos gerados até o retorno do NTP refletirão o relógio local salvo pela Pi (`fake-hwclock`).
- **Armazenamento local em processo único:** os arquivos `data/employees_cache.json`, `data/rasp_state.json` e `data/events_queue.json` são dimensionados para um único processo controlador por porta/leitor RC522, sem concorrência multi-processo no mesmo arquivo.
- **Sincronização cooperativa no loop principal:** o envio da fila ocorre de forma cooperativa em lotes curtos (`EVENT_SYNC_BATCH_SIZE`) entre varreduras do leitor RFID, evitando threads paralelas de escrita em disco e mantendo o tempo de resposta de leitura limitado pelo timeout HTTP de cada lote (`5s`).
- **Estado de alternância local por leitor:** a classificação offline entre `entrada` e `saida` utiliza o estado local da própria Raspberry Pi (`data/rasp_state.json`), assumindo um único ponto de controle para a sala monitorada.

## Tempo de permanência

`GET /api/stay?date=YYYY-MM-DD[&employee_id=N]` (admin) devolve, por colaborador, as sessões do dia e `total_seconds`. `date` é obrigatório (400 se inválido); `employee_id` é opcional (400 se não for inteiro positivo, 404 se não existir).

```json
{"date": "2026-10-28", "employees": [{"employee_id": 1, "name": "Ana", "total_seconds": 3600, "sessions": [
  {"entrada": "2026-10-28T11:00:00Z", "saida": "2026-10-28T12:00:00Z", "duration_seconds": 3600, "sem_saida": false},
  {"entrada": "2026-10-29T01:00:00Z", "saida": null, "duration_seconds": null, "sem_saida": true}]}]}
```

Regra de alternância, por colaborador, só com eventos `entrada`/`saida` do dia, em ordem de `timestamp` (empate: ordem de chegada):

- O dia é de 00:00 a 24:00 em `America/Sao_Paulo`; os horários saem em UTC (`Z`).
- `entrada` seguida de `saida` fecha uma sessão; `total_seconds` soma só as fechadas.
- `entrada` sem `saida` até o fim do dia, ou seguida de outra `entrada`, vira sessão `sem_saida`: aparece na lista, fora do total. Vale também para o dia atual.
- `saida` sem `entrada` aberta no dia é ignorada, inclusive a do dia seguinte: a sessão aberta não vaza para o novo dia.
- Sem `employee_id`, lista quem tem ao menos um `entrada`/`saida` no dia. Eventos de tag desconhecida são ignorados.

## Hardware (Raspberry Pi)

### Mapa de Pinos GPIO

| Pino Físico (BOARD) | Pino GPIO (BCM) | Variável (`.env`) | Componente / Descrição |
| :---: | :---: | :--- | :--- |
| **8** | **GPIO 14** | `GPIO_BUZZER=14` | Buzzer (`+` no pino 8, `-` no GND) |
| **32** | **GPIO 12** | `GPIO_LED_GREEN=12` | LED Verde (em série com resistor 220–330 Ω para GND) |
| **34** | **GND** | — | GND para o barramento negativo (`-`) da protoboard |
| **36** | **GPIO 16** | `GPIO_LED_YELLOW=16` | LED Amarelo (em série com resistor 220–330 Ω para GND) |
| **40** | **GPIO 21** | `GPIO_LED_RED=21` | LED Vermelho (em série com resistor 220–330 Ω para GND) |
| **1** | **3.3V** | — | Leitor RFID RC522 (`VCC` / `3.3V`) |
| **6** | **GND** | — | Leitor RFID RC522 (`GND`) |
| **19** | **GPIO 10** | — | Leitor RFID RC522 (`MOSI` / SPI0 MOSI) |
| **21** | **GPIO 9** | — | Leitor RFID RC522 (`MISO` / SPI0 MISO) |
| **22** | **GPIO 25** | `GPIO_RFID_RST=25` | Leitor RFID RC522 (`RST`) |
| **23** | **GPIO 11** | — | Leitor RFID RC522 (`SCK` / SPI0 SCLK) |
| **24** | **GPIO 8** | `GPIO_RFID_SDA=8` | Leitor RFID RC522 (`SDA` / `NSS` / SPI0 CE0) |

### Diagrama de Ligação (Header 40 Pinos)

```text
          Coluna Ímpar (Interna)          Coluna Par (Borda Externa)
         ------------------------------------------------------------
          3.3V (RFID VCC)  --> [ 1]  |  [ 2] 5V
                        GPIO 2 [ 3]  |  [ 4] 5V
                        GPIO 3 [ 5]  |  [ 6] <-- GND (RFID GND)
                        GPIO 4 [ 7]  |  [ 8] <-- GPIO 14 (BUZZER)
                           GND [ 9]  |  [10] GPIO 15
                       GPIO 17 [11]  |  [12] GPIO 18
                       GPIO 27 [13]  |  [14] GND
                       GPIO 22 [15]  |  [16] GPIO 23
                          3.3V [17]  |  [18] GPIO 24
          (RFID MOSI)  GPIO 10 [19]  |  [20] GND
          (RFID MISO)   GPIO 9 [21]  |  [22] <-- GPIO 25 (RFID RST)
          (RFID SCK)   GPIO 11 [23]  |  [24] <-- GPIO 8  (RFID SDA)
                           GND [25]  |  [26] GPIO 7
                        GPIO 0 [27]  |  [28] GPIO 1
                        GPIO 5 [29]  |  [30] GND
                        GPIO 6 [31]  |  [32] <-- GPIO 12 (LED VERDE)
                       GPIO 13 [33]  |  [34] <-- GND (PARA PROTOBOARD)
                       GPIO 19 [35]  |  [36] <-- GPIO 16 (LED AMARELO)
                       GPIO 26 [37]  |  [38] GPIO 20
                           GND [39]  |  [40] <-- GPIO 21 (LED VERMELHO)
         ------------------------------------------------------------
                           [ Portas USB / Ethernet ]
```

* **LEDs:** perna maior (ânodo `+`) conectada ao respectivo pino GPIO; perna menor (cátodo `-`) conectada a um resistor de **220 Ω a 330 Ω** ligado ao barramento **GND** da protoboard (pino físico 34).
* **Buzzer:** terminal positivo (`+`) no pino físico 8 (**GPIO 14**) e terminal negativo (`-`) no barramento **GND** da protoboard.
* **Leitor RFID (RC522):** conectado ao barramento SPI0 (habilitar via `sudo raspi-config` → *Interface Options* → *SPI*). Alimentar exclusivamente em **3.3V** (pino 1).

### Lista de Componentes

| Componente | Especificação | Qtd. |
| :--- | :--- | :---: |
| **Raspberry Pi** | Raspberry Pi 3B+ / 4B (com fonte e microSD) | 1 |
| **Módulo Leitor RFID** | MFRC522 (13,56 MHz, SPI, 3.3V) + tag/chaveiro | 1 |
| **Tags / Crachás RFID extras** | Mifare 13,56 MHz (cartão ISO / chaveiro) | 4 |
| **LEDs Difusos 5 mm** | 1x Verde, 1x Amarelo, 1x Vermelho | 3 |
| **Resistores** | 220 Ω ou 330 Ω (1/4 W) | 3 |
| **Buzzer** | Buzzer 3.3V / 5V (ativo ou passivo) | 1 |
| **Protoboard** | 400 ou 830 pontos | 1 |
| **Jumpers** | Kit cabos Macho-Fêmea e Macho-Macho (20 cm) | 1 |

### Teste de Hardware

Com o circuito conectado e o SPI habilitado na Raspberry Pi, execute o script de diagnóstico para testar individualmente cada LED, o buzzer e a leitura de uma tag RFID:

```bash
uv run python rasp/test_hardware.py
```

*(Os pinos podem ser sobrescritos via variáveis de ambiente no arquivo `.env` conforme a tabela acima).*

### Executar o Controle de Acesso

Na Raspberry Pi, com `.env` configurado (`API_BASE_URL`, `PI_API_KEY` igual ao do backend):

```bash
uv run python -m rasp.access
```
