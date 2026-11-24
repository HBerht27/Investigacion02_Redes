#!/usr/bin/env python3
r"""
Laboratorio 1 - Topología de prueba del router IPv4 estático.

Este archivo es la ÚNICA fuente de verdad de la red: hosts, routers, enlaces,
direcciones y tablas de enrutamiento estáticas. Al ejecutarlo genera:

  - topology.json           -> topología Mininet (la usa run_exercise.py)
  - runtime/sN-runtime.json -> entradas de tabla que el plano de control
                               instala en cada router vía P4Runtime

Uso:
    python3 topology.py          # genera los archivos
    python3 topology.py --show   # además imprime el plan de direccionamiento

Diagrama (3 routers P4 en triángulo, 4 hosts en 4 subredes distintas):

        h1 (10.0.1.1/24)                     h2 (10.0.2.2/24)
              |                                    |
            p1|                                  p1|
            [ s1 ]p2 ----- 10.10.12.0/24 -----p2[ s2 ]
              p3 \                              / p3
                  \                            /
       10.10.13.0/24                       10.10.23.0/24
                    \                        /
                     p3 \                  / p4
                         [       s3       ]
                         p1 |          | p2
                            |          |
              h3 (10.0.3.3/24)      h4 (10.0.4.4/24)

Los switches se llaman s1..s3 porque así lo espera la infraestructura de los
tutoriales de P4 (run_exercise.py), pero cada uno funciona como un router.
"""

import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# Nombres de archivos generados por el compilador (ver Makefile)
P4INFO = "build/router.p4info.txtpb"
BMV2_JSON = "build/router.json"


def router_mac(router, port):
    """MAC de la interfaz `port` del router `router` (p.ej. s1, 2 -> 00:aa:00:00:01:02)."""
    n = int(router[1:])
    return "00:aa:00:00:%02x:%02x" % (n, port)


# --------------------------------------------------------------------------
# Hosts: cada uno en su propia subred /24 (y /64 en IPv6)
# --------------------------------------------------------------------------
HOSTS = {
    "h1": {"ip": "10.0.1.1", "mac": "08:00:00:00:01:11", "router": "s1", "port": 1,
           "ip6": "2001:db8:1::1"},
    "h2": {"ip": "10.0.2.2", "mac": "08:00:00:00:02:22", "router": "s2", "port": 1,
           "ip6": "2001:db8:2::2"},
    "h3": {"ip": "10.0.3.3", "mac": "08:00:00:00:03:33", "router": "s3", "port": 1,
           "ip6": "2001:db8:3::3"},
    "h4": {"ip": "10.0.4.4", "mac": "08:00:00:00:04:44", "router": "s3", "port": 2,
           "ip6": "2001:db8:4::4"},
}

# --------------------------------------------------------------------------
# Interfaces de los routers: puerto -> (IP de la interfaz, vecino)
#   vecino = "hX" para un host, o "sY-pZ" para el puerto Z de otro router
# --------------------------------------------------------------------------
ROUTERS = {
    "s1": {
        1: {"ip": "10.0.1.254", "ip6": "2001:db8:1::fe", "peer": "h1"},
        2: {"ip": "10.10.12.1", "peer": "s2-p2"},
        3: {"ip": "10.10.13.1", "peer": "s3-p3"},
    },
    "s2": {
        1: {"ip": "10.0.2.254", "ip6": "2001:db8:2::fe", "peer": "h2"},
        2: {"ip": "10.10.12.2", "peer": "s1-p2"},
        3: {"ip": "10.10.23.2", "peer": "s3-p4"},
    },
    "s3": {
        1: {"ip": "10.0.3.254", "ip6": "2001:db8:3::fe", "peer": "h3"},
        2: {"ip": "10.0.4.254", "ip6": "2001:db8:4::fe", "peer": "h4"},
        3: {"ip": "10.10.13.3", "peer": "s1-p3"},
        4: {"ip": "10.10.23.3", "peer": "s2-p3"},
    },
}

# --------------------------------------------------------------------------
# Tablas de enrutamiento estáticas IPv4: (prefijo, puerto de salida)
# La MAC del siguiente salto se deduce del vecino conectado a ese puerto.
#
# Casos interesantes para demostrar LPM:
#   * s1 tiene una ruta AGREGADA 10.0.0.0/16 -> s2. Todo lo que esté en 10.0.x.x
#     y no tenga una ruta más específica sale hacia s2. Por eso:
#       - 10.0.2.2  -> usa la /16 (hacia s2)        -> llega a h2
#       - 10.0.99.1 -> usa la /16 (hacia s2), pero s2 no tiene ruta -> s2 descarta
#   * s3 tiene una ruta de HOST 10.0.2.2/32 -> s1, más específica que su
#     10.0.2.0/24 -> s2. El tráfico de h3/h4 hacia h2 da la vuelta por s1
#     (s3 -> s1 -> s2), lo que se ve con traceroute.
#   * Cualquier destino fuera de estas rutas (p.ej. 192.168.50.1) se descarta
#     en el primer router (default drop).
# --------------------------------------------------------------------------
ROUTES_V4 = {
    "s1": [
        ("10.0.1.0/24", 1),   # h1, directamente conectado
        ("10.0.0.0/16", 2),   # ruta agregada hacia s2
        ("10.0.3.0/24", 3),   # h3 via s3
        ("10.0.4.0/24", 3),   # h4 via s3
    ],
    "s2": [
        ("10.0.2.0/24", 1),   # h2, directamente conectado
        ("10.0.1.0/24", 2),   # h1 via s1
        ("10.0.3.0/24", 3),   # h3 via s3
        ("10.0.4.0/24", 3),   # h4 via s3
    ],
    "s3": [
        ("10.0.3.0/24", 1),   # h3, directamente conectado
        ("10.0.4.0/24", 2),   # h4, directamente conectado
        ("10.0.1.0/24", 3),   # h1 via s1
        ("10.0.2.0/24", 4),   # h2 via s2 ...
        ("10.0.2.2/32", 3),   # ... excepto el host 10.0.2.2: via s1 (LPM gana la /32)
    ],
}

# Rutas IPv6 (opcional): mismas direcciones de salida, sin trucos de LPM.
ROUTES_V6 = {
    "s1": [("2001:db8:1::/64", 1), ("2001:db8:2::/64", 2),
           ("2001:db8:3::/64", 3), ("2001:db8:4::/64", 3)],
    "s2": [("2001:db8:2::/64", 1), ("2001:db8:1::/64", 2),
           ("2001:db8:3::/64", 3), ("2001:db8:4::/64", 3)],
    "s3": [("2001:db8:3::/64", 1), ("2001:db8:4::/64", 2),
           ("2001:db8:1::/64", 3), ("2001:db8:2::/64", 4)],
}


# --------------------------------------------------------------------------
# Generación de archivos
# --------------------------------------------------------------------------

def peer_mac(router, port):
    """MAC del equipo conectado al otro lado de router:port (siguiente salto)."""
    peer = ROUTERS[router][port]["peer"]
    if peer.startswith("h"):
        return HOSTS[peer]["mac"]
    peer_router, peer_port = peer.split("-p")
    return router_mac(peer_router, int(peer_port))


def gateway_of(host):
    h = HOSTS[host]
    iface = ROUTERS[h["router"]][h["port"]]
    return iface["ip"], iface["ip6"], router_mac(h["router"], h["port"])


def build_topology():
    hosts = {}
    for name, h in HOSTS.items():
        gw_ip, gw_ip6, gw_mac = gateway_of(name)
        hosts[name] = {
            "ip": h["ip"] + "/24",
            "mac": h["mac"],
            "commands": [
                # IPv4: gateway por defecto + ARP estático (el router no responde ARP)
                "route add default gw %s dev eth0" % gw_ip,
                "arp -i eth0 -s %s %s" % (gw_ip, gw_mac),
                # IPv6 (opcional): Mininet/P4Host lo deshabilita, se reactiva aquí
                "sysctl -w net.ipv6.conf.all.disable_ipv6=0",
                "sysctl -w net.ipv6.conf.eth0.disable_ipv6=0",
                "ip -6 addr add %s/64 dev eth0 nodad" % h["ip6"],
                "ip -6 neigh replace %s lladdr %s dev eth0 nud permanent" % (gw_ip6, gw_mac),
                "ip -6 route add default via %s dev eth0" % gw_ip6,
            ],
        }

    switches = {r: {"runtime_json": "runtime/%s-runtime.json" % r} for r in ROUTERS}

    links = []
    for name, h in HOSTS.items():                       # host primero (lo exige run_exercise)
        links.append([name, "%s-p%d" % (h["router"], h["port"])])
    seen = set()
    for r, ports in ROUTERS.items():
        for p, iface in ports.items():
            peer = iface["peer"]
            if peer.startswith("h"):
                continue
            a, b = "%s-p%d" % (r, p), peer
            if (b, a) in seen:
                continue
            seen.add((a, b))
            links.append([a, b])

    return {"hosts": hosts, "switches": switches, "links": links}


def entry(table, match, action, params):
    return {"table": table, "match": match, "action_name": action, "action_params": params}


def build_runtime(router):
    entries = [
        {"table": "MyIngress.ipv4_lpm", "default_action": True,
         "action_name": "MyIngress.drop_no_route", "action_params": {}},
        {"table": "MyIngress.ipv6_lpm", "default_action": True,
         "action_name": "MyIngress.drop_no_route_v6", "action_params": {}},
    ]

    # MAC e IP de cada interfaz del router
    for port, iface in sorted(ROUTERS[router].items()):
        entries.append(entry("MyEgress.port_mac",
                             {"standard_metadata.egress_port": port},
                             "MyEgress.set_smac",
                             {"mac": router_mac(router, port)}))
        entries.append(entry("MyIngress.port_ipv4",
                             {"standard_metadata.ingress_port": port},
                             "MyIngress.set_router_ip",
                             {"ip": iface["ip"]}))

    for prefix, port in ROUTES_V4[router]:
        net, plen = prefix.split("/")
        entries.append(entry("MyIngress.ipv4_lpm",
                             {"hdr.ipv4.dstAddr": [net, int(plen)]},
                             "MyIngress.ipv4_forward",
                             {"dstAddr": peer_mac(router, port), "port": port}))

    for prefix, port in ROUTES_V6[router]:
        net, plen = prefix.split("/")
        entries.append(entry("MyIngress.ipv6_lpm",
                             {"hdr.ipv6.dstAddr": [net, int(plen)]},
                             "MyIngress.ipv6_forward",
                             {"dstAddr": peer_mac(router, port), "port": port}))

    return {"target": "bmv2", "p4info": P4INFO, "bmv2_json": BMV2_JSON,
            "table_entries": entries}


def show_plan():
    print("== Hosts ==")
    for name, h in HOSTS.items():
        gw_ip, _, gw_mac = gateway_of(name)
        print("  %s  %-10s %s  gw %s (%s)  conectado a %s-p%d"
              % (name, h["ip"], h["mac"], gw_ip, gw_mac, h["router"], h["port"]))
    print("== Interfaces de los routers ==")
    for r, ports in ROUTERS.items():
        for p, iface in sorted(ports.items()):
            print("  %s-p%d  %-11s %s  -> %s" % (r, p, iface["ip"], router_mac(r, p), iface["peer"]))
    print("== Rutas IPv4 ==")
    for r, routes in ROUTES_V4.items():
        for prefix, port in routes:
            print("  %s: %-14s -> puerto %d (siguiente salto %s, %s)"
                  % (r, prefix, port, ROUTERS[r][port]["peer"], peer_mac(r, port)))
        print("  %s: %-14s -> DROP (acción por defecto)" % (r, "*"))


def main():
    parser = argparse.ArgumentParser(description="Genera topology.json y runtime/*.json")
    parser.add_argument("--show", action="store_true", help="imprime el plan de direccionamiento")
    args = parser.parse_args()

    os.makedirs(os.path.join(HERE, "runtime"), exist_ok=True)
    with open(os.path.join(HERE, "topology.json"), "w") as f:
        json.dump(build_topology(), f, indent=2)
    for r in ROUTERS:
        with open(os.path.join(HERE, "runtime", "%s-runtime.json" % r), "w") as f:
            json.dump(build_runtime(r), f, indent=2)
    print("Generados topology.json y runtime/{%s}-runtime.json" % ",".join(ROUTERS))

    if args.show:
        show_plan()


if __name__ == "__main__":
    main()
