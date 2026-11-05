# Simulador de Máquina de Turing

Aplicación de escritorio para construir, visualizar y ejecutar máquinas de Turing. Está desarrollada en Python con Tkinter y tiene una interfaz en español.

## Funcionalidades

- Cargar y guardar configuraciones de máquinas en `turing_machines.json`.
- Crear máquinas indicando estados, alfabetos, estados finales y transiciones.
- Validar que las transiciones sean deterministas y que usen símbolos válidos.
- Ejecutar una máquina paso a paso o automáticamente.
- Visualizar la cinta, el cabezal, el estado actual y el grafo de transiciones.
- Generar palabras aleatorias para probar una configuración.
- Usar un modo manual tipo sandbox para experimentar con la cinta.
- Guardar el resultado de ejecuciones y exportar una sesión manual como configuración.

## Requisitos

- Python 3.10 o posterior.
- Tkinter, incluido normalmente en las instalaciones oficiales de Python para Windows y macOS.

En Linux, instala Tkinter con:

```bash
sudo apt install python3-tk
```

## Ejecución

Desde la carpeta del proyecto:

```bash
python turing.py
```

En Windows también puedes usar:

```powershell
py turing.py
```

## Archivos principales

- `turing.py`: aplicación y motor de simulación.
- `turing_machines.json`: configuraciones de ejemplo y máquinas guardadas.

La aplicación puede crear `cintas_guardadas.json` al guardar resultados de ejecuciones. Ese archivo es local y generado por el usuario; no es necesario incluirlo en el repositorio.

## Convenciones de las transiciones

Las direcciones aceptadas son:

- `R` o `D`: mover a la derecha.
- `L` o `I`: mover a la izquierda.
- `S`: permanecer en la misma celda y detenerse.

El símbolo blanco predeterminado es `^`.

## Licencia

Este proyecto no especifica todavía una licencia.
