# Investigación 2 de Redes: Redes programables con P4

Tarea de Redes sobre el plano de datos programable. Incluye un informe de investigación sobre P4 y dos laboratorios implementados en P4₁₆ para BMv2.

## Integrantes

- Roberto Murillo Lozano C05436
- Matías Venegas Sancho C4K929

## Estructura del repositorio

| Carpeta / archivo | Contenido |
|---|---|
| `lab1-router/` | Laboratorio 1: router IPv4 estático (LPM, TTL, reescritura de MAC, ICMP Time Exceeded) |
| `lab2-counters/` | Laboratorio 2: contadores y estadísticas de tráfico, con detección de flujo elefante |
| `informe/` | Informe de investigación (`informe.pdf`) |
| `demo.mp4` / enlace | Video demostrativo (máximo 5 minutos): [completar enlace] |

Cada laboratorio tiene su propio `README.md` con el detalle de las funcionalidades, la topología y las pruebas.

## Requisitos

Los laboratorios se desarrollaron y probaron en la VM de P4 de los tutoriales oficiales (usuario `p4`), que ya trae:

- `p4c` (compilador P4, `p4c-bm2-ss`)
- BMv2 (`simple_switch_grpc` y `simple_switch_CLI`)
- Mininet
- Scapy
- iperf
- El repositorio [p4lang/tutorials](https://github.com/p4lang/tutorials) en `~/tutorials`, del que se usa `utils/run_exercise.py`

Si el repositorio de tutoriales está en otra ruta, se indica con `make run TUTORIALS=/ruta/a/tutorials`.

## Cómo ejecutar los laboratorios

Los dos laboratorios son independientes. Cada uno se ejecuta desde su carpeta.

### Laboratorio 1: router IPv4 estático

```bash
cd lab1-router
make run                  # compila, genera la topología y abre el CLI de Mininet
```

Dentro de Mininet se pueden correr todas las pruebas con `source tests/demo.mn`. Detalles en [`lab1-router/README.md`](lab1-router/README.md).

### Laboratorio 2: contadores y estadísticas

Se usan dos terminales.

```bash
# Terminal 1
cd lab2-counters
make run                  # compila y abre el CLI de Mininet

# Terminal 2
cd lab2-counters
make controller           # lee y muestra las estadísticas cada 5 s
```

El tráfico de prueba se genera desde el CLI de Mininet con `traffic_gen.py` o `iperf`. Detalles y resultados esperados en [`lab2-counters/README.md`](lab2-counters/README.md).

### Limpieza

Al terminar, en la carpeta del laboratorio:

```bash
make clean                # detiene Mininet y borra build/, logs/ y pcaps/
```
