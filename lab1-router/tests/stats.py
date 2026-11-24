#!/usr/bin/env python3
"""
Lee el contador `MyIngress.stats` de cada router con simple_switch_CLI (Thrift)
y muestra cuántos paquetes se reenviaron y cuántos se descartaron, por motivo.

Uso (con Mininet corriendo):
    mininet> sh python3 tests/stats.py
o desde otra terminal de la VM, en la carpeta lab1-router:
    python3 tests/stats.py
"""

import argparse
import re
import subprocess

# Deben coincidir con las constantes STAT_* de router.p4
STATS = [
    (6, "IPv4 reenviados"),
    (0, "IPv4 descartados: sin ruta"),
    (1, "IPv4 descartados: TTL agotado"),
    (5, "ICMP Time Exceeded generados"),
    (2, "IPv4 descartados: checksum inválido"),
    (7, "IPv6 reenviados"),
    (3, "IPv6 descartados"),
    (4, "Otros descartados (ARP, opciones IPv4)"),
]

# run_exercise.py asigna los puertos Thrift en orden: s1=9090, s2=9091, s3=9092
ROUTERS = [("s1", 9090), ("s2", 9091), ("s3", 9092)]


def read_counter(port, index):
    cmd = "counter_read MyIngress.stats %d\n" % index
    out = subprocess.run(["simple_switch_CLI", "--thrift-port", str(port)],
                         input=cmd, capture_output=True, text=True).stdout
    # Formatos según la versión de BMv2:
    #   "MyIngress.stats[6]= (1176 bytes, 12 packets)"
    #   "MyIngress.stats[6]=  BmCounterValue(packets=12, bytes=1176)"
    m = re.search(r"(\d+) packets", out) or re.search(r"packets=(\d+)", out)
    return int(m.group(1)) if m else None


def main():
    parser = argparse.ArgumentParser(description="Estadísticas de los routers P4")
    parser.add_argument("--reset", action="store_true", help="pone los contadores en cero")
    args = parser.parse_args()

    if args.reset:
        for name, port in ROUTERS:
            subprocess.run(["simple_switch_CLI", "--thrift-port", str(port)],
                           input="counter_reset MyIngress.stats\n",
                           capture_output=True, text=True)
        print("Contadores reiniciados.")
        return

    header = "%-40s" % "Estadística" + "".join("%8s" % n for n, _ in ROUTERS)
    print(header)
    print("-" * len(header))
    for index, label in STATS:
        values = []
        for _, port in ROUTERS:
            v = read_counter(port, index)
            values.append("%8s" % ("?" if v is None else v))
        print("%-40s" % label + "".join(values))


if __name__ == "__main__":
    main()
