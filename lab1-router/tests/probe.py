#!/usr/bin/env python3
"""
Envía sondas ICMP Echo Request con Scapy desde un host de Mininet y muestra
qué responde la red. Sirve para las tres demostraciones del laboratorio:

  1) Conectividad y TTL:
       h1 python3 tests/probe.py 10.0.4.4 --count 3
     -> Echo Reply desde 10.0.4.4; el TTL del reply muestra cuántos routers
        lo decrementaron (64 - TTL recibido = número de saltos).

  2) TTL agotado / ICMP Time Exceeded (traceroute):
       h1 python3 tests/probe.py 10.0.4.4 --ttl 1
       h1 python3 tests/probe.py 10.0.4.4 --trace
     -> Cada router responde Time Exceeded con la IP de su interfaz.

  3) Descarte sin ruta:
       h1 python3 tests/probe.py 192.168.50.1
     -> Sin respuesta (el router aplica la acción por defecto: drop).

Se construye el frame Ethernet a mano con la MAC del gateway (tomada de la
tabla ARP estática del host), porque el router P4 no responde ARP.
"""

import argparse
import socket
import struct
import sys
import time

from scapy.all import ICMP, IP, Ether, conf, get_if_hwaddr, srp1

conf.verb = 0

ICMP_TYPES = {0: "Echo Reply", 3: "Destination Unreachable", 11: "Time Exceeded"}


def default_gateway():
    """Lee el gateway por defecto de /proc/net/route (namespace del host)."""
    with open("/proc/net/route") as f:
        for line in f.readlines()[1:]:
            fields = line.split()
            if fields[1] == "00000000":  # destino 0.0.0.0 = ruta por defecto
                return fields[0], socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
    sys.exit("No hay ruta por defecto en este host")


def arp_lookup(ip):
    """Busca la MAC de `ip` en la tabla ARP del host (/proc/net/arp)."""
    with open("/proc/net/arp") as f:
        for line in f.readlines()[1:]:
            fields = line.split()
            if fields[0] == ip:
                return fields[3]
    sys.exit("No hay entrada ARP para el gateway %s" % ip)


def send_probe(iface, gw_mac, dst, ttl, seq, timeout):
    pkt = (Ether(src=get_if_hwaddr(iface), dst=gw_mac) /
           IP(dst=dst, ttl=ttl) /
           ICMP(type=8, id=0x4c31, seq=seq) /
           b"lab1-router-probe")
    start = time.time()
    reply = srp1(pkt, iface=iface, timeout=timeout)
    return reply, (time.time() - start) * 1000


def describe(reply):
    ip = reply[IP]
    icmp = reply[ICMP]
    kind = ICMP_TYPES.get(icmp.type, "ICMP tipo %d" % icmp.type)
    return "%-15s %-16s (tipo %d, código %d)  TTL recibido=%d" % (
        ip.src, kind, icmp.type, icmp.code, ip.ttl)


def main():
    parser = argparse.ArgumentParser(description="Sondas ICMP para probar el router P4")
    parser.add_argument("dst", help="IP destino")
    parser.add_argument("--ttl", type=int, default=64, help="TTL inicial (por defecto 64)")
    parser.add_argument("--count", type=int, default=1, help="número de sondas")
    parser.add_argument("--trace", action="store_true",
                        help="modo traceroute: TTL = 1, 2, 3... hasta llegar al destino")
    parser.add_argument("--max-hops", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()

    iface, gw = default_gateway()
    gw_mac = arp_lookup(gw)
    print("Interfaz %s, gateway %s (%s)" % (iface, gw, gw_mac))

    if args.trace:
        print("traceroute a %s (máximo %d saltos)" % (args.dst, args.max_hops))
        for ttl in range(1, args.max_hops + 1):
            reply, rtt = send_probe(iface, gw_mac, args.dst, ttl, ttl, args.timeout)
            if reply is None or ICMP not in reply:
                print(" %2d  *  (sin respuesta: paquete descartado)" % ttl)
                continue
            print(" %2d  %s  %.1f ms" % (ttl, describe(reply), rtt))
            if reply[ICMP].type == 0:
                break
        return

    lost = 0
    for seq in range(1, args.count + 1):
        reply, rtt = send_probe(iface, gw_mac, args.dst, args.ttl, seq, args.timeout)
        if reply is None or ICMP not in reply:
            lost += 1
            print("seq=%d ttl_enviado=%d -> SIN RESPUESTA (descartado en la red)"
                  % (seq, args.ttl))
        else:
            print("seq=%d ttl_enviado=%d -> respuesta de %s  %.1f ms"
                  % (seq, args.ttl, describe(reply), rtt))
        time.sleep(0.2)
    print("%d enviados, %d con respuesta, %d sin respuesta"
          % (args.count, args.count - lost, lost))


if __name__ == "__main__":
    main()
