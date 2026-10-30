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
- Las etiquetas físicas de N1-N6 son los propios refs (usuario, 2026-10-30),
  así que `label:` queda en null a propósito: una etiqueta igual al `ref` sería
  una segunda copia libre de desincronizarse, y además metería N1-N6 en la
  lista de palabras prohibidas de `test_hard_rules`. Anotado como comentario en
  el encabezado de los nodos de `rapa-nui.yaml`. GW, D1 y D2 también llevan su
  ref como etiqueta (usuario, 2026-10-30), así que `label:` queda en null en
  todo el archivo. Queda por saber qué caja es N3.
- **URGENTE — secreto en git:** `deployments/psks-san-joaquin-longturbo.txt`
  está **trackeado y no ignorado**, con los dos PSKs reales del campus
  (`LORA_TELEMETRY_CHANNEL_PSK`, `LORA_MSG_CHANNEL_PSK`, 32 bytes cada uno).
  Entró en el commit `cebcf4f`. Viola la regla 8 (PSKs solo en `.env`). Borrar
  el archivo ahora NO lo saca del historial: hay que rotar las dos claves o
  reescribir el historial. Pendiente de decisión del usuario.
- Quedó huérfano ese mismo `.txt` al borrarse `san-joaquin-longturbo.yaml`.
- `docs/testbeds/san-joaquin.md`, `.env.example` y el comentario de
  `bench-lilygo.yaml:37` siguen mencionando san-joaquin; se dejan hasta saber
  cómo se llama el deployment que lo reemplace.
- ...
```

---

## 2026-10-30 — Identidades duplicadas entre deployments; reconexión serie y el bloque pbx
**Time:** 11:30 (aprox)
**User request:** por qué el aprovisionamiento se niega cuando el node_id está
en otro deployment; limpiar esos ids dejándolos en null (solo `node_id` y
`mac`); si las SenseCAP tienen MAC dinámica; si es posible reconectar el puerto
serie tras un reboot o desenchufe; si D1/D2 deberían tener campos `ble` y
`serial` para servir a la mesh PBX.

### Actions taken
- Diagnosticado el rechazo: `identity.preflight` recorre TODOS los archivos de
  `deployments/` y bloquea si el `node_id` del equipo aparece en otro con un
  `ref` distinto (`identity.py:88-94`). Seis radios estaban registradas con dos
  nombres: `rapa-nui` N1–N3 ↔ `san-joaquin` 1–3, y N4–N6 ↔ `office-bench` N1–N3.
- `deployments/rapa-nui.yaml`: `node_id` y `mac` a `null` en N1–N6 (11 líneas).
  Nada más tocado. Copia del original en el scratchpad de la sesión.
- Verificado: `validate --all` ✓ en los seis archivos; cero `node_id`
  compartidos con refs distintos.
- Revisado el camino de desconexión serie en la librería `meshtastic` 2.7.8 y
  el ciclo de `receiver.py`.
- Revisado `plan.serial_settings` / `bluetooth_settings` y la invariante X.
- Borrado `deployments/san-joaquin.yaml` (`git rm`, pedido del usuario: el
  campus pasa a tener más nodos y se reescribirá). El usuario ya había borrado
  antes `office-bench.yaml` y `san-joaquin-longturbo.yaml` en el árbol de
  trabajo. Quedan tres deployments: `bench-lilygo`, `mini`, `rapa-nui`.
- Verificado tras el borrado: `validate --all` ✓ en los tres; 209 tests OK.
- `git rm` de `deployments/psks-san-joaquin-longturbo.txt` y patrón de
  `.gitignore` ampliado de `psks.txt` a `psks*.txt`, para que un
  `psks-<deployment>.txt` no se pueda volver a commitear.
- El primer intento del patrón llevaba comentario al final de la línea y
  **no filtraba nada**: `.gitignore` solo reconoce `#` al inicio de línea.
  Detectado al probarlo con `git check-ignore`, no al leerlo.
- **Nuevo:** `meshtastic_platform/registry/export.py` y `configure.py show
  --csv DIR`: una planilla por familia de MCU, una fila por nodo. Generada y
  nunca leída de vuelta — el YAML sigue siendo la única declaración de la malla
  (regla 1). Una celda de cadencia vacía significa que el nodo no emite ese
  flujo (V3b: ausente, nunca 0); el resto de las celdas vacías son la lista de
  pendientes para terreno. `tests/test_export.py`, 10 pruebas (219 en total,
  OK). README actualizado.
- **Nuevo campo `site.asset_type`** (modelo, loader, `_template.yaml`, las
  nueve entradas de `rapa-nui.yaml` en null, columna en la planilla y en la
  tabla de sitios de `show`). Es un registro: dice a qué activo del operador
  está atornillado el nodo, en el vocabulario del operador. No se valida contra
  ninguna lista en el código — el vocabulario pertenece al deployment, no al
  código (regla 1). 222 tests OK.
- `deployments/sasipa-info/activos_sasipa.csv` tiene 16 activos con la columna
  `layer` en exactamente dos valores (8 y 8), más `codigo` y `nombre`.
- Llenados `site.name`, `asset_code` y `asset_type` de N1-N6 y GW desde
  `sasipa-info/sitios_sasipa.json`, tras verificar que las nueve coordenadas
  `planned` del registro coinciden EXACTAMENTE con las del JSON (comparación
  programática, no a ojo). N1 ESRK-1 Estanque, N2 CSUBS-31 Captacion, N3 ESPP-2
  Estanque, N4 ESLC-1 Estanque, N5 Relay sin activo (1088 m del más cercano),
  N6 y GW comparten Central SASIPA. D1/D2 siguen sin sitio.
- N4 lleva ahora un `notes:` propio: el JSON marca una posible transposición
  ESVAI-1/ESLC-1 (Cota_Fondo 151.54 m contra SRTM 100 m y curvas 94.9 m). Va en
  el nodo y no en un comentario, para que viaje con el dato.
- El usuario repobló `rapa-nui.yaml` en el IDE: N1, N2, N4-N6 recuperaron
  `node_id`/`mac`/`firmware` y GW, D1 y D2 tomaron las identidades que estaban
  en los archivos borrados (`!6c74104c`, `!6c72f308`, `!6c743130`). Solo N3
  sigue sin identidad. Ya no hay conflicto cruzado porque los otros archivos no
  existen: la malla quedó consolidada en un solo deployment.

### Decisions
- **Se limpia `rapa-nui`, no los otros archivos.** Sus seis entradas están
  `status: planned`: un nodo planificado no debe reclamar una radio concreta.
  `office-bench` y `san-joaquin*` describen radios que existen hoy y conservan
  sus identidades.
- **Marcar `status: retired` NO sirve** para liberar una identidad:
  `Registry.by_node_id` recorre todos los nodos sin mirar `status`
  (`model.py:191`). Tiene que ser `node_id: null`.
- **La MAC de las SenseCAP no es dinámica.** Es la dirección BLE *random
  static* del FICR del nRF52840: inmutable, sobrevive a un reflasheo. Se
  verifica en los datos — el `node_id` son sus cuatro bytes bajos, y los cinco
  primeros bytes registrados eran todos ≥ `0xC0`, firma de random static. La
  MAC faltante de N3 nunca se registró (viene `null` desde `32ae967`): un dato
  no copiado, no una propiedad del equipo.
- **No se agregan campos `ble:`/`serial:` de configuración a D1/D2.**
  Contradiría la decisión del 2026-10-26 (el enlace radio↔PBX es del proyecto
  PBX). El mecanismo ya existe y está keyeado por `function: pbx`, que hace que
  la plataforma no escriba ni serie ni Bluetooth (`plan.py:142,153`).
- **D1/D2 quedan como `access` por ahora** (usuario, 2026-10-30). Son las
  únicas radios por las que una persona llega a la malla desde el teléfono;
  convertirlas en `pbx` apagaría la mensajería antes de tener el reemplazo de
  meshpbx andando.
- **No se implementó reconexión serie** (usuario: solo evaluar).
- **No se nullearon los campos de `san-joaquin.yaml`**: se borró el archivo
  entero. Probado antes en copia — nullear `node_id`/`mac`/`firmware` ahí daba
  6 errores (V1 y V5), porque 1–3 son `status: deployed` en un archivo
  `kind: field` (`validate.py:303`).

### Outcomes
- Seis conflictos de identidad resueltos; `validate --all` ✓.
- Hallazgo: `User.macaddr` está **DEPRECATED** en el protobuf de Meshtastic
  (campo 4). Si una versión futura del firmware deja de poblarlo, `inspect`
  reportará MAC vacía en radios con dirección estable y la comprobación V1
  «node_id = bytes bajos de la mac» (`validate.py:172`) se queda sin insumo.
  El `node_id` es la identidad durable; la MAC es corroboración.
- Hallazgo (regla 9): al desconectarse el puerto, `receiver.py` **no se entera**.
  La librería mata su hilo lector, publica `meshtastic.connection.lost` y pone
  `stream = None`; el bucle sigue, `rx.tick()` anuncia gaps de toda la malla
  (se lee como silencio de la malla, no como notebook sin radio) y
  `own_position()` no lanza: `getMyNodeInfo()` es una búsqueda en el diccionario
  en memoria (`mesh_interface.py:1075`) y devuelve el último fix para siempre,
  contado como `repeated`, nunca como error.

### Next steps / open questions
- Si se implementa reconexión: detectar y **registrar el corte** primero (un
  intervalo en `session.json` y los gaps de esa ventana suprimidos) — una
  reconexión sin registrar el corte da datos que mienten. Después reconectar
  (hay que construir un `SerialInterface` nuevo; no hay `reopen()`), exigiendo
  path `/dev/serial/by-id/`, reverificando `node_id` y sin re-suscribir a
  pubsub.
- Al aprovisionar Rapa Nui, las seis entradas entran ahora por el camino de
  *commissioning*: hay que copiar `node_id` y `mac` al archivo.
- La guía SASIPA usa `!0b64122b` como ejemplo de comillas YAML
  (`07-verificacion.tex:34`); ese id pertenece hoy a `san-joaquin:1`. Ofrecido
  cambiarlo por uno inventado, sin respuesta.
- `external/meshtastic-gateway/deployments/` todavía no existe: la regla 2 no
  tiene nada que sincronizar.
- Si meshpbx necesita que el registro diga dónde está su radio, el lugar es el
  bloque `pbx` (un registro, nunca escrito): `link`, `uart_baud`, dirección BLE.
  Decisión pendiente del proyecto PBX.

---

## 2026-10-29 — La guía SASIPA con la plantilla de trazabilidad
**Time:** 12:40 (aprox)
**User request:** aplicar a la guía `docs/sasipa-despliegue/` el estilo de
documento de `trazabilidad_latex.zip` (copiado por el usuario a esa carpeta).

### Actions taken
- `main.tex`: `report` → `article` 11pt; portada de la plantilla (logo
  `figuras/logo16.pdf`, título en tres líneas, centro, autor y cargo, fecha),
  resumen entre `\hrulefill` con la tabla de alcance, índice.
- `preambulo.tex`: márgenes, `setstretch{0.8}`, `parskip`, `float`, marcas
  `\pendiente{}`/`\medir{}`/`\dms{}`; fuera `titlesec`. El recuadro
  `pendiente` pasó a llamarse `abierto` (choque de nombres).
- `secciones/`: chapter → section, section → subsection; "capítulo \ref" →
  "sección \ref". Flotantes `[H]`.
- `docs/diagrams/palette.tex`: nuevo `\paletteKeepFont`, que salta la elección
  de Times; sin él (todos los diagramas) nada cambia.
- Tres figuras ajustadas al ancho de Computer Modern (topología, procedimiento,
  mensajería); `\figuranuestra` vuelve a interlineado 1.

### Decisions
- Tipografía de la plantilla (Computer Modern) en lugar de Times: es lo más
  visible del estilo. Volver a Times es borrar `\def\paletteKeepFont{}`.
- Escrito "Cyber-Physical" donde la plantilla dice "Ciber-Physical".
- Anexos con la numeración por omisión de `article` (A, B, …).

### Outcomes
- `make` construye `guia-sasipa.pdf`, 24 páginas (eran 37), 1 aviso de caja
  (el filete bajo el resumen, igual que en la plantilla).

### Next steps / open questions
- Ninguna marca `\pendiente{}` en el texto todavía: los puntos abiertos siguen
  en recuadros `abierto`.

### Más tarde: herramientas (13:10 aprox)
- Pedido: listado de herramientas para armar el set-up; para la abrazadera
  basta un destornillador, proponer uno.
- `secciones/08-sitio.tex`, nueva §8.1 "Qué llevar": tabla banco/terreno
  (`tab:herramientas`). Propuesto: **destornillador plano 6,5 × 150 mm**.
  La abrazadera de stock del P1 Pro es de tornillo sinfín para postes de
  70–100 mm (fuente de terceros: no se encontró guía de montaje de Seeed). La
  ranura de su cabeza la toma cualquier punta plana; se descartó el de vaso
  porque exige conocer la medida del hexágono, que nadie confirmó.
- Dos `\pendiente{}` (primeras marcas rojas del documento): la medida real de
  la cabeza del tornillo, y el herraje de las antenas fiberglass (si usan
  abrazadera en U, hace falta una llave).

---

## 2026-10-28 — Guía de despliegue SASIPA en LaTeX
**Time:** 16:40 (aprox)
**User request:** generar un proyecto .tex dentro de `docs/`, gitignoreado, con
una guía de despliegue y configuración para los nodos de SASIPA; el usuario
provee diagramas y yo defino dónde van los suyos y los míos. Asumir que los
mensajes de texto van por la app celular de Meshtastic; `meshpbx` lo integra
él después.

### Actions taken
- Preguntado idioma y alcance antes de escribir (una sola interrupción): la
  respuesta fue **español para el equipo CPS-RTC** y alcance **nodos + gateway +
  mensajería**, dejando fuera R1/R2 y el estudio de canal.
- Creado `docs/sasipa-despliegue/`: `main.tex`, `preambulo.tex`, `Makefile`,
  `README.md`, 12 capítulos en `secciones/00..11`, 4 anexos `A..D` y 4 diagramas
  TikZ en `figuras/`. Agregado `docs/sasipa-despliegue/` al `.gitignore` con el
  mismo razonamiento que `report/`.
- Todo valor citado se verificó contra el repositorio, no de memoria: salida real
  de `configure.py show -d rapa-nui` y de `validate`, los siete pasos de
  `provision/plan.py`, la tabla de invariantes del encabezado de
  `registry/validate.py`, `.env.example`, `requirements.txt`.
- El preámbulo hace `\input{../diagrams/palette}`: la guía usa la misma
  tipografía y paleta que los diagramas del repo.

### Decisions
- **Las figuras tienen dos mecanismos distintos.** `\figuranuestra{}` hace
  `\input` de un TikZ de `figuras/`; `\figurasasipa{}{}{}` deja un hueco que
  en el PDF se ve como una caja punteada con la especificación de lo que debe
  mostrar, y desaparece sola cuando aparece `figuras/<nombre>.pdf|.png`. Nadie
  tiene que editar `.tex` para llenar un hueco. Rechazado dejar el hueco
  invisible: un documento que esconde lo que le falta contradice la regla 9.
- **La guía declara explícitamente que no es la fuente de verdad** y cada tabla
  dice con qué comando se reproduce; el README lista los cuatro lugares a revisar
  cuando cambie el registro.
- babel-spanish no está instalado en esta máquina: el preámbulo lo usa si existe
  y si no traduce los rótulos a mano, así que compila igual.

### Outcomes
- `make` construye `guia-sasipa.pdf`, 37 páginas, 5 avisos de caja menores.
- 205 tests OK; `validate --all` ✓ en los seis deployments.
- Dos hallazgos que la guía deja anotados como puntos abiertos, no resueltos por
  mí: (1) **S1 se cumple a medias** — fiberglass {N1,N2,N6} y sensorizado
  {N1,N2,N3} se solapan en dos unidades; el momento de corregirlo es al etiquetar
  las unidades físicas, porque después es una visita a terreno. (2) **la
  mensajería no se puede operar con el registro actual**: no hay radios de mano,
  y las tres salidas (emparejarse al GW, emparejarse a un nodo en sitio, agregar
  radios de mano) tienen costos distintos; emparejarse al GW contradice que sea
  `CLIENT_MUTE`.

### Next steps / open questions
- El equipo decide S1 y si se agregan radios de mano al registro.
- Las cuatro figuras del equipo: `mapa-sitios`, `sensecap-instalado`,
  `perfiles-enlace`, `gateway-central`.
- Si la guía se va a entregar a SASIPA y no solo al equipo, hay que reescribirla:
  está en registro técnico, no en registro de terreno.

---

## 2026-10-28 — El pin manual del dashboard y un GPS que no fija
**Time:** 18:40 (aprox)
**User request:** (1) ¿dónde va el cambio para que el usuario del gateway pueda
ubicar a mano las coordenadas de un nodo y poner un pin en el dashboard: en la
plataforma o en el gateway? (2) "¿Seguro que se puede registrar mi posición
dinámica con el GPS embebido de la radio? La dejé horas en una ventana abierta y
no engancha ninguna constelación."

### Actions taken
- Revisado el gateway (submódulo, solo lectura): la función YA está construida.
  `monitor/app.py:64-81` resuelve la posición por nodo como `surveyed` cuando
  existe y, si no, la última reportada por GPS, con un campo `source` que dice
  cuál es; `gateway/deployment.py:55` parsea `site.surveyed` ("for the
  dashboard's map") y rechaza un lat/lon en 0 como "looks unset, not surveyed";
  `monitor/templates/map.html` dibuja el marcador Leaflet y ya tiene escrito el
  caso vacío.
- Inventariado qué nodos tienen pin hoy: san-joaquin y san-joaquin-longturbo
  1/2/3/p1/p2 sí; rapa-nui ninguno (los 9 bloques en null, regla 11); los `gw`
  no (sin `node_id` y sin bloque `site`).
- `docs/troubleshooting.md`: corregida la fila `0 fixes in M samples` (decía
  "un cold start toma minutos", que es cierto para una placa sana y engañoso
  para la falla que el usuario tiene) y agregada la subsección
  "A GPS that never fixes" con la escalera de diagnóstico: `inspect` →
  `--noproto` para ver el log del firmware → antena GPS en el u.FL → variante
  de firmware (pines y riel del AXP192) → módulo u-blox falsificado.

- Log del `--noproto` del usuario: `U-blox 6 detected`, soft 7.03 (45969), hard
  00040007, `GNSS module config saved!`, y luego
  `Publish pos@0:2, hasVal=0, Sats=0, GPSlock=0` con `lat=0 lon=0`. El módulo es
  genuino y el firmware lo maneja: descarta módulo ausente, pines y variante.
  Queda la cadena de RF (u.FL / antena) como sospechoso, a confirmar mirando si
  `Sats` sube durante 10-15 min (el log mostrado era de 3 s después del boot).
- `channel_study/track.py`: ese `lat=0 lon=0` es lo que publica el firmware sin
  lock. Hoy la librería no entrega la clave `latitude` cuando vale 0 (proto3
  omite defaults, `mesh_interface._fixupPosition`), así que el Tracker ya lo
  contaba como `no_fix` por casualidad. Endurecido: (0, 0) se descarta explícito
  y se cuenta aparte (`discarded_zero`, visible en los contadores y en
  `session.json`). Test nuevo; 205 tests OK.
- `docs/troubleshooting.md`: agregado "Reading the GPS log" — qué cierra el
  `U-blox 6 detected` y por qué el contador `Sats` es el instrumento.
- Segundo log (`message.txt`): el sniffer R1 (`!6c72f308`) está DECODIFICANDO la
  malla del campus. `fr=0x0b64122b` es el nodo 1, `Use channel 0 (hash 0xec)` +
  `Use AES256 key!` → la PSK de `telCPS_RTC` calza; `Portnum=3` POSITION con
  `siv=18 pdop=98 msl=612`; `hopStart=2 HopLim=1 relay=0x2` → lo retransmitió el
  nodo 2 (`!7c70da02`); `No rebroadcast: Role = CLIENT_MUTE` (I5 confirmado en
  vivo). `rxSNR=-15` decodificado confirma SF alto: a MEDIUM_FAST (SF9, piso
  -12.5 dB) ese paquete no habría pasado — evidencia independiente de que la
  malla instalada es LONG_TURBO.
- La posición que reporta el nodo 1 queda a 10.7 m del punto relevado en el
  archivo (dlat -10.7 m, dlon -1.0 m): exactamente la lectura de error de GPS
  que `registry/model.py` protege. NO se escribe `msl=612` en `surveyed`.
- `docs/troubleshooting.md`: nueva sección "The radio drops packets before the
  recorder sees them" por el `WARN [Router] ToPhone queue is full, drop packet`
  del log — bajo `--noproto` es esperable (no hay cliente drenando), pero
  grabando es el único error de medición que los datos no pueden delatar: se ve
  como pérdida de canal en `gaps.csv`.

### Decisions
- El pin manual se escribe en `deployments/<mesh>.yaml` → `site.surveyed`, en la
  plataforma, y el gateway lo lee de su copia idéntica. **Rechazado:** darle al
  dashboard una UI para arrastrar el pin y guardarlo en su base — crea una
  segunda fuente de verdad para dónde está un nodo y rompe la propiedad que
  `registry/model.py:76-85` protege (la diferencia entre `surveyed` y lo que el
  nodo reporta se lee como error de GPS). Si se quiere ayuda en el mapa, que
  imprima el snippet YAML para pegar en el archivo.
- Horas sin fix se trata como falla de hardware/configuración, no como
  geometría: el síntoma se separa con el log del firmware (`--noproto`), que
  distingue "módulo no detectado" de "módulo sin cielo".

### Outcomes
- Nada que construir para el pin: es dato (llenar `surveyed`) más la copia a
  mano al gateway (regla 2).
- Entrada de troubleshooting reescrita por síntoma.

### Next steps / open questions
- Resultado de `meshtastic --port <port> --noproto` en la T-Beam del sniffer:
  decide si el módulo GPS existe o no para el firmware.
- Si el GPS está muerto: evaluar la posición provista por el teléfono vía BLE
  (el firmware la adopta como propia y `getMyNodeInfo()["position"]` la
  entrega, sin tocar código), teniendo en cuenta que entonces `sats_in_view`
  viene vacío y `gps_time` es del teléfono — la lógica de `repeated` depende de
  que ese timestamp avance.
- Agregar bloque `site` al `gw` de San Joaquín cuando se sepa dónde queda la
  Raspberry.

---

## 2026-10-28 — Sniffer del campus San Joaquín: deployment del estado instalado
**Time:** 10:30 (aprox)
**User request:** probar la grabación de coordenadas GPS con una LILYGO conectada
por USB al PC, escuchando la malla que está instalada hoy en el campus San
Joaquín. "Todos los datos están en el proyecto viejo."

### Actions taken
- Localizado el monorepo viejo en
  `~/Desktop/Personal-AI-Studio/meshtastic-testbed-platform` (solo lectura) y
  extraído de ahí el estado real de la malla:
  - `src/common/radio_config.py:46` → `LORA_PRESET = "LONG_TURBO"`, región ANZ,
    canales `telCPS_RTC` / `msgPUC_NET`, precisión 32, `LOCAL_ONLY`,
    `channel_num` nunca escrito.
  - `mesh_config.json` → node_ids, `hop_limit: 2`, roles, cadencias
    (1-3: device 120, environment 120, position 600; p1/p2: device 600,
    position 1800) y posiciones relevadas. Coinciden con `san-joaquin.yaml`.
  - `psks.txt` → `LORA_TELEMETRY_CHANNEL_PSK` y `LORA_MSG_CHANNEL_PSK`, los
    mismos nombres de variable que lee esta plataforma.
- Calculado con nuestro propio código el slot que el firmware deriva del nombre
  del canal primario: `resolve_slot('ANZ','LONG_TURBO',None,'telCPS_RTC')` →
  **slot 17/26 = 923.250 MHz** (djb2). Confirma el comentario de
  `san-joaquin.yaml`.
- Creado `deployments/san-joaquin-longturbo.yaml`: el campus TAL COMO ESTÁ
  (LONG_TURBO, slot 17 explícito, mismos canales, nodos y cadencias) más una
  entrada `R1` de función `receiver` (T-Beam, CLIENT_MUTE, hop_limit 1,
  `intervals: {position: 900}`) para el sniffer. `validate` ✓.
- `profile.channel_psks`: el mensaje de error ya no recomienda
  `openssl rand -base64 32` (no existe en Windows y omite el prefijo
  `base64:`); ahora da el one-liner de Python y aclara que la clave de una malla
  existente no se genera, se copia.

### Decisions
- **Archivo aparte en vez de tocar `san-joaquin.yaml`.** Ese archivo es el
  objetivo (MEDIUM_FAST, slot 45) y describe a dónde se va a re-provisionar la
  malla. Un receptor configurado desde él no oye NADA de lo que hay en el aire:
  otro preset, otra frecuencia, sin error, solo silencio. Además `session.json`
  habría etiquetado los datos con un preset falso, y es justo lo que
  `load_sessions()` existe para impedir.
- `channel_num: 17` explícito y no nulo: V7 rechaza un slot implícito en una
  malla viva (bien), y un receptor que derive el slot del NOMBRE seguiría el
  nombre en silencio si alguien lo edita. El valor es el que los nodos calculan.
- Las entradas de los nodos de campo van en el archivo pero **nada los
  re-provisiona**: el receptor necesita sus node_ids (para nombrar al emisor),
  sus cadencias (para anunciar silencios) y sus antenas y potencia (cada
  registro de recepción lleva los dos extremos).
- `position: 900` en R1 para que `provision` encienda su GPS; la resolución del
  trayecto la da `--track-secs 30` por USB. Quitar `position` lo deja fuera del
  aire, pero entonces no hay traza.

### Outcomes
- `validate -d san-joaquin-longturbo` ✓ (7 nodos, 923.250 MHz, cap SUBTEL j.3
  27 dBm); `provision --dry-run --node R1` imprime el plan esperado.
- 204 tests OK.

### Next steps / open questions
- **Bloqueante:** las dos claves del campus están como `base64:CHANGE_ME` en
  `.env`. Hay que copiarlas de `psks.txt` del proyecto viejo (el cargador se
  queda con la PRIMERA aparición de cada nombre, así que hay que borrar las
  líneas placeholder). `provision` se niega sin ellas; `--dry-run` no.
- La T-Beam del sniffer debe ser una NO registrada en otro deployment:
  `!6c74104c` es GW de office-bench, `!bb8106c4` y `!6c743130` son p1/p2 de
  san-joaquin. El preflight se niega a reasignarlas, a propósito.
- Confirmar si los roles de los nodos 1 y 3 están hoy como dice
  `mesh_config.json` (3 = CLIENT_BASE) o como dice la cabecera de
  `san-joaquin.yaml` (1 = CLIENT_BASE). Para escuchar no importa; para el
  análisis de saltos, sí.
- Copiar `san-joaquin-longturbo.yaml` a `meshtastic-gateway/deployments/` si el
  gateway va a medir esta malla (regla 2).

---

## 2026-10-30 — Rapa Nui: perfil de terreno, antenas, BLE
**Time:** 11:00 (aprox)
**User request:** (1) análisis de parámetros óptimos para `rapa-nui` a partir de
un perfil de heywhatsthat entre dos puntos; (2) luego: dejar `hop_limit` en 3,
antena de fibra para N2, N5 y N6, `tx_power` 30 dBm en MEDIUM_FAST, y BLE activo.

### Actions taken
- Los dos puntos del enlace son N1 (ESRK-1) y GW/N6 (Central SASIPA). Como la
  página renderiza en el navegador, el perfil se reconstruyó con SRTM 30 m
  (OpenTopoData, la misma fuente que ya usa el archivo en `alt_source`): 1.488 m,
  86 → 36 m, F1 = 8,5 m en el peor punto; 93 % de F1 con 3 m/3 m de antena y
  126 % con el GW a 6 m. Margen de enlace 63 dB en MEDIUM_FAST.
- Mismo análisis sobre los ocho enlaces candidatos: todos los nodos tienen
  línea de vista al gateway; los bloqueados son nodo-a-nodo (N2–N1 −204 % de F1,
  N4–N5 −57 %). Airtime originado de los seis nodos a 120 s: 1,63 % en
  MEDIUM_FAST contra 3,84 % (LONG_TURBO) y 5,68 % (LONG_FAST).
- `deployments/rapa-nui.yaml`: la antena de fibra pasa de N1 a N5, así el juego
  de tres queda en N2, N5 y N6 (N1, N3, N4 con la goma de fábrica).
- BLE: `provision` no escribía `bluetooth.*` en ninguna radio. Se agregó
  `plan.bluetooth_settings()` en espejo de `serial_settings()` — escribe
  `bluetooth.enabled true` en toda radio que no sea `pbx` —, el chequeo
  correspondiente en el inspector, dos tests y la fila en la tabla del README.

### Decisions
- BLE se escribe, no se asume: una radio reusada del proyecto PBX llega con
  Bluetooth apagado (`BLUETOOTH_ENABLE = False` en meshpbx), y sin esto el
  provisioning no lo devolvía. En una radio `pbx` se sigue sin tocar (ADR-0002).
- `hop_limit` queda en 3 por decisión del usuario, pese a que el terreno dice
  que la malla es una estrella sobre el gateway y que 2 bastaría.
- `tx_power_dbm: 30`: planteadas tres salidas (22 dBm derivado / antena de
  8 dBi para llegar a 30 dBm EIRP / dejar 30 literal), el usuario eligió dejar
  **30 literal**. Como eso choca con la regla dura 5, se implementó una
  excepción explícita en vez de borrar el chequeo: `radio.tx_power_policy`,
  `derived` (default, sin cambios para el resto de los despliegues) o
  `declared`. Con `declared` el número del archivo es el que `provision`
  escribe —antes se escribía siempre el derivado, así que el 30 ni siquiera
  habría llegado a la radio— y los tres chequeos V2 pasan de error a warning
  que se imprime en cada corrida. `rapa-nui` lo declara con un comentario que
  deja constancia de la decisión y de que el firmware recorta a 22 dBm.
- Archivos tocados por eso: `radio/profile.py` (campo + propiedad),
  `registry/{model,loader,validate}.py`, `configure.py` (la etiqueta decía
  "(derived)" siempre), README y la regla dura 5 de CLAUDE.md, más tres tests
  nuevos.

### Outcomes
- Antenas, BLE y `tx_power_policy` aplicados. `validate --all`: los seis
  despliegues en verde. Suite: 209 tests, OK.
- `rapa-nui` queda con `hop_limit 3`, fibra en N2/N5/N6, `tx_power_dbm 30`
  declarado (la radio emitirá 22) y BLE encendido en toda radio no-`pbx`.

### Next steps / open questions
- Al inspeccionar en terreno, `lora.tx_power` va a leer 22 y el reporte va a
  marcar diferencia contra el 30 declarado: es lo esperado, no un defecto.
- Medir `hop_start − hop_limit` en el gateway para confirmar si 3 saltos se usan.

## 2026-10-27 — Diagramas de retransmisión y acceso al canal (CSMA/CA)
**Time:** 17:10 (aprox)
**User request:** Pegó las ecuaciones del algoritmo de retransmisión y del
CSMA/CA de Meshtastic (ToA, slot, ventana de contención, tablas por SNR y por
utilización) y pidió un diagrama detallado, con buena nomenclatura de variables
(δ para el retardo), corrigiendo lo que estuviera mal.

### Actions taken
- Releídas las constantes en el firmware exacto del despliegue,
  `meshtastic/firmware` tag `v2.7.26.54e0d8d`: `RadioInterface.{h,cpp}`
  (`computeSlotTimeMsec`, `getPacketTime`, `getTxDelayMsec`, `getCWsize`,
  `getTxDelayMsecWeighted(Worst)`, `getRetransmissionMsec`),
  `RadioLibInterface.cpp` (`onNotify`, `setTransmitDelay`), `airtime.{h,cpp}`,
  `FloodingRouter.cpp`, `NextHopRouter.cpp`, `PacketHistory.cpp`.
- Verificadas las cifras con `meshtastic_platform.radio.presets` para
  `LONG_TURBO`: T_s 4,096 ms, R_b 1343 bps, ToA(37 B) 345 ms, slot 17,84 → 17 ms.
  Coinciden exactamente con `report/es/02-analitico-enlace-y-canal.md` §4.
- Creados dos diagramas TikZ en `docs/diagrams/` (mismo patrón que
  `membership.tex`: `palette.tex` + `build.sh`), construidos a PNG y PDF:
  `rebroadcast.tex` (pipeline de decisión de retransmisión, con la rama de
  duplicados) y `channel-access.tex` (lazo backoff + CAD, ecuaciones y
  ventanas sobre el eje de tiempo).
- A pedido del usuario (misma sesión, 2026-10-28), `channel-access.tex` se
  dividió en tres figuras independientes y se borró la combinada:
  `channel-access-loop` (el lazo del MAC, con δ = kσ en grande dentro de la
  caja del sorteo), `channel-access-model` (todas las ecuaciones) y
  `channel-access-window` (las ventanas sobre el eje de tiempo + las dos
  tablas). Cada una lleva su propia nota de procedencia del firmware, salvo
  `channel-access-loop`: ahí la caja del sorteo muestra solo δ = kσ y la nota
  de constantes se sacó, porque ninguna de ellas aparece en esa figura.
- El camino de interrupciones del transceptor se agregó y, a pedido del
  usuario, terminó en su propia figura: ahora son cuatro.
  `channel-access-loop` queda de alto nivel (el viaje del paquete), con las dos
  cajas de sensado anotadas con la señal que realmente leen —
  `isActivelyReceiving()` consulta por SPI los flags `PREAMBLE_DETECTED` /
  `HEADER_VALID` del SX1262 (no están cableados a DIO1), con sus timeouts de
  falsa detección; `isChannelActive()` es `scanChannel()` en modo CAD.
  `channel-access-irq` es la de bajo nivel: DIO1 (`RxDone`/`TxDone`) →
  `isrLevel0Common()` (`disableInterrupt` + `notifyFromISR`) → `onNotify()` con
  sus tres causas, el temporizador `notifyLater(δ)`, el armado
  `startSend()`/`startReceive()` → `isrTxLevel0`/`isrRxLevel0`, y dónde se
  alimenta `U_ch` (`RX_ALL_LOG`, `RX_LOG`, `TX_LOG`). Se agregó además
  `channel-access-trip`: el mismo lazo sin los recuadros de sensado ni las
  notas, para una lámina o una primera mención en el texto. En
  `channel-access-model` se sacó la función `map()` de Arduino: el exponente w
  ahora se presenta como la interpolación lineal entera que es, con su forma
  cerrada por caso. Corrección de la versión
  anterior: el ToA se contabiliza en `U_ch` en `completeSending()`, al llegar la
  interrupción de Tx, no en `startSend()`.

### Decisions
- **Correcciones a las ecuaciones pegadas** (todas verificadas en el firmware
  del despliegue, no en una versión anterior): `CWmin/CWmax` son **3/8**, no
  2/7 → CW_size = ⌊U_ch/20⌋+3 y ⌊(SNR+20)/6⌋+3, y el piso del CLIENT es
  2·CWmax = **16 slots = 272 ms**, no 14 slots/250 ms. El slot se trunca a
  **17 ms** (`uint32`), así que todo δ es múltiplo de 17, no de 17,84. R_b
  estaba invertida: R_b = SF·(BW/2^SF)·(4/d). ToA necesita N_sym explícito con
  preámbulo de 16 símbolos (82,9 ms de los 345). La rama ROUTER es **lineal**
  (`random(0, 2·CWsize)`), no 2^CWsize. U_ch cuenta TX propio **más toda**
  recepción, decodificable o no, en 6 baldes de 10 s.
- Figuras en inglés y en TikZ: es el precedente de `docs/diagrams/` y entran
  directo en el LaTeX del informe; los captions del informe quedan en español.
- No se tocó `report/es/02` §4: ya estaba correcto y las cifras coinciden.

### Outcomes
- `docs/diagrams/rebroadcast.{tex,png,pdf}`,
  `docs/diagrams/channel-access-loop.{tex,png,pdf}`,
  `docs/diagrams/channel-access-trip.{tex,png,pdf}`,
  `docs/diagrams/channel-access-irq.{tex,png,pdf}`,
  `docs/diagrams/channel-access-model.{tex,png,pdf}` y
  `docs/diagrams/channel-access-window.{tex,png,pdf}` construidos y revisados.

### Next steps / open questions
- Si el informe los usa, decidir si las etiquetas se traducen al español para
  `report/es/` o si se comparten en inglés entre ambas versiones.
- Re-verificar las constantes al subir de firmware: `CWmin/CWmax` ya cambiaron
  de 2/7 a 3/8 entre versiones, y `SNR_MAX` es +10 (no +15) hoy.

## 2026-10-27 — README multimáquina, paquetes propios y traza GPS del receptor
**Time:** 16:30 (aprox)
**User request:** (1) la sección "Channel study" del README no es clara respecto
al soporte multimáquina, y el `export` del bloque de comandos no aplica; (2) por
qué el receptor escucha sus propios paquetes y los muestra con `?` en hops, RSSI
y SNR, y si esas copias pasan por el aire; (3) que el computador + nodo registre
la posición cada 30 s-1 min para poder trazar el trayecto.

### Actions taken
- `README.md`, "Channel study": fuera `export MESH_DEPLOYMENT=my-mesh` (solo
  bash/zsh); los comandos usan `-d my-mesh` explícito. Párrafo nuevo: ambos se
  corren desde la raíz del repo en cualquier OS, el único argumento que
  pertenece a la máquina es `--port` (el receptor siempre lo necesita, a
  diferencia de `inspect`), y los directorios de salida son rutas relativas que
  los sinks crean solos (`sink/csv.py:25`, `sink/jsonl.py:22`).
- Subsección nueva "Recording from more than one machine": una radio, un
  `receiver.py`, un `--operator`, un directorio por corrida (un segundo
  receptor apuntado al mismo directorio sobrescribe su `session.json`); cada
  corrida se autodescribe (run id, operador, radio receptora, SHA-256 del
  deployment, `git describe`), y `load_sessions()` se niega a mezclar
  deployments o presets. Dicho explícitamente que `plot_session` grafica un
  directorio a la vez y que `load_sessions()` es función de biblioteca, sin CLI.
- Donde se introduce `MESH_DEPLOYMENT` (sección Deployments): las tres formas de
  definirla (`export` / `$env:` / `set`), y que nada se asume por defecto.
- Comparación con la copia del gateway: agregado el equivalente Windows de
  `sha256sum` (`Get-FileHash`), mismo defecto que el `export`.
- Respondida la pregunta de los paquetes propios sin cambiar código.

### Decisions (documentación)
- "Multimáquina" se documentó en sus dos lecturas, porque las dos estaban poco
  claras: cualquier OS/máquina (solo cambia el puerto) y varios receptores
  grabando a la vez (un directorio por corrida, comparables por los hashes).
- No se oculta en el terminal lo que la radio del receptor origina. Se ofreció
  una bandera `--show-own` y el usuario prefirió dejarlo como está: esas filas
  llevan `(own)`, quedan fuera del resumen y de la detección de silencios
  (`listener.py:108,111`) y `plot_session` usa `own == 1` a propósito para la
  traza GPS del receptor.
- `?` y no `0` en hops/RSSI/SNR de un paquete propio: nunca entró por el
  demodulador, así que no hay `rxRssi`/`rxSnr`/`hopStart` que leer. Un 0 sería
  un dato inventado (0 dBm y 0.0 dB son medidas reales; regla 9).
- Sin placeholders con nombres reales en el README: `--operator <name>` y
  `runs/2026-11-03-hilltop/` en lugar del handle del usuario.

### Outcomes (documentación)
- 193 tests OK; `configure.py validate --all` sin errores en esa primera parte,
  solo documentación.

- **Traza GPS del receptor (pedido del usuario: posición cada 30 s-1 min para
  trazar el trayecto).** Implementado leyendo el fix por USB, no por el aire:
  - `channel_study/track.py` (nuevo): `Tracker` muestrea con periodo fijo,
    `own_position(iface)` lee `getMyNodeInfo()["position"]`, `TRACK_COLUMNS` /
    `track.csv`. El primer muestreo es inmediato (una sesión corta igual deja
    constancia de dónde empezó) y un fix idéntico al anterior se marca
    `repeated=1` (la marca de tiempo del GPS entra en la comparación: un receptor
    quieto con GPS vivo NO se marca, porque su timestamp avanza; lo que se marca
    es que no llegó nada nuevo).
  - `receiver.py`: `--track-secs` (30 por defecto, `0` apaga), activo solo con
    `--csv`/`--jsonl`; avisa si `position.gps_mode` no es `ENABLED`; imprime el
    primer fix y los contadores al cerrar; `session.json` gana el bloque
    `track` y `receiver.position` (el fix de arranque, que ya estaba en
    `snapshot()` y se descartaba).
  - `sink/csv.py` y `sink/jsonl.py`: método `track()` (`track.csv`;
    `events.jsonl` con `event: own_position`), mismo patrón que `note()`.
  - `analysis/plot_session.py`: la traza sale de `track.csv` si existe y, si no,
    de las posiciones que la radio emitió (sesiones anteriores siguen
    graficando); el caption dice de dónde salió y cuántas muestras repiten.
  - 8 tests nuevos en `test_channel_study.py` (periodo, apagado, repetidos, sin
    fix, error de lectura, cabecera estable con celdas vacías, evento JSONL,
    `own_position`).

### Decisions
- **Dos cadencias separadas, y es la decisión de diseño del cambio:** lo que la
  radio pone AL AIRE es el flujo `position` declarado en el archivo de
  deployment (regla 3: las cadencias viven ahí); cada cuánto el computador lee
  el fix por USB es `--track-secs`, propiedad de la máquina que graba, como
  `--port`. Leer no cuesta aire, así que se puede trazar el trayecto sin
  ensuciar el canal que se mide: `position: 3600` al aire + `--track-secs 30`
  da trayecto denso por un paquete cada hora.
- No se agregó un campo nuevo al deployment para "GPS encendido y nunca al
  aire": el firmware emitiría igual a la cadencia por defecto, un flujo que
  nadie declaró ni espera — justo lo que la regla 3 evita. Rechazado.
- `GPS_UPDATE_INTERVAL_S["receiver"]` ya era 30 s, así que el muestreo a 30 s no
  repite por construcción. Con `--track-secs` más corto que eso, sí repetiría: de
  ahí la columna `repeated` y su línea en troubleshooting.
- Una muestra sin fix no escribe fila (no se inventan ceros) pero se cuenta
  (`no_fix`), y un error de lectura espera un periodo completo en vez de
  reintentar cada segundo (`Tracker.defer`).

### Outcomes
- 201 tests OK; pyflakes limpio; `configure.py validate --all` sin errores.
- Documentado en README (bullet "Where the receiver was"), troubleshooting
  (entrada nueva "The GPS track is empty or frozen", con tabla de causas) y
  project-overview (decisión de las dos cadencias).

- Leída la documentación del módulo Position de Meshtastic (indicada por el
  usuario) y aplicado lo que sirve:
  - `position.fixed_position` se escribe en **false en toda radio**, con GPS o
    sin él (`plan.position_settings`). El CLI lo enciende de forma implícita
    cuando alguien fija una latitud y longitud, así que una radio reutilizada
    puede llegar con él puesto y reportar coordenadas guardadas mientras su GPS
    funciona. El inspector ya lo revisaba (I3) pero `provision` nunca lo
    escribía: se revisaba algo que no se configuraba.
  - Defectos de fábrica anotados en el código, porque los tres son malos para un
    estudio de canal: `gps_update_interval` 0 = cada 2 min,
    `position_broadcast_secs` 0 = 15 min, `position_broadcast_smart_enabled`
    = **true**. Los tres se escriben explícitamente.
  - Confirmado que el plan ya manda todos los campos de posición en UN solo
    comando `--set`, que es justo lo que recomienda la documentación.
  - Receptores con flujo `position: 900` (15 min al aire, > 10 min que aprobó el
    usuario) en `mini.yaml` y en R1/R2 de `rapa-nui.yaml`; la resolución del
    trayecto la da `--track-secs 30` por USB. Comentario corregido en
    `rapa-nui.yaml` y en `_template.yaml`: decían "agrega `position: 30` para
    registrar la traza", que ahora gastaría el canal medido sin necesidad.
  - `position.flags` queda en UNSET: los paquetes POSITION llevan solo lat/lon
    (sin altitud, sats ni DOP). Es lo correcto para el aire (paquete más corto =
    menos tiempo en el aire = menos perturbación de la medición), pero explica
    por qué la columna `altitude` de un nodo remoto puede venir vacía.

### Decisions
- Se modificó la LETRA de `test_no_position_is_ever_written_to_a_radio`, no su
  intención: antes prohibía el texto `fixed_position` en el plan; ahora prohíbe
  `--setlat/--setlon/--setalt` y `fixed_position true`, y EXIGE
  `--set position.fixed_position false` en toda radio. Escribir ese campo en
  false no es escribir una posición: es lo que impide que la radio invente una.

- **Decisión del usuario sobre `fixed_position` (preguntado explícitamente).**
  Se le planteó que poner `fixed_position true` en los SenseCAP estáticos
  obligaría a escribir las coordenadas de `site.surveyed` en la radio, lo que
  contradice la regla 6 y, sobre todo, destruye la única verificación de que un
  nodo quedó donde dice el archivo (`model.py:80-83`: la diferencia entre lo
  reportado y lo relevado se lee como error de GPS). Además hoy no hay nada que
  escribir: los `surveyed` de Rapa Nui son `null`.
  Respuesta: **GPS real, pero con los intervalos máximos de update y
  transmisión en los estáticos.** Aplicado:
  - `GPS_UPDATE_INTERVAL_S` pasa a `{node: 3600, pbx: 3600, receiver: 30,
    gateway: 3600}`. La tabla se indexa por función porque la función es lo que
    dice si la radio se mueve. NO se usó maxint, que el firmware lee como "un
    fix solo al arrancar": un nodo encendido bajo techo durante la instalación
    no volvería a fijar nunca y no reportaría posición en semanas, en silencio.
  - Nodos de campo de `rapa-nui`: `position: 600` → `position: 3600`. El flujo
    de posición queda como el flujo disperso (el `GapWatcher` lo anuncia a
    1.5 x 3600 s); los densos siguen siendo `device` y `environment` a 120 s.
  - `fixed_position` sigue escribiéndose `false` en toda radio.

### Next steps / open questions
- `san-joaquin` NO se tocó: sus nodos 1-3 están `deployed` con `position: 600` y
  fueron provisionados con `gps_update_interval` 300. Con la tabla nueva,
  `inspect` sobre ellos va a reportar 3600 esperado vs 300 leído hasta que se
  re-provisionen (es una diferencia benigna: el intervalo de fix no cuesta aire
  ni afecta a ningún estimador). Decidir si se re-provisionan en la próxima
  visita o si se baja la tabla a 300 para esa malla.
- Un LILYGO bajo techo nunca consigue fix; probar la traza al aire libre.
- Confirmar en la primera salida si `getMyNodeInfo()["position"]` entrega
  altitud y `satsInView` del propio nodo (las columnas existen y quedan vacías
  si el firmware no las da; `position.flags` solo afecta a lo que sale al aire).
- `bench-lilygo` mantiene su receptor con `intervals: {}`: es un escritorio, no
  hay fix bajo techo.

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

- Segundo reporte del usuario, mismo nodo: el paso final `--reboot` terminó con
  `Aborting due to WriteFile failed (PermissionError(13,'The device does not
  recognize the command.',None,22))`. Es pyserial en Windows levantando el error
  22 de Win32 (`ERROR_BAD_COMMAND`) al escribir en un COM cuyo dispositivo USB
  ya desapareció — justo lo que hace una radio al reiniciarse. Los ajustes ya
  estaban escritos: `--reboot` es el último paso del plan y no escribe ninguno.
- `node.report()`: cuando el ÚNICO paso fallido es `reboot`, ya no dice "the
  node may be partially configured" (era inexacto y mandaba a buscar un
  problema inexistente); explica que todo se escribió antes y que se confirme
  con `inspect`. Con cualquier otro fallo, el mensaje sigue igual. Sigue
  saliendo con código 1: no se puede saber desde el mensaje si la radio
  alcanzó a recibir el reboot.
- Entrada nueva en troubleshooting: "The reboot step fails on Windows".
- Test nuevo para los dos mensajes de `report()`.

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
