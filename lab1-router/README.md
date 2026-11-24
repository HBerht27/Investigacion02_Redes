# Laboratorio 1: Router IPv4 estático en P4

Router IPv4 (y opcionalmente IPv6) escrito en P4₁₆ para la arquitectura v1model y el switch de software BMv2 (`simple_switch_grpc`). Las tablas de enrutamiento se cargan de forma estática desde el plano de control mediante P4Runtime.

## Archivos

| Archivo | Contenido |
|---|---|
| `router.p4` | Programa P4 del router |
| `topology.py` | Define la red (hosts, routers, IPs, MACs y rutas estáticas) y genera `topology.json` y `runtime/sN-runtime.json` |
| `topology.json` | Topología de Mininet (generada por `topology.py`) |
| `runtime/sN-runtime.json` | Entradas de tabla que se instalan en cada router por P4Runtime (generadas) |
| `Makefile` | `make run`, `make stop`, `make clean` |
| `tests/probe.py` | Envía ICMP Echo con Scapy (TTL configurable y modo traceroute) |
| `tests/receive.py` | Captura con Scapy en el host destino y muestra el TTL recibido |
| `tests/ttl_report.py` | Lee los pcaps de BMv2 y muestra el TTL de entrada y salida en cada router |
| `tests/stats.py` | Lee los contadores del router (reenviados y descartados por motivo) |
| `tests/demo.mn` | Todas las pruebas en orden, para correr con `source` en Mininet |

## Funcionalidades

| Requisito | Dónde está |
|---|---|
| Parsing de Ethernet, IPv4 e IPv6 | `MyParser` |
| Tabla LPM configurada desde el control plane | tablas `ipv4_lpm` / `ipv6_lpm`, cargadas con P4Runtime desde `runtime/*.json` |
| Decremento de TTL y descarte si llega a 0 | `ipv4_forward` (TTL − 1); en `apply`, si `ttl <= 1` no se reenvía |
| Reescritura de MAC origen y destino | MAC destino en `ipv4_forward` (siguiente salto); MAC origen en la tabla `port_mac` del egress (MAC de la interfaz de salida) |
| ICMP Time Exceeded (opcional, +10%) | acción `send_icmp_time_exceeded` y checksums en `MyComputeChecksum` |
| Descarte de paquetes sin ruta | `default_action = drop_no_route()` |
| Extras | verificación del checksum IPv4, contador `stats` por motivo de descarte, enrutamiento IPv6 |

### Cómo funciona el ICMP Time Exceeded

Cuando llega un paquete con TTL ≤ 1, el router lo convierte en la respuesta en lugar de crear un paquete nuevo:

```
recibido:  Ethernet | IPv4 original | 8 bytes | resto del paquete
enviado:   Ethernet | IPv4 nueva | ICMP 11/0 | IPv4 original | 8 bytes
```

- La IPv4 nueva lleva como origen la IP de la interfaz del router por la que entró el paquete (tabla `port_ipv4`) y como destino la IP origen del paquete original.
- La IPv4 original se cita sin cambios y se conservan los primeros 8 bytes de datos, como pide el RFC 792. Por eso el parser extrae esos 8 bytes (`l4_peek`).
- `truncate(70)` elimina el resto del paquete.
- Los checksums IPv4 e ICMP se calculan en `MyComputeChecksum`.
- No se genera ICMP en respuesta a otro error ICMP (RFC 1812).

## Topología

```
   h1 10.0.1.1                          h2 10.0.2.2
        |p1                                  |p1
      [s1]p2 ------ 10.10.12.0/24 ------ p2[s2]
        p3 \                              / p3
     10.10.13.0/24                 10.10.23.0/24
             p3 \                      / p4
                  [        s3        ]
                   p1 |          | p2
               h3 10.0.3.3    h4 10.0.4.4
```

Son 3 routers P4 y 4 hosts, cada uno en su propia subred /24. Para ver el plan completo de direcciones y rutas, corra `python3 topology.py --show`.

Rutas pensadas para demostrar LPM:

- **s1** tiene una ruta agregada `10.0.0.0/16 → s2`. Por eso `10.0.2.2` sale hacia s2 sin necesitar una ruta propia, mientras que `10.0.99.1` también sale hacia s2 pero ahí se descarta porque s2 no tiene ruta.
- **s3** tiene `10.0.2.0/24 → s2` y también `10.0.2.2/32 → s1`. Gana la /32, así que el tráfico de h3 a h2 da la vuelta por s1. Se ve con el traceroute.
- Cualquier otro destino (por ejemplo `192.168.50.1`) cae en la acción por defecto y se descarta.

## Cómo ejecutarlo

En la VM de P4 (usuario `p4`), con el repositorio `~/tutorials` presente:

```bash
cd lab1-router
make run          # compila, genera la topología y abre el CLI de Mininet
```

Dentro de Mininet, todas las pruebas de una vez:

```
mininet> source tests/demo.mn
```

Para salir: `exit` y luego `make clean`.

Si `~/tutorials` está en otra ruta: `make run TUTORIALS=/ruta/a/tutorials`.

## Pruebas y resultados esperados

| Prueba | Comando en Mininet | Resultado esperado |
|---|---|---|
| Conectividad | `pingall` | `0% dropped (12/12 received)` |
| TTL (ping) | `h1 ping -c 3 10.0.4.4` | `ttl=62`: el reply pasó por 2 routers (64 − 2) |
| TTL (Scapy en destino) | `h4 python3 tests/receive.py ... &` y luego `h1 python3 tests/probe.py 10.0.4.4 --count 3` | h4 recibe `TTL=62` y MAC origen `00:aa:00:00:03:02` (la de s3, no la de h1) |
| TTL por salto | `sh python3 tests/ttl_report.py --src 10.0.1.1 --dst 10.0.4.4` | `s1-eth1_in` TTL 64, `s1-eth3_out` 63, `s3-eth3_in` 63, `s3-eth2_out` 62 |
| TTL agotado | `h1 python3 tests/probe.py 10.0.4.4 --ttl 1` | `10.0.1.254 Time Exceeded (tipo 11, código 0)` |
| Traceroute | `h1 python3 tests/probe.py 10.0.4.4 --trace` | salto 1: 10.0.1.254 (s1), salto 2: 10.10.13.3 (s3), salto 3: 10.0.4.4 Echo Reply |
| LPM /32 | `h3 python3 tests/probe.py 10.0.2.2 --trace` | s3 (10.0.3.254), luego s1 (10.10.13.1), luego s2 (10.10.12.2), luego h2 |
| Sin ruta | `h1 python3 tests/probe.py 192.168.50.1 --count 2` | sin respuesta; sube "IPv4 descartados: sin ruta" en s1 |
| Sin ruta en s2 | `h1 python3 tests/probe.py 10.0.99.1 --count 2` | sin respuesta; el contador sube en s2, no en s1 (s1 lo reenvió por la /16) |
| IPv6 (opcional) | `h1 ping -6 -c 2 2001:db8:4::4` | respuestas con `ttl=62` |
| Contadores | `sh python3 tests/stats.py` | tabla con reenviados y descartados por motivo en s1, s2 y s3 |

Para mostrar los paquetes en Wireshark, abra cualquier archivo de `pcaps/` (por ejemplo `s3-eth2_out.pcap`).

## Simplificaciones

- **ARP:** el router no responde ARP. Cada host tiene una entrada ARP estática para su gateway (ver `commands` en `topology.json`). Los ARP que llegan al router se descartan y se cuentan en "Otros".
- **Opciones IPv4:** no se soportan (IHL ≠ 5). Esos paquetes se descartan.
- **Ruta del ICMP Time Exceeded:** se devuelve por el mismo puerto de entrada, hacia la MAC del salto anterior, y ese equipo lo enruta normalmente.
- **IPv6:** se enruta con su propia tabla LPM y decremento de Hop Limit, pero no se genera ICMPv6. Los hosts envían algunos mensajes IPv6 multicast (RS/MLD) que el router descarta; aparecen en el contador "IPv6 descartados".
