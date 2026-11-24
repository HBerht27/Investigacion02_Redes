#!/usr/bin/env python3
"""
Analiza las capturas que BMv2 guarda en pcaps/ (una por interfaz y sentido:
sN-ethP_in.pcap y sN-ethP_out.pcap) y muestra el TTL de los ICMP Echo Request
entre dos hosts en cada punto del camino.

Así se comprueba, router por router, que el TTL de salida es el de entrada
menos 1 y que las MAC se reescriben en cada salto.

Uso (desde la carpeta lab1-router, en la terminal de la VM o con `sh` en
el CLI de Mininet):
    python3 tests/ttl_report.py --src 10.0.1.1 --dst 10.0.4.4
"""

import argparse
import glob
import os
import re

from scapy.all import ICMP, IP, Ether, rdpcap


def iface_key(path):
    # ordena por router, interfaz y entrada antes que salida
    m = re.match(r"s(\d+)-eth(\d+)_(in|out)\.pcap", os.path.basename(path))
    if not m:
        return (999, 999, 9)
    return (int(m.group(1)), int(m.group(2)), 0 if m.group(3) == "in" else 1)


def main():
    parser = argparse.ArgumentParser(description="TTL por salto a partir de los pcaps de BMv2")
    parser.add_argument("--src", required=True)
    parser.add_argument("--dst", required=True)
    parser.add_argument("--pcaps", default="pcaps")
    args = parser.parse_args()

    files = sorted(glob.glob(os.path.join(args.pcaps, "*.pcap")), key=iface_key)
    if not files:
        print("No hay archivos en %s/. ¿Corrió `make run` y envió tráfico?" % args.pcaps)
        return

    rows = []
    for path in files:
        try:
            packets = rdpcap(path)
        except Exception:
            continue
        ttls, macs = [], set()
        for p in packets:
            if IP in p and ICMP in p and p[ICMP].type == 8 \
                    and p[IP].src == args.src and p[IP].dst == args.dst:
                ttls.append(p[IP].ttl)
                macs.add("%s -> %s" % (p[Ether].src, p[Ether].dst))
        if ttls:
            rows.append((os.path.basename(path), sorted(set(ttls)), len(ttls), sorted(macs)))

    print("Echo Request %s -> %s vistos en las interfaces de los routers:\n" % (args.src, args.dst))
    print("%-22s %-10s %-9s %s" % ("captura", "TTL", "paquetes", "MAC origen -> MAC destino"))
    for name, ttls, n, macs in rows:
        print("%-22s %-10s %-9d %s" % (name, ",".join(map(str, ttls)), n, "; ".join(macs)))
    if not rows:
        print("(ninguno: envíe tráfico primero, p.ej. h1 ping -c 3 %s)" % args.dst)
    else:
        print("\n_in = paquete entrando al router, _out = saliendo del router.")
        print("En cada router el TTL de _out debe ser el de _in menos 1.")


if __name__ == "__main__":
    main()
