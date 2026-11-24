#!/usr/bin/env python3
"""
Captura con Scapy los paquetes IPv4 que llegan a un host y muestra su TTL.

Se ejecuta en el host DESTINO para comprobar que cada router decrementó el TTL:
    h4 python3 tests/receive.py --count 3 --timeout 15
    h1 python3 tests/probe.py 10.0.4.4 --count 3      (en otra terminal)

Si h1 envía con TTL 64 y el camino es h1 -> s1 -> s3 -> h4, h4 debe ver TTL 62.
También verifica que las MAC fueron reescritas: la MAC origen debe ser la del
router (00:aa:...) y no la de h1.
"""

import argparse

from scapy.all import ICMP, IP, Ether, conf, sniff

conf.verb = 0


def show(pkt):
    if IP not in pkt:
        return
    ip = pkt[IP]
    extra = ""
    if ICMP in pkt:
        extra = " ICMP tipo=%d seq=%d" % (pkt[ICMP].type, pkt[ICMP].seq)
    print("RECIBIDO  %s -> %s  TTL=%d  MAC %s -> %s%s"
          % (ip.src, ip.dst, ip.ttl, pkt[Ether].src, pkt[Ether].dst, extra), flush=True)


def main():
    parser = argparse.ArgumentParser(description="Muestra el TTL de los paquetes recibidos")
    parser.add_argument("--iface", default="eth0")
    parser.add_argument("--count", type=int, default=0, help="0 = sin límite")
    parser.add_argument("--timeout", type=float, default=None, help="segundos")
    args = parser.parse_args()

    print("Escuchando ICMP Echo Request en %s ..." % args.iface, flush=True)
    sniff(iface=args.iface, filter="icmp[icmptype] == icmp-echo",
          prn=show, count=args.count, timeout=args.timeout, store=False)


if __name__ == "__main__":
    main()
