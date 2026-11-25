/* -*- P4_16 -*- */
/*
 * Lab 2 - Contadores y estadisticas de trafico (arquitectura v1model / BMv2)
 *
 * Funciones:
 *  1. Direct counters por flujo (IP origen + IP destino)  -> tabla flow_stats
 *  2. Contadores globales por protocolo: TCP, UDP, ICMP, otros -> proto_counter
 *  3. Tamano de paquetes con registers: histograma, maximo, minimo, ultimo
 *  4. Deteccion de flujo elefante: bytes acumulados por flujo (register) contra un
 *     umbral configurable desde el control plane (register elephant_threshold).
 *     Al superarlo se marca el flujo en elephant_flag y se cuentan sus paquetes.
 *
 * El reenvio es L2 (por MAC destino) porque el lab usa 1 solo switch.
 */
#include <core.p4>
#include <v1model.p4>

const bit<16> TYPE_IPV4  = 0x0800;
const bit<8>  PROTO_ICMP = 1;
const bit<8>  PROTO_TCP  = 6;
const bit<8>  PROTO_UDP  = 17;

#define MAX_FLOWS   64     // maximo de flujos rastreados (flow_id < 64)
#define NUM_BUCKETS 6      // histograma de tamanos

typedef bit<9>  egressSpec_t;
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

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

struct metadata {
    bit<32> flow_id;
    bit<1>  tracked;
}

struct headers {
    ethernet_t ethernet;
    ipv4_t     ipv4;
}

/*************************** PARSER ***************************/
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
            default:   accept;
        }
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition accept;
    }
}

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}

/*************************** INGRESS ***************************/
control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    /* 2. Contadores por protocolo: 0=TCP 1=UDP 2=ICMP 3=otros */
    counter(4, CounterType.packets_and_bytes) proto_counter;

    /* 1. Direct counter asociado a la tabla de flujos */
    direct_counter(CounterType.packets_and_bytes) flow_counter;

    /* 3. Tamano de paquetes */
    register<bit<32>>(NUM_BUCKETS) size_hist;   // <=64,<=128,<=256,<=512,<=1024,>1024
    register<bit<32>>(3)           size_stats;  // 0=max, 1=min, 2=ultimo

    /* 4. Flujo elefante */
    register<bit<64>>(MAX_FLOWS) flow_bytes;        // bytes acumulados por flujo
    register<bit<1>>(MAX_FLOWS)  elephant_flag;     // 1 = flujo marcado como elefante
    register<bit<32>>(MAX_FLOWS) elephant_pkts;     // paquetes vistos despues de marcarse
    register<bit<64>>(1)         elephant_threshold; // umbral en bytes (0 = deshabilitado)

    action drop() {
        mark_to_drop(standard_metadata);
    }

    action forward(egressSpec_t port) {
        standard_metadata.egress_spec = port;
    }

    action track_flow(bit<32> flow_id) {
        meta.flow_id = flow_id;
        meta.tracked = 1;
        flow_counter.count();        // direct counter: cuenta por entrada de la tabla
    }

    table dmac_fwd {
        key = { hdr.ethernet.dstAddr: exact; }
        actions = { forward; drop; }
        size = 16;
        default_action = drop();
    }

    table flow_stats {
        key = {
            hdr.ipv4.srcAddr: exact;
            hdr.ipv4.dstAddr: exact;
        }
        actions = { track_flow; NoAction; }
        counters = flow_counter;
        size = MAX_FLOWS;
        default_action = NoAction();
    }

    apply {
        bit<32> len   = standard_metadata.packet_length;  // bytes de la trama (incluye Ethernet)
        bit<32> pidx  = 3;
        bit<32> b     = 5;
        bit<32> tmp32 = 0;
        bit<64> acc   = 0;
        bit<64> thr   = 0;
        bit<1>  flag  = 0;

        meta.tracked = 0;
        meta.flow_id = 0;

        if (hdr.ipv4.isValid()) {
            /* ---- contador por protocolo ---- */
            if (hdr.ipv4.protocol == PROTO_TCP)       { pidx = 0; }
            else if (hdr.ipv4.protocol == PROTO_UDP)  { pidx = 1; }
            else if (hdr.ipv4.protocol == PROTO_ICMP) { pidx = 2; }
            proto_counter.count(pidx);

            /* ---- histograma de tamanos ---- */
            if (len <= 64)        { b = 0; }
            else if (len <= 128)  { b = 1; }
            else if (len <= 256)  { b = 2; }
            else if (len <= 512)  { b = 3; }
            else if (len <= 1024) { b = 4; }
            size_hist.read(tmp32, b);
            size_hist.write(b, tmp32 + 1);

            /* ---- maximo, minimo y ultimo tamano ---- */
            size_stats.read(tmp32, 0);
            if (len > tmp32) { size_stats.write(0, len); }
            size_stats.read(tmp32, 1);
            if (tmp32 == 0 || len < tmp32) { size_stats.write(1, len); }
            size_stats.write(2, len);

            /* ---- contador directo por flujo + deteccion de elefante ---- */
            flow_stats.apply();
            if (meta.tracked == 1) {
                flow_bytes.read(acc, meta.flow_id);
                acc = acc + (bit<64>) len;
                flow_bytes.write(meta.flow_id, acc);

                elephant_threshold.read(thr, 0);
                if (thr != 0 && acc >= thr) {
                    elephant_flag.write(meta.flow_id, 1);
                    elephant_pkts.read(tmp32, meta.flow_id);
                    elephant_pkts.write(meta.flow_id, tmp32 + 1);
                }
            }
        }

        dmac_fwd.apply();
    }
}

/*************************** EGRESS ***************************/
control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {
    apply { }
}

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply { }   // no se modifica el paquete, no hay que recalcular checksum
}

/*************************** DEPARSER ***************************/
control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
    }
}

V1Switch(
    MyParser(),
    MyVerifyChecksum(),
    MyIngress(),
    MyEgress(),
    MyComputeChecksum(),
    MyDeparser()
) main;
