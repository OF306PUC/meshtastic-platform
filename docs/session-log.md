# Session Log — Bitácora

Chronological log of every work session. A new entry is added at the start of
each session and filled in real time as work progresses. **Newest entry on top.**

Entry format:
```
## YYYY-MM-DD — [brief session title]
**Time:** HH:MM (aprox)
**User request:** ...
### Actions taken
- ...
### Decisions
- ...
### Outcomes
- ...
### Next steps / open questions
- ...
```

---

## 2026-10-27 — Falso positivo: "device.rebroadcast_mode did not persist"
**Time:** 14:00 (aprox)
**User request:** al configurar un nodo SenseCAP en Windows (`--port COM4`)
apareció `WARNING: device.rebroadcast_mode did not persist (expected
LOCAL_ONLY, read '2')`.

### Actions taken
- Verificado contra el protobuf: en `Config.DeviceConfig.RebroadcastMode`,
  `LOCAL_ONLY` **es** el 2. El ajuste sí había quedado guardado.
- Causa: `meshtastic --get` imprime los campos con `util.toStr`, y para un enum
  eso es el entero crudo (`device.rebroadcast_mode: 2`). `node.execute`
  comparaba el NOMBRE contra esa salida (`"local_only" not in "2"`), así que la
  verificación fallaba **siempre**, en todos los nodos y sistemas operativos:
  `provision` terminaba con "configuration completed with ERRORS" sin que
  hubiera error. El docstring de `get_config_value` afirmaba que el CLI imprime
  `LOCAL_ONLY`; era falso.
- `meshtastic_cli.reads_as(actual, expected, enum_type)`: acepta el nombre o el
  número, resolviendo el nombre con el enum del protobuf; sin enum o con valor
  vacío no hay coincidencia (no se "arregla" aceptando cualquier cosa).
- `node.execute` la usa con `Config.DeviceConfig.RebroadcastMode`.
- Dos tests de regresión en `test_provision.py`: la tabla de equivalencias y el
  camino completo de `execute` con una radio que responde `'2'`.

### Decisions
- No se tocó el inspector: lee por protobuf (`enum_name`), no por el CLI, así
  que ya obtenía `LOCAL_ONLY`. Confirmado.
- La comparación sigue siendo estricta ante un valor vacío o un modo distinto:
  la verificación existe porque `rebroadcast_mode` se vio no persistir de
  verdad cuando se fijaba junto a `device.role`.

### Outcomes
- 192 tests OK (190 + 2 nuevos); pyflakes limpio.
- Los nodos configurados mientras aparecía esa advertencia están bien; se puede
  confirmar con `configure.py inspect`.

### Next steps / open questions
- ¿Que `receiver.py` autodetecte el puerto como `inspect`? (pendiente anterior)

---

## 2026-10-27 — Generación de claves portable (Windows)
**Time:** 13:20 (aprox)
**User request:** `openssl rand -base64 32` no funciona en Windows.

### Actions taken
- Reemplazado por un one-liner de Python en `.env.example` y en la cabecera de
  `deployments/mini.yaml`:
  `python -c "import secrets,base64;print('base64:'+base64.b64encode(secrets.token_bytes(32)).decode())"`
  Verificado: produce 32 bytes que `radio.profile.decode_psk` acepta.
- README: nota de setup para Windows (`python -m venv`, `copy`,
  `.venv\Scripts\activate`) y una línea que manda a generar las claves con el
  comando del `.env.example`.

### Decisions
- Python en vez de PowerShell: la plataforma ya lo exige, así que es el único
  comando que sirve en los tres sistemas. Además imprime el valor completo con
  el prefijo `base64:`, que `openssl` no incluye.
- `openssl` queda mencionado como alternativa en Linux/macOS, con la advertencia
  de que hay que agregarle el prefijo a mano.

### Outcomes
- 190 tests OK; `validate -d mini` OK.

- Puertos serie (el usuario preguntó dónde están definidos): **en ninguna
  parte** — son siempre el argumento `--port`, porque pertenecen al computador
  y no a la malla. Documentado en una sección nueva del README, "The serial
  port", con tabla por sistema (COMn / by-id / cu.*) y cómo encontrarlo;
  los ejemplos del README usan `<port>` en vez de `/dev/ttyACM0`. La ayuda de
  `--port` en `configure.py` y `receiver.py` nombra los tres formatos. En
  troubleshooting, el consejo de usar `by-id` quedó marcado como propio de
  Linux, con qué hacer en Windows/macOS (identificar por `node_id` con
  `inspect`).
- Corregido de paso: `inspector.py` imprimía "Radio (vs radio/config.py y el
  deployment)" — ese archivo se eliminó en la generalización.
- `configure.py inspect` autodetecta el puerto con una sola radio conectada
  (`meshtastic.util.findPorts`, que en Windows devuelve COMn); `receiver.py`
  sigue exigiendo `--port`.

### Next steps / open questions
- ¿Que `receiver.py` también autodetecte el puerto cuando hay una sola radio,
  como hace `inspect`? Hoy es obligatorio pasarlo.

---

## 2026-10-27 — `meshtastic-gateway` como submódulo
**Time:** 13:00 (aprox)
**User request:** actualizar el README con el agregado del submódulo del gateway.

### Actions taken
- Verificado: el repositorio del gateway ya tiene su primer commit (`50dd922`)
  y `external/meshtastic-gateway` está agregado (`.gitmodules`).
- README: la sección de submódulos pasa a tabla de dos filas (meshpbx y
  meshtastic-gateway), marcada **solo como referencia**, y explica qué parte de
  una radio posee cada repositorio: el proyecto PBX el enlace de una radio
  `pbx`, el gateway nada de configuración (se acopla solo por el archivo de
  despliegue). Agregado el `sha256sum` para comparar las dos copias, con la nota
  de que el `deployments/` del gateway todavía no tiene ningún archivo.
- CLAUDE.md y project-overview: fuera el "once it has a first commit" y la
  restricción "no puede ser submódulo hasta que tenga un commit"; la ruta de la
  copia del gateway ahora es concreta.
- `docs/troubleshooting.md`: el comando de comparación usa la ruta del submódulo.

### Outcomes
- 190 tests OK; sin enlaces rotos en README ni docs.

### Next steps / open questions
- Copiar a `external/meshtastic-gateway/deployments/` los archivos que el
  gateway vaya a medir, antes de su primera corrida.

---

## 2026-10-27 — `report/` fuera de git y al día con la plataforma
**Time:** 11:00–12:30 (aprox)
**User request:** ignorar `report/` en git (es metodología específica de una
aplicación) y actualizar sus archivos al estado de la plataforma.

### Actions taken
- `.gitignore`: `report/`. README (layout), overview y
  `docs/testbeds/san-joaquin.md` ya no enlazan a `report/`; dicen que es local.
- Copia de los originales en el scratchpad antes de editar.
- `report/README.md` reescrito: procedencia, tabla "dos configuraciones"
  (LONG_TURBO grabado vs MEDIUM_FAST objetivo: slot, tope SUBTEL, tx_power,
  roles), de dónde salen los números.
- `02-analytical…`: nueva §0 con el punto de operación MEDIUM_FAST (slot 45,
  926,125 MHz) lado a lado con LONG_TURBO — ToA, sensibilidad, alcance, slot MAC
  12 ms, backoff, retransmisión 5,62 s, carga 35,9 s/h = 1,00 %, ocupación por
  m, techo de escala — y una columna MEDIUM_FAST en las predicciones P1–P8.
  ToA y pisos verificados con `meshtastic_platform.radio` (coinciden exacto con
  las tablas pegadas); el resto calculado con las fórmulas del documento.
- `00-context`: hardware (T-Beam SX1276, roles grabado → objetivo, inventario
  en el deployment), configuración (tabla grabado vs objetivo), slot 45 y
  deployments que lo comparten, puntos de medición (P1/P2 no portados al
  gateway, P3 gateway, P4 receiver.py), esquema del gateway (tres medidas),
  semántica de `hop` cambiada (D1/D2), registros de receiver.py, qué se puede
  medir, restricciones 1–10 actualizadas, tabla de discrepancias con columna
  "Now".
- `01-methodology`: estado de la deuda de instrumentación (5.9 hecho; 5.5 a la
  espera de reaprovisionar; 5.1/5.6 parcial; 5.2–5.4 del gateway; 5.8
  bloqueado), E4 reformulado (el cambio ya está decidido), E6 choca con la regla
  C1 del validador (cadence_scale prohibido en field), E7 `ignore_incoming` a
  mano, E8 bloqueado, amenazas a la validez, secuencia.
- Versión en español completada: un agente alcanzó a aplicar §1–§4 de
  `00-contexto.md` antes de cortarse por límite de sesión; el resto
  (`00-contexto` §5–§10, `01-metodologia`, `02-analitico-enlace-y-canal` y el
  `README.md` reescrito) se aplicó en esta sesión. Verificado: mismas cifras que
  el inglés (12 valores clave contrastados), misma estructura de encabezados
  (17/29/24/4), sin enlaces rotos, sin voseo.

### Decisions
- Se conserva el análisis LONG_TURBO (describe los datos existentes) y se
  agrega MEDIUM_FAST al lado, en vez de reemplazarlo.
- `lora_model.py` no existe en ningún repositorio: se dice así, y se indica cómo
  reproducir la parte PHY con la plataforma.

### Next steps / open questions
- Verificar si el firmware 2.7 entrega las métricas propias de la radio al
  cliente con la telemetría apagada (01 §5.1): daría `channel_util` del sumidero
  sin tiempo de aire.

---

## 2026-10-27 — Diagrama de puertos del gateway (en el repo del gateway)
**Time:** 10:15–10:30 (aprox)
**User request:** dibujar en TeX la arquitectura de puertos del gateway
(opción B), basada en `../meshtastic-gateway/`.

### Actions taken
- Creado `meshtastic-gateway/docs/diagrams/port-architecture.tex` (+ `.png`,
  `.pdf`), con copias de `palette.tex` y `build.sh` de `docs/diagrams/`.
  Registrado en la bitácora del gateway.

### Decisions
- Nada en este repo: la regla 2 prohíbe mencionar broker, base de datos o
  contenedores.

---

## 2026-10-27 — Deployment `mini`; documentación al día con el gateway
**Time:** 09:30–10:30 (aprox)
**User request:** crear el deployment mínimo de 3 nodos (pruebas hoy). ¿Están
al día troubleshooting, session-log, project-overview, flashing, scalability/ y
testbeds/? ¿Consideran la implementación actual del gateway? Agregar a
scalability dos ideas para después de Rapa Nui: meshpbx en PCB y mesh-sniffer.

### Actions taken
- `deployments/mini.yaml`: N1–N3 SenseCAP (rubber 2 dBi, 22 dBm, device 120 s)
  + receptor R1 (T-Beam SX1276, CLIENT_MUTE); canal `miniT`, clave `MINI_PSK`
  (agregada a `.env.example`). Cabecera con los pasos y cómo pasar a `bench`.
- Leído `meshtastic-gateway` (solo lectura; sin commits aún, con código):
  `GATEWAY-DIRECTIVES.md` §0.1 — el gateway NO depende del código de la
  plataforma (forkeó `decode/`), se empareja solo por copias idénticas del
  deployment (mismo SHA-256); su lector ignora campos que no usa (el bloque
  `pbx` no lo rompe). `REFACTOR-PLATFORM-GATEWAY.md` se movió a ese repo.
- Corregido lo que decía lo contrario: CLAUDE.md (regla 2 y enlace al guía),
  README (submódulos/gateway, el decoder), project-overview (sección del
  gateway, estado, visión, restricciones), `report/` (procedencia), diagrama
  `membership` (la flecha ahora es la copia del deployment, no `decode()`).
- `docs/testbeds/san-joaquin.md` reescrito: los datos de radios remiten al
  deployment; estado real (LONG_TURBO, tx_power sin fijar, roles), p1/p2,
  gateway actual; enlaces muertos eliminados.
- `docs/scalability/README.md`: enlaces muertos fuera, método con
  receiver.py/gateway/bench, y las dos ideas (meshpbx en PCB, mesh-sniffer).
- `docs/troubleshooting.md`: "A pbx radio lost its membership" y "The
  gateway's copy of the deployment differs".

### Outcomes
- 190 tests OK; `validate --all` OK (cuatro deployments).

- El usuario subió `docs/diagrams/mesh-platform.png` (malla 1–6, MeshPBX,
  gateway 5G) como diagrama del repositorio: va arriba en el README, con un
  texto que aclara que la mitad radio del MeshPBX y del gateway también es
  miembro de la malla. `membership.png` y `pbx-connector.png` quedan como
  detalle. A pedido del usuario se escribió
  `docs/architecture/ADR-0002-membership-and-connectors.md`: contexto (quién
  configura la radio del PBX; slot 17 con los scripts de meshpbx), decisión
  (membresía / conector, tabla por función), la conexión PBX en detalle (BLE,
  UART Stream API, LoRa, portnum 256), ejemplo p1 de San Joaquín (membresía y
  conector con sus comandos), consecuencias y alternativas; con ambos
  diagramas. El README enlaza al ADR desde la sección de membresía.

### Next steps / open questions
- Copiar los deployments al gateway cuando los use (hoy su `deployments/` solo
  tiene README).

---

## 2026-10-26 — Diagrama TikZ de membresía y conectores
**Time:** 14:50–15:10 (aprox)
**User request:** un dibujo (TikZ) del conector de membresía con los módulos
meshpbx y gateway.

### Actions taken
- `docs/diagrams/membership.tex` (standalone TikZ): deployment →
  meshtastic-platform → membresía (azul) a las cuatro radios de la malla (node,
  pbx, receiver, gateway); conectores (naranjo) radio↔módulo: UART/PROTO/BT off
  al módulo meshpbx (nRF54L15), USB al laptop (receiver.py) y al host del
  gateway; dependencia de código (verde) gateway → decode() + deployments;
  relleno de cajas por repositorio.
- Compilado con pdflatex y revisado como PNG (en el scratchpad, no en el repo).

- Pedido siguiente: Times New Roman, colores Meshtastic/LoRa, teléfonos sin
  límite, y un segundo dibujo del conector y el módulo.
- `docs/diagrams/palette.tex` (común): Times (mathptmx con pdflatex; Times New
  Roman vía fontspec con lualatex/xelatex — aquí lualatex no compila
  `standalone` por falta de `luatex85.sty`), paleta Meshtastic #2C2D3C/#67EA94
  (+ Green 600/700 para líneas y texto, github.com/meshtastic/design), LoRa
  blue #00AEEF (guía de logo LoRa de Semtech), ámbar para el conector.
- `membership.tex` reestilizado; teléfonos 1, 2, …, n.
- `pbx-connector.tex`: módulo meshpbx (sesión UART, router, sesiones por
  teléfono, GATT BLE) ↔ UART/Stream API ↔ radio pbx (módulo serial PROTO,
  firmware Meshtastic, transceptor LoRa; marco de membresía) → antena → malla.
  Arriba, el proyecto PBX (firmware + ajustes del conector); abajo, la
  plataforma (membresía desde el deployment).
- Ojo: con `-output-directory`, TeX también busca entradas ahí; una copia vieja
  del .tex en ese directorio se compiló en su lugar. Compilar a un directorio
  sin fuentes .tex.

### Next steps / open questions
- ¿Incluir los PNG en el README (sección de membresía)?

---

## 2026-10-26 — Membresía: la plataforma no configura el enlace del PBX
**Time:** 14:15–14:45 (aprox)
**User request:** ¿configurar las radios del PBX desde esta plataforma o desde
el proyecto PBX? El usuario ve el PBX como un "conector configurable" a la
malla. Acordado: el proyecto PBX configura el conector; esta plataforma, la
membresía. Explicar la membresía en el README, breve.

### Actions taken
- `plan.serial_settings`: en radios `pbx` no escribe nada (ni serial ni
  Bluetooth); en las demás, `serial.enabled false`. El paso "serial" no aparece
  en el plan de una radio pbx. El inspector solo verifica membresía en ellas.
- Bloque `pbx` reducido a `mcu` + `firmware` (registro); `uart` sale del modelo,
  del loader (ahora lo rechaza), del validador, de san-joaquin y la plantilla.
- README: sección "Mesh membership: what gets configured on a radio".
- CLAUDE.md, overview, memoria actualizados.

### Decisions
- Evidencia para no dejar la membresía en meshpbx: su `tools/meshtastic` fija
  canales `telCPS_RTC`/`msgPUC_NET`, `HOP_LIMIT = 1` y no fija `channel_num` ni
  `tx_power` → caería en el slot 17 (919,125 MHz, hash del nombre) en vez del 45.
- Lo que haga meshpbx con sus scripts de radio (pruebas de configuración) lo ve
  el usuario.

### Outcomes
- 190 tests OK; pyflakes limpio; `validate --all` OK.

### Next steps / open questions
- En meshpbx: que su configuración de la radio escriba solo el conector.

---

## 2026-10-26 — `pbx` como función de primera clase; tests de reglas duras
**Time:** 13:00–14:00 (aprox)
**User request:** el PBX debería ser una función de primera clase en
`FUNCTIONS`; se diseña su hardware, que corre principalmente en un Nordic
nRF54x. No entiende `test_dependency_rule`.

### Actions taken
- Leído `external/meshpbx` (README y `tools/meshtastic/`) y el `src/pbx/` del
  monorepo (solo lectura): el PBX es un procesador BLE (Zephyr) que multiplexa
  teléfonos sobre UNA radio Meshtastic conectada por UART (módulo serial en
  PROTO, Bluetooth de la radio apagado; en el prototipo, T-Beam UART1 GPIO15/35
  a 115200).
- `FUNCTIONS` = node, pbx, gateway, receiver. Nuevo bloque `pbx` por nodo
  (`mcu`, `firmware`, `uart: {txd, rxd, baud}`) → `model.Pbx`; loader estricto.
  `hardware.PBX_MCUS` = nrf52840, nrf54l15, nrf54h20.
- Validador (código X): `pbx` obligatorio en radios pbx y prohibido en otras;
  mcu en el catálogo; baud de Meshtastic; txd ≠ rxd; `pbx.firmware` en la lista
  de pendientes (P) y obligatorio al desplegar. Las reglas de sitio aplican a
  pbx como a node/gateway.
- `plan.serial_settings`: en radios pbx, `bluetooth.enabled false` + serial
  PROTO con pines y baud del archivo; en las demás, `serial.enabled false`.
  El inspector verifica lo mismo. `tx_function` en cada registro del receptor.
- `tests/test_dependency_rule.py` → `tests/test_hard_rules.py`: docstring que
  explica qué lee y por qué; "pbx" fuera de la lista prohibida; coincidencia por
  palabra completa (`node-1` ya no coincide dentro de `node-10`).
- README (tabla de funciones, fila `serial.*`/`bluetooth.enabled`, corrección de
  `CLIENT_MUTE`), `_template.yaml` (ejemplo P1), CLAUDE.md, overview, memoria.

### Decisions
- Una radio pbx es la radio Meshtastic (la que tiene `node_id`, potencia,
  canales); el PBX es un componente adjunto registrado en su bloque, igual que
  un sensor. Funciona tanto para el prototipo (DK + T-Beam) como para una placa
  integrada con nRF54.
- Sin restricción de rol para pbx: `CLIENT_MUTE` también envía lo propio.
- No se decodifican aún las tramas del PBX (siguen como `private`).
- No se agregaron P1/P2 a ningún deployment (el usuario no lo pidió).

### Outcomes
- 189 tests OK; pyflakes limpio; `validate --all` OK; la plantilla valida salvo
  el nombre de archivo (esperado).

- Respuesta del usuario: parte nRF54L15 (`PBX_MCUS` = nrf52840, nrf54l15);
  volver a registrar los PBX de san-joaquin; las tramas del portnum 256 solo
  por tamaño (las decodifica y muestra el gateway); los mensajes de texto de
  Meshtastic se pueden mostrar.
- `san-joaquin.yaml`: p1 (`!bb8106c4`, MIDE) y p2 (`!6c743130`, DIE) como
  radios pbx: T-Beam SX1276, 20 dBm, antena asumida de fábrica, PBX nRF52840
  DK por UART1 (GPIO15/35, 115200), cadencias {device 600, position 1800}.
  Quedan `planned` hasta registrar el firmware de la radio y del PBX: con
  `deployed` y firmware nulo el archivo no valida.
- README y docstring del decoder: portnum 256 solo tamaño, lo decodifica el
  gateway; texto en terminal, a archivo solo con `--capture-content`.

### Next steps / open questions
- Leer con `inspect` el firmware de p1/p2 y la versión del PBX; luego `deployed`.
- Pines UART de la placa nRF54L15.

---

## 2026-10-26 — Canales EasterNet, canales por índice, qué configura provision
**Time:** 11:30–12:15 (aprox)
**User request:** verificar que el repo (1) configura los nodos de la aplicación
descrita en deployments y (2) corre un receptor que revisa la malla y registra
datos para channel study; `report/` puede quedar si referencia un deployment;
¿provision configura el modem_preset? ¿y nombres y claves de canal? Canales de
rapa-nui: `EasterNetM` (mensajería) y `EasterNetT` (telemetría). El README no
explica brevemente qué se configura (preset, canales, región…).

### Actions taken
- `deployments/rapa-nui.yaml`: índice 0 `EasterNetT` (telemetría), índice 1
  `EasterNetM` (mensajería); mismas variables de PSK.
- Revisado el CLI de meshtastic 2.7.8: `--ch-add` usa el primer índice libre y
  rechaza nombres de más de 10 caracteres; `--ch-set ... --ch-index i` escribe y
  habilita el índice i. `plan.channel_steps` ahora escribe cada canal por índice
  (nombre, PSK, precisión) y ya no usa `--ch-add`.
- Inspector: lee si cada canal está habilitado; marca un canal declarado
  deshabilitado y cualquier canal habilitado que el deployment no declara (con el
  comando para borrarlo). Entrada nueva en troubleshooting.
- Validador (R): índices 0..7 y contiguos; nombre de 1..11 bytes (límite del
  firmware).
- README: sección "What gets configured on a radio" (tabla setting → campo del
  archivo → efecto); `report/` en el layout.

### Decisions
- Con otro nombre el hash de canal cambia, así que rapa-nui ya no decodifica a
  san-joaquin ni al bench; con claves propias, además, no podría aunque los
  nombres coincidieran.
- `report/` se queda: su README lo ata a `deployments/san-joaquin.yaml`.

### Outcomes
- 180 tests OK; pyflakes limpio; `validate --all` OK.

- Claves propias para rapa-nui (pedido del usuario a continuación):
  `EASTERNET_TELEMETRY_PSK` y `EASTERNET_MSG_PSK`; `.env.example` agrupa las
  variables por deployment e indica cómo generar una clave
  (`openssl rand -base64 32`). No hay `.env` en el repo todavía: las claves las
  genera y distribuye el usuario.
- `channel_psks` ahora rechaza (nombrando la variable, nunca el valor) una clave
  que no sea base64 estricto de 1, 16 o 32 bytes — incluido el `CHANGE_ME` de la
  plantilla. Motivo: el cargador de `.env` se queda con la PRIMERA aparición de
  una variable, así que agregar la clave al final de una copia de la plantilla
  dejaba el placeholder activo. `provision` se niega (exit 2); `inspect` avisa y
  no compara claves.

### Next steps / open questions
- Posible chequeo en el receptor: `hopStart` de cada paquete contra el
  `hop_limit` del nodo en el archivo (detecta configuración errónea sin USB).

---

## 2026-10-26 — Generalización: la aplicación vive solo en deployments/
**Time:** 10:30–11:30 (aprox)
**User request:** el repositorio no generaliza. meshpbx y el gateway deben ser
submódulos de GitHub; la plataforma configura los nodos de campo y corre un
receptor para verificar y hacer channel study. El README tiene ruido (SUBTEL,
plataforma anterior, validación, Rapa Nui). Lo que es de la aplicación debe
estar solo en los deployments y no referenciarse en el código. ¿Qué hace el
decoder?

### Actions taken
- Bloque `radio` en cada deployment (región, preset, `channel_num`, canales con
  `psk_env`, rebroadcast, precisión, RX boosted gain, `eirp_caps`).
  `radio/config.py` eliminado; nuevo `radio/profile.py` (`RadioSpec`,
  `RadioProfile`, `build_profile`, `channel_psks`). `regulatory.py` genérico:
  `Band`, `Chip`, `eirp_cap(slot, caps)`.
- PBX eliminado del decoder, del aprovisionamiento y del inspector; PRIVATE_APP
  queda como `private` opaco (solo tamaño). `plot_panels.py` y
  `analyze_phy.py` eliminados (analizan exportaciones del gateway; los
  originales siguen en el monorepo).
- `external/meshpbx` agregado como submódulo (staged). El gateway no puede serlo
  aún: su repositorio no tiene commits.
- Validador sin S1/S2 (eran reglas de una aplicación). `_template.yaml` con el
  esquema comentado.
- `tests/test_dependency_rule.py`: nueva regla — ningún nombre de la aplicación
  en el código; la lista se arma desde los propios deployments (nombre, canales,
  `psk_env`, labels) más nombres del proyecto. `test_scripts.py` usa un
  deployment sintético vía `MESH_DEPLOYMENTS_DIR`.
- README reescrito corto y genérico; CLAUDE.md (reglas), troubleshooting,
  flashing, project-overview, `.env.example`, CI y memoria actualizados.

### Decisions
- Los nombres de la aplicación pueden aparecer en deployments/, docs y report/,
  no en `meshtastic_platform/`, `channel_study/` ni en los dos scripts.
- Ningún código importa desde `external/`: los submódulos se versionan juntos,
  no son dependencias.

### Outcomes
- 177 tests OK; pyflakes limpio; la búsqueda de nombres de la aplicación en el
  código no encuentra nada.

### Next steps / open questions
- Agregar `meshtastic-gateway` como submódulo cuando tenga su primer commit.
- `report/` es material de una aplicación (traído del monorepo): decidir si se
  queda aquí.

---

## 2026-10-26 — Plan de slots, T-Beam SX1276, N6 en fibra, sin PBX, sin pyproject
**Time:** 10:00–10:10 (aprox)
**User request:** (1) slots ANZ por preset: LONG_TURBO 14/26 = 921,75 MHz,
LONG_FAST 20/52 = 919,875 MHz, MEDIUM_FAST 45/52 = 926,125 MHz; (2) las T-Beam
son SX1276; (3) N6 lleva antena de fibra y es un nodo centralizador `CLIENT`
escuchado por el receptor `CLIENT_MUTE`; (4) no considerar los PBX todavía;
y ¿por qué queda `pyproject.toml`?

### Actions taken
- `SLOT_PLAN` en `radio/config.py` (los tres slots, verificados con la fórmula
  del firmware: coinciden con las frecuencias dadas). Los registros ya no fijan
  `channel_num`: lo da el plan; `meta.channel_num` queda como reemplazo
  deliberado, que el validador reporta (V7, aviso). Un preset fuera del plan sin
  `channel_num` es error.
- SX1276 verificado en el código fuente: Meshtastic `RF95_MAX_POWER = 20`;
  RadioLib PA_BOOST acepta 2–17 y 20 (18/19 → error crítico
  `INVALID_RADIO_SETTING`), bajo 2 cambia a la salida RFO. Chip `sx1276`
  (2..20, sin 18/19) en el catálogo; `lilygo_tbeam` → sx1276; la derivación
  salta valores inválidos; el validador los rechaza. Quitadas del catálogo las
  LILYGO que no están en el inventario (S3 Core, T3S3).
- Registros: LILYGO (GW, R1, R2, gw de San Joaquín) → 20 dBm; banco → 2 dBm;
  N6 → fibra (y N4 → goma, para mantener 3+3); N6 anotado como nodo centralizador;
  San Joaquín sin p1/p2 (el código de provisión PBX se mantiene, sin uso).
- S1 ampliado: también es confusión que la fibra sea exactamente el complemento
  de los sensorizados ("fibra" = "menos tráfico").
- `pyproject.toml` eliminado: sólo servía para que el gateway hiciera
  `pip install`; el gateway usará este repo como submódulo git.
- Tests: 187 verdes (plan de slots, SX1276, S1 complemento, N6, potencias).

### Decisions
- **Slot por preset, no por despliegue**: un solo plan, y cambiar de preset
  cambia de slot (y de banda SUBTEL) automáticamente.
- **Banco y San Joaquín comparten el slot 45 en el mismo campus**: no deben
  estar al aire a la vez (o uno lleva `channel_num` de reemplazo). `validate
  --all` lo recuerda.
- **2 dBm de mínimo en el banco**: no se usa la salida RFO porque no está
  verificado que llegue a la antena en la T-Beam.

### Next steps / open questions
- Verificar en una T-Beam la línea de arranque `Power output set to N` /
  `Final Tx power` con 20 y con 2 dBm.
- Si 2 dBm satura en el banco: atenuadores (la guía lo prevé).

---

## 2026-10-26 — Sitios de Rapa Nui como plantilla; DISENO fuera
**Time:** 09:45–10:00 (aprox)
**User request:** no hacer caso a `DISENO-ANTENAS-SENSORES.md`. Las posiciones
finales no están definidas: por ahora N1–N6 son nodos de cluster y el receptor
del channel-study es PC + LILYGO. Dejar un formato plantilla para llenar las
posiciones finales en Rapa Nui.

### Actions taken
- `rapa-nui.yaml` reescrito como plantilla: N1–N6 nodos de cluster (todos
  `CLIENT`, `hop_limit: 1`), cada nodo con el mismo bloque `site` vacío
  (`name`, `asset_code`, `surveyed{lat, lon, alt_m, alt_source}`,
  `antenna_height_m`, `mount`); guía de llenado paso a paso en el encabezado y,
  sólo como referencia comentada, los sitios candidatos del plan (anexo B.1).
  Quitados Vaitea, las posiciones de escritorio, las notas por sitio y la nota
  de DISENO.
- R1/R2: LILYGO en un PC, GPS apagado (un receptor fijo registra su punto en
  `site`; para caminar con él se agrega `position: 30`).
- Loader: un bloque de posición con todo `null` es "aún no llenado" (None); uno a
  medio llenar es error.
- Validador: la lista de pendientes incluye `site.antenna_height_m`; aviso si un
  nodo desplegado no la tiene. `configure.py show` agrega una tabla de sitios
  (qué está llenado y qué falta).
- Tests: plantilla vacía, llenado de un nodo en terreno (valida como
  desplegado; sin `surveyed` lo rechaza V6), posición a medio llenar, receptor
  fijo vs. caminando. 178 verdes.
- `CLAUDE.md` (reglas 10–11), memoria: `diseno-antenas-not-followed`,
  `tx-power-derived-by-band` (reemplaza a la de la asimetría, basada en DISENO).

### Decisions
- La asignación antena/sensor por nodo queda **provisional por unidad**: la
  restricción de inventario (3+3 antenas, 3 SHT4X, cortes no alineados) viene de
  la guía, no de DISENO, y el validador la sigue exigiendo.
- `role` de todos en `CLIENT`: el `CLIENT_BASE` de N3 dependía de su sitio.
- Los candidatos del plan van sólo como comentario: no son asignaciones y nunca
  van en `surveyed`.

### Next steps / open questions
- Llenar los sitios en terreno; confirmar qué unidad lleva qué antena y sensor.
- Siguen abiertos: slot 47 de San Joaquín, chip de las T-Beam (SX1262/SX1276).

---

## 2026-10-26 — Scripts sin instalación + correcciones de inventario
**Time:** 09:00–09:45 (aprox)
**User request:** (1) explicar lo de la asimetría de antenas; (2) el gateway no
es un SenseCAP, es una LILYGO conectada a una Raspberry Pi o Jetson; (3) las
LILYGO son T-Beam LoRa32; (4) la antena de goma cubre 902–928 MHz; (5) San
Joaquín hoy está en LONG_TURBO pero debe quedar en MEDIUM_FAST; (6) ok a no
tocar el monorepo; (7) explicar cómo se cae field_testing con tramas PBX
válidas. Y: no usar instalación; un "main.py" o similar para configurar nodos y
para el receptor del channel_study.

### Actions taken
- **Programas en la raíz, sin instalar el repo:** `configure.py` (validate /
  show / provision / inspect, con `--node`) y `receiver.py` (el receptor; la
  clase pasó a `channel_study/listener.py` para no tener dos `receiver.py`).
  Eliminados `meshtastic_platform/__main__.py` y los `[project.scripts]`;
  `requirements.txt` nuevo; paquete desinstalado del venv para verificar.
  `pyproject.toml` queda sólo para que el gateway pueda depender del código.
- `rapa-nui.yaml`: GW → LILYGO T-Beam (host RPi/Jetson); los 6 SenseCAP son
  N1–N5 + **N6 en Vaitea** (plan §1.5: "5 en el cluster + 1 en Vaitea"), goma,
  sin sensor; antenas de goma 902–928 MHz; R1/R2 T-Beam.
- `bench-lilygo.yaml`: hardware T-Beam; advertencia SX1262 vs SX1276.
- `san-joaquin.yaml`: pasa de histórico a despliegue vivo con la configuración
  OBJETIVO (MEDIUM_FAST, slot 47 propuesto, roles 1↔3 intercambiados según plan
  §2.6, antenas de serie asumidas); el estado previo (LONG_TURBO, slot 17 por
  hash = 923,25 MHz) queda documentado en el encabezado.
- Validador: `shared_channels()` — `validate --all` avisa de despliegues con el
  mismo preset y slot (con los PSK globales, se escuchan entre sí).
- `plot_panels` / `analyze_phy`: `--preset` obligatorio (es propiedad de los
  datos; el registro describe un objetivo).
- `tests/test_scripts.py`: ambos scripts ejecutados como subprocesos desde otro
  directorio. 174 tests verdes con el repo sin instalar; equivalencia contra el
  código viejo re-verificada (0 fallas).
- Punto 7 verificado: `field_testing/mesh_receiver.py` lee `self.capture_content`
  (nunca asignado) sólo en el camino de la trama PBX VÁLIDA → `AttributeError`.
  La librería entrega cada paquete en `DeferredExecution` (`mesh_interface.py`
  ~1663, `util.py` ~307), que atrapa la excepción, imprime el traceback y sigue:
  el programa no muere, pero cada mensaje PBX válido se pierde del log.

### Decisions
- **Se corrige mi inferencia anterior:** San Joaquín corre LONG_TURBO (dato del
  usuario; el propio `report/README.md` ya lo decía). Borrada la memoria
  `san-joaquin-preset-measured`.
- **Slot 47 para San Joaquín** (propuesto): el banco (41) está en el mismo
  campus y con los mismos PSK; en el mismo slot se mezclarían las mallas y E6
  cargaría el canal del testbed.
- **N6 con antena de goma** (la que queda). Por el criterio de DISENO §2.5 (fibra
  donde el margen es más estrecho), Vaitea (+25,6 dB al GW) la merecería: se
  deja anotado, decide el usuario.
- **hop_limit 1** en Rapa Nui aunque se agregue Vaitea: N6 llega directo al GW;
  sube a 2 sólo si se agrega un nodo más allá de Vaitea.

### Outcomes
- Uso: `python configure.py ...` y `python receiver.py ...` desde un clon con
  `pip install -r requirements.txt`; funcionan desde cualquier directorio.
- `validate --all`: sin errores; los avisos de antena fuera de banda
  desaparecieron.

### Next steps / open questions
- Confirmar el slot 47 de San Joaquín, sus antenas y si p1/p2 son T-Beam.
- Confirmar el transceptor de cada T-Beam (SX1262 vs SX1276).
- ¿Fibra en N6 (Vaitea) en vez de N4? Y el acceso a Vaitea (día 1).
- Reconciliar DISENO §2.4 con j.4 (asimetría 0 dB, no 1,0 dB).

---

## 2026-10-23 — Creación de `meshtastic-platform` según REFACTOR-PLATFORM-GATEWAY
**Time:** 16:00–17:15 (aprox)
**User request:** seguir las directivas de `REFACTOR-PLATFORM-GATEWAY.md`; este
repositorio contiene sólo la plataforma, basada en el proyecto anterior
(`meshtastic-testbed-platform`) y modificada para tener más nodos.

### Actions taken
- Lectura completa de la guía, `DISENO-ANTENAS-SENSORES.md`, el `CLAUDE.md` y la
  memoria del monorepo, `docs/troubleshooting.md`, y del plan
  `SASIPA/PLAN-POC-MESH-LORA-RAPANUI.md` (§1.2, §1.7–1.9, §2) más
  `SASIPA/data/sitios_sasipa.json` (coordenadas y catastro de los sitios).
- Línea base del monorepo verificada **sin modificarlo**: 164 tests verdes; el
  `git status` quedó idéntico antes y después.
- **Decodificador extraído una sola vez** (`meshtastic_platform/decode/`):
  `decode()` puro (sin reloj, sin E/S, sin deduplicación), una dataclass por
  payload, envolvente común, `hops_taken` calculado aquí, `DecodeStats` para lo
  no mapeado.
- **Prueba de equivalencia contra el código viejo**: un arnés en el scratchpad
  ejecuta en modo sólo-lectura el `MeshReceiver` del gateway y el de
  field_testing del monorepo, con reloj inyectado, y compara cada payload
  publicado contra `decode()` + un mapeo de referencia (el que heredará el
  gateway). Corpus de 271 paquetes × 2 modos de `capture_content` = 528
  payloads: **0 fallas**; sólo dos divergencias, clasificadas y deliberadas:
  D1 (`hopLimit` ausente con `hopStart` presente → antes `None`, ahora
  `hopStart`) y D2 (`rxSnr` ausente con `rxRssi` presente → antes `None`, ahora
  0,0 dB). El camino del sweep del `CadencePdrTracker` también coincide.
- Hallazgo del arnés: el receptor de field_testing lanza
  `AttributeError: capture_content` en **cada** trama PBX válida (86 de 86) —
  la divergencia entre copias que la guía anticipaba en §0.1.
- Paquete instalable (`pyproject.toml`, `pip install -e .`), sin ningún
  `sys.path.insert`; funciona desde cualquier cwd.
- `radio/`: `config.py` (fuente única; PSK con carga perezosa pero ruidosa),
  `presets.py` (catálogo, ToA, sensibilidad; agrega LONG_TURBO, que faltaba),
  `regulatory.py` (slot → frecuencia como el firmware, hash djb2, bandas
  SUBTEL j.3/j.4, `tx_power` derivado, potencia efectiva con tx_power sin fijar).
- `registry/`: loader estricto (clave desconocida = error), modelo, catálogo de
  hardware y validador V1–V8 + I5, S1 (cortes no alineados), S2 (gateway sin
  sensor), C1 (escalado de cadencias sólo en el banco), M (nombre = archivo).
- `deployments/`: `rapa-nui.yaml` (6 SenseCAP N1–N5 + GW según DISENO §2.6,
  más R1/R2 receptores portátiles), `bench-lilygo.yaml` (6 LILYGO a −9 dBm +
  R1), `san-joaquin.yaml` (histórico, tal como fue).
- `provision/`: plan puro (registro → pasos CLI), preflight (identidad, MCU,
  modelo, firmware, pertenencia a otro despliegue), ejecución con reporte de
  fallas, PBX vía API para PSK, e inspector extendido (tx_power derivado, EIRP
  vs tope, slot, cadencias, sensor vs telemetría ambiental, GPS vs flujo de
  posición, smart position, fixed_position, firmware, modelo).
- `channel_study/`: receptor (`python -m channel_study.receiver`), sinks
  terminal/CSV/JSONL, huecos en vivo a 1,5× la cadencia, resumen por nodo
  (niveles sólo con paquetes directos), `session.json`, propagación de los
  datos del registro de ambos extremos (`tx_*`, `rx_*`) a cada registro.
- `channel_study/analysis/`: `plotstyle.py` (autoritativo; familias desde
  `radio.presets`, roster configurable desde el registro, más marcadores sin
  colores nuevos), `plot_panels.py` y `analyze_phy.py` (cadencias y preset
  desde el registro, `--deployment` obligatorio), y `plot_session.py`, que
  reemplaza a `plot_data.py` llevándolo a conformidad IEEE (7,16 in, sin
  títulos, PDF + PNG con dpi explícito, procedencia en el caption).
- Tests (unittest): 164 verdes. `tests/test_dependency_rule.py` convierte en
  test el grep de §1, la ausencia de `sys.path.insert` y la invariante I1.
  CI en `.github/workflows/ci.yml` (tests + `validate --all` + grep).
- Documentos: README, `CLAUDE.md`, `docs/flashing.md` (§4.5; enlaces oficiales
  verificados), `docs/troubleshooting.md` (mitad de radio + entradas nuevas),
  `docs/project-overview.md`, memoria en `.claude/memory/`. Movidos sin cambios
  con nota de procedencia: `report/`, ADR-0001, `docs/testbeds/san-joaquin.md`,
  `docs/scalability/README.md`.
- **Error propio, corregido:** siete archivos de `channel_study/` se
  escribieron por error en `network-platforms/channel_study/` (fuera del repo,
  faltaba el segmento `meshtastic-platform/`). Se detectó al fallar un import,
  se verificó que el directorio sólo contenía esos siete archivos, se movieron
  al repo y se eliminó el directorio vacío; `network-platforms/` quedó como
  estaba.

### Decisions
- **No se modificó el monorepo.** La guía (§8.1) pide extraer `decode()` dentro
  del monorepo; tiene trabajo sin commitear (incluidos los golden de la etapa
  1). Se preservó el motivo —la equivalencia se prueba mientras el código viejo
  existe para discrepar— corriendo el código viejo en sólo-lectura. Alternativa
  rechazada: editar el monorepo en una rama.
- **D1/D2 se corrigen en el decodificador.** Con `hop_limit: 1` (Rapa Nui y el
  banco) cada paquete relayed llega sin `hopLimit`; el código viejo lo reportaba
  `None` y E1 (¿malla o estrella?) habría perdido justo esos saltos.
- **Región/preset/slot por despliegue en `meta`; el resto de la radio, global en
  `radio/config.py`.** Alternativa rechazada: preset global, incompatible con
  un San Joaquín histórico distinto de Rapa Nui.
- **Posiciones `planned` separadas de `surveyed`.** Las coordenadas del GIS son
  tentativas; tratarlas como relevadas habría vaciado V6. El ejemplo de la guía
  las ponía como `surveyed`.
- **`tx_power` derivado por igualdad.** A slot 41 (j.4) todas las antenas dan
  22 dBm; el ejemplo de la guía (21 con channel_num 41) contradice su propia
  tabla §4.1, y DISENO §2.4 asume j.3. Se registró 22 y se dejó la nota.
- **GW es un SenseCAP** (DISENO §2.6), aunque el plan §3.1 diga LILYGO.
- **San Joaquín registra LONG_FAST** (lo que muestran los datos), no LONG_TURBO
  (lo que decía `radio_config.py` desde el 2026-07-21, commit 7dbe451).
- **`meta.deployment` debe coincidir con el nombre de archivo** (un solo
  nombre por despliegue; el ejemplo de la guía usaba `rapa-nui-sasipa`).
- **Se quitó `via_mqtt` del envelope**: el grep de §1 debe dar cero; el campo
  sigue en `raw` y en el JSONL.
- **`CLAUDE.md` y `.claude/` en `.gitignore`**, como en el monorepo, aunque §9.4
  prevé skills versionadas en `.claude/skills/` (queda anotado en el `.gitignore`).
- Las skills de §9 no se instalaron: son especificaciones en revisión.

### Outcomes
- `pip install -e ".[analysis]"` e imports funcionan desde cualquier cwd.
- 164 tests verdes; `meshtastic-platform validate --all` sin errores; el grep de
  §1 devuelve cero resultados.
- Equivalencia probada contra el código viejo (0 fallas, D1/D2 clasificadas).
- Sesión sintética grabada con los sinks reales → `plot_session.py` produce
  figuras conformes (revisadas visualmente: cortes en los huecos, inicio/fin
  por forma y etiqueta).
- Nada commiteado: el usuario no lo pidió.

### Next steps / open questions
- Reconciliar DISENO §2.1–2.4 con el slot 41 (asimetría predicha 0 dB, no 1,0).
- Confirmar si el GW es SenseCAP o LILYGO; registrar el modelo de las LILYGO.
- La antena de goma de serie es de 868–915 MHz: fuera de banda a 925 MHz
  (aviso V4 en N3, N5, GW). ¿Cambiarla antes del viaje?
- Confirmar el preset real de San Joaquín leyendo una radio.
- Grabar una sesión real con una LILYGO (cierra la etapa 5 de la guía).
- Etapa 6: portar al gateway el mapeo de payloads (el del arnés), PDR y publish,
  con su mitad de los golden — ojo: los tests viejos que esperan `hop=None` sin
  `hopLimit` codifican el bug D1.
- Commit inicial cuando el usuario lo indique.
