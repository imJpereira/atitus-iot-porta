# atitus-iot-porta

Stack e convenções em [AGENTS.md](AGENTS.md).

```bash
uv sync
export PI_API_KEY=... SECRET_KEY=...   # ver .env.example
uv run flask --app api create-admin <usuario>   # pede a senha (ou use ADMIN_PASSWORD)
uv run flask --app api run --debug
```

Rotas administrativas (`/api/employees`, `GET /api/events*`, `/api/export/*`) exigem login em `POST /api/auth/login`; a Raspberry Pi usa só `X-API-Key`.

## Tag RFID

- `rfid_tag` é opcional e única. Vincule, troque ou remova com `PATCH /api/employees/<id>`; `null` desvincula.
- Ao salvar, a tag é normalizada com `strip().upper()` (`" aa:bb "` vira `"AA:BB"`). Qualquer string não vazia vale; não há regex.
- Tag já usada por outro colaborador responde 409 `{"error": "rfid_tag already exists", "owner": {"id", "name", "registration_id"}}`.
- `GET /api/sync/employees` (chave da Pi) lista só colaboradores com tag, inclusive inativos; a Pi decide por `is_active` e `has_room_access`. Tag trocada ou removida some da lista.

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

### Lista de Componentes e Custo Estimado (MVP)

| Componente | Especificação | Qtd. | Custo Unit. (R$) | Subtotal (R$) |
| :--- | :--- | :---: | :---: | :---: |
| **Raspberry Pi** | Raspberry Pi 3B+ / 4B (com fonte e microSD) | 1 | 380,00 | 380,00 |
| **Módulo Leitor RFID** | MFRC522 (13,56 MHz, SPI, 3.3V) + tag/chaveiro | 1 | 18,00 | 18,00 |
| **Tags / Crachás RFID extras** | Mifare 13,56 MHz (cartão ISO / chaveiro) | 4 | 3,00 | 12,00 |
| **LEDs Difusos 5 mm** | 1x Verde, 1x Amarelo, 1x Vermelho | 3 | 0,50 | 1,50 |
| **Resistores** | 220 Ω ou 330 Ω (1/4 W) | 3 | 0,20 | 0,60 |
| **Buzzer** | Buzzer 3.3V / 5V (ativo ou passivo) | 1 | 3,50 | 3,50 |
| **Protoboard** | 400 ou 830 pontos | 1 | 15,00 | 15,00 |
| **Jumpers** | Kit cabos Macho-Fêmea e Macho-Macho (20 cm) | 1 | 12,00 | 12,00 |
| **Total Estimado** | | | | **R$ 442,60** |

### Teste de Hardware

Com o circuito conectado e o SPI habilitado na Raspberry Pi, execute o script de diagnóstico para testar individualmente cada LED, o buzzer e a leitura de uma tag RFID:

```bash
uv run python rasp/test_hardware.py
```

*(Os pinos podem ser sobrescritos via variáveis de ambiente no arquivo `.env` conforme a tabela acima).*
