# Laboratorio 2: Contadores y estadísticas de tráfico en P4

Sistema de monitoreo de tráfico escrito en P4₁₆ para la arquitectura v1model y el switch de software BMv2 (`simple_switch_grpc`). El plano de datos cuenta paquetes y bytes por flujo y por protocolo, registra el tamaño de los paquetes y marca los flujos elefante. Un controlador en Python lee esos datos cada 5 segundos y los imprime en consola.

## Archivos

| Archivo | Contenido |
|---|---|
| `counters.p4` | Programa P4: contadores, registers y detección de flujo elefante |
| `topology.json` | Topología de Mininet: 1 switch (`s1`) y 4 hosts, con ARP estático |
| `controller.py` | Instala las tablas, fija el umbral de flujo elefante y lee los contadores periódicamente |
| `traffic_gen.py` | Genera tráfico controlado con Scapy (UDP, TCP, ICMP u otro) e imprime cuántos bytes envió |
| `Makefile` | `make run`, `make controller`, `make stop`, `make clean` |
| `run_tests.md` | Guion de pruebas con los valores esperados |

## Funcionalidades

| Requisito | Dónde está |
|---|---|
| Contadores directos por flujo (IP origen + IP destino) | tabla `flow_stats` con `direct_counter flow_counter` (paquetes y bytes por entrada) |
| Contadores globales por protocolo (TCP, UDP, ICMP, otros) | `counter proto_counter` de 4 posiciones, indexado según `ipv4.protocol` |
| Tamaño de los paquetes | registers `size_hist` (histograma de 6 rangos) y `size_stats` (máximo, mínimo y último) |
| Script Python que lee los contadores cada 5 s | `controller.py`, vía Thrift con `simple_switch_CLI` |
| Detección de flujo elefante con umbral configurable | register `flow_bytes` (bytes acumulados por flujo), `elephant_threshold` (umbral, escrito por el controlador) y `elephant_flag` (marca del flujo) |
| Extras | `elephant_pkts` cuenta los paquetes de cada flujo después de marcarse; el controlador calcula el tamaño promedio |

### Cómo funciona

```
Ethernet | IPv4  ->  proto_counter  ->  size_hist/size_stats  ->  flow_stats  ->  dmac_fwd
                                                                     |
                                                       flow_counter (direct counter)
                                                       flow_bytes >= umbral ? elephant_flag
```

- Todo se mide en el ingress, antes de decidir el reenvío. Los bytes son bytes de **trama** (incluyen los 14 bytes de Ethernet), no solo del paquete IP.
- La tabla `flow_stats` tiene una entrada por cada par origen → destino (12 flujos para 4 hosts). Cada entrada tiene su propio contador directo y un `flow_id` que indexa los registers del flujo elefante. Un flujo sin entrada en la tabla no se cuenta por flujo, pero sí por protocolo.
- El umbral se guarda en un register para poder cambiarlo sin recompilar. Un valor de 0 deshabilita la detección.
- El reenvío es L2: `dmac_fwd` busca la MAC destino y descarta si no la conoce. Es suficiente porque hay un solo switch.

## Topología

```
   h1 10.0.0.1 --p1--+
   h2 10.0.0.2 --p2--+
                     +-- [ s1 ]
   h3 10.0.0.3 --p3--+
   h4 10.0.0.4 --p4--+
```

Los 4 hosts están en la misma subred 10.0.0.0/24, con MACs `00:00:00:00:00:01` a `00:00:00:00:00:04`.

## Cómo ejecutarlo

En la VM de P4 (usuario `p4`), con el repositorio `~/tutorials` presente. Se usan dos terminales.

Terminal 1:

```bash
cd lab2-counters
make run          # compila counters.p4 y abre el CLI de Mininet
```

Terminal 2, con la red ya levantada:

```bash
cd lab2-counters
make controller                    # umbral por defecto: 100000 bytes
make controller THRESHOLD=50000    # otro umbral
```

El controlador reinicia los contadores al arrancar (`--reset`) y muestra las estadísticas cada 5 segundos. Para salir: `Ctrl+C` en la terminal 2, `exit` en Mininet y luego `make clean`.

Si `~/tutorials` está en otra ruta: `make run TUTORIALS=/ruta/a/tutorials`.

## Pruebas y resultados esperados

Los comandos se escriben en el CLI de Mininet. Cada ejecución de `traffic_gen.py` imprime una línea `ENVIADO: ...` que debe coincidir con lo que muestra el controlador.

| Prueba | Comando en Mininet | Resultado esperado |
|---|---|---|
| UDP | `h1 python3 traffic_gen.py --dst 10.0.0.2 --proto udp --count 100 --size 500` | flujo 10.0.0.1 → 10.0.0.2 con 100 paquetes y 50000 bytes; UDP con 100 paquetes; histograma `257-512`: 100 |
| TCP | `h3 python3 traffic_gen.py --dst 10.0.0.4 --proto tcp --count 50 --size 200` | flujo 10.0.0.3 → 10.0.0.4 con 50 paquetes y 10000 bytes; TCP con 50 paquetes |
| ICMP | `h2 python3 traffic_gen.py --dst 10.0.0.1 --proto icmp --count 20 --size 100` | ICMP con 20 paquetes y 2000 bytes |
| Otros protocolos | `h4 python3 traffic_gen.py --dst 10.0.0.1 --proto other --count 10 --size 100` | "Otros" con 10 paquetes |
| Ping | `h1 ping -c 5 h3` | flujos 1 → 3 y 3 → 1 con 5 paquetes cada uno (98 bytes de trama por paquete) |
| Flujo elefante | `h2 iperf -s -u &` y luego `h1 iperf -c 10.0.0.2 -u -b 20M -t 10` | el flujo 10.0.0.1 → 10.0.0.2 aparece como elefante al superar el umbral |
| Tamaños | cualquiera de las anteriores | máximo, mínimo, último, promedio e histograma coherentes con los tamaños enviados |

## Simplificaciones

- **ARP:** el switch no maneja broadcast. Cada host tiene entradas ARP estáticas para los demás (ver `commands` en `topology.json`). Los mensajes IPv6 multicast que envían los hosts se descartan en `dmac_fwd` y no se cuentan, porque solo se miden paquetes IPv4.
- **Flujos fijos:** `controller.py` instala los 12 flujos entre los 4 hosts. Para monitorear otros flujos hay que agregar entradas a `flow_stats`; el máximo es 64.
- **Elefante por IP:** el flujo se define solo por IP origen y destino, no por puertos. Dos conexiones entre el mismo par de hosts se suman como un único flujo.
- **Marcado:** el flujo elefante se registra (`elephant_flag`) pero el paquete no se modifica.
- **Contadores en el ingress:** un paquete se cuenta aunque después sea descartado por no tener MAC destino conocida.
