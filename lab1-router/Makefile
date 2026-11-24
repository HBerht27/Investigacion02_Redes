# Laboratorio 1 - Router IPv4 estático
#
#   make run     compila router.p4, genera la topología y levanta Mininet
#   make stop    limpia Mininet (mn -c)
#   make clean   stop + borra build/, logs/ y pcaps/
#
# Usa la infraestructura del repositorio oficial p4lang/tutorials, que ya
# viene en la VM (/home/p4/tutorials). Si está en otro lugar:
#   make run TUTORIALS=/ruta/a/tutorials

TUTORIALS  ?= $(HOME)/tutorials
RUN_SCRIPT  = $(TUTORIALS)/utils/run_exercise.py

P4C        = p4c-bm2-ss
BMV2_EXE   = simple_switch_grpc
BUILD_DIR  = build
PCAP_DIR   = pcaps
LOG_DIR    = logs

PROG       = router
P4_JSON    = $(BUILD_DIR)/$(PROG).json
P4INFO     = $(BUILD_DIR)/$(PROG).p4info.txtpb

.PHONY: all run build topo stop clean

all: run

run: build topo
	sudo PATH=$(PATH) python3 $(RUN_SCRIPT) -t topology.json -j $(P4_JSON) -b $(BMV2_EXE)

build: dirs $(P4_JSON)

$(P4_JSON): $(PROG).p4
	$(P4C) --p4v 16 --p4runtime-files $(P4INFO) -o $@ $<

topo:
	python3 topology.py

dirs:
	mkdir -p $(BUILD_DIR) $(PCAP_DIR) $(LOG_DIR)

stop:
	sudo PATH=$(PATH) `which mn` -c

clean: stop
	rm -rf $(BUILD_DIR) $(PCAP_DIR) $(LOG_DIR)
