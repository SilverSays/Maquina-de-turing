
import json
import math
import os
import random
from datetime import datetime

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, simpledialog
except ImportError:  # tkinter no está instalado
    tk = ttk = messagebox = simpledialog = None

CARPETA = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_CONFIG = os.path.join(CARPETA, "turing_machines.json")
ARCHIVO_CINTAS = os.path.join(CARPETA, "cintas_guardadas.json")

BLANCO = "^"          # símbolo blanco por defecto
CELDAS = 50           # celdas visibles de la cinta
MAX_PASOS = 10000     # protección contra bucles infinitos

# Se aceptan D/I (español) y R/L (inglés) como sinónimos.
DIRECCIONES = {"R": "R", "D": "R", "L": "L", "I": "L", "S": "S"}


# ====================================================================
#                            MOTOR (sin interfaz)
# ====================================================================
def parsear_conjunto(texto):
    """'q0, q1 q2' -> ['q0', 'q1', 'q2'] (sin repetidos, conserva el orden)."""
    return list(dict.fromkeys(texto.replace(",", " ").split()))


def cinta_aleatoria(simbolos, largo, con_blanco=True, blanco=BLANCO):
    """Palabra aleatoria de `largo` celdas con los símbolos dados (y blancos si se pide)."""
    pool = list(simbolos) + ([blanco] if con_blanco else [])
    return "".join(random.choice(pool) for _ in range(largo))


def normalizar_direccion(d):
    d = str(d).strip().upper()
    if d not in DIRECCIONES:
        raise ValueError(f"Dirección inválida '{d}' (use R/D, L/I o S).")
    return DIRECCIONES[d]


def fmt_transicion(q, x, q2, y, d):
    return f"δ({q},{x}) = ({q2},{y},{d})"


class Cinta:
    """Cinta infinita en ambos sentidos; solo guarda las celdas no blancas."""

    def __init__(self, texto="", blanco=BLANCO):
        self.blanco = blanco
        self.celdas = {i: c for i, c in enumerate(texto) if c != blanco}

    def leer(self, pos):
        return self.celdas.get(pos, self.blanco)

    def escribir(self, pos, simbolo):
        if simbolo == self.blanco:
            self.celdas.pop(pos, None)
        else:
            self.celdas[pos] = simbolo

    def rango(self, cabezal=0):
        claves = list(self.celdas) + [0, cabezal]
        return min(claves), max(claves)

    def segmento(self, desde, hasta):
        return "".join(self.leer(i) for i in range(desde, hasta + 1))

    def contenido(self, cabezal=0):
        return self.segmento(*self.rango(cabezal))


class TuringMachine:
    def __init__(self, name, states, input_alphabet, tape_alphabet, blank_symbol,
                 initial_state, final_states, transitions, input_word=""):
        self.name = name
        self.states = set(states)
        self.input_alphabet = set(input_alphabet)
        self.tape_alphabet = set(tape_alphabet)
        self.blank = blank_symbol
        self.initial_state = initial_state
        self.final_states = set(final_states)
        # {(estado, simbolo): (nuevo_estado, simbolo_a_escribir, 'R'|'L'|'S')}
        self.transitions = transitions
        self.input_word = input_word

    # ---------------------------- construcción ----------------------------
    @classmethod
    def construir(cls, nombre, estados, entrada, extra, blanco, inicial, finales,
                  palabra, transiciones):
        """Valida los datos del formulario y crea la máquina.
        `transiciones` es una lista de tuplas (q, X, q', Y, D).
        Si hay problemas lanza ValueError con la lista completa."""
        errores = []
        nombre = nombre.strip()
        if not nombre:
            errores.append("Escriba un nombre para la configuración.")

        Q = parsear_conjunto(estados)
        sigma = parsear_conjunto(entrada)
        extras = parsear_conjunto(extra)
        F = parsear_conjunto(finales)
        blanco = blanco.strip() or BLANCO
        inicial = inicial.strip()
        palabra = palabra.strip()

        if not Q:
            errores.append("Debe haber al menos un estado.")
        if not sigma:
            errores.append("El alfabeto de entrada no puede estar vacío.")
        largos = [s for s in sigma + extras if len(s) != 1]
        if largos:
            errores.append(f"Los símbolos deben ser de un solo carácter: {largos}")
        if len(blanco) != 1:
            errores.append("El símbolo blanco debe ser de un solo carácter.")
        if blanco in sigma:
            errores.append("El símbolo blanco no puede estar en el alfabeto de entrada.")

        gamma = set(sigma) | set(extras) | {blanco}

        if inicial not in Q:
            errores.append(f"El estado inicial '{inicial}' no está en Q.")
        if not F:
            errores.append("Debe haber al menos un estado final.")
        fuera = [f for f in F if f not in Q]
        if fuera:
            errores.append(f"Estados finales que no están en Q: {fuera}")

        malos = sorted({c for c in palabra if c not in set(sigma) | {blanco}})
        if malos:
            errores.append(f"La palabra de entrada tiene símbolos fuera de Σ: {malos}")

        trans = {}
        for (q, x, q2, y, d) in transiciones:
            nombre_t = f"δ({q},{x})"
            if q not in Q:
                errores.append(f"{nombre_t}: el estado '{q}' no está en Q.")
            elif q in F:
                errores.append(f"{nombre_t}: no se definen transiciones desde estados finales.")
            if x not in gamma:
                errores.append(f"{nombre_t}: el símbolo '{x}' no está en Γ.")
            if q2 not in Q:
                errores.append(f"{nombre_t}: el nuevo estado '{q2}' no está en Q.")
            if y not in gamma:
                errores.append(f"{nombre_t}: el símbolo a escribir '{y}' no está en Γ.")
            try:
                mov = normalizar_direccion(d)
            except ValueError as e:
                errores.append(f"{nombre_t}: {e}")
                continue
            if (q, x) in trans:
                errores.append(f"{nombre_t}: transición repetida (la MT debe ser determinista).")
            trans[(q, x)] = (q2, y, mov)

        if errores:
            raise ValueError("\n".join(errores))
        return cls(nombre, Q, sigma, gamma, blanco, inicial, F, trans, palabra)

    # ------------------------------ JSON ---------------------------------
    def to_dict(self):
        return {
            "states": sorted(self.states),
            "input_alphabet": sorted(self.input_alphabet),
            "tape_alphabet": sorted(self.tape_alphabet),
            "blank_symbol": self.blank,
            "initial_state": self.initial_state,
            "final_states": sorted(self.final_states),
            "input_word": self.input_word,
            "transitions": [
                {"from": q, "read": s, "to": q2, "write": w, "move": d}
                for (q, s), (q2, w, d) in sorted(self.transitions.items())
            ],
        }

    @classmethod
    def from_dict(cls, name, cfg):
        """Lee el formato nuevo y también el de la versión por consola
        (accept_state/reject_state y transiciones 'q|s': [q2, w, d])."""
        trans = {}
        crudas = cfg.get("transitions", [])
        if isinstance(crudas, dict):                       # formato antiguo
            for clave, v in crudas.items():
                q, s = clave.split("|", 1)
                trans[(q, s)] = (v[0], v[1], normalizar_direccion(v[2]))
        else:
            for t in crudas:
                trans[(t["from"], t["read"])] = (t["to"], t["write"],
                                                 normalizar_direccion(t["move"]))
        finales = cfg.get("final_states")
        if finales is None:
            finales = [cfg["accept_state"]] if cfg.get("accept_state") else []
        return cls(name, cfg.get("states", []), cfg.get("input_alphabet", []),
                   cfg.get("tape_alphabet", []), cfg.get("blank_symbol", BLANCO),
                   cfg.get("initial_state", ""), finales, trans,
                   cfg.get("input_word", ""))

    def resumen(self):
        return (f"Estados: {sorted(self.states)}  |  Σ: {sorted(self.input_alphabet)}  |  "
                f"q0: {self.initial_state}  |  F: {sorted(self.final_states)}\n"
                f"Palabra de entrada: '{self.input_word}'  |  "
                f"Transiciones: {len(self.transitions)}")


class Ejecucion:
    """Una corrida de la MT. `paso()` ejecuta exactamente una transición."""

    def __init__(self, maquina, palabra=None):
        self.m = maquina
        palabra = maquina.input_word if palabra is None else palabra
        self.cinta = Cinta(palabra, maquina.blank)
        self.cabezal = 0
        self.estado = maquina.initial_state
        self.pasos = 0
        self.estatus = "corriendo"   # corriendo | aceptada | rechazada | limite
        self._evaluar()

    def _evaluar(self):
        if self.estado in self.m.final_states:
            self.estatus = "aceptada"
        elif (self.estado, self.cinta.leer(self.cabezal)) not in self.m.transitions:
            self.estatus = "rechazada"       # se detiene sin llegar a un final
        elif self.pasos >= MAX_PASOS:
            self.estatus = "limite"
        else:
            self.estatus = "corriendo"

    def paso(self):
        """Devuelve un dict con la transición aplicada, o None si ya terminó."""
        if self.estatus != "corriendo":
            return None
        leido = self.cinta.leer(self.cabezal)
        nuevo, escribe, mov = self.m.transitions[(self.estado, leido)]
        info = {"estado": self.estado, "leido": leido, "nuevo": nuevo,
                "escrito": escribe, "mov": mov, "pos": self.cabezal}
        self.cinta.escribir(self.cabezal, escribe)
        self.estado = nuevo
        if mov == "R":
            self.cabezal += 1
        elif mov == "L":
            self.cabezal -= 1
        self.pasos += 1
        self._evaluar()
        return info

    def correr(self):
        while self.estatus == "corriendo":
            self.paso()
        return self.estatus == "aceptada"


# ===================== PERSISTENCIA (JSON) ========================
def cargar_configuraciones():
    if not os.path.exists(ARCHIVO_CONFIG):
        return {}
    try:
        with open(ARCHIVO_CONFIG, "r", encoding="utf-8") as f:
            crudo = json.load(f)
    except (OSError, ValueError):
        return {}
    maquinas = {}
    for nombre, cfg in crudo.items():
        try:
            maquinas[nombre] = TuringMachine.from_dict(nombre, cfg)
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return maquinas


def guardar_configuraciones(maquinas):
    crudo = {nombre: m.to_dict() for nombre, m in maquinas.items()}
    with open(ARCHIVO_CONFIG, "w", encoding="utf-8") as f:
        json.dump(crudo, f, indent=2, ensure_ascii=False)


# ====================================================================
#                              INTERFAZ
# ====================================================================
Canvas = tk.Canvas if tk else object
Frame = ttk.Frame if tk else object
Raiz = tk.Tk if tk else object
Toplevel = tk.Toplevel if tk else object


class TapeView(Canvas):
    """Dibuja CELDAS celdas de la cinta con el cabezal resaltado."""
    ALTO = 92

    def __init__(self, padre, ancho_celda):
        self.cw = ancho_celda
        self.margen = 10
        super().__init__(padre, width=CELDAS * ancho_celda + 2 * self.margen,
                         height=self.ALTO, bg="#f5f5f5",
                         highlightthickness=1, highlightbackground="#bbb")
        self.inicio = -2

    def reiniciar_vista(self):
        self.inicio = -2

    def mostrar(self, leer, cabezal, modificadas=()):
        self.delete("all")
        if not (self.inicio + 2 <= cabezal <= self.inicio + CELDAS - 3):
            self.inicio = cabezal - CELDAS // 2
        y0, h = 30, 36
        for i in range(CELDAS):
            pos = self.inicio + i
            x = self.margen + i * self.cw
            if pos == cabezal:
                fondo, borde, grosor = "#ffd54f", "#c62828", 3
            elif pos in modificadas:
                fondo, borde, grosor = "#ffccbc", "#444", 1
            else:
                fondo, borde, grosor = "white", "#444", 1
            self.create_rectangle(x, y0, x + self.cw, y0 + h, fill=fondo,
                                  outline=borde, width=grosor)
            self.create_text(x + self.cw / 2, y0 + h / 2, text=leer(pos),
                             font=("Courier", 12, "bold"))
            self.create_text(x + self.cw / 2, y0 + h + 11, text=str(pos),
                             font=("Courier", 7), fill="#777")
        xc = self.margen + (cabezal - self.inicio) * self.cw + self.cw / 2
        self.create_polygon(xc - 7, 8, xc + 7, 8, xc, 26, fill="#c62828", outline="")


# ------------------------ VISUALIZADOR DE GRAFOS ---------------------
class VentanaGrafo(Toplevel):
    """Ventana interactiva que dibuja el grafo de transiciones de una MT."""
    RADIO = 28

    def __init__(self, padre, maquina, estado_activo=None, ultima_trans=None):
        super().__init__(padre)
        self.m = None
        self.estado_activo = None
        self.ultima_trans = None
        self.pos = {}           # {estado: [x, y]}
        self.arrastrando = None

        self.geometry("820x580")
        self.minsize(600, 420)

        barra = ttk.Frame(self, padding=6)
        barra.pack(fill="x")
        self.lbl_info = ttk.Label(barra, text="", font=("TkDefaultFont", 10, "bold"))
        self.lbl_info.pack(side="left")
        ttk.Button(barra, text="Reorganizar en círculo",
                   command=self._distribuir_nodos).pack(side="right", padx=4)
        ttk.Label(barra, text="Tip: arrastre los estados con el mouse  ",
                  foreground="#666").pack(side="right")

        leyenda = ttk.Frame(self, padding=(6, 0, 6, 4))
        leyenda.pack(fill="x")
        for color, borde, texto in (
            ("#e3f2fd", "#1565c0", "Estado inicial (q0)"),
            ("#e8f5e9", "#2e7d32", "Estado final (doble círculo)"),
            ("#ffd54f", "#c62828", "Estado activo (en ejecución)"),
        ):
            c = tk.Canvas(leyenda, width=16, height=16, highlightthickness=0)
            c.create_oval(2, 2, 14, 14, fill=color, outline=borde, width=2)
            c.pack(side="left", padx=(0, 4))
            ttk.Label(leyenda, text=texto).pack(side="left", padx=(0, 16))

        self.canvas = tk.Canvas(self, bg="white", highlightthickness=1,
                                highlightbackground="#ccc")
        self.canvas.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self.canvas.bind("<ButtonPress-1>", self._al_presionar)
        self.canvas.bind("<B1-Motion>", self._al_arrastrar)
        self.canvas.bind("<ButtonRelease-1>", self._al_soltar)
        self.canvas.bind("<Configure>", self._al_redimensionar)

        self.cargar_maquina(maquina, estado_activo, ultima_trans)

    def cargar_maquina(self, maquina, estado_activo=None, ultima_trans=None):
        misma_maquina = (self.m is not None and self.m.name == maquina.name
                         and self.m.states == maquina.states)
        self.m = maquina
        self.estado_activo = estado_activo
        self.ultima_trans = ultima_trans
        self.title(f"Grafo de la Máquina de Turing · {maquina.name}")
        self.lbl_info.config(
            text=f"MT: {maquina.name}   |   |Q| = {len(maquina.states)}   |   "
                 f"|δ| = {len(maquina.transitions)}")
        if not misma_maquina or not self.pos:
            self.after(20, self._distribuir_nodos)
        else:
            self.dibujar()

    def actualizar_estado(self, estado_activo=None, ultima_trans=None):
        self.estado_activo = estado_activo
        self.ultima_trans = ultima_trans
        self.dibujar()

    def _orden_estados(self):
        intermedios = sorted(self.m.states - {self.m.initial_state} - self.m.final_states)
        finales = sorted(self.m.final_states - {self.m.initial_state})
        orden = []
        if self.m.initial_state in self.m.states:
            orden.append(self.m.initial_state)
        orden.extend(intermedios)
        orden.extend(finales)
        return orden

    def _distribuir_nodos(self):
        w = max(self.canvas.winfo_width(), 640)
        h = max(self.canvas.winfo_height(), 420)
        cx, cy = w / 2, h / 2
        rx = max(110, min(w, h) * 0.34)
        ry = max(95, min(w, h) * 0.32)

        estados = self._orden_estados()
        n = len(estados)
        self.pos = {}
        if n == 1:
            self.pos[estados[0]] = [cx, cy]
        else:
            for i, q in enumerate(estados):
                # Empezamos en ángulo pi (izquierda) para que q0 quede a la izquierda
                ang = math.pi - (2 * math.pi * i / n)
                self.pos[q] = [cx + rx * math.cos(ang), cy - ry * math.sin(ang)]
        self.dibujar()

    def _al_redimensionar(self, _evento):
        if not self.pos:
            self._distribuir_nodos()
        else:
            self.dibujar()

    def _al_presionar(self, evento):
        for q, (x, y) in self.pos.items():
            if math.hypot(evento.x - x, evento.y - y) <= self.RADIO:
                self.arrastrando = q
                break

    def _al_arrastrar(self, evento):
        if self.arrastrando:
            r = self.RADIO + 6
            w = max(self.canvas.winfo_width(), 200)
            h = max(self.canvas.winfo_height(), 200)
            self.pos[self.arrastrando] = [
                max(r, min(w - r, evento.x)),
                max(r, min(h - r, evento.y)),
            ]
            self.dibujar()

    def _al_soltar(self, _evento):
        self.arrastrando = None

    def _dibujar_etiqueta(self, x, y, texto, resaltada=False):
        color_texto = "#b71c1c" if resaltada else "#222"
        tid = self.canvas.create_text(
            x, y, text=texto, font=("Courier", 9, "bold"),
            fill=color_texto, justify="center")
        bbox = self.canvas.bbox(tid)
        if bbox:
            pad = 2
            fondo = "#fff8e1" if resaltada else "white"
            borde = "#ffb300" if resaltada else ""
            rid = self.canvas.create_rectangle(
                bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad,
                fill=fondo, outline=borde)
            self.canvas.tag_lower(rid, tid)

    def dibujar(self):
        self.canvas.delete("all")
        if not self.m or not self.pos:
            return

        r = self.RADIO
        # Agrupar transiciones por par (origen, destino)
        aristas = {}
        arista_activa = None
        if self.ultima_trans:
            arista_activa = (self.ultima_trans["estado"], self.ultima_trans["nuevo"])

        for (q, x), (q2, y, d) in sorted(self.m.transitions.items()):
            aristas.setdefault((q, q2), []).append(f"{x} → {y},{d}")

        w = max(self.canvas.winfo_width(), 600)
        h = max(self.canvas.winfo_height(), 400)
        cx, cy = w / 2, h / 2

        # 1. Dibujar aristas y bucles
        for (u, v), etiquetas in aristas.items():
            if u not in self.pos or v not in self.pos:
                continue
            x1, y1 = self.pos[u]
            x2, y2 = self.pos[v]
            texto = "\n".join(etiquetas)
            activa = (arista_activa == (u, v))
            color_linea = "#1565c0" if activa else "#424242"
            grosor = 2.5 if activa else 1.8

            if u == v:
                # Bucle (self-loop) apuntando hacia afuera del centro del lienzo
                dx, dy = x1 - cx, y1 - cy
                dist = math.hypot(dx, dy)
                if dist < 10:
                    ox, oy = 0.0, -1.0
                else:
                    ox, oy = dx / dist, dy / dist
                px, py = -oy, ox

                sx = x1 + ox * (r * 0.78) - px * (r * 0.62)
                sy = y1 + oy * (r * 0.78) - py * (r * 0.62)
                ex = x1 + ox * (r * 0.78) + px * (r * 0.62)
                ey = y1 + oy * (r * 0.78) + py * (r * 0.62)

                c1x = x1 + ox * (r + 48) - px * 28
                c1y = y1 + oy * (r + 48) - py * 28
                c2x = x1 + ox * (r + 48) + px * 28
                c2y = y1 + oy * (r + 48) + py * 28

                self.canvas.create_line(
                    sx, sy, c1x, c1y, c2x, c2y, ex, ey,
                    smooth=True, arrow=tk.LAST, width=grosor,
                    fill=color_linea, arrowshape=(10, 12, 5))

                lx = x1 + ox * (r + 58)
                ly = y1 + oy * (r + 58)
                self._dibujar_etiqueta(lx, ly, texto, activa)
            else:
                dx, dy = x2 - x1, y2 - y1
                dist = math.hypot(dx, dy) or 1.0
                ux, uy = dx / dist, dy / dist
                px, py = -uy, ux

                # Si hay arista en sentido contrario, curvar para no solaparlas
                curva = 36 if (v, u) in aristas else 0
                mx = (x1 + x2) / 2 + px * curva
                my = (y1 + y2) / 2 + py * curva

                # Punto inicial en el borde de u (en dirección al punto medio)
                d1x, d1y = mx - x1, my - y1
                l1 = math.hypot(d1x, d1y) or 1.0
                sx = x1 + (d1x / l1) * r
                sy = y1 + (d1y / l1) * r

                # Punto final en el borde de v (desde el punto medio)
                d2x, d2y = x2 - mx, y2 - my
                l2 = math.hypot(d2x, d2y) or 1.0
                ex = x2 - (d2x / l2) * r
                ey = y2 - (d2y / l2) * r

                if curva:
                    self.canvas.create_line(
                        sx, sy, mx, my, ex, ey,
                        smooth=True, arrow=tk.LAST, width=grosor,
                        fill=color_linea, arrowshape=(10, 12, 5))
                    lx = (x1 + x2) / 2 + px * (curva * 0.75)
                    ly = (y1 + y2) / 2 + py * (curva * 0.75)
                else:
                    self.canvas.create_line(
                        sx, sy, ex, ey,
                        arrow=tk.LAST, width=grosor,
                        fill=color_linea, arrowshape=(10, 12, 5))
                    lx = (x1 + x2) / 2 + px * 16
                    ly = (y1 + y2) / 2 + py * 16

                self._dibujar_etiqueta(lx, ly, texto, activa)

        # 2. Dibujar nodos (estados)
        for q, (x, y) in self.pos.items():
            if q == self.estado_activo:
                fondo, borde, grosor = "#ffd54f", "#c62828", 3
            elif q in self.m.final_states:
                fondo, borde, grosor = "#e8f5e9", "#2e7d32", 2
            elif q == self.m.initial_state:
                fondo, borde, grosor = "#e3f2fd", "#1565c0", 2
            else:
                fondo, borde, grosor = "white", "#333333", 2

            # Flecha de estado inicial
            if q == self.m.initial_state:
                self.canvas.create_line(
                    x - r - 38, y, x - r, y,
                    arrow=tk.LAST, width=2.2, fill="#1565c0",
                    arrowshape=(10, 12, 5))
                self.canvas.create_text(
                    x - r - 19, y - 10, text="inicio",
                    font=("TkDefaultFont", 8, "italic"), fill="#1565c0")

            self.canvas.create_oval(
                x - r, y - r, x + r, y + r,
                fill=fondo, outline=borde, width=grosor)

            # Doble círculo para estados de aceptación / finales
            if q in self.m.final_states:
                r_int = r - 5
                self.canvas.create_oval(
                    x - r_int, y - r_int, x + r_int, y + r_int,
                    fill="", outline=borde, width=1.8)

            self.canvas.create_text(
                x, y, text=q, font=("TkDefaultFont", 10, "bold"), fill="#111")


# ------------------------------- INICIO ------------------------------
class PestanaInicio(Frame):
    def __init__(self, padre, app):
        super().__init__(padre, padding=14)
        self.app = app
        self.nombres = []

        ttk.Label(self, text="Simulador de Máquina de Turing",
                  font=("TkDefaultFont", 18, "bold")).pack(anchor="w")
        ttk.Label(self, text="Autómatas y lenguajes formales · Proyecto Final 2026",
                  foreground="#555").pack(anchor="w", pady=(0, 12))

        cols = ttk.Frame(self)
        cols.pack(fill="both", expand=True)
        cols.columnconfigure(0, weight=3)
        cols.columnconfigure(1, weight=2)
        cols.rowconfigure(0, weight=1)

        izq = ttk.LabelFrame(cols, text="Modo 1 · Ejecución automática (simulación gráfica)",
                             padding=10)
        izq.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ttk.Label(izq, text="Cree una nueva configuración o busque una guardada por nombre:"
                  ).pack(anchor="w")
        self.v_buscar = tk.StringVar()
        self.v_buscar.trace_add("write", lambda *_: self.refrescar())
        ttk.Entry(izq, textvariable=self.v_buscar).pack(fill="x", pady=4)

        marco = ttk.Frame(izq)
        marco.pack(fill="both", expand=True)
        self.lista = tk.Listbox(marco, height=12, exportselection=False)
        sb = ttk.Scrollbar(marco, command=self.lista.yview)
        self.lista.configure(yscrollcommand=sb.set)
        self.lista.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.lista.bind("<<ListboxSelect>>", lambda e: self._detalle())
        self.lista.bind("<Double-Button-1>", lambda e: self.usar())

        self.lbl_detalle = ttk.Label(izq, text="", foreground="#444",
                                     justify="left", wraplength=620)
        self.lbl_detalle.pack(anchor="w", pady=6)

        fila = ttk.Frame(izq)
        fila.pack(fill="x")
        ttk.Button(fila, text="Nueva configuración", command=self.nueva).pack(side="left", padx=2)
        ttk.Button(fila, text="Ejecutar la seleccionada", command=self.usar).pack(side="left", padx=2)
        ttk.Button(fila, text="Ver grafo", command=self.ver_grafo).pack(side="left", padx=2)
        ttk.Button(fila, text="Editar", command=self.editar).pack(side="left", padx=2)
        ttk.Button(fila, text="Eliminar", command=self.eliminar).pack(side="left", padx=2)

        der = ttk.LabelFrame(cols, text="Modo 2 · Ejecución manual (sandbox)", padding=10)
        der.grid(row=0, column=1, sticky="nsew")
        ttk.Label(der, wraplength=380, justify="left", text=(
            "Llene la cinta al azar con su propio alfabeto y mueva el cabezal a mano "
            "(D = derecha, I = izquierda, S = no mover/paro). Cada movimiento queda "
            "registrado y puede exportarse como una configuración para el Modo 1.")
        ).pack(anchor="w", pady=(0, 10))
        ttk.Button(der, text="Abrir modo manual",
                   command=lambda: app.ir(app.tab_manual)).pack(anchor="w")
        self.refrescar()

    def refrescar(self):
        filtro = self.v_buscar.get().strip().lower()
        self.nombres = [n for n in sorted(self.app.machines, key=str.lower)
                        if filtro in n.lower()]
        self.lista.delete(0, "end")
        for n in self.nombres:
            self.lista.insert("end", n)
        total = len(self.app.machines)
        self.lbl_detalle.config(
            text=f"{len(self.nombres)} de {total} configuración(es) guardada(s). "
                 "Seleccione una para ver su detalle.")

    def seleccionada(self):
        sel = self.lista.curselection()
        if not sel:
            messagebox.showinfo("Seleccione una", "Seleccione una configuración de la lista.")
            return None
        return self.nombres[sel[0]]

    def _detalle(self):
        sel = self.lista.curselection()
        if sel:
            maquina = self.app.machines[self.nombres[sel[0]]]
            self.lbl_detalle.config(text=maquina.resumen())
            # Si la ventana de grafo ya está abierta, actualizarla al cambiar de selección
            if self.app.ventana_grafo is not None and self.app.ventana_grafo.winfo_exists():
                self.app.mostrar_grafo(maquina)

    def nueva(self):
        self.app.tab_config.limpiar()
        self.app.ir(self.app.tab_config)

    def usar(self):
        nombre = self.seleccionada()
        if nombre:
            self.app.usar_maquina(nombre)

    def ver_grafo(self):
        nombre = self.seleccionada()
        if nombre:
            self.app.mostrar_grafo(self.app.machines[nombre])

    def editar(self):
        nombre = self.seleccionada()
        if nombre:
            self.app.tab_config.cargar(self.app.machines[nombre])
            self.app.ir(self.app.tab_config)

    def eliminar(self):
        nombre = self.seleccionada()
        if nombre and messagebox.askyesno("Eliminar", f"¿Eliminar la configuración '{nombre}'?"):
            del self.app.machines[nombre]
            guardar_configuraciones(self.app.machines)
            self.refrescar()


# --------------------------- MODO 1: CONFIGURACIÓN -------------------
class PestanaConfiguracion(Frame):
    def __init__(self, padre, app):
        super().__init__(padre, padding=10)
        self.app = app
        self.editando = None
        self.trans = {}        # {(q, X): (q', Y, D)} en orden de ingreso

        form = ttk.LabelFrame(
            self, text="Definición formal:  M = (Q, Σ, Γ, δ, q0, B, F)", padding=8)
        form.pack(fill="x")
        campos = [
            ("nombre", "Nombre de la configuración:", "para poder cargarla después"),
            ("estados", "Estados (Q):", "ej: q0 q1 q2 qf   (separe con espacios o comas)"),
            ("entrada", "Alfabeto de entrada (Σ):", "ej: a b"),
            ("extra", "Símbolos extra de cinta (Γ − Σ):", "ej: X Y   (opcional)"),
            ("blanco", "Símbolo blanco (B):", "un carácter; por defecto ^"),
            ("inicial", "Estado inicial (q0):", ""),
            ("finales", "Estados finales (F):", "ej: qf   (la MT se detiene al llegar a uno)"),
            ("palabra", "Palabra de entrada:", "se coloca desde la celda 0; vacía = cinta en blanco"),
        ]
        self.vars = {}
        for i, (clave, etiqueta, ayuda) in enumerate(campos):
            ttk.Label(form, text=etiqueta).grid(row=i, column=0, sticky="e", padx=4, pady=2)
            v = tk.StringVar()
            self.vars[clave] = v
            ttk.Entry(form, textvariable=v, width=36).grid(row=i, column=1, sticky="w", padx=4)
            ttk.Label(form, text=ayuda, foreground="#666").grid(row=i, column=2, sticky="w")

        tf = ttk.LabelFrame(
            self, text="Función de transición  δ(qi, X) = (qj, Y, D),  D ∈ {R, L, S}", padding=8)
        tf.pack(fill="both", expand=True, pady=8)
        fila = ttk.Frame(tf)
        fila.pack(fill="x")
        self.t_vars = [tk.StringVar() for _ in range(4)]
        etiquetas = ("qi (estado actual)", "X (símbolo leído)",
                     "qj (nuevo estado)", "Y (símbolo a escribir)", "D (mover)")
        for i, et in enumerate(etiquetas):
            ttk.Label(fila, text=et).grid(row=0, column=i, padx=4)
        for i, v in enumerate(self.t_vars):
            ttk.Entry(fila, textvariable=v, width=14).grid(row=1, column=i, padx=4)
        self.t_dir = tk.StringVar(value="R")
        ttk.Combobox(fila, textvariable=self.t_dir, values=["R", "L", "S"],
                     width=5, state="readonly").grid(row=1, column=4, padx=4)
        ttk.Button(fila, text="Agregar / reemplazar",
                   command=self.agregar_transicion).grid(row=1, column=5, padx=6)
        ttk.Button(fila, text="Quitar seleccionada",
                   command=self.quitar_transicion).grid(row=1, column=6)

        marco = ttk.Frame(tf)
        marco.pack(fill="both", expand=True, pady=(6, 0))
        self.tree = ttk.Treeview(marco, columns=("q", "x", "q2", "y", "d"),
                                 show="headings", height=7)
        for col, texto, ancho in (("q", "qi", 110), ("x", "X", 80), ("q2", "qj", 110),
                                  ("y", "Y", 80), ("d", "D", 60)):
            self.tree.heading(col, text=texto)
            self.tree.column(col, width=ancho, anchor="center")
        sb = ttk.Scrollbar(marco, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._al_seleccionar)

        botones = ttk.Frame(self)
        botones.pack(fill="x")
        ttk.Button(botones, text="Guardar y ejecutar",
                   command=lambda: self.guardar(True)).pack(side="left", padx=3)
        ttk.Button(botones, text="Guardar solamente",
                   command=lambda: self.guardar(False)).pack(side="left", padx=3)
        ttk.Button(botones, text="Ver grafo",
                   command=self.ver_grafo).pack(side="left", padx=3)
        ttk.Button(botones, text="Limpiar formulario",
                   command=self.limpiar).pack(side="left", padx=3)
        self.limpiar()

    # El Treeview solo muestra; los datos reales viven en self.trans
    # (así no se pierden ceros a la izquierda ni se convierten símbolos a números).
    def _pintar(self):
        self.tree.delete(*self.tree.get_children())
        for i, ((q, x), (q2, y, d)) in enumerate(self.trans.items()):
            self.tree.insert("", "end", iid=str(i), values=(q, x, q2, y, d))

    def _al_seleccionar(self, _evento):
        sel = self.tree.selection()
        if sel:
            (q, x), (q2, y, d) = list(self.trans.items())[int(sel[0])]
            for v, valor in zip(self.t_vars, (q, x, q2, y)):
                v.set(valor)
            self.t_dir.set(d)

    def agregar_transicion(self):
        q, x, q2, y = (v.get().strip() for v in self.t_vars)
        if not (q and x and q2 and y):
            messagebox.showwarning("Faltan datos", "Complete qi, X, qj e Y.")
            return
        self.trans[(q, x)] = (q2, y, normalizar_direccion(self.t_dir.get()))
        self._pintar()

    def quitar_transicion(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Seleccione una", "Seleccione una transición de la tabla.")
            return
        del self.trans[list(self.trans)[int(sel[0])]]
        self._pintar()

    def limpiar(self):
        for v in self.vars.values():
            v.set("")
        self.vars["blanco"].set(BLANCO)
        for v in self.t_vars:
            v.set("")
        self.t_dir.set("R")
        self.trans = {}
        self.editando = None
        self._pintar()

    def cargar(self, m):
        self.limpiar()
        extras = m.tape_alphabet - m.input_alphabet - {m.blank}
        valores = {"nombre": m.name, "estados": " ".join(sorted(m.states)),
                   "entrada": " ".join(sorted(m.input_alphabet)),
                   "extra": " ".join(sorted(extras)), "blanco": m.blank,
                   "inicial": m.initial_state,
                   "finales": " ".join(sorted(m.final_states)),
                   "palabra": m.input_word}
        for clave, valor in valores.items():
            self.vars[clave].set(valor)
        self.trans = dict(sorted(m.transitions.items()))
        self.editando = m.name
        self._pintar()

    def _construir_actual(self, nombre_por_defecto=None):
        v = {k: x.get() for k, x in self.vars.items()}
        nombre = v["nombre"].strip() or nombre_por_defecto or ""
        lista = [(q, x, q2, y, d) for (q, x), (q2, y, d) in self.trans.items()]
        return TuringMachine.construir(
            nombre, v["estados"], v["entrada"], v["extra"],
            v["blanco"], v["inicial"], v["finales"], v["palabra"], lista)

    def ver_grafo(self):
        try:
            m = self._construir_actual(nombre_por_defecto="Vista previa")
        except ValueError as e:
            messagebox.showerror("Configuración incompleta o inválida", str(e))
            return
        self.app.mostrar_grafo(m)

    def guardar(self, ejecutar):
        try:
            m = self._construir_actual()
        except ValueError as e:
            messagebox.showerror("Configuración inválida", str(e))
            return
        if m.name in self.app.machines and m.name != self.editando:
            if not messagebox.askyesno("Ya existe", f"Ya existe '{m.name}'. ¿Sobrescribirla?"):
                return
        self.app.guardar_maquina(m)
        self.editando = m.name
        if ejecutar:
            self.app.usar_maquina(m.name)
        else:
            messagebox.showinfo("Guardada", f"Configuración '{m.name}' guardada.")


# --------------------------- MODO 1: EJECUCIÓN -----------------------
class PestanaEjecucion(Frame):
    def __init__(self, padre, app):
        super().__init__(padre, padding=10)
        self.app = app
        self.maquina = None
        self.ejec = None
        self.corriendo = False
        self.job = None
        self.ultima_info = None
        self.palabra_actual = ""

        self.lbl_titulo = ttk.Label(self, text="", font=("TkDefaultFont", 12, "bold"))
        self.lbl_titulo.pack(anchor="w")
        self.lbl_aviso = ttk.Label(
            self, foreground="#b71c1c",
            text="No se podrá ejecutar si no se ha configurado previamente. "
                 "Cree o cargue una configuración desde la pestaña Inicio.")
        self.lbl_aviso.pack(anchor="w")

        self.cinta_vista = TapeView(self, app.cw)
        self.cinta_vista.pack(pady=8)

        info = ttk.Frame(self)
        info.pack(fill="x")
        self.lbl_estado = ttk.Label(info, text="", font=("TkDefaultFont", 11, "bold"))
        self.lbl_estado.pack(side="left")
        self.lbl_paso = ttk.Label(info, text="", foreground="#444")
        self.lbl_paso.pack(side="left", padx=20)
        self.lbl_resultado = ttk.Label(info, text="", font=("TkDefaultFont", 11, "bold"))
        self.lbl_resultado.pack(side="right")

        ctl = ttk.Frame(self)
        ctl.pack(fill="x", pady=6)
        self.b_iniciar = ttk.Button(ctl, text="Iniciar", command=self.iniciar)
        self.b_pausa = ttk.Button(ctl, text="Pausar", command=self.pausar)
        self.b_paso = ttk.Button(ctl, text="Un paso", command=self.un_paso)
        self.b_reiniciar = ttk.Button(ctl, text="Reiniciar", command=self.reiniciar)
        self.b_grafo = ttk.Button(ctl, text="Ver grafo (en vivo)", command=self.ver_grafo)
        for b in (self.b_iniciar, self.b_pausa, self.b_paso, self.b_reiniciar, self.b_grafo):
            b.pack(side="left", padx=3)
        ttk.Label(ctl, text="     Velocidad (ms entre pasos):").pack(side="left")
        self.vel = tk.DoubleVar(value=400)
        ttk.Scale(ctl, from_=20, to=2000, variable=self.vel, length=240,
                  command=self._vel_cambio).pack(side="left", padx=4)
        self.lbl_vel = ttk.Label(ctl, text="400 ms", width=8)
        self.lbl_vel.pack(side="left")

        azar = ttk.LabelFrame(self, text="Cinta aleatoria (símbolos de Σ y blancos)", padding=4)
        azar.pack(fill="x", pady=(0, 6))
        ttk.Label(azar, text="Longitud:").pack(side="left")
        self.v_largo = tk.StringVar(value="20")
        ttk.Spinbox(azar, from_=1, to=CELDAS - 5, textvariable=self.v_largo,
                    width=5).pack(side="left", padx=4)
        self.v_blancos = tk.BooleanVar(value=True)
        ttk.Checkbutton(azar, text=f"Incluir blancos ({BLANCO})",
                        variable=self.v_blancos).pack(side="left", padx=8)
        self.b_azar = ttk.Button(azar, text="Rellenar cinta al azar", command=self.rellenar_azar)
        self.b_azar.pack(side="left", padx=4)
        self.v_auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(azar, text="Rellenar automáticamente si la configuración no trae "
                                   "palabra de entrada",
                        variable=self.v_auto).pack(side="left", padx=8)

        hist = ttk.LabelFrame(
            self, text="Historial de configuración: terna (Estado actual, Contenido, Posición)",
            padding=4)
        hist.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(hist, columns=("paso", "estado", "contenido", "pos", "trans"),
                                 show="headings", height=10)
        for col, texto, ancho, anchor in (
                ("paso", "Paso", 60, "center"), ("estado", "Estado actual", 110, "center"),
                ("contenido", "Contenido de la cinta", 340, "w"),
                ("pos", "Posición", 80, "center"), ("trans", "Transición aplicada", 280, "w")):
            self.tree.heading(col, text=texto)
            self.tree.column(col, width=ancho, anchor=anchor)
        sb = ttk.Scrollbar(hist, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._botones()

    # ---- carga ----
    def _titulo(self):
        self.lbl_titulo.config(
            text=f"Configuración: {self.maquina.name}   |   "
                 f"Palabra en la cinta: '{self.palabra_actual}'")

    def _palabra_azar(self):
        try:
            n = max(1, min(CELDAS - 5, int(self.v_largo.get())))
        except ValueError:
            n = 20
        return cinta_aleatoria(sorted(self.maquina.input_alphabet), n,
                               self.v_blancos.get(), self.maquina.blank)

    def cargar_maquina(self, m, auto=True):
        self.maquina = m
        self.lbl_aviso.pack_forget()
        palabra = m.input_word
        if self.v_auto.get() and not palabra.strip():
            palabra = self._palabra_azar()
        self.palabra_actual = palabra
        self._titulo()
        self.reiniciar()
        if auto:
            self.iniciar()

    def rellenar_azar(self):
        """Pone una cinta nueva con símbolos de Σ (y blancos) al azar y reinicia."""
        if not self.maquina:
            messagebox.showinfo("Sin configuración",
                                "Cargue o cree una configuración desde Inicio primero.")
            return
        self.palabra_actual = self._palabra_azar()
        self._titulo()
        self.reiniciar()

    def ver_grafo(self):
        if self.maquina:
            estado = self.ejec.estado if self.ejec else None
            self.app.mostrar_grafo(self.maquina, estado, self.ultima_info)

    # ---- control ----
    def _vel_cambio(self, valor):
        self.lbl_vel.config(text=f"{int(float(valor))} ms")

    def _parar(self):
        if self.job is not None:
            self.after_cancel(self.job)
            self.job = None
        self.corriendo = False

    def reiniciar(self):
        self._parar()
        if not self.maquina:
            return
        self.ejec = Ejecucion(self.maquina, self.palabra_actual)
        self.ultima_info = None
        self.cinta_vista.reiniciar_vista()
        self.tree.delete(*self.tree.get_children())
        self._agregar_fila(None)
        self._dibujar()
        self._resultado()
        self._botones()

    def iniciar(self):
        if not self.ejec or self.ejec.estatus != "corriendo":
            return
        self.corriendo = True
        self._botones()
        self._programar()

    def pausar(self):
        self._parar()
        self._botones()

    def un_paso(self):
        self._parar()
        self._avanzar()
        self._botones()

    def _programar(self):
        self.job = self.after(int(self.vel.get()), self._tick)

    def _tick(self):
        self.job = None
        if not self.corriendo:
            return
        self._avanzar()
        if self.corriendo:
            self._programar()
        self._botones()

    def _avanzar(self):
        info = self.ejec.paso()
        if info:
            self.ultima_info = info
            self._agregar_fila(info)
            self._dibujar()
        self._resultado()

    # ---- presentación ----
    def _agregar_fila(self, info):
        e = self.ejec
        if info is None:
            trans = "Configuración inicial"
        else:
            trans = fmt_transicion(info["estado"], info["leido"], info["nuevo"],
                                   info["escrito"], info["mov"])
        iid = self.tree.insert("", "end", values=(
            e.pasos, e.estado, e.cinta.contenido(e.cabezal), e.cabezal, trans))
        self.tree.see(iid)

    def _dibujar(self):
        e = self.ejec
        self.cinta_vista.mostrar(e.cinta.leer, e.cabezal)
        self.lbl_estado.config(text=f"Estado actual: {e.estado}")
        self.lbl_paso.config(
            text=f"Paso: {e.pasos}    Posición del cabezal: {e.cabezal}    "
                 f"Símbolo bajo el cabezal: '{e.cinta.leer(e.cabezal)}'")
        # Sincronizar grafo en tiempo real si la ventana está abierta
        vg = self.app.ventana_grafo
        if vg is not None and vg.winfo_exists() and vg.m == self.maquina:
            vg.actualizar_estado(e.estado, self.ultima_info)

    def _resultado(self):
        e = self.ejec
        textos = {
            "aceptada": ("ACEPTADA ✔ (llegó a un estado final)", "#1b5e20"),
            "rechazada": ("RECHAZADA ✘ (se detuvo sin llegar a un estado final)", "#b71c1c"),
            "limite": (f"Se alcanzó el límite de {MAX_PASOS} pasos (posible bucle infinito)",
                       "#e65100"),
        }
        if e.estatus in textos:
            texto, color = textos[e.estatus]
            self.lbl_resultado.config(text=texto, foreground=color)
            self.corriendo = False
        else:
            self.lbl_resultado.config(text="")

    def _botones(self):
        activo = self.ejec is not None and self.ejec.estatus == "corriendo"
        self.b_iniciar.config(text="Reanudar" if (self.ejec and self.ejec.pasos) else "Iniciar",
                              state="normal" if (activo and not self.corriendo) else "disabled")
        self.b_pausa.config(state="normal" if self.corriendo else "disabled")
        self.b_paso.config(state="normal" if (activo and not self.corriendo) else "disabled")
        self.b_reiniciar.config(state="normal" if self.ejec is not None else "disabled")
        self.b_grafo.config(state="normal" if self.maquina is not None else "disabled")
        self.b_azar.config(state="normal" if self.maquina is not None else "disabled")


# ------------------------- MODO 2: MANUAL (SANDBOX) ------------------
class PestanaManual(Frame):
    SIN_CAMBIOS = "(continuar sin cambios)"

    def __init__(self, padre, app):
        super().__init__(padre, padding=8)
        self.app = app
        self.ses = None
        self.estados_def = ["q0", "qf"]       # estados disponibles para elegir

        prep = ttk.LabelFrame(self, text="1. Preparación: alfabeto, cinta y estados", padding=6)
        prep.pack(fill="x")
        self.v_alfabeto = tk.StringVar(value="0 1")
        self.v_largo = tk.StringVar(value="20")
        self.v_con_blanco = tk.BooleanVar(value=True)
        self.v_cinta = tk.StringVar()
        self.v_q0 = tk.StringVar(value="q0")
        self.v_qf = tk.StringVar(value="qf")
        self.v_estado_def = tk.StringVar()

        ttk.Label(prep, text="Alfabeto:").grid(row=0, column=0, sticky="e")
        ttk.Entry(prep, textvariable=self.v_alfabeto, width=18).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(prep, text="Longitud de la cinta:").grid(row=0, column=2, sticky="e")
        ttk.Spinbox(prep, from_=1, to=CELDAS, textvariable=self.v_largo,
                    width=5).grid(row=0, column=3, sticky="w", padx=4)
        ttk.Checkbutton(prep, text=f"Incluir blanco ({BLANCO}) al llenar",
                        variable=self.v_con_blanco).grid(row=0, column=4, padx=6)
        ttk.Button(prep, text="Llenar cinta al azar",
                   command=self.llenar_azar).grid(row=0, column=5, padx=4)
        ttk.Label(prep, text="Cinta inicial:").grid(row=1, column=0, sticky="e", pady=3)
        ttk.Entry(prep, textvariable=self.v_cinta, width=60).grid(
            row=1, column=1, columnspan=4, sticky="we", padx=4)
        ttk.Label(prep, text=f"({BLANCO} = blanco; también puede escribirla a mano)",
                  foreground="#666").grid(row=1, column=5, sticky="w")
        ttk.Label(prep, text="Estado inicial:").grid(row=2, column=0, sticky="e")
        self.cb_q0 = ttk.Combobox(prep, textvariable=self.v_q0, values=self.estados_def,
                                  state="readonly", width=10)
        self.cb_q0.grid(row=2, column=1, sticky="w", padx=4)
        ttk.Label(prep, text="Estado final a alcanzar:").grid(row=2, column=2, sticky="e")
        self.cb_qf = ttk.Combobox(prep, textvariable=self.v_qf, values=self.estados_def,
                                  state="readonly", width=10)
        self.cb_qf.grid(row=2, column=3, sticky="w", padx=4)
        ttk.Button(prep, text="Iniciar sesión", command=self.iniciar).grid(
            row=2, column=5, padx=4, pady=3)

        ttk.Label(prep, text="Añadir/quitar estado:").grid(row=3, column=0, sticky="e")
        e_estado = ttk.Entry(prep, textvariable=self.v_estado_def, width=10)
        e_estado.grid(row=3, column=1, sticky="w", padx=4)
        e_estado.bind("<Return>", lambda e: self.anadir_estado())
        botones_e = ttk.Frame(prep)
        botones_e.grid(row=3, column=2, columnspan=2, sticky="w")
        ttk.Button(botones_e, text="Añadir", command=self.anadir_estado).pack(side="left", padx=2)
        ttk.Button(botones_e, text="Quitar", command=self.quitar_estado).pack(side="left", padx=2)
        self.lbl_estados = ttk.Label(prep, text="", foreground="#444")
        self.lbl_estados.grid(row=3, column=4, columnspan=2, sticky="w", padx=6)

        self.cinta_vista = TapeView(self, app.cw)
        self.cinta_vista.pack(pady=6)
        self.lbl_cinta = ttk.Label(self, text="", font=("Courier", 10))
        self.lbl_cinta.pack(anchor="w")
        self.lbl_seg = ttk.Label(self, text="", font=("Courier", 10), foreground="#bf360c")
        self.lbl_seg.pack(anchor="w")

        paso = ttk.LabelFrame(self, text="2. Movimiento manual (en cada celda: leer, cambiar y mover)",
                              padding=6)
        paso.pack(fill="x", pady=4)
        self.lbl_estado = ttk.Label(paso, text="Inicie una sesión para comenzar.",
                                    font=("TkDefaultFont", 10, "bold"))
        self.lbl_estado.grid(row=0, column=0, columnspan=7, sticky="w")
        ttk.Label(paso, text="¿Cambiar el símbolo de la celda?").grid(row=1, column=0, sticky="e")
        self.cb_simbolo = ttk.Combobox(paso, state="readonly", width=24, values=[self.SIN_CAMBIOS])
        self.cb_simbolo.grid(row=1, column=1, padx=4, pady=3)
        self.cb_simbolo.current(0)
        ttk.Label(paso, text="Nuevo estado:").grid(row=1, column=2, sticky="e")
        self.v_nuevo = tk.StringVar()
        self.cb_estado = ttk.Combobox(paso, textvariable=self.v_nuevo, width=12)
        self.cb_estado.grid(row=1, column=3, padx=4)
        self.botones_mov = []
        for i, (texto, cod) in enumerate((("D · Derecha", "D"), ("I · Izquierda", "I"),
                                          ("S · No mover (paro)", "S"))):
            b = ttk.Button(paso, text=texto, state="disabled",
                           command=lambda c=cod: self.aplicar(c))
            b.grid(row=1, column=4 + i, padx=3)
            self.botones_mov.append(b)
        ttk.Button(paso, text="+ Añadir estado", command=self.anadir_desde_panel).grid(
            row=1, column=7, padx=3)
        self.lbl_fin = ttk.Label(paso, text="", font=("TkDefaultFont", 10, "bold"))
        self.lbl_fin.grid(row=2, column=0, columnspan=7, sticky="w")

        reg = ttk.LabelFrame(self, text="Registro de movimientos y cambios", padding=4)
        reg.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            reg, columns=("n", "estado", "leido", "escribe", "mov", "nuevo", "pos"),
            show="headings", height=6)
        for col, texto, ancho in (("n", "#", 50), ("estado", "Estado", 100),
                                  ("leido", "Leído", 70), ("escribe", "Escrito", 70),
                                  ("mov", "Mov.", 60), ("nuevo", "Nuevo estado", 110),
                                  ("pos", "Celda", 70)):
            self.tree.heading(col, text=texto)
            self.tree.column(col, width=ancho, anchor="center")
        sb = ttk.Scrollbar(reg, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        abajo = ttk.Frame(self)
        abajo.pack(fill="x", pady=4)
        ttk.Button(abajo, text="Guardar cinta", command=self.guardar_cinta).pack(side="left", padx=3)
        ttk.Button(abajo, text="Exportar registro como configuración del Modo 1",
                   command=self.exportar).pack(side="left", padx=3)
        self._sync_estados()

    # ---- estados ----
    @staticmethod
    def _nombre_valido(nombre):
        return bool(nombre) and len(nombre.split()) == 1 and "," not in nombre

    def _sync_estados(self):
        self.cb_q0.config(values=self.estados_def)
        self.cb_qf.config(values=self.estados_def)
        self.lbl_estados.config(text="Estados: " + ", ".join(self.estados_def))
        if self.ses:
            self.cb_estado.config(values=self.ses["estados"])

    def anadir_estado(self, nombre=None):
        """Agrega un estado a la lista (para elegirlo como inicial, final o siguiente)."""
        nombre = (self.v_estado_def.get() if nombre is None else nombre).strip()
        if not self._nombre_valido(nombre):
            messagebox.showerror("Estado inválido",
                                 "Escriba un nombre sin espacios ni comas (ej.: q1, q2).")
            return False
        if nombre not in self.estados_def:
            self.estados_def.append(nombre)
        if self.ses and nombre not in self.ses["estados"]:
            self.ses["estados"].append(nombre)
        self.v_estado_def.set("")
        self._sync_estados()
        return True

    def quitar_estado(self):
        nombre = self.v_estado_def.get().strip()
        if nombre not in self.estados_def:
            messagebox.showinfo("Quitar estado",
                                "Escriba en el cuadro el nombre de un estado existente.")
            return
        if nombre in (self.v_q0.get(), self.v_qf.get()):
            messagebox.showerror("No se puede quitar",
                                 "Es el estado inicial o final elegido; cambie la selección primero.")
            return
        if self.ses and nombre in (self.ses["estado"], self.ses["q0"], self.ses["qf"]) or (
                self.ses and any(nombre in (l[0], l[4]) for l in self.ses["log"])):
            messagebox.showerror("No se puede quitar",
                                 "El estado ya se usa en la sesión actual.")
            return
        self.estados_def.remove(nombre)
        if self.ses and nombre in self.ses["estados"]:
            self.ses["estados"].remove(nombre)
        self.v_estado_def.set("")
        self._sync_estados()

    def anadir_desde_panel(self):
        """Botón junto a «Nuevo estado»: añade el nombre escrito en esa lista."""
        nombre = self.v_nuevo.get().strip()
        if self.anadir_estado(nombre):
            self.v_nuevo.set(nombre)

    # ---- preparación ----
    def _alfabeto(self):
        return parsear_conjunto(self.v_alfabeto.get())

    def llenar_azar(self):
        alfabeto = self._alfabeto()
        if not alfabeto or any(len(s) != 1 for s in alfabeto) or BLANCO in alfabeto:
            messagebox.showerror("Alfabeto inválido",
                                 f"Escriba símbolos de un solo carácter, separados por espacios "
                                 f"(el {BLANCO} está reservado para el blanco).")
            return
        try:
            n = max(1, min(CELDAS, int(self.v_largo.get())))
        except ValueError:
            n = 20
        self.v_cinta.set(cinta_aleatoria(alfabeto, n, self.v_con_blanco.get()))

    def iniciar(self):
        alfabeto = self._alfabeto()
        texto = self.v_cinta.get().strip()
        q0, qf = self.v_q0.get().strip(), self.v_qf.get().strip()
        errores = []
        if not alfabeto:
            errores.append("Ingrese el alfabeto (símbolos separados por espacios).")
        if any(len(s) != 1 for s in alfabeto):
            errores.append("Cada símbolo del alfabeto debe ser de un solo carácter.")
        if BLANCO in alfabeto:
            errores.append(f"El {BLANCO} está reservado para el blanco; no lo incluya en el alfabeto.")
        if not texto:
            errores.append("La cinta está vacía: use «Llenar cinta al azar» o escríbala.")
        malos = sorted({c for c in texto if c not in set(alfabeto) | {BLANCO}})
        if malos:
            errores.append(f"La cinta tiene símbolos fuera del alfabeto: {malos}")
        for etiqueta, valor in (("inicial", q0), ("final", qf)):
            if valor not in self.estados_def:
                errores.append(f"Elija el estado {etiqueta} de la lista de estados.")
        if q0 and q0 == qf:
            errores.append("El estado inicial y el final deben ser distintos.")
        if errores:
            messagebox.showerror("No se puede iniciar", "\n".join(errores))
            return
        if self.ses and self.ses["log"] and not messagebox.askyesno(
                "Nueva sesión", "Hay una sesión con registro. ¿Descartarla y empezar de nuevo?"):
            return
        self.ses = {"alfabeto": alfabeto, "cinta": Cinta(texto), "inicial_texto": texto,
                    "head": 0, "estado": q0, "q0": q0, "qf": qf, "estados": list(self.estados_def),
                    "log": [], "trans": {}, "modificadas": set(), "fin": False}
        self.tree.delete(*self.tree.get_children())
        self.cinta_vista.reiniciar_vista()
        self.lbl_fin.config(text="")
        self._refrescar()

    # ---- movimiento ----
    def aplicar(self, mov):
        s = self.ses
        if not s or s["fin"]:
            return
        cinta, pos = s["cinta"], s["head"]
        leido = cinta.leer(pos)
        opciones = s["alfabeto"] + [BLANCO]
        sel = self.cb_simbolo.current()
        escribe = leido if sel <= 0 else opciones[sel - 1]

        nuevo = self.v_nuevo.get().strip()
        if mov == "S":                      # estado de paro: termina en el estado final
            nuevo = s["qf"]
        elif not nuevo or len(nuevo.split()) != 1 or "," in nuevo:
            messagebox.showerror("Estado inválido",
                                 "El nuevo estado debe ser un nombre sin espacios ni comas.")
            return

        codigo = {"D": "R", "I": "L", "S": "S"}[mov]
        clave, valor = (s["estado"], leido), (nuevo, escribe, codigo)
        previa = s["trans"].get(clave)
        if previa is not None and previa != valor:
            if not messagebox.askyesno(
                    "Transición distinta",
                    f"Antes registró {fmt_transicion(clave[0], clave[1], *previa)}.\n"
                    "Esta acción es distinta; al exportar (la MT es determinista) solo se "
                    "conservará la primera.\n\n¿Aplicarla de todos modos?"):
                return
        s["trans"].setdefault(clave, valor)

        if escribe != leido:
            cinta.escribir(pos, escribe)
            s["modificadas"].add(pos)
        s["head"] += {"D": 1, "I": -1, "S": 0}[mov]
        s["estado"] = nuevo
        if nuevo not in s["estados"]:
            s["estados"].append(nuevo)
        if nuevo not in self.estados_def:
            self.estados_def.append(nuevo)
        s["log"].append((clave[0], leido, escribe, mov, nuevo, pos))
        iid = self.tree.insert("", "end", values=(
            len(s["log"]), clave[0], leido, escribe, mov, nuevo, pos))
        self.tree.see(iid)

        if mov == "S":
            s["fin"] = True
            self.lbl_fin.config(text="Estado de paro (S): la máquina se detuvo.",
                                foreground="#e65100")
        elif nuevo == s["qf"]:
            s["fin"] = True
            self.lbl_fin.config(text=f"Se alcanzó el estado final '{s['qf']}'.",
                                foreground="#1b5e20")
        self._refrescar()

    def _refrescar(self):
        s = self.ses
        cinta = s["cinta"]
        self.cinta_vista.mostrar(cinta.leer, s["head"], s["modificadas"])
        leido = cinta.leer(s["head"])
        self.lbl_estado.config(
            text=f"Estado actual: {s['estado']}   |   Estado final: {s['qf']}   |   "
                 f"Celda #{s['head']} contiene: '{leido}'")
        lo, hi = cinta.rango(s["head"])
        self.lbl_cinta.config(
            text=f"Cinta actual (celdas {lo} a {hi}): {cinta.segmento(lo, hi)}")
        if s["modificadas"]:
            a, b = min(s["modificadas"]), max(s["modificadas"])
            self.lbl_seg.config(
                text=f"Segmento modificado (celdas {a} a {b}): {cinta.segmento(a, b)}")
        else:
            self.lbl_seg.config(text="Segmento modificado: (ninguno todavía)")
        self.cb_simbolo.config(values=[self.SIN_CAMBIOS] + s["alfabeto"] + [BLANCO])
        self.cb_simbolo.current(0)
        self.cb_estado.config(values=s["estados"])
        self.v_nuevo.set(s["estado"])
        self._sync_estados()
        for b in self.botones_mov:
            b.config(state="disabled" if s["fin"] else "normal")

    # ---- grabar y exportar ----
    def guardar_cinta(self):
        s = self.ses
        if not s:
            messagebox.showinfo("Sin sesión", "Inicie una sesión primero.")
            return
        cinta = s["cinta"]
        lo, hi = cinta.rango(0)
        seg = None
        if s["modificadas"]:
            a, b = min(s["modificadas"]), max(s["modificadas"])
            seg = {"desde_celda": a, "hasta_celda": b, "contenido": cinta.segmento(a, b)}
        registro = {"fecha": datetime.now().isoformat(timespec="seconds"),
                    "alfabeto": s["alfabeto"], "cinta_inicial": s["inicial_texto"],
                    "cinta_final": cinta.segmento(lo, hi), "desde_celda": lo,
                    "posicion_cabezal": s["head"], "estado_actual": s["estado"],
                    "segmento_modificado": seg, "movimientos": len(s["log"])}
        datos = []
        if os.path.exists(ARCHIVO_CINTAS):
            try:
                with open(ARCHIVO_CINTAS, "r", encoding="utf-8") as f:
                    datos = json.load(f)
            except (OSError, ValueError):
                datos = []
        datos.append(registro)
        with open(ARCHIVO_CINTAS, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=2, ensure_ascii=False)
        messagebox.showinfo("Cinta guardada",
                            f"Cinta grabada en:\n{ARCHIVO_CINTAS}\n({len(datos)} registro(s) en total)")

    def exportar(self):
        s = self.ses
        if not s or not s["trans"]:
            messagebox.showinfo("Sin movimientos", "Realice al menos un movimiento antes de exportar.")
            return
        nombre = simpledialog.askstring(
            "Exportar al Modo 1", "Nombre de la nueva configuración:", parent=self,
            initialvalue=f"sandbox_{datetime.now():%Y%m%d_%H%M}")
        if not nombre:
            return
        nombre = nombre.strip()
        if nombre in self.app.machines and not messagebox.askyesno(
                "Ya existe", f"Ya existe '{nombre}'. ¿Sobrescribirla?"):
            return
        trans = [(q, x, q2, y, d) for (q, x), (q2, y, d) in s["trans"].items()]
        try:
            m = TuringMachine.construir(
                nombre, " ".join(s["estados"]), " ".join(s["alfabeto"]), "", BLANCO,
                s["q0"], s["qf"], s["inicial_texto"].rstrip(BLANCO), trans)
        except ValueError as e:
            messagebox.showerror("No se pudo exportar", str(e))
            return
        self.app.guardar_maquina(m)
        if messagebox.askyesno("Exportada",
                               f"Configuración '{nombre}' guardada con {len(trans)} transiciones.\n"
                               "¿Ejecutarla ahora en el Modo 1?"):
            self.app.usar_maquina(nombre)


# -------------------------------- APP --------------------------------
class App(Raiz):
    def __init__(self):
        super().__init__()
        self.title("Simulador de Máquina de Turing · Proyecto Final 2026")
        self.cw = max(14, min(24, (self.winfo_screenwidth() - 120) // CELDAS))
        ancho = CELDAS * self.cw + 70
        alto = min(820, self.winfo_screenheight() - 80)
        self.geometry(f"{ancho}x{alto}")
        self.minsize(900, 600)
        self.machines = cargar_configuraciones()
        self.ventana_grafo = None

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self.tab_inicio = PestanaInicio(self.nb, self)
        self.tab_config = PestanaConfiguracion(self.nb, self)
        self.tab_ejec = PestanaEjecucion(self.nb, self)
        self.tab_manual = PestanaManual(self.nb, self)
        self.nb.add(self.tab_inicio, text="Inicio")
        self.nb.add(self.tab_config, text="Modo 1 · 1. Configuración")
        self.nb.add(self.tab_ejec, text="Modo 1 · 2. Ejecución")
        self.nb.add(self.tab_manual, text="Modo 2 · Manual (sandbox)")
        # No se puede ejecutar hasta que haya una configuración cargada.
        self.nb.tab(self.tab_ejec, state="disabled")

    def ir(self, pestana):
        self.nb.select(pestana)

    def guardar_maquina(self, m):
        self.machines[m.name] = m
        guardar_configuraciones(self.machines)
        self.tab_inicio.refrescar()

    def usar_maquina(self, nombre):
        self.nb.tab(self.tab_ejec, state="normal")
        self.tab_ejec.cargar_maquina(self.machines[nombre])
        self.ir(self.tab_ejec)

    def mostrar_grafo(self, maquina, estado_activo=None, ultima_trans=None):
        if self.ventana_grafo is not None and self.ventana_grafo.winfo_exists():
            self.ventana_grafo.cargar_maquina(maquina, estado_activo, ultima_trans)
            self.ventana_grafo.lift()
            return
        self.ventana_grafo = VentanaGrafo(self, maquina, estado_activo, ultima_trans)


def main():
    if tk is None:
        print("Este programa necesita tkinter.\n"
              "  Windows/Mac: reinstale Python marcando 'tcl/tk'.\n"
              "  Linux:       sudo apt install python3-tk")
        return
    App().mainloop()


if __name__ == "__main__":
    main()