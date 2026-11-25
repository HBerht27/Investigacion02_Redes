# Laboratorio 2 - Contadores y estadísticas de tráfico
#
#   make run          compila counters.p4 y levanta Mininet (1 switch, 4 hosts)
#   make controller   (en otra terminal) instala tablas y muestra estadísticas cada 5 s
#   make stop         limpia Mininet (mn -c)
#   make clean        stop + borra build/, logs/ y pcaps/
#
# Usa la infraestructura de p4lang/tutorials (igual que el Lab 1).
#   make run TUTORIALS=/ruta/a/tutorials

TUTORIALS  ?= $(HOME)/tutorials
RUN_SCRIPT  = $(TUTORIALS)/utils/run_exercise.py

P4C        = p4c-bm2-ss
BMV2_EXE   = simple_switch_grpc
BUILD_DIR  = build
PCAP_DIR   = pcaps
LOG_DIR    = logs

PROG       = counters
P4_JSON    = $(BUILD_DIR)/$(PROG).json
P4INFO     = $(BUILD_DIR)/$(PROG).p4info.txtpb

THRESHOLD ?= 100000

.PHONY: all run build controller stop clean

all: run

run: build
	sudo PATH=$(PATH) python3 $(RUN_SCRIPT) -t topology.json -j $(P4_JSON) -b $(BMV2_EXE)

build: dirs $(P4_JSON)

$(P4_JSON): $(PROG).p4
	$(P4C) --p4v 16 --p4runtime-files $(P4INFO) -o $@ $<

controller:
	python3 controller.py --reset --threshold $(THRESHOLD)

dirs:
	mkdir -p $(BUILD_DIR) $(PCAP_DIR) $(LOG_DIR)

stop:
	sudo PATH=$(PATH) `which mn` -c

clean: stop
	rm -rf $(BUILD_DIR) $(PCAP_DIR) $(LOG_DIR)
