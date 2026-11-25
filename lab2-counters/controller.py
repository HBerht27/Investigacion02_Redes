#!/usr/bin/env python3
"""
Controlador del Lab 2 (Thrift via simple_switch_CLI).

1. Instala las entradas: dmac_fwd (reenvio por MAC) y flow_stats (12 flujos IP origen->destino).
2. Configura el umbral de flujo elefante (register elephant_threshold).
3. Cada INTERVAL segundos lee y muestra: contadores por flujo, por protocolo, histograma
   de tamanos, estadisticas de tamano y flujos elefante.

Uso: python3 controller.py [--threshold 100000] [--interval 5] [--thrift-port 9090]
"""
import argparse
import re
import subprocess
import time
from datetime import datetime

NUM_HOSTS = 4
PROTOS = ["TCP", "UDP", "ICMP", "Otros"]
BUCKETS = ["<=64", "65-128", "129-256", "257-512", "513-1024", ">1024"]
CTR_RE = re.compile(r"(\S+)\[(\d+)\]=\s*\(\s*(\d+)\s*bytes,\s*(\d+)\s*packets\)")
REG_RE = re.compile(r"(\S+)\[(\d+)\]=\s*(\d+)")


def cli(thrift_port, commands):
    """Ejecuta comandos en simple_switch_CLI y devuelve la salida completa."""
    out = subprocess.run(["simple_switch_CLI", "--thrift-port", str(thrift_port)],
                         input="\n".join(commands) + "\n",
                         capture_output=True, text=True)
    return out.stdout


def host_ip(i):
    return "10.0.0.%d" % i


def host_mac(i):
    return "00:00:00:00:00:%02x" % i


def install_tables(port):
    cmds = ["table_clear MyIngress.dmac_fwd", "table_clear MyIngress.flow_stats"]
    for i in range(1, NUM_HOSTS + 1):
        cmds.append("table_add MyIngress.dmac_fwd MyIngress.forward %s => %d" % (host_mac(i), i))
    flows = {}
    fid = 0
    for s in range(1, NUM_HOSTS + 1):
        for d in range(1, NUM_HOSTS + 1):
            if s != d:
                cmds.append("table_add MyIngress.flow_stats MyIngress.track_flow %s %s => %d"
                            % (host_ip(s), host_ip(d), fid))
                flows[fid] = (host_ip(s), host_ip(d))
                fid += 1
    out = cli(port, cmds)
    # El handle de cada entrada aparece en orden en la salida "added with handle N"
    handles = [int(h) for h in re.findall(r"handle (\d+)", out)]
    flow_handles = handles[NUM_HOSTS:]                     # primeras NUM_HOSTS = dmac_fwd
    if len(flow_handles) != len(flows):
        print("[AVISO] No se pudieron leer los handles de flow_stats. Salida del CLI:\n" + out)
    return flows, dict(zip(flows.keys(), flow_handles))


def read_all(port, flows, handles):
    cmds = []
    for fid in flows:
        if fid in handles:
            cmds.append("counter_read MyIngress.flow_counter %d" % handles[fid])
    for p in range(4):
        cmds.append("counter_read MyIngress.proto_counter %d" % p)
    for b in range(6):
        cmds.append("register_read MyIngress.size_hist %d" % b)
    for k in range(3):
        cmds.append("register_read MyIngress.size_stats %d" % k)
    for fid in flows:
        cmds.append("register_read MyIngress.flow_bytes %d" % fid)
        cmds.append("register_read MyIngress.elephant_flag %d" % fid)
        cmds.append("register_read MyIngress.elephant_pkts %d" % fid)
    out = cli(port, cmds)

    flow_ctr, proto_ctr = {}, {}
    inv = {v: k for k, v in handles.items()}
    for name, idx, nbytes, npkts in CTR_RE.findall(out):
        idx = int(idx)
        if name.endswith("flow_counter"):
            if idx in inv:
                flow_ctr[inv[idx]] = (int(npkts), int(nbytes))
        elif name.endswith("proto_counter"):
            proto_ctr[idx] = (int(npkts), int(nbytes))
    regs = {}
    for name, idx, val in REG_RE.findall(out):
        regs[(name.split(".")[-1], int(idx))] = int(val)
    return flow_ctr, proto_ctr, regs


def show(flows, flow_ctr, proto_ctr, regs, threshold):
    print("\n" + "=" * 70)
    print(" Estadisticas P4  %s   (umbral elefante = %d bytes)"
          % (datetime.now().strftime("%H:%M:%S"), threshold))
    print("=" * 70)

    print("\n[Contadores directos por flujo]  (solo flujos con trafico)")
    print("  %-12s -> %-12s %10s %12s %10s" % ("IP origen", "IP destino", "Paquetes", "Bytes", "Elefante"))
    any_flow = False
    for fid, (src, dst) in flows.items():
        pk, by = flow_ctr.get(fid, (0, 0))
        if pk:
            any_flow = True
            ele = "SI" if regs.get(("elephant_flag", fid), 0) else "no"
            print("  %-12s -> %-12s %10d %12d %10s" % (src, dst, pk, by, ele))
    if not any_flow:
        print("  (sin trafico)")

    print("\n[Contadores por protocolo]")
    print("  %-8s %10s %12s" % ("Proto", "Paquetes", "Bytes"))
    for p in range(4):
        pk, by = proto_ctr.get(p, (0, 0))
        print("  %-8s %10d %12d" % (PROTOS[p], pk, by))

    total_pk = sum(v[0] for v in proto_ctr.values())
    total_by = sum(v[1] for v in proto_ctr.values())
    print("\n[Tamano de paquetes]  (bytes de trama, incluye Ethernet)")
    print("  max=%d  min=%d  ultimo=%d  promedio=%.1f"
          % (regs.get(("size_stats", 0), 0), regs.get(("size_stats", 1), 0),
             regs.get(("size_stats", 2), 0), (total_by / total_pk) if total_pk else 0))
    print("  histograma: " + "  ".join("%s:%d" % (BUCKETS[b], regs.get(("size_hist", b), 0))
                                       for b in range(6)))

    print("\n[Flujos elefante]")
    found = False
    for fid, (src, dst) in flows.items():
        if regs.get(("elephant_flag", fid), 0):
            found = True
            print("  ** %s -> %s: %d bytes acumulados, %d paquetes tras el umbral"
                  % (src, dst, regs.get(("flow_bytes", fid), 0), regs.get(("elephant_pkts", fid), 0)))
    if not found:
        print("  ninguno")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--thrift-port", type=int, default=9090)
    ap.add_argument("--threshold", type=int, default=100000, help="umbral elefante en bytes (0 = off)")
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--reset", action="store_true", help="reiniciar registros y contadores al inicio")
    args = ap.parse_args()

    print("Instalando tablas...")
    flows, handles = install_tables(args.thrift_port)
    cmds = ["register_write MyIngress.elephant_threshold 0 %d" % args.threshold]
    if args.reset:
        cmds += ["counter_reset MyIngress.proto_counter", "counter_reset MyIngress.flow_counter",
                 "register_reset MyIngress.size_hist", "register_reset MyIngress.size_stats",
                 "register_reset MyIngress.flow_bytes", "register_reset MyIngress.elephant_flag",
                 "register_reset MyIngress.elephant_pkts"]
    cli(args.thrift_port, cmds)
    print("Listo: %d flujos configurados. Leyendo cada %.0f s (Ctrl+C para salir)."
          % (len(flows), args.interval))

    try:
        while True:
            flow_ctr, proto_ctr, regs = read_all(args.thrift_port, flows, handles)
            show(flows, flow_ctr, proto_ctr, regs, args.threshold)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nFin.")


if __name__ == "__main__":
    main()
