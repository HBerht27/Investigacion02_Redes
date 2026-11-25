# Plan de pruebas Lab 2 (guion para el video)

Terminal 1: `sudo python3 topology.py`
Terminal 2: `python3 controller.py --reset --threshold 100000`

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
