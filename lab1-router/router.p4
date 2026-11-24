/* -*- P4_16 -*- */
/*
 * Laboratorio 1 - Router IPv4 estático en P4 (arquitectura v1model / BMv2)
 *
 * Funcionalidades:
 *   - Parsing de Ethernet, IPv4 e IPv6.
 *   - Tablas de enrutamiento LPM (Longest Prefix Match) para IPv4 e IPv6,
 *     cargadas estáticamente desde el plano de control (P4Runtime).
 *   - Decremento del TTL (IPv4) / Hop Limit (IPv6) en cada salto.
 *   - Descarte de paquetes cuyo TTL llegaría a 0.
 *   - Reescritura de MAC destino (siguiente salto) y MAC origen (MAC de la
 *     interfaz de salida del router).
 *   - Generación de ICMP Time Exceeded (tipo 11, código 0) cuando el TTL se
 *     agota (funcionalidad opcional).
 *   - Descarte por defecto de paquetes sin ruta (default drop).
 *   - Contador de estadísticas para justificar cada descarte.
 *
 * Simplificaciones (documentadas en el README):
 *   - No se soportan opciones IPv4 (IHL != 5): esos paquetes se descartan.
 *   - El router no responde ARP; los hosts usan entradas ARP estáticas.
 *   - El ICMP Time Exceeded se devuelve por el mismo puerto por el que entró
 *     el paquete original, hacia la MAC que lo envió (el salto anterior).
 */
#include <core.p4>
#include <v1model.p4>

/*************************************************************************
 *********************** C O N S T A N T E S *****************************
 *************************************************************************/

const bit<16> TYPE_IPV4 = 0x0800;
const bit<16> TYPE_IPV6 = 0x86DD;

const bit<8>  PROTO_ICMP = 1;

const bit<8>  ICMP_DEST_UNREACHABLE = 3;
const bit<8>  ICMP_TIME_EXCEEDED    = 11;
const bit<8>  ICMP_PARAM_PROBLEM    = 12;
const bit<8>  ICMP_TTL_EXCEEDED_IN_TRANSIT = 0;   /* código del tipo 11 */

const bit<8>  ICMP_DEFAULT_TTL = 64;

/* Tamaño del paquete ICMP Time Exceeded generado:
 *   IPv4 nueva (20) + ICMP (8) + IPv4 original (20) + 8 bytes de datos = 56
 * y con Ethernet (14) el frame completo mide 70 bytes. */
const bit<16> ICMP_TE_IP_TOTAL_LEN = 56;
const bit<32> ICMP_TE_FRAME_LEN    = 70;

/* Índices del contador de estadísticas `stats` */
const bit<32> STAT_V4_NO_ROUTE     = 0;  /* IPv4 descartado: sin ruta          */
const bit<32> STAT_V4_TTL_EXPIRED  = 1;  /* IPv4 descartado: TTL agotado       */
const bit<32> STAT_V4_BAD_CHECKSUM = 2;  /* IPv4 descartado: checksum inválido */
const bit<32> STAT_V6_DROP         = 3;  /* IPv6 descartado (sin ruta o HL=0)  */
const bit<32> STAT_OTHER_DROP      = 4;  /* No IP (p.ej. ARP) u opciones IPv4  */
const bit<32> STAT_ICMP_TE_SENT    = 5;  /* ICMP Time Exceeded generados       */
const bit<32> STAT_V4_FORWARDED    = 6;  /* IPv4 reenviados correctamente      */
const bit<32> STAT_V6_FORWARDED    = 7;  /* IPv6 reenviados correctamente      */
const bit<32> NUM_STATS            = 8;

/*************************************************************************
 *********************** C A B E C E R A S *******************************
 *************************************************************************/

typedef bit<9>   egressSpec_t;
typedef bit<48>  macAddr_t;
typedef bit<32>  ip4Addr_t;
typedef bit<128> ip6Addr_t;

header ethernet_t {
    macAddr_t dstAddr;
    macAddr_t srcAddr;
    bit<16>   etherType;
}

header ipv4_t {
    bit<4>    version;
    bit<4>    ihl;
    bit<8>    diffserv;
    bit<16>   totalLen;
    bit<16>   identification;
    bit<3>    flags;
    bit<13>   fragOffset;
    bit<8>    ttl;
    bit<8>    protocol;
    bit<16>   hdrChecksum;
    ip4Addr_t srcAddr;
    ip4Addr_t dstAddr;
}

header ipv6_t {
    bit<4>    version;
    bit<8>    trafficClass;
    bit<20>   flowLabel;
    bit<16>   payloadLen;
    bit<8>    nextHdr;
    bit<8>    hopLimit;
    ip6Addr_t srcAddr;
    ip6Addr_t dstAddr;
}

/* Cabecera ICMP genérica de 8 bytes (tipo, código, checksum y 4 bytes
 * cuyo significado depende del tipo; en Time Exceeded van en cero). */
header icmp_t {
    bit<8>  type;
    bit<8>  code;
    bit<16> checksum;
    bit<32> rest;
}

/* Primeros 8 bytes después de la cabecera IPv4. Se extraen para poder
 * incluirlos en el mensaje ICMP Time Exceeded (RFC 792) y en su checksum.
 * En paquetes reenviados normalmente se vuelven a emitir sin cambios. */
header l4_peek_t {
    bit<64> data;
}

struct metadata {
    ip4Addr_t router_ip;        /* IP de la interfaz de entrada del router */
    bit<1>    router_ip_valid;  /* 1 si la tabla port_ipv4 tuvo hit        */
}

struct headers {
    ethernet_t ethernet;
    ipv4_t     icmp_ipv4;   /* IPv4 exterior del ICMP generado (solo TE) */
    icmp_t     icmp_te;     /* cabecera ICMP Time Exceeded (solo TE)     */
    ipv4_t     ipv4;        /* IPv4 del paquete recibido                 */
    ipv6_t     ipv6;
    l4_peek_t  l4_peek;
}

/*************************************************************************
 *************************** P A R S E R *********************************
 *************************************************************************/

parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t standard_metadata) {

    state start {
        transition parse_ethernet;
    }

    state parse_ethernet {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.etherType) {
            TYPE_IPV4: parse_ipv4;
            TYPE_IPV6: parse_ipv6;
            default:   accept;
        }
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        /* Solo se miran los 8 bytes siguientes si no hay opciones IPv4 */
        transition select(hdr.ipv4.ihl) {
            5:       parse_l4_peek;
            default: accept;
        }
    }

    state parse_l4_peek {
        packet.extract(hdr.l4_peek);
        transition accept;
    }

    state parse_ipv6 {
        packet.extract(hdr.ipv6);
        transition accept;
    }
}

/*************************************************************************
 ************   V E R I F I C A C I Ó N   D E   C H E C K S U M   *********
 *************************************************************************/

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply {
        /* Si el checksum no coincide, BMv2 pone
         * standard_metadata.checksum_error = 1 y el ingress lo descarta. */
        verify_checksum(
            hdr.ipv4.isValid() && hdr.ipv4.ihl == 5,
            { hdr.ipv4.version,
              hdr.ipv4.ihl,
              hdr.ipv4.diffserv,
              hdr.ipv4.totalLen,
              hdr.ipv4.identification,
              hdr.ipv4.flags,
              hdr.ipv4.fragOffset,
              hdr.ipv4.ttl,
              hdr.ipv4.protocol,
              hdr.ipv4.srcAddr,
              hdr.ipv4.dstAddr },
            hdr.ipv4.hdrChecksum,
            HashAlgorithm.csum16);
    }
}

/*************************************************************************
 ***************  I N G R E S S   P R O C E S S I N G   ******************
 *************************************************************************/

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    /* Estadísticas del router: se leen con simple_switch_CLI
     *   counter_read MyIngress.stats <índice>  */
    counter(NUM_STATS, CounterType.packets) stats;

    action drop() {
        mark_to_drop(standard_metadata);
    }

    /* ---------------------------- IPv4 -------------------------------- */

    /* Acción por defecto de ipv4_lpm: si no hay ruta, se descarta. */
    action drop_no_route() {
        stats.count(STAT_V4_NO_ROUTE);
        mark_to_drop(standard_metadata);
    }

    /* Reenvío IPv4: puerto de salida, MAC del siguiente salto y TTL - 1.
     * La MAC origen se reescribe en el egress según el puerto de salida. */
    action ipv4_forward(macAddr_t dstAddr, egressSpec_t port) {
        standard_metadata.egress_spec = port;
        hdr.ethernet.dstAddr = dstAddr;
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
        stats.count(STAT_V4_FORWARDED);
    }

    table ipv4_lpm {
        key = {
            hdr.ipv4.dstAddr: lpm;
        }
        actions = {
            ipv4_forward;
            drop_no_route;
        }
        size = 1024;
        default_action = drop_no_route();
    }

    /* ---------------------------- IPv6 -------------------------------- */

    action drop_no_route_v6() {
        stats.count(STAT_V6_DROP);
        mark_to_drop(standard_metadata);
    }

    action ipv6_forward(macAddr_t dstAddr, egressSpec_t port) {
        standard_metadata.egress_spec = port;
        hdr.ethernet.dstAddr = dstAddr;
        hdr.ipv6.hopLimit = hdr.ipv6.hopLimit - 1;
        stats.count(STAT_V6_FORWARDED);
    }

    table ipv6_lpm {
        key = {
            hdr.ipv6.dstAddr: lpm;
        }
        actions = {
            ipv6_forward;
            drop_no_route_v6;
        }
        size = 1024;
        default_action = drop_no_route_v6();
    }

    /* ------------------ ICMP Time Exceeded (opcional) ------------------ */

    /* IP que el router tiene en cada puerto. Se usa como IP origen del
     * mensaje ICMP Time Exceeded que se devuelve por ese puerto. */
    action set_router_ip(ip4Addr_t ip) {
        meta.router_ip = ip;
        meta.router_ip_valid = 1;
    }

    table port_ipv4 {
        key = {
            standard_metadata.ingress_port: exact;
        }
        actions = {
            set_router_ip;
            NoAction;
        }
        size = 64;
        default_action = NoAction();
    }

    /* Convierte el paquete recibido en un ICMP Time Exceeded:
     *
     *   antes:  Ethernet | IPv4 original | 8 bytes | resto...
     *   ahora:  Ethernet | IPv4 nueva | ICMP(11,0) | IPv4 original | 8 bytes
     *
     * La IPv4 original se deja intacta (tal como llegó) porque el RFC 792
     * pide incluirla en el mensaje. El resto del paquete se elimina con
     * truncate(). Los checksums se calculan en MyComputeChecksum. */
    action send_icmp_time_exceeded() {
        hdr.icmp_ipv4.setValid();
        hdr.icmp_ipv4.version        = 4;
        hdr.icmp_ipv4.ihl            = 5;
        hdr.icmp_ipv4.diffserv       = 0;
        hdr.icmp_ipv4.totalLen       = ICMP_TE_IP_TOTAL_LEN;
        hdr.icmp_ipv4.identification = 0;
        hdr.icmp_ipv4.flags          = 0;
        hdr.icmp_ipv4.fragOffset     = 0;
        hdr.icmp_ipv4.ttl            = ICMP_DEFAULT_TTL;
        hdr.icmp_ipv4.protocol       = PROTO_ICMP;
        hdr.icmp_ipv4.hdrChecksum    = 0;
        hdr.icmp_ipv4.srcAddr        = meta.router_ip;
        hdr.icmp_ipv4.dstAddr        = hdr.ipv4.srcAddr;

        hdr.icmp_te.setValid();
        hdr.icmp_te.type     = ICMP_TIME_EXCEEDED;
        hdr.icmp_te.code     = ICMP_TTL_EXCEEDED_IN_TRANSIT;
        hdr.icmp_te.checksum = 0;
        hdr.icmp_te.rest     = 0;

        /* Se devuelve a quien lo envió (host o router anterior). La MAC
         * origen la pone el egress con la MAC del puerto de salida. */
        hdr.ethernet.dstAddr = hdr.ethernet.srcAddr;
        standard_metadata.egress_spec = standard_metadata.ingress_port;

        truncate(ICMP_TE_FRAME_LEN);
        stats.count(STAT_ICMP_TE_SENT);
    }

    /* --------------------------- Pipeline ------------------------------ */

    apply {
        if (hdr.ipv4.isValid()) {

            if (standard_metadata.checksum_error == 1) {
                stats.count(STAT_V4_BAD_CHECKSUM);
                drop();

            } else if (hdr.ipv4.ihl != 5) {
                /* Opciones IPv4 no soportadas */
                stats.count(STAT_OTHER_DROP);
                drop();

            } else if (hdr.ipv4.ttl <= 1) {
                /* Al decrementar, el TTL quedaría en 0: no se reenvía. */
                stats.count(STAT_V4_TTL_EXPIRED);
                port_ipv4.apply();

                /* No se generan errores ICMP en respuesta a otros errores
                 * ICMP (RFC 1812, sección 4.3.2.7). */
                bool is_icmp_error = hdr.ipv4.protocol == PROTO_ICMP &&
                                     hdr.l4_peek.isValid() &&
                                     (hdr.l4_peek.data[63:56] == ICMP_DEST_UNREACHABLE ||
                                      hdr.l4_peek.data[63:56] == ICMP_TIME_EXCEEDED ||
                                      hdr.l4_peek.data[63:56] == ICMP_PARAM_PROBLEM);

                if (meta.router_ip_valid == 1 &&
                    hdr.l4_peek.isValid() &&
                    !is_icmp_error) {
                    send_icmp_time_exceeded();
                } else {
                    drop();
                }

            } else {
                /* Caso normal: búsqueda LPM. Sin ruta => drop_no_route */
                ipv4_lpm.apply();
            }

        } else if (hdr.ipv6.isValid()) {

            if (hdr.ipv6.hopLimit <= 1) {
                stats.count(STAT_V6_DROP);
                drop();
            } else {
                ipv6_lpm.apply();
            }

        } else {
            /* Tráfico no IP (p.ej. ARP): el router no lo procesa. */
            stats.count(STAT_OTHER_DROP);
            drop();
        }
    }
}

/*************************************************************************
 ****************  E G R E S S   P R O C E S S I N G   *******************
 *************************************************************************/

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {

    /* MAC de cada interfaz del router. Al salir por un puerto, la MAC
     * origen del frame pasa a ser la MAC de ese puerto. */
    action set_smac(macAddr_t mac) {
        hdr.ethernet.srcAddr = mac;
    }

    table port_mac {
        key = {
            standard_metadata.egress_port: exact;
        }
        actions = {
            set_smac;
            NoAction;
        }
        size = 64;
        default_action = NoAction();
    }

    apply {
        if (hdr.ethernet.isValid()) {
            port_mac.apply();
        }
    }
}

/*************************************************************************
 *************   C Á L C U L O   D E   C H E C K S U M S   ***************
 *************************************************************************/

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply {
        /* 1) IPv4 reenviada: el TTL cambió, hay que recalcular.
         *    Si se generó un ICMP TE, la IPv4 original va citada dentro
         *    del ICMP y se deja exactamente como llegó. */
        update_checksum(
            hdr.ipv4.isValid() && !hdr.icmp_te.isValid(),
            { hdr.ipv4.version,
              hdr.ipv4.ihl,
              hdr.ipv4.diffserv,
              hdr.ipv4.totalLen,
              hdr.ipv4.identification,
              hdr.ipv4.flags,
              hdr.ipv4.fragOffset,
              hdr.ipv4.ttl,
              hdr.ipv4.protocol,
              hdr.ipv4.srcAddr,
              hdr.ipv4.dstAddr },
            hdr.ipv4.hdrChecksum,
            HashAlgorithm.csum16);

        /* 2) Cabecera IPv4 exterior del ICMP Time Exceeded. */
        update_checksum(
            hdr.icmp_ipv4.isValid(),
            { hdr.icmp_ipv4.version,
              hdr.icmp_ipv4.ihl,
              hdr.icmp_ipv4.diffserv,
              hdr.icmp_ipv4.totalLen,
              hdr.icmp_ipv4.identification,
              hdr.icmp_ipv4.flags,
              hdr.icmp_ipv4.fragOffset,
              hdr.icmp_ipv4.ttl,
              hdr.icmp_ipv4.protocol,
              hdr.icmp_ipv4.srcAddr,
              hdr.icmp_ipv4.dstAddr },
            hdr.icmp_ipv4.hdrChecksum,
            HashAlgorithm.csum16);

        /* 3) Checksum ICMP: cubre la cabecera ICMP y todos sus datos
         *    (IPv4 original completa + primeros 8 bytes). */
        update_checksum(
            hdr.icmp_te.isValid(),
            { hdr.icmp_te.type,
              hdr.icmp_te.code,
              hdr.icmp_te.rest,
              hdr.ipv4.version,
              hdr.ipv4.ihl,
              hdr.ipv4.diffserv,
              hdr.ipv4.totalLen,
              hdr.ipv4.identification,
              hdr.ipv4.flags,
              hdr.ipv4.fragOffset,
              hdr.ipv4.ttl,
              hdr.ipv4.protocol,
              hdr.ipv4.hdrChecksum,
              hdr.ipv4.srcAddr,
              hdr.ipv4.dstAddr,
              hdr.l4_peek.data },
            hdr.icmp_te.checksum,
            HashAlgorithm.csum16);
    }
}

/*************************************************************************
 *************************  D E P A R S E R  *****************************
 *************************************************************************/

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        /* emit() ignora las cabeceras inválidas, así que el mismo orden
         * sirve para paquetes reenviados y para ICMP Time Exceeded. */
        packet.emit(hdr.ethernet);
        packet.emit(hdr.icmp_ipv4);
        packet.emit(hdr.icmp_te);
        packet.emit(hdr.ipv4);
        packet.emit(hdr.ipv6);
        packet.emit(hdr.l4_peek);
    }
}

/*************************************************************************
 *************************  S W I T C H  *********************************
 *************************************************************************/

V1Switch(
    MyParser(),
    MyVerifyChecksum(),
    MyIngress(),
    MyEgress(),
    MyComputeChecksum(),
    MyDeparser()
) main;
