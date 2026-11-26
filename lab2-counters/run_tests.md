# Plan de pruebas Lab 2 (guion para el video)

Terminal 1: `make run`
Terminal 2: `make controller`

| # | Comando en Mininet | Esperado en el controlador |
|---|--------------------|----------------------------|
| 1 | `h1 python3 traffic_gen.py --dst 10.0.0.2 --proto udp --count 100 --size 500` | flujo 10.0.0.1->10.0.0.2: 100 paquetes, 50000 bytes; UDP: 100 paq; histograma 257-512: 100 |
| 2 | `h3 python3 traffic_gen.py --dst 10.0.0.4 --proto tcp --count 50 --size 200` | flujo 10.0.0.3->10.0.0.4: 50 paq, 10000 bytes; TCP: 50 |
| 3 | `h2 python3 traffic_gen.py --dst 10.0.0.1 --proto icmp --count 20 --size 100` | ICMP: 20 paq, 2000 bytes |
| 4 | `h4 python3 traffic_gen.py --dst 10.0.0.1 --proto other --count 10 --size 100` | Otros: 10 paq |
| 5 | `h2 iperf -s -u &` y `h1 iperf -c 10.0.0.2 -u -b 20M -t 10` | flujo 10.0.0.1->10.0.0.2 marcado ELEFANTE al pasar 100000 bytes |
| 6 | `h1 ping -c 5 h3` | flujos 1->3 y 3->1 con 5 paq c/u (98 bytes de trama) |

Los bytes del switch son bytes de **trama** (con cabecera Ethernet): compararlos con la
linea "ENVIADO" de traffic_gen.py, no con el tamano IP.

## Nota sobre los números

Los contadores cuentan **todo** lo que pasa por el switch, incluidas las respuestas que generan los
kernels de los hosts, no solo lo que envía `traffic_gen.py`:

- UDP a un puerto sin servidor: el host destino responde con unos pocos ICMP "puerto inalcanzable"
  (Linux limita su ritmo), de hasta 528 bytes de trama con paquetes de 500 bytes.
- TCP SYN a un puerto cerrado: cada SYN de 200 bytes recibe un RST de 54 bytes
  (50 x 200 + 50 x 54 = 12700 bytes en 100 paquetes).
- ICMP echo: cada petición recibe su respuesta del mismo tamaño.
- Protocolo 253: el destino responde con ICMP "protocolo inalcanzable".
Para tener cifras sin esas respuestas, abra un servidor antes (`h2 iperf -s -u &`) o reinicie con `make clean`.
