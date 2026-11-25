#!/usr/bin/env python3
"""
Generador de trafico controlado con Scapy. Imprime cuantos paquetes/bytes de trama envio,
para comparar contra los contadores del switch.

Ejemplos (dentro de Mininet):
  h1 python3 traffic_gen.py --dst 10.0.0.2 --proto udp  --count 100 --size 500
  h1 python3 traffic_gen.py --dst 10.0.0.2 --proto tcp  --count 50  --size 200
  h1 python3 traffic_gen.py --dst 10.0.0.2 --proto icmp --count 20  --size 100
  h1 python3 traffic_gen.py --dst 10.0.0.2 --proto other --count 10 --size 100
"""
import argparse
import time

from scapy.all import Ether, IP, TCP, UDP, ICMP, Raw, sendp, get_if_hwaddr, get_if_list


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dst", required=True)
    ap.add_argument("--proto", choices=["udp", "tcp", "icmp", "other"], default="udp")
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--size", type=int, default=200, help="tamano TOTAL de la trama en bytes (>=60)")
    ap.add_argument("--interval", type=float, default=0.01)
    ap.add_argument("--dst-mac", help="MAC destino (por defecto 00:00:00:00:00:0X segun la IP)")
    args = ap.parse_args()

    iface = [i for i in get_if_list() if "eth" in i][0]
    dst_mac = args.dst_mac or "00:00:00:00:00:%02x" % int(args.dst.split(".")[-1])

    eth = Ether(src=get_if_hwaddr(iface), dst=dst_mac)
    if args.proto == "udp":
        l3 = IP(dst=args.dst) / UDP(sport=4000, dport=5000)
    elif args.proto == "tcp":
        l3 = IP(dst=args.dst) / TCP(sport=4000, dport=5000, flags="S")
    elif args.proto == "icmp":
        l3 = IP(dst=args.dst) / ICMP()
    else:
        l3 = IP(dst=args.dst, proto=253)          # protocolo experimental -> cae en "otros"

    base = len(eth / l3)
    pkt = eth / l3 / Raw(b"x" * max(0, args.size - base))

    print("Enviando %d paquetes %s de %d bytes de %s a %s"
          % (args.count, args.proto.upper(), len(pkt), iface, args.dst))
    t0 = time.time()
    sendp(pkt, iface=iface, count=args.count, inter=args.interval, verbose=False)
    print("ENVIADO: %d paquetes, %d bytes de trama totales (%.2f s)"
          % (args.count, args.count * len(pkt), time.time() - t0))


if __name__ == "__main__":
    main()
