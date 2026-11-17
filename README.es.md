# meshtastic-platform 

[English](README.md) · **Español**

Esta plataforma configura las radios de la red mesh LoRa/Meshtastic de SASIPA
en Rapa Nui a partir de **un solo archivo**, comprueba que cada radio quedó como
ese archivo dice y permite escuchar la malla desde un computador portátil.

Este documento es para el personal técnico y de TI de las oficinas de SASIPA
que va a **revisar, reconfigurar o dar mantención** a las radios. No hace falta
saber programar ni conocer LoRa: los términos que aparecen están en el
[glosario](#glosario). El detalle de diseño está en [`README.md`](README.md)
(inglés) y en [`docs/`](docs/).

## Contenido

- [Qué es y cómo encaja](#qué-es-y-cómo-encaja)
- [La red de Rapa Nui](#la-red-de-rapa-nui)
- [Preparar el portátil (una sola vez)](#preparar-el-portátil-una-sola-vez)
- [Tareas habituales](#tareas-habituales)
- [Lo que no se debe hacer](#lo-que-no-se-debe-hacer)
- [Si algo falla](#si-algo-falla)
- [Glosario](#glosario)

## Qué es y cómo encaja

La red tiene dos programas que **no comparten código** y que hacen cosas
distintas:

```
  nodos N1–N6 ──── LoRa ────►  radio GW ──USB──►  Raspberry Pi  ──WiFi──►  tablero
  (en terreno)                 (Central SASIPA)   (el gateway)             (navegador)

        ▲
        │ USB, una radio a la vez
  portátil con meshtastic-platform   ◄── este repositorio
```

| | `meshtastic-platform` (este repositorio) | [`meshtastic-gateway`](https://github.com/OF306PUC/meshtastic-gateway) |
|---|---|---|
| Qué hace | **Configura** las radios y verifica que coincidan con el archivo | **Recibe**, mide y muestra lo que transmite la malla |
| Dónde corre | En un portátil, conectado por USB a la radio que se está tocando | En la Raspberry Pi de la Central SASIPA, de forma permanente |
| Cuándo se usa | Al instalar, cambiar o reemplazar una radio, y para revisarla | Todos los días: es el tablero |
| Escribe en las radios | Sí: su **membresía** en la malla | No: solo lee el aire |

El gateway tiene su propia guía para el personal de TI, con la instalación del
servidor y del tablero; este documento cubre solo las **radios**.

Todo lo que describe la red de Rapa Nui —nodos, canales, frecuencia, cadencias
de transmisión— vive en un único archivo:
[`deployments/rapa-nui.yaml`](deployments/rapa-nui.yaml). El código es el mismo
para cualquier red; el archivo es lo que lo hace "de Rapa Nui".

## La red de Rapa Nui

Región `ANZ`, perfil de módem `MEDIUM_FAST`, ranura 45 (926.125 MHz) y dos
canales cifrados: uno de **telemetría** y uno de **mensajería**. Son diez
radios:

| Ref | Equipo | Rol | Para qué sirve |
|---|---|---|---|
| `N1`–`N6` | SenseCAP Solar Node P1 Pro (solar) | `CLIENT` | Nodos de campo: miden y retransmiten. Envían telemetría del equipo cada 120 s y su posición cada hora. `N1`–`N3` llevan sensor de temperatura y humedad |
| `GW` | LILYGO T-Beam, conectada a la Raspberry Pi | `CLIENT_MUTE` | La radio del gateway: oye la malla y nunca retransmite. Tiene el Bluetooth apagado |
| `D1`, `D2` | LILYGO T-Beam | `CLIENT_MUTE` | Nodos de **acceso**: una persona se conecta por Bluetooth desde el teléfono y escribe en el canal de mensajería |
| `Rx` | LILYGO T-Beam | `CLIENT_MUTE` | Receptor para verificar nodos en terreno y hacer pruebas de canal, conectado a un portátil |

Cada radio lleva su etiqueta (`N1`, `GW`…) pintada en la carcasa: **esa
etiqueta es la identidad de la radio** en el archivo y en el tablero.

### Diferencias conocidas entre el archivo y el terreno

Estado al **17 de noviembre de 2026**, según la guía de despliegue. Conviene
saberlas antes de revisar una radio, porque `show` e `inspect` comparan contra
el archivo, no contra lo que hay instalado:

- La malla está **instalada y transmitiendo**, pero el archivo todavía declara
  los nodos como `planned` y sin el sitio relevado. Cerrar eso es trabajo de
  quien administra la malla, no una falla.
- Las antenas de **fibra de vidrio** quedaron físicamente en `N2`, `N3` y `N4`;
  el archivo las declara en `N2`, `N5` y `N6`.
- El sensor de temperatura y humedad de `N1` y `N3` está **fuera de servicio**
  desde el 10 de noviembre de 2026; el archivo sigue declarando su telemetría
  ambiental y el tablero oculta esas lecturas.

## Preparar el portátil (una sola vez)

Hace falta un portátil con **Windows, Linux o macOS**, Python 3 (el código se
prueba con 3.12), Git y un cable USB **de datos** —un cable solo de carga no
sirve—. No se instala nada en el sistema: los programas se ejecutan desde la
carpeta clonada. Tampoco hacen falta los submódulos de `external/`.

**Linux y macOS**

```bash
git clone https://github.com/OF306PUC/meshtastic-platform.git
cd meshtastic-platform
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
source .venv/bin/activate
```

**Windows (PowerShell)**

```powershell
git clone https://github.com/OF306PUC/meshtastic-platform.git
cd meshtastic-platform
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Si PowerShell bloquea el script de activación, ejecutar antes
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` (vale solo para esa
ventana) o usar el símbolo del sistema (`cmd`). Con el entorno activado, el
resto de los comandos de este documento es **igual en los tres sistemas**.

### Las claves: el archivo `.env`

Abrir `.env` y completar las tres variables con los valores que entrega **quien
administra la malla**:

```
EASTERNET_TELEMETRY_PSK=base64:...      # clave del canal de telemetría
EASTERNET_MSG_PSK=base64:...            # clave del canal de mensajería
RAPA_NUI_BLE_PIN=<seis dígitos>         # PIN de emparejamiento Bluetooth
```

- **Nunca se inventan ni se generan de nuevo.** Una radio con otra clave
  queda fuera de la malla sin mostrar ningún error.
- `.env` está excluido de Git a propósito. **No subirlo, no copiarlo a un
  correo ni a un chat**: quien tiene las claves puede leer la malla.
- Cada variable debe aparecer **una sola vez**; si se repite, se usa la primera.
- `inspect` y `provision` son los únicos programas que las leen.

### Primera comprobación

```bash
python configure.py validate -d rapa-nui
```

Debe terminar sin errores. Las **advertencias** (`WARNING`) no bloquean: las de
tipo `P` avisan de sitios todavía sin relevar y las de tipo `V2` de la potencia
declarada, y se ven en cada ejecución.

> **`-d rapa-nui` siempre es obligatorio.** Ninguna herramienta elige una malla
> por su cuenta: aplicar el archivo equivocado escribe claves y frecuencias de
> otra red en una radio, que después no oye nada y no avisa. Para no repetirlo
> en cada comando, se puede definir `MESH_DEPLOYMENT=rapa-nui` en el entorno.

## Tareas habituales

### 1. Ver qué debería tener cada radio

```bash
python configure.py show -d rapa-nui
```

Imprime los nodos, la frecuencia de la ranura, la potencia y los sitios que
faltan por llenar. Con `--csv hojas/` deja las mismas tablas como planillas.

### 2. Comprobar que una radio está bien configurada

Es la tarea más frecuente y **no escribe nada** en la radio.

1. Conectar la radio al portátil por USB. Averiguar el puerto:

   | Sistema | Cómo se ve | Cómo encontrarlo |
   |---|---|---|
   | Windows | `COM3`, `COM4`… | Administrador de dispositivos → Puertos (COM y LPT) |
   | Linux | `/dev/serial/by-id/usb-…` | `ls /dev/serial/by-id/` |
   | macOS | `/dev/cu.usbserial-…` o `/dev/cu.usbmodem…` | `ls /dev/cu.*` |

   El puerto depende del computador, no de la malla: se escribe cada vez en la
   línea de comandos y no se guarda en ningún archivo. Si hay **una sola**
   radio conectada, `inspect` lo encuentra solo.

2. Ejecutar:

   ```bash
   python configure.py inspect -d rapa-nui --node N1 --port COM3
   ```

   (`--node` es la etiqueta que se espera encontrar; en Linux, reemplazar
   `COM3` por la ruta de `/dev/serial/by-id/`.)

3. Leer el final:

   - `=== Node healthy: no drift or mismatch detected. ===` y código de salida
     **0**: la radio coincide con el archivo.
   - `=== Issues found ===` y código de salida **1**: lista cada diferencia con
     lo esperado y lo leído. Una diferencia **no es una avería**: es una radio
     que no coincide con el archivo. Anotarla y consultar a quien administra la
     malla antes de corregirla.

   Las claves y el PIN se comparan **sin mostrarse nunca**: la salida solo dice
   si coinciden. Cerca del final, `inspect` imprime también una nota sobre la
   potencia (`Final Tx power`): es informativa.

### 3. Configurar una radio (instalación o reemplazo)

Escribir la configuración **es el único paso que modifica una radio**. Se hace
de a una por vez:

```bash
python configure.py provision -d rapa-nui --node N1 --port COM3 --dry-run   # ensayo: imprime el plan y no escribe nada
python configure.py provision -d rapa-nui --node N1 --port COM3             # escribe
python configure.py inspect   -d rapa-nui --node N1 --port COM3             # verificación: debe quedar sana
```

`provision` **se niega a escribir** si lo que hay en el puerto no es la radio
que el archivo describe (otro `node_id`, otra placa o un firmware distinto de
`2.7.26`), y se detiene si falta el PIN o una clave en `.env`. Es un freno
intencional: una radio mal configurada sigue transmitiendo y el error aparece
semanas después. Termina reiniciando la radio.

> **Reemplazar una radio no es solo una tarea de TI.** Una radio nueva tiene
> otro `node_id` y otra MAC, y el archivo los usa para reconocerla: hay que
> actualizar su entrada **antes** de configurarla, y el cambio tiene que llegar
> a las dos copias del archivo (ver la tarea 5). Coordinarlo con quien
> administra la malla.

### 4. Escuchar la malla sin el gateway

Sirve para confirmar, en el mismo lugar, que un nodo recién instalado
transmite, sin esperar al tablero. Conectar `Rx` al portátil y ejecutar:

```bash
python receiver.py -d rapa-nui --port COM3 --node N1
```

Cada línea es un paquete: hora, nodo de origen, tipo, saltos, RSSI, SNR y
contenido. Esperar **al menos 120 s** (un ciclo de telemetría); la terminal
avisa si a un nodo le falta un paquete a su cadencia. **Ctrl+C** corta e
imprime un resumen por nodo.

Para guardar la sesión en archivos (un `session.json` queda al lado):

```bash
python receiver.py -d rapa-nui --port COM3 --csv runs/2026-11-17-central/ --operator <su nombre>
```

Usar **una carpeta por sesión**, con el lugar en el nombre. La carpeta `runs/`
queda solo en ese portátil (Git la ignora): respaldarla es responsabilidad de
quien graba.

Si no aparece nada, `receiver.py` avisa **antes de escuchar** si su radio está
en otro perfil, ranura o canal que el archivo; esa línea `WARNING` es lo primero
que hay que leer.

### 5. Confirmar que plataforma y gateway usan el mismo archivo

El gateway lee **su propia copia** de `rapa-nui.yaml`, y nada mantiene iguales
las dos copias: si difieren, el tablero mide contra el archivo equivocado y no
avisa (descarta paquetes de nodos "desconocidos", les pone otro nombre o les
cobra pérdidas que no ocurrieron). Las dos deben tener el **mismo SHA-256**:

```bash
sha256sum deployments/rapa-nui.yaml                  # Linux y macOS
Get-FileHash deployments\rapa-nui.yaml               # Windows (PowerShell)
```

El archivo **oficial** es el del repositorio del gateway
(`deployments/sasipa/rapa-nui.yaml`); esta copia lo sigue byte a byte. Si algo
tiene que cambiar, se cambia **primero allá** y se copia aquí idéntico —nunca al
revés— y después se vuelve a ejecutar `validate`. No editar ninguno de los dos
sin acordarlo con quien administra la malla.

## Lo que no se debe hacer

- **No reconfigurar una radio desde la app de Meshtastic del teléfono.** La app
  puede cambiar rol, canales o potencia, y la radio deja de coincidir con el
  archivo sin que nadie se entere hasta el próximo `inspect`. La app se usa para
  **mandar mensajes**, nada más.
- **No compartir el código QR de "compartir canal"** de la app: contiene la
  clave. Compartirlo es entregar la malla.
- **No cambiar el perfil, la ranura o una clave en una sola radio.** Todas deben
  coincidir. Una radio distinta no "funciona peor": no oye ni es oída, y el
  único síntoma es el silencio. Un cambio de este tipo se hace en las diez, de
  forma coordinada.
- **No reiniciar ni desenergizar un nodo sin necesidad.** El primer aviso de
  vecinos de un nodo sale **una vez transcurrido el intervalo completo**
  (4 horas) después de encenderlo, así que cada reinicio retrasa su aparición en
  el gráfico de enlaces del tablero. Anotar la hora de cualquier reinicio.
- **No conectar `GW` a un portátil mientras el gateway está operando.** Solo un
  programa puede abrir un puerto serie a la vez; competir con el gateway por él
  lo interrumpe.
- **No cambiar el PIN de Bluetooth a la ligera.** Se entrega a quien lo necesita
  y se cambia cuando alguien deja el equipo, pero cambiarlo es volver a
  configurar todas las radios con Bluetooth encendido: un PIN nuevo en algunas
  deja al resto con el viejo, y nadie lo nota hasta que hace falta emparejar.
- **No subir `.env` a Git** ni pegar claves o el PIN en tickets, correos o
  chats.

## Si algo falla

Casi todos los fallos de este sistema son **silenciosos**: la radio transmite,
algo la oye, el programa termina sin error y el número está mal. Por eso la
tabla dice cómo distinguir las causas. El catálogo completo, por síntoma, está
en [`docs/troubleshooting.md`](docs/troubleshooting.md) (inglés).

| Síntoma | Qué significa | Qué hacer |
|---|---|---|
| `provision` imprime `REFUSING to provision` | La radio en el puerto no es la que el archivo describe: otro `node_id`, otra placa (por ejemplo una LILYGO de banco en vez de un SenseCAP de campo) o firmware distinto de `2.7.26` | No se escribió nada. Ejecutar `inspect` en ese puerto para ver el `Node ID` real. Si es el firmware: [`docs/flashing.md`](docs/flashing.md) |
| `provision` se detiene por el PIN o por una clave | Falta la variable en `.env`, sigue con el valor `CHANGE_ME`, o el PIN no tiene exactamente seis dígitos | Pedir el valor a quien administra la malla. No usar `123456`: es el PIN por defecto del firmware y es público |
| En Windows, el **último paso** de `provision` falla con `WriteFile failed` | La radio se reinició antes de que el comando terminara. **Los ajustes ya quedaron escritos**: ese paso no escribe ninguno | Ejecutar `inspect`. Si responde y sale con 0, está lista. Si no responde, desconectar y volver a conectar el USB, y repetir `inspect` |
| `receiver.py` arranca y **no aparece ningún paquete** | La radio receptora tiene otro perfil, otra ranura u otra clave | Leer las líneas `WARNING` previas al encabezado y ejecutar `inspect` sobre la radio receptora. Al cortar con Ctrl+C, un contador de paquetes **no descifrables** indica que otra malla transmite en la misma frecuencia con otra clave |
| No se puede abrir el puerto, o la placa se reinicia al conectar | Solo un proceso puede tener el puerto: el gateway, otro `receiver.py`, un monitor serie o el flasheador web | Cerrar el otro proceso. Que una LILYGO se reinicie al abrir su consola es normal |
| `inspect` lista `channel N: expected=none actual=<nombre>` | La radio viene de otra malla y conserva un canal que el archivo no declara | Borrarlo con `meshtastic --port <puerto> --ch-index N --ch-del`, empezando por el índice más alto, y volver a ejecutar `inspect` |
| El tablero no muestra un nodo, lo muestra con otro nombre, o le cobra pérdidas que el receptor no ve | Las dos copias del archivo difieren | Comparar los SHA-256 (tarea 5) y copiar el archivo oficial |
| Un nodo no aparece en el gráfico de enlaces | Si se encendió o reinició hace menos de 4 horas, es el intervalo del aviso de vecinos | Esperar. Si ya pasaron más de 4 horas, ejecutar `inspect` y revisar que sus avisos de vecinos estén encendidos |

## Glosario

| Término | Qué es |
|---|---|
| **Radio / nodo** | Cada equipo Meshtastic de la red. "Nodo" suele referirse a los de campo |
| **Aprovisionar** | Escribir en una radio, por USB, todo lo que el archivo declara para ella. Después de eso, la radio es miembro de la malla |
| **Despliegue (*deployment*) / registro** | El archivo `deployments/rapa-nui.yaml`: la descripción completa de la malla. Es la única fuente de verdad |
| **Perfil de módem (*preset*)** | Combinación de ancho de banda y velocidad que decide alcance contra tiempo en el aire. Aquí `MEDIUM_FAST`. **Debe ser el mismo en todas las radios** |
| **Ranura (*slot*)** | La frecuencia exacta dentro de la banda. Aquí la 45, que es 926.125 MHz |
| **PSK** | La clave cifrada de un canal. Nombre y clave deben coincidir para poder leer el canal |
| **Rol** | `CLIENT`: reporta y retransmite lo que oye. `CLIENT_MUTE`: oye y nunca retransmite |
| **NodeInfo** | El aviso con que una radio dice quién es (nombre, rol, equipo). Aquí, cada 2 horas |
| **NeighborInfo** | El aviso con que una radio dice a qué vecinos oye y con qué calidad. Con estos avisos el tablero dibuja el gráfico de enlaces entre nodos. Aquí, cada 4 horas |
| **RSSI / SNR** | La potencia con que llegó un paquete y qué tan por sobre el ruido. Un SNR bajo es una señal al límite de lo que el perfil puede demodular |
| **Saltos (*hops*)** | Cuántas veces fue retransmitido un paquete hasta llegar. 0 es un enlace directo |
| **PDR** | Tasa de entrega: qué fracción de los paquetes que un nodo debía enviar llegó realmente. La calcula el gateway |

## Más información

| Para… | Ver |
|---|---|
| Grabar el firmware en una radio | [`docs/flashing.md`](docs/flashing.md) |
| Cualquier error, por síntoma | [`docs/troubleshooting.md`](docs/troubleshooting.md) |
| Cómo está hecho el código, las pruebas y todas las opciones | [`README.md`](README.md) |
| Instalar y operar el servidor y el tablero | El repositorio [`meshtastic-gateway`](https://github.com/OF306PUC/meshtastic-gateway) |
| Las claves, el PIN y los cambios al archivo | Quien administra la malla |
