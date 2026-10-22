#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CHRONOS · Reloj neón interactivo en Python puro
================================================
Toda la interfaz está dibujada a mano sobre un Canvas de tkinter (incluido
con Python): sin HTML, sin CSS y sin librerías externas.

    python chronos.py

Secciones (teclas 1-6 o flechas ← →):
  1 Reloj       analógico neón + digital, hora en palabras, progreso del
                día/semana/mes/año, recorrido del sol y fase lunar real.
  2 Mundo       9 ciudades con horario de verano calculado a mano.
  3 Cronómetro  vueltas, mejor/peor vuelta y gráfico de barras.
  4 Pomodoro    ciclos de enfoque/descanso con respiración guiada.
  5 Alarmas     se guardan en chronos_alarmas.json, con posponer.
  6 Binario     reloj binario BCD + timestamp Unix en bits.

Atajos: T tema · H 12/24 h · Z modo zen · F pantalla completa
        M sonido · C campanada cada hora · clic = chispas
"""

import datetime as dt
import json
import math
import os
import random
import threading
import time
import tkinter as tk
import tkinter.font as tkfont

try:
    import winsound  # Solo Windows; en otros sistemas se usa la campana de Tk
except ImportError:
    winsound = None

FRAME_MS = 33
TAU = math.tau
ALARM_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chronos_alarmas.json")

THEMES = [
    {"name": "Neón Cyber", "bg": "#05060f", "bg2": "#10143a", "a1": "#00f0ff", "a2": "#ff2bd6",
     "a3": "#8a5bff", "txt": "#e8f6ff", "dim": "#5a6488"},
    {"name": "Aurora", "bg": "#03100d", "bg2": "#0a2a20", "a1": "#3dffa8", "a2": "#36c9ff",
     "a3": "#b46bff", "txt": "#e6fff6", "dim": "#4f7a6d"},
    {"name": "Atardecer", "bg": "#12060a", "bg2": "#2e1220", "a1": "#ffb03a", "a2": "#ff4f6d",
     "a3": "#ff7ae0", "txt": "#fff1e6", "dim": "#8a5f66"},
    {"name": "Matrix", "bg": "#000a02", "bg2": "#032010", "a1": "#39ff14", "a2": "#00e676",
     "a3": "#b2ff59", "txt": "#d9ffd0", "dim": "#3f6b44"},
    {"name": "Hielo", "bg": "#050a14", "bg2": "#10203e", "a1": "#7fd8ff", "a2": "#f2f8ff",
     "a3": "#4f7cff", "txt": "#eef7ff", "dim": "#5b7090"},
]

CIUDADES = [  # (nombre, UTC estándar, regla de horario de verano)
    ("Los Ángeles", -8, "US"), ("Nueva York", -5, "US"), ("Bogotá", -5, None),
    ("Buenos Aires", -3, None), ("Londres", 0, "EU"), ("Madrid", 1, "EU"),
    ("Dubái", 4, None), ("Tokio", 9, None), ("Sídney", 10, "AU"),
]

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
NUM = ("cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince "
       "dieciséis diecisiete dieciocho diecinueve veinte veintiuno veintidós veintitrés veinticuatro "
       "veinticinco veintiséis veintisiete veintiocho veintinueve treinta").split()
HORAS_TXT = "doce una dos tres cuatro cinco seis siete ocho nueve diez once".split()

CHIME = [(1046, 110), (1318, 110), (1568, 220)]
POMO_SOUND = [(784, 140), (988, 140), (1175, 140), (1568, 320)]
ALARM_MELODY = [(880, 170), (0, 60), (1175, 170), (0, 60), (1568, 260), (0, 520)]

HINTS = {
    "reloj": "Clic en cualquier parte = chispas  ·  H 12/24 h  ·  C campanada horaria",
    "mundo": "Horario de verano calculado automáticamente  ·  H 12/24 h",
    "crono": "Espacio iniciar/pausar  ·  L vuelta  ·  R reiniciar",
    "pomo": "Espacio iniciar/pausar  ·  S saltar fase  ·  R reiniciar",
    "alarmas": "Flechas: ±1  ·  Rueda del ratón sobre los dígitos: ±1 h / ±5 min  ·  Enter agregar",
    "binario": "Suma los valores de los LEDs encendidos en cada columna",
}


# ───────────────────────────── utilidades ─────────────────────────────

_rgb = {}


def hex2rgb(c):
    v = _rgb.get(c)
    if v is None:
        if len(_rgb) > 6000:
            _rgb.clear()
        s = c.lstrip("#")
        v = _rgb[c] = (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    return v


def mix(c1, c2, t):
    """Mezcla dos colores hex: t=0 devuelve c1, t=1 devuelve c2."""
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    r1, g1, b1 = hex2rgb(c1)
    r2, g2, b2 = hex2rgb(c2)
    return "#%02x%02x%02x" % (int(r1 + (r2 - r1) * t), int(g1 + (g2 - g1) * t), int(b1 + (b2 - b1) * t))


def clamp(v, a, b):
    return a if v < a else b if v > b else v


def ease_out(t):
    return 1 - (1 - t) ** 3


def fmt_dur(secs):
    secs = int(max(0, secs))
    d, r = divmod(secs, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    if d:
        return f"{d} d {h} h"
    if h:
        return f"{h} h {m} min"
    return f"{m} min {s} s"


def fmt_sw(t):
    cs = int(t * 100)
    h, r = divmod(cs, 360000)
    m, r = divmod(r, 6000)
    s, c = divmod(r, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}" if h else f"{m:02d}:{s:02d}.{c:02d}"


def fmt_off(o):
    sign = "+" if o >= 0 else "-"
    a = abs(o)
    h = int(a)
    m = int(round((a - h) * 60))
    return f"{sign}{h}" + (f":{m:02d}" if m else "")


def local_offset():
    return dt.datetime.now().astimezone().utcoffset().total_seconds() / 3600


def nth_sunday(year, month, n):
    """n-ésimo domingo del mes (n=-1 → último)."""
    if n > 0:
        d = dt.date(year, month, 1)
        d += dt.timedelta(days=(6 - d.weekday()) % 7)
        return d + dt.timedelta(weeks=n - 1)
    d = dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() - 6) % 7)


def utc_offset(base, rule, utc):
    """Desfase UTC de una ciudad aplicando su regla de horario de verano."""
    y = utc.year
    if rule == "EU":
        start = dt.datetime.combine(nth_sunday(y, 3, -1), dt.time(1))
        end = dt.datetime.combine(nth_sunday(y, 10, -1), dt.time(1))
        return base + (1 if start <= utc < end else 0)
    std = utc + dt.timedelta(hours=base)
    if rule == "US":
        start = dt.datetime.combine(nth_sunday(y, 3, 2), dt.time(2))
        end = dt.datetime.combine(nth_sunday(y, 11, 1), dt.time(1))
        return base + (1 if start <= std < end else 0)
    if rule == "AU":
        start = dt.datetime.combine(nth_sunday(y, 10, 1), dt.time(2))
        end = dt.datetime.combine(nth_sunday(y, 4, 1), dt.time(2))
        return base + (1 if std >= start or std < end else 0)
    return base


def frase_hora(h, m):
    """Hora dicha en palabras, como la diría una persona."""
    if m == 0 and h == 0:
        return "Es medianoche en punto"
    if m == 0 and h == 12:
        return "Es mediodía en punto"
    if m <= 30:
        hh = h
        mid = (" en punto" if m == 0 else " y cuarto" if m == 15 else " y media" if m == 30
               else " y un minuto" if m == 1 else f" y {NUM[m]}")
    else:
        hh = (h + 1) % 24
        r = 60 - m
        mid = " menos cuarto" if r == 15 else " menos un minuto" if r == 1 else f" menos {NUM[r]}"
    pre = "Es la" if hh % 12 == 1 else "Son las"
    if 6 <= h < 12:
        per = "de la mañana"
    elif h == 12:
        per = "del mediodía"
    elif 12 < h < 20:
        per = "de la tarde"
    elif h >= 20:
        per = "de la noche"
    else:
        per = "de la madrugada"
    return f"{pre} {HORAS_TXT[hh % 12]}{mid} {per}"


def fase_lunar(ts):
    """Fracción del ciclo lunar (0 = nueva, 0.5 = llena)."""
    ref = dt.datetime(2000, 1, 6, 18, 14, tzinfo=dt.timezone.utc).timestamp()
    return ((ts - ref) / 86400 / 29.530588853) % 1.0


def nombre_fase(p):
    for lim, name in ((.033, "Luna nueva"), (.216, "Creciente"), (.284, "Cuarto creciente"),
                      (.466, "Gibosa creciente"), (.534, "Luna llena"), (.716, "Gibosa menguante"),
                      (.784, "Cuarto menguante"), (.967, "Menguante")):
        if p < lim:
            return name
    return "Luna nueva"


# ───────────────────────────── sonido ─────────────────────────────

class Sound:
    def __init__(self, root):
        self.root = root
        self.on = True
        self.stop_evt = threading.Event()

    def _beep(self, f, d):
        try:
            if f:
                winsound.Beep(int(f), int(d))
            else:
                time.sleep(d / 1000)
        except RuntimeError:
            pass

    def play(self, notes):
        if not self.on:
            return
        if winsound is None:
            self.root.bell()
            return
        threading.Thread(target=lambda: [self._beep(f, d) for f, d in notes], daemon=True).start()

    def alarm_start(self):
        self.stop_evt.clear()
        if winsound is None:
            return

        def run():
            while not self.stop_evt.is_set():
                if not self.on:
                    time.sleep(0.2)
                    continue
                for f, d in ALARM_MELODY:
                    if self.stop_evt.is_set():
                        break
                    self._beep(f, d)
        threading.Thread(target=run, daemon=True).start()

    def alarm_stop(self):
        self.stop_evt.set()


# ───────────────────────────── aplicación ─────────────────────────────

class Chronos:
    TABS = [("reloj", "Reloj"), ("mundo", "Mundo"), ("crono", "Cronómetro"),
            ("pomo", "Pomodoro"), ("alarmas", "Alarmas"), ("binario", "Binario")]
    GLOW = ((11, .92), (7, .82), (4, .62))
    POMO_NAMES = {"work": "ENFOQUE", "short": "DESCANSO CORTO", "long": "DESCANSO LARGO"}

    def __init__(self, root):
        self.root = root
        root.title("CHRONOS · Reloj neón")
        # Todo se dibuja en coordenadas "lógicas" (96 ppp) y al final se escala por S,
        # así la interfaz mantiene su tamaño en pantallas con escalado de Windows (125 %, 150 %…)
        self.S = float(os.environ.get("CHRONOS_SCALE", 0)) or max(1.0, root.winfo_fpixels("1i") / 96)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        wp = min(sw - 40, max(int(1100 * self.S), int(sw * 0.78)))
        hp = min(sh - 80, max(int(700 * self.S), int(sh * 0.82)))
        root.geometry(f"{wp}x{hp}+{(sw - wp) // 2}+{max(0, (sh - hp) // 3)}")
        root.minsize(min(int(1000 * self.S), sw - 40), min(int(640 * self.S), sh - 80))
        self.W, self.H = wp / self.S, hp / self.S
        root.configure(bg=THEMES[0]["bg"])
        self.cv = tk.Canvas(root, highlightthickness=0, bd=0, bg=THEMES[0]["bg"])
        self.cv.pack(fill="both", expand=True)

        fams = set(tkfont.families(root))
        self.MONO = next((f for f in ("Consolas", "Cascadia Mono", "DejaVu Sans Mono", "Menlo", "Courier New")
                          if f in fams), "Courier")
        self.SANS = next((f for f in ("Segoe UI", "Helvetica Neue", "DejaVu Sans", "Arial") if f in fams),
                         "Helvetica")
        self._fonts = {}

        # tema (con transición suave entre temas)
        self.ti = 0
        self.T = THEMES[0]
        self.theme_from = dict(THEMES[0])
        self.theme_to = THEMES[0]
        self.theme_t0 = 0.0

        self.mode = "reloj"
        self.mode_t0 = time.time()
        self.ind_x = None
        self.ind_w = 0
        self.mx = self.my = -1000
        self.btns, self.wheels = [], []
        self.block = False
        self.parts, self.waves = [], []
        self.stars = [self.new_star(True) for _ in range(110)]
        self.tip = self.clock_c = self.ring_c = None
        self.last = None
        self.flash = 0.0
        self.toast_msg, self.toast_t0 = None, 0.0
        self.sound = Sound(root)
        self.chime = True
        self.h24 = True
        self.zen = False
        self.fullscreen = False
        self.now_ts = time.time()
        self.now = dt.datetime.fromtimestamp(self.now_ts)

        # cronómetro
        self.sw_run, self.sw_t0, self.sw_acc, self.laps = False, 0.0, 0.0, []
        # pomodoro
        self.pcfg = {"work": 25, "short": 5, "long": 15}
        self.pphase, self.pleft, self.prun, self.pend = "work", 25 * 60.0, False, 0.0
        self.pdone, self.pfocus = 0, 0
        # alarmas
        self.alarms = self.load_alarms()
        self.new_h, self.new_m = 7, 0
        self.ringing, self.ring_t0, self._bell_tick = None, 0.0, 0
        # binario
        self.bin_state = {}

        self.cv.bind("<Configure>", self.on_resize)
        self.cv.bind("<Motion>", self.on_motion)
        self.cv.bind("<Leave>", lambda e: self.on_motion(None))
        self.cv.bind("<Button-1>", self.on_click)
        self.cv.bind("<MouseWheel>", self.on_wheel)
        self.cv.bind("<Button-4>", lambda e: self.on_wheel(e, 1))
        self.cv.bind("<Button-5>", lambda e: self.on_wheel(e, -1))
        root.bind("<Key>", self.on_key)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.toast("Bienvenido a CHRONOS  ·  pulsa T para cambiar de tema")
        self.loop()

    # ───────── fuentes y primitivas de dibujo ─────────

    def F(self, px, style="normal", mono=False):
        return (self.MONO if mono else self.SANS, -max(7, int(px * self.S)), style)

    def measure(self, font, text):
        f = self._fonts.get(font)
        if f is None:
            fam, size, style = font
            f = self._fonts[font] = tkfont.Font(root=self.root, family=fam, size=size,
                                                weight="bold" if "bold" in style else "normal",
                                                slant="italic" if "italic" in style else "roman")
        return f.measure(text) / self.S

    def fit(self, px, style, text, maxw, mono=False):
        """Fuente de tamaño px, reducida si el texto no cabe en maxw."""
        f = self.F(px, style, mono)
        w = self.measure(f, text)
        return f if w <= maxw else self.F(max(8, px * maxw / w), style, mono)

    def rrect(self, x1, y1, x2, y2, r, **kw):
        r = max(1, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
        pts = (x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r,
               x2, y2 - r, x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2,
               x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1)
        return self.cv.create_polygon(pts, smooth=True, **kw)

    def gline(self, pts, col, w, bg, glow=3):
        for extra, k in self.GLOW[3 - glow:]:
            self.cv.create_line(*pts, fill=mix(col, bg, k), width=w + extra, capstyle="round")
        self.cv.create_line(*pts, fill=col, width=w, capstyle="round")

    def garc(self, cx, cy, r, start, extent, col, w, bg, glow=3):
        if abs(extent) < 0.3:
            return
        extent = clamp(extent, -359.9, 359.9)
        box = (cx - r, cy - r, cx + r, cy + r)
        start %= 360
        for extra, k in self.GLOW[3 - glow:]:
            self.cv.create_arc(*box, start=start, extent=extent, style="arc", outline=mix(col, bg, k),
                               width=w + extra)
        self.cv.create_arc(*box, start=start, extent=extent, style="arc", outline=col, width=w)

    def gdot(self, x, y, r, col, bg, glow=3):
        for extra, k in self.GLOW[3 - glow:]:
            rr = r + extra * 0.6
            self.cv.create_oval(x - rr, y - rr, x + rr, y + rr, fill=mix(col, bg, k), outline="")
        self.cv.create_oval(x - r, y - r, x + r, y + r, fill=col, outline="")

    def gtext(self, x, y, text, font, col, bg, glow_col=None, glow=2, anchor="center"):
        gc = glow_col or col
        cv = self.cv
        if glow >= 2:
            c = mix(gc, bg, .86)
            for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3)):
                cv.create_text(x + dx, y + dy, text=text, font=font, fill=c, anchor=anchor)
        if glow >= 1:
            c = mix(gc, bg, .62)
            for dx, dy in ((-1, -1), (1, 1), (-1, 1), (1, -1)):
                cv.create_text(x + dx, y + dy, text=text, font=font, fill=c, anchor=anchor)
        cv.create_text(x, y, text=text, font=font, fill=col, anchor=anchor)

    def hov(self, x1, y1, x2, y2):
        return not self.block and x1 <= self.mx <= x2 and y1 <= self.my <= y2

    def button(self, x, y, w, h, text, cb, P, col=None, active=False, px=14):
        col = col or P["a1"]
        bg = P["bg"]
        hv = self.hov(x, y, x + w, y + h)
        if hv or active:
            self.rrect(x - 4, y - 4, x + w + 4, y + h + 4, h / 2 + 4, fill="", outline=mix(col, bg, .78), width=4)
        self.rrect(x, y, x + w, y + h, h / 2, fill=mix(col, bg, .62 if active else .8 if hv else .93),
                   outline=col if (hv or active) else mix(col, bg, .5), width=2)
        self.cv.create_text(x + w / 2, y + h / 2, text=text, font=self.F(px, "bold"),
                            fill=P["txt"] if (hv or active) else mix(col, P["txt"], .35))
        self.btns.append((x, y, x + w, y + h, cb))

    def panel(self, x, y, w, h, title, P, accent=None):
        cv = self.cv
        bg = P["bg"]
        ac = accent or P["a1"]
        self.rrect(x, y, x + w, y + h, 16, fill=mix(P["bg2"], bg, .45), outline=mix(ac, bg, .78), width=1)
        L = 18
        for px, py, dx, dy in ((x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
            cv.create_line(px + dx * 5, py + dy * (5 + L), px + dx * 5, py + dy * 5, px + dx * (5 + L),
                           py + dy * 5, fill=ac, width=2)
        if title:
            cv.create_text(x + 24, y + 28, text=title, anchor="w", font=self.F(14, "bold"), fill=ac)
            cv.create_line(x + 24, y + 46, x + w - 24, y + 46, fill=mix(ac, bg, .8))

    def seg_bar(self, x, y, w, h, frac, P, n=24):
        gap = 3
        sw = (w - gap * (n - 1)) / n
        filled = frac * n
        pulse = 0.5 + 0.5 * math.sin(self.now_ts * 6)
        for i in range(n):
            x1 = x + i * (sw + gap)
            full = mix(P["a1"], P["a2"], i / (n - 1))
            if i + 1 <= filled:
                c = full
            elif i < filled:
                c = mix(full, P["bg"], .25 + .45 * pulse)
            else:
                c = mix(P["dim"], P["bg"], .72)
            self.cv.create_rectangle(x1, y, x1 + sw, y + h, fill=c, outline="")

    # ───────── efectos ─────────

    def new_star(self, init=False):
        return [random.uniform(0, self.W), random.uniform(0, self.H) if init else self.H + 5,
                random.uniform(.2, 1), random.uniform(0, TAU)]

    def spark(self, x, y, col, speed=3.0, life=40, size=2.5):
        a = random.uniform(0, TAU)
        v = random.uniform(.3, 1) * speed
        self.parts.append([x, y, math.cos(a) * v, math.sin(a) * v, life, life, col, size * random.uniform(.6, 1.3)])

    def burst(self, x, y, n=26):
        cols = (self.T["a1"], self.T["a2"], self.T["a3"])
        for _ in range(n):
            self.spark(x, y, random.choice(cols), speed=5.5, life=random.randint(30, 60))
        self.wave(x, y, 4, 90, self.T["a1"])

    def wave(self, x, y, r0, r1, col, frames=40, w=3):
        self.waves.append([x, y, r0, r1, col, (r1 - r0) / frames, r0, w])

    def toast(self, msg):
        self.toast_msg, self.toast_t0 = msg, time.time()

    # ───────── bucle principal ─────────

    def loop(self):
        t0 = time.perf_counter()
        try:
            self.frame()
        except Exception:
            import traceback
            traceback.print_exc()
        spent = (time.perf_counter() - t0) * 1000
        self.root.after(max(4, int(FRAME_MS - spent)), self.loop)

    def theme(self):
        k = ease_out(clamp((self.now_ts - self.theme_t0) / 0.8, 0, 1))
        if k >= 1:
            return self.theme_to
        return {key: (val if key == "name" else mix(self.theme_from[key], val, k))
                for key, val in self.theme_to.items()}

    def frame(self):
        self.now_ts = time.time()
        self.now = dt.datetime.fromtimestamp(self.now_ts)
        self.T = T = self.theme()
        self.events()
        if self.prun and self.now_ts >= self.pend:
            self.pomo_complete()
        if self.ringing and winsound is None and self.sound.on and int(self.now_ts) != self._bell_tick:
            self._bell_tick = int(self.now_ts)
            self.root.bell()

        cv = self.cv
        cv.delete("all")
        self.btns, self.wheels = [], []
        self.block = self.ringing is not None
        self.flash *= 0.9
        cv.configure(bg=mix(T["bg"], T["a1"], self.flash * 0.22))
        self.draw_background(T)

        fade = 1 - ease_out(clamp((self.now_ts - self.mode_t0) / 0.45, 0, 1))
        P = T if fade <= 0 else {k: (v if k in ("bg", "name") else mix(v, T["bg"], fade)) for k, v in T.items()}
        top = (0 if self.zen else 64) + fade * 34
        if self.mode != "reloj":
            self.tip = None
        getattr(self, "draw_" + self.mode)(P, top)

        if not self.zen:
            self.draw_nav(T)
            self.draw_footer(T)
        if self.ringing:
            self.draw_alarm(T)
        self.draw_fx(T)
        self.draw_toast(T)
        if self.S != 1:
            cv.scale("all", 0, 0, self.S, self.S)

    def events(self):
        """Eventos que ocurren al cambiar de segundo, minuto u hora."""
        n = self.now
        hms = (n.hour, n.minute, n.second)
        last, self.last = self.last, hms
        if last is None or last == hms:
            return
        if self.tip:
            for _ in range(5):
                self.spark(*self.tip, self.T["a1"], speed=2.2, life=30, size=2)
        if hms[1] != last[1]:
            if self.mode == "reloj" and self.clock_c:
                cx, cy, R = self.clock_c
                self.wave(cx, cy, R * .2, R * 1.7, self.T["a2"], frames=50)
            self.check_alarms(n)
        if hms[0] != last[0]:
            self.flash = 1.0
            cx, cy = (self.clock_c[:2] if self.clock_c else (self.W / 2, self.H / 2))
            for i in range(3):
                self.wave(cx, cy, 10 + i * 60, max(self.W, self.H) * .7, (self.T["a1"], self.T["a2"], self.T["a3"])[i], 70)
            if self.chime:
                self.sound.play(CHIME)
            self.toast(f"Son las {n.hour:02d}:00  ·  {frase_hora(n.hour, 0)}")

    # ───────── fondo, partículas, navegación ─────────

    def draw_background(self, T):
        cv, W, H, t, bg = self.cv, self.W, self.H, self.now_ts, T["bg"]
        cx, cy = W / 2, H * .45
        for i in range(5, 0, -1):
            r = max(W, H) * .13 * i
            cv.create_oval(cx - r * 1.3, cy - r, cx + r * 1.3, cy + r, fill=mix(T["bg2"], bg, .6 + i * .075), outline="")

        # suelo "synthwave" en perspectiva
        hy = H - 120
        gcol = T["a3"]
        for i in range(-12, 13):
            cv.create_line(W / 2 + i * W / 40, hy, W / 2 + i * W / 8, H, fill=mix(gcol, bg, .84))
        ph = (t * .35) % 1
        for j in range(9):
            z = (j + ph) / 9
            cv.create_line(0, hy + (H - hy) * z * z, W, hy + (H - hy) * z * z, fill=mix(gcol, bg, .93 - .15 * z))
        cv.create_line(0, hy, W, hy, fill=mix(T["a2"], bg, .55), width=2)

        # estrellas que huyen del ratón + constelación alrededor del cursor
        mx, my = self.mx, self.my
        near = []
        for s in self.stars:
            s[1] -= .12 + .35 * s[2]
            s[0] += math.sin(t * .3 + s[3]) * .12 * s[2]
            dx, dy = s[0] - mx, s[1] - my
            d = math.hypot(dx, dy)
            if 0 < d < 120:
                push = (120 - d) / 120 * 1.6
                s[0] += dx / d * push
                s[1] += dy / d * push
            if s[1] < -6 or s[0] < -10 or s[0] > W + 10:
                s[:] = self.new_star()
                s[0] = random.uniform(0, W)
            if d < 170:
                near.append((s, d))
            tw = .6 + .4 * math.sin(t * 2 + s[3] * 3)
            r = .7 + s[2] * 1.5
            cv.create_oval(s[0] - r, s[1] - r, s[0] + r, s[1] + r, fill=mix(T["txt"], bg, 1 - s[2] * tw * .85), outline="")
        for s, d in near:
            cv.create_line(s[0], s[1], mx, my, fill=mix(T["a1"], bg, .55 + .45 * d / 170))
        for i in range(len(near)):
            for j in range(i + 1, len(near)):
                a, b = near[i][0], near[j][0]
                dd = math.hypot(a[0] - b[0], a[1] - b[1])
                if dd < 90:
                    cv.create_line(a[0], a[1], b[0], b[1], fill=mix(T["a3"], bg, .5 + .5 * dd / 90))

    def draw_fx(self, T):
        cv, bg = self.cv, T["bg"]
        alive = []
        for p in self.parts:
            p[0] += p[2]
            p[1] += p[3]
            p[2] *= .97
            p[3] = p[3] * .97 + .04
            p[4] -= 1
            if p[4] <= 0:
                continue
            alive.append(p)
            k = p[4] / p[5]
            r = p[7] * (.4 + .6 * k)
            cv.create_oval(p[0] - r, p[1] - r, p[0] + r, p[1] + r, fill=mix(p[6], bg, 1 - k), outline="")
        self.parts = alive[-450:]
        waves = []
        for w in self.waves:
            w[2] += w[5]
            k = 1 - (w[2] - w[6]) / (w[3] - w[6])
            if k <= 0:
                continue
            waves.append(w)
            cv.create_oval(w[0] - w[2], w[1] - w[2], w[0] + w[2], w[1] + w[2], outline=mix(w[4], bg, 1 - k),
                           width=max(1, w[7] * k))
        self.waves = waves

    def draw_nav(self, T):
        cv, W, bg, t, h = self.cv, self.W, T["bg"], self.now_ts, 64
        cv.create_rectangle(0, 0, W, h, fill=mix(T["bg2"], bg, .45), outline="")
        cv.create_line(0, h, W, h, fill=mix(T["a1"], bg, .7))
        sx = (t * 260) % (W + 600) - 300
        self.gline([sx, h, sx + 220, h], T["a1"], 1, bg, glow=2)

        # logo con ola de color
        x = 28
        fnt = self.F(26, "bold", True)
        for i, ch in enumerate("CHRONOS"):
            col = mix(T["a1"], T["a2"], .5 + .5 * math.sin(t * 2.2 - i * .6))
            self.gtext(x, h / 2, ch, fnt, col, bg, glow=1, anchor="w")
            x += self.measure(fnt, ch) + 1
        logo_end = x + 24

        # botones de la derecha
        rx = W - 20
        pill = self.F(13, "bold")
        w = 128
        rx -= w
        hv = self.hov(rx, 15, rx + w, h - 15)
        self.rrect(rx, 15, rx + w, h - 15, 17, fill=mix(T["a1"], bg, .82 if hv else .93),
                   outline=T["a1"] if hv else mix(T["a1"], bg, .6), width=1)
        dot = T["a1"] if self.sound.on else mix(T["dim"], bg, .3)
        self.gdot(rx + 20, h / 2, 5, dot, bg, glow=2 if self.sound.on else 0)
        cv.create_text(rx + 34, h / 2, text="SONIDO " + ("ON" if self.sound.on else "OFF"), anchor="w", font=pill,
                       fill=T["txt"] if hv else mix(T["txt"], bg, .3))
        self.btns.append((rx, 15, rx + w, h - 15, self.toggle_sound))
        w = 104
        rx -= w + 10
        hv = self.hov(rx, 15, rx + w, h - 15)
        self.rrect(rx, 15, rx + w, h - 15, 17, fill=mix(T["a2"], bg, .82 if hv else .93),
                   outline=T["a2"] if hv else mix(T["a2"], bg, .6), width=1)
        cv.create_text(rx + 16, h / 2, text="TEMA", anchor="w", font=pill, fill=T["txt"] if hv else mix(T["txt"], bg, .3))
        for i, c in enumerate((T["a1"], T["a2"], T["a3"])):
            cx = rx + 66 + i * 12
            cv.create_oval(cx - 5, h / 2 - 5, cx + 5, h / 2 + 5, fill=c, outline=bg)
        self.btns.append((rx, 15, rx + w, h - 15, self.next_theme))
        if self.mode != "reloj" and W > 1250:
            n = self.now
            rx -= 12
            self.gtext(rx, h / 2, f"{n:%H:%M:%S}", self.F(20, "bold", True), T["a1"], bg, glow=1, anchor="e")
            rx -= self.measure(self.F(20, "bold", True), "00:00:00")
        right_start = rx - 16

        # pestañas con indicador que se desliza
        fnt = self.F(15, "bold")
        widths = [self.measure(fnt, name) + 34 for _, name in self.TABS]
        x = max(logo_end, (logo_end + right_start) / 2 - sum(widths) / 2)
        tx = tw = 0
        for i, ((key, name), w) in enumerate(zip(self.TABS, widths)):
            active = key == self.mode
            hv = self.hov(x, 8, x + w, h - 8)
            if hv and not active:
                self.rrect(x + 3, 12, x + w - 3, h - 12, 12, fill=mix(T["a1"], bg, .9), outline="")
            col = T["txt"] if active else (mix(T["txt"], bg, .1) if hv else T["dim"])
            cv.create_text(x + w / 2, h / 2 - 1, text=name, font=fnt, fill=col)
            cv.create_text(x + 9, 17, text=str(i + 1), font=self.F(10, "bold"), fill=mix(T["dim"], bg, .35))
            if active:
                tx, tw = x + 12, w - 24
            self.btns.append((x, 8, x + w, h - 8, lambda k=key: self.set_mode(k)))
            x += w
        if self.ind_x is None:
            self.ind_x, self.ind_w = tx, tw
        self.ind_x += (tx - self.ind_x) * .22
        self.ind_w += (tw - self.ind_w) * .22
        self.gline([self.ind_x, h - 7, self.ind_x + self.ind_w, h - 7], T["a1"], 3, bg)

    def draw_footer(self, T):
        txt = HINTS[self.mode] + "   ·   1-6 / ← → secciones  ·  T tema  ·  Z zen  ·  F pantalla completa  ·  M sonido"
        self.cv.create_text(self.W / 2, self.H - 14, text=txt, font=self.F(11), fill=mix(T["dim"], T["bg"], .1))

    def draw_toast(self, T):
        if not self.toast_msg:
            return
        el = self.now_ts - self.toast_t0
        if el > 2.6:
            self.toast_msg = None
            return
        k = clamp(min(el / .2, (2.6 - el) / .4), 0, 1)
        bg = T["bg"]
        fnt = self.F(15, "bold")
        w = self.measure(fnt, self.toast_msg) + 48
        x, y = self.W / 2 - w / 2, self.H - 84 + (1 - k) * 14
        self.rrect(x, y, x + w, y + 38, 19, fill=mix(mix(T["bg2"], T["a1"], .15), bg, 1 - k),
                   outline=mix(T["a1"], bg, 1 - k * .8), width=2)
        self.cv.create_text(self.W / 2, y + 19, text=self.toast_msg, font=fnt, fill=mix(T["txt"], bg, 1 - k))

    # ───────── 1. RELOJ ─────────

    def draw_reloj(self, P, top):
        W, H, cv, n = self.W, self.H, self.cv, self.now
        # el alto disponible se reparte entre la esfera (2R) y los textos de abajo (~0.5R + margen)
        if self.zen:
            R = max(120, min(W * .26, (H - 140) / 2.45))
            cx, cy = W / 2, top + 36 + R
        else:
            R = max(110, min(W * .19, (H - top - 160) / 2.55))
            cx, cy = W / 2, top + 48 + R
        self.clock_c = (cx, cy, R)
        self.draw_analog(cx, cy, R, P)

        dsz = R * .36
        y = cy + R + 36 + dsz / 2
        self.draw_digital(cx, y, dsz, P)
        fecha = f"{DIAS[n.weekday()]}, {n.day} de {MESES[n.month - 1]} de {n.year}".upper()
        y2 = y + dsz * .62 + 12
        cv.create_text(cx, y2, text=fecha, font=self.F(max(13, R * .062), "bold"), fill=mix(P["txt"], P["bg"], .25))
        if self.zen:
            return
        cv.create_text(cx, y2 + max(23, R * .11), text=frase_hora(n.hour, n.minute),
                       font=self.F(max(14, R * .072), "italic"), fill=mix(P["a3"], P["txt"], .35))

        pw = min(330, cx - R - 100 - 40)
        if pw >= 200:
            ph = min(H - top - 110, 450)
            py = max(top + 26, cy - ph / 2)
            self.panel_progreso(40, py, pw, ph, P)
            self.panel_cielo(W - 40 - pw, py, pw, ph, P)

    def draw_analog(self, cx, cy, R, P):
        cv, bg, t, n = self.cv, P["bg"], self.now_ts, self.now
        frac = t % 1
        s = n.second + frac
        m = n.minute + s / 60
        h = n.hour % 12 + m / 60

        for i in range(6, 0, -1):  # esfera con degradado radial
            rr = R * (.5 + .09 * i)
            cv.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=mix(P["bg2"], bg, .25 + i * .1), outline="")

        # anillos decorativos que giran en sentidos opuestos
        r1 = R + 20
        c1 = mix(P["a3"], bg, .55)
        for k in range(36):
            cv.create_arc(cx - r1, cy - r1, cx + r1, cy + r1, start=(t * 14 + k * 10) % 360, extent=4,
                          style="arc", outline=c1, width=2)
        r2 = R + 33
        for k in range(3):
            self.garc(cx, cy, r2, -t * 25 + k * 120, 46, P["a2"], 2, bg, glow=2)
        oa = t * .9
        self.gdot(cx + r2 * math.cos(oa), cy - r2 * math.sin(oa), 3, P["a1"], bg, 2)

        # anillos de progreso: segundos, minutos y horas
        for rr, val, col, w in ((R, s / 60, P["a1"], 4), (R - 11, m / 60, P["a2"], 3), (R - 20, h / 12, P["a3"], 2)):
            cv.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=mix(col, bg, .86), width=w)
            self.garc(cx, cy, rr, 90, -val * 360, col, w, bg, glow=2)
            a = val * TAU
            self.gdot(cx + rr * math.sin(a), cy - rr * math.cos(a), w * .9 + 1, mix(col, "#ffffff", .4), bg, 2)

        # marcas con estela de cometa detrás del segundero
        for i in range(60):
            a = i / 60 * TAU
            sa, ca = math.sin(a), math.cos(a)
            big = i % 5 == 0
            ro = R - 31
            ri = ro - (13 if big else 6)
            d = (s - i) % 60
            b = 1 - d / 9 if d < 9 else 0
            col = mix(mix(P["dim"], bg, .2 if big else .5), P["a1"], b)
            cv.create_line(cx + ri * sa, cy - ri * ca, cx + ro * sa, cy - ro * ca, fill=col,
                           width=(3 if big else 1) + (1 if b > .5 else 0))

        fnum = self.F(max(11, R * .085), "bold")
        rn = R - 60
        cur = n.hour % 12
        for i in range(12):
            a = i / 12 * TAU
            x, y = cx + rn * math.sin(a), cy - rn * math.cos(a)
            if i == cur:
                self.gtext(x, y, str(i or 12), fnum, P["a2"], bg, glow=1)
            else:
                cv.create_text(x, y, text=str(i or 12), font=fnum, fill=mix(P["txt"], bg, .45))

        k = ease_out(frac)  # latido que sale del centro cada segundo
        rr = R * .08 + k * R * .5
        cv.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=mix(P["a1"], bg, .55 + .45 * k), width=2)

        def hand(val, length, w, col, tail=0.0):
            a = val * TAU
            sa, ca = math.sin(a), math.cos(a)
            pts = [cx - tail * sa, cy + tail * ca, cx + length * sa, cy - length * ca]
            self.gline(pts, col, w, bg)
            return pts[2], pts[3]

        hand(h / 12, R * .46, 8, P["a3"])
        hand(m / 60, R * .68, 5, P["a2"])
        self.tip = hand(s / 60, R * .8, 2, P["a1"], tail=R * .16)
        self.gdot(*self.tip, 4, P["a1"], bg)
        self.gdot(cx, cy, 9, P["a1"], bg)
        cv.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill=bg, outline="")

    def draw_digital(self, cx, y, size, P):
        n, frac, bg = self.now, self.now_ts % 1, P["bg"]
        h, suf = n.hour, ""
        if not self.h24:
            suf, h = ("AM" if h < 12 else "PM"), (h % 12 or 12)
        main = f"{h:02d}{':' if frac < .5 else ' '}{n.minute:02d}"
        fm, fs = self.F(size, "bold", True), self.F(size * .42, "bold", True)
        wm, ws = self.measure(fm, main), self.measure(fs, "00")
        x0 = cx - (wm + 14 + ws) / 2
        self.gtext(x0, y, main, fm, P["txt"], bg, glow_col=P["a1"], anchor="w")
        self.gtext(x0 + wm + 14, y + size * .2, f"{n.second:02d}", fs, P["a2"], bg, glow=1, anchor="w")
        if suf:
            self.cv.create_text(x0 + wm + 14, y - size * .22, text=suf, anchor="w",
                                font=self.F(size * .24, "bold"), fill=P["a3"])

    def panel_progreso(self, x, y, w, h, P):
        cv, n = self.cv, self.now
        self.panel(x, y, w, h, "PROGRESO DEL TIEMPO", P)
        sod = n.hour * 3600 + n.minute * 60 + n.second + n.microsecond / 1e6
        dim_ = (dt.date(n.year + n.month // 12, n.month % 12 + 1, 1) - dt.date(n.year, n.month, 1)).days
        y0, y1 = dt.datetime(n.year, 1, 1), dt.datetime(n.year + 1, 1, 1)
        yf = (n - y0).total_seconds() / (y1 - y0).total_seconds()
        wk = n.weekday() * 86400 + sod
        mo = (n.day - 1) * 86400 + sod
        items = [
            ("DÍA", sod / 86400, 4, f"faltan {fmt_dur(86400 - sod)}"),
            ("SEMANA", wk / 604800, 5, f"faltan {fmt_dur(604800 - wk)}"),
            ("MES", mo / (dim_ * 86400), 5, f"faltan {fmt_dur(dim_ * 86400 - mo)}"),
            ("AÑO", yf, 7, f"faltan {fmt_dur((y1 - n).total_seconds())}"),
        ]
        step = (h - 120) / 4
        iy = y + 70
        for label, fr, dec, sub in items:
            cv.create_text(x + 24, iy, text=label, anchor="w", font=self.F(13, "bold"), fill=P["txt"])
            cv.create_text(x + w - 24, iy, text=f"{fr * 100:.{dec}f}%", anchor="e", font=self.F(14, "bold", True),
                           fill=P["a1"])
            self.seg_bar(x + 24, iy + 14, w - 48, 11, fr, P)
            cv.create_text(x + 24, iy + 40, text=sub, anchor="w", font=self.F(12), fill=P["dim"])
            iy += step
        cv.create_text(x + 24, y + h - 46, anchor="w", font=self.F(12, "bold"), fill=mix(P["txt"], P["bg"], .3),
                       text=f"Día {n.timetuple().tm_yday} del año  ·  Semana {n.isocalendar()[1]}")
        nxt = self.next_alarm()
        txt = (f"Próxima alarma {self.fmt_hm(nxt['h'], nxt['m'])}  (en {fmt_dur(self.until(nxt))})"
               if nxt else "Sin alarmas activas")
        cv.create_text(x + 24, y + h - 24, anchor="w", font=self.F(12), fill=P["a2"] if nxt else P["dim"], text=txt)

    def panel_cielo(self, x, y, w, h, P):
        cv, n, bg = self.cv, self.now, P["bg"]
        self.panel(x, y, w, h, "CIELO Y LUNA", P, P["a2"])
        hf = n.hour + n.minute / 60 + n.second / 3600
        r = w * .36
        acx, acy = x + w / 2, y + 66 + r
        cv.create_arc(acx - r, acy - r, acx + r, acy + r, start=0, extent=180, style="arc",
                      outline=mix(P["dim"], bg, .2), dash=(3, 5))
        cv.create_line(x + 24, acy, x + w - 24, acy, fill=mix(P["a2"], bg, .45), width=2)
        day = 6 <= hf < 18
        tt = (hf - 6) / 12 if day else ((hf - 18) % 24) / 12
        col = mix("#ffd25a", P["a1"], .12) if day else P["txt"]
        if tt > .002:  # estela del recorrido
            cv.create_arc(acx - r, acy - r, acx + r, acy + r, start=180, extent=-180 * tt, style="arc",
                          outline=mix(col, bg, .45), width=3)
        th = math.pi * (1 - tt)
        bx, by = acx + r * math.cos(th), acy - r * math.sin(th)
        if day:
            rot = self.now_ts * .7
            for i in range(10):
                a = rot + i / 10 * TAU
                cv.create_line(bx + 15 * math.cos(a), by + 15 * math.sin(a), bx + 22 * math.cos(a),
                               by + 22 * math.sin(a), fill=mix(col, bg, .3), width=2)
            self.gdot(bx, by, 11, col, bg)
        else:
            self.gdot(bx, by, 10, col, bg)
            cv.create_oval(bx - 5, by - 13, bx + 15, by + 7, fill=mix(P["bg2"], bg, .45), outline="")
        if hf < 6:
            per = "MADRUGADA"
        elif hf < 12:
            per = "MAÑANA"
        elif hf < 18:
            per = "TARDE"
        else:
            per = "NOCHE"
        cv.create_text(x + 24, acy + 16, text="06:00", anchor="w", font=self.F(11, mono=True), fill=P["dim"])
        cv.create_text(x + w - 24, acy + 16, text="18:00", anchor="e", font=self.F(11, mono=True), fill=P["dim"])
        cv.create_text(acx, acy + 16, text=per, font=self.F(12, "bold"), fill=col)

        p = fase_lunar(self.now_ts)
        ill = (1 - math.cos(TAU * p)) / 2 * 100
        mr = min(46, w * .15)
        mcx, mcy = x + 30 + mr, acy + 50 + mr
        self.draw_moon(mcx, mcy, mr, p, P)
        tx = mcx + mr + 22
        tw = x + w - 20 - tx
        full = ((.5 - p) % 1) * 29.530588853
        new = ((1 - p) % 1) * 29.530588853
        for dy_, txt, px, style, col in ((-30, nombre_fase(p), 16, "bold", P["txt"]),
                                         (-6, f"Iluminación {ill:.1f}%", 12, "normal", P["a1"]),
                                         (14, f"Llena en {full:.1f} días", 12, "normal", P["dim"]),
                                         (32, f"Nueva en {new:.1f} días", 12, "normal", P["dim"])):
            cv.create_text(tx, mcy + dy_, text=txt, anchor="w", font=self.fit(px, style, txt, tw), fill=col)
        u = dt.datetime.now(dt.timezone.utc)
        txt = f"UTC {u:%H:%M:%S}  ·  Unix {int(self.now_ts)}"
        cv.create_text(x + 24, y + h - 24, anchor="w", font=self.fit(12, "normal", txt, w - 44, True),
                       fill=mix(P["txt"], bg, .3), text=txt)

    def draw_moon(self, cx, cy, r, p, P):
        cv, bg = self.cv, P["bg"]
        lit = mix(P["txt"], "#fff5d6", .4)
        ill = (1 - math.cos(TAU * p)) / 2
        for f, k in ((1.3, .94), (1.12, .86)):
            rr = r * f
            cv.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=mix(lit, bg, k + (1 - k) * (1 - ill) * .8), outline="")
        cv.create_oval(cx - r, cy - r, cx + r, cy + r, fill=mix(P["bg2"], lit, .1), outline=mix(lit, bg, .6))
        sgn = 1 if p < .5 else -1
        kx = math.cos(TAU * p)
        pts = []
        N = 32
        for i in range(N + 1):  # borde iluminado
            a = -math.pi / 2 + math.pi * i / N
            pts += [cx + sgn * r * math.cos(a), cy + r * math.sin(a)]
        for i in range(N + 1):  # terminador (elipse)
            a = math.pi / 2 - math.pi * i / N
            pts += [cx + sgn * r * math.cos(a) * kx, cy + r * math.sin(a)]
        cv.create_polygon(pts, fill=lit, outline="")
        for dx, dy, cr in ((-.3, -.25, .18), (.28, .3, .13), (.1, -.5, .09), (-.15, .4, .11)):
            ox, oy, rr = cx + dx * r, cy + dy * r, cr * r
            cv.create_oval(ox - rr, oy - rr, ox + rr, oy + rr, outline=mix(lit, "#000000", .18), width=1)

    # ───────── 2. MUNDO ─────────

    def draw_mundo(self, P, top):
        cv, W, H, bg = self.cv, self.W, self.H, P["bg"]
        utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        loff = local_offset()
        cv.create_text(40, top + 36, text="RELOJ MUNDIAL", anchor="w", font=self.F(24, "bold"), fill=P["txt"])
        cv.create_text(W - 40, top + 36, anchor="e", font=self.F(14, mono=True), fill=P["dim"],
                       text=f"Tu zona: UTC{fmt_off(loff)}   ·   UTC {utc:%H:%M:%S}")
        gap = 18
        x0, y0 = 40, top + 70
        cw = (W - 80 - gap * 2) / 3
        ch = (H - y0 - 44 - gap * 2) / 3
        for i, (name, base, rule) in enumerate(CIUDADES):
            off = utc_offset(base, rule, utc)
            ct = utc + dt.timedelta(hours=off)
            x = x0 + (i % 3) * (cw + gap)
            y = y0 + (i // 3) * (ch + gap)
            hv = self.hov(x, y, x + cw, y + ch)
            if hv:
                y -= 4
            day = 6 <= ct.hour < 18
            face = mix(P["bg2"], P["a1"], .08) if day else mix(P["bg2"], bg, .4)
            if hv:
                self.rrect(x - 4, y - 4, x + cw + 4, y + ch + 4, 20, fill="", outline=mix(P["a1"], bg, .72), width=5)
            self.rrect(x, y, x + cw, y + ch, 16, fill=face, outline=P["a1"] if hv else mix(P["a1"], bg, .72),
                       width=2 if hv else 1)
            r = min(ch * .34, cw * .19)
            mcx, mcy = x + 22 + r, y + ch / 2
            self.mini_clock(mcx, mcy, r, ct, P, face)
            tx = mcx + r + 24
            cv.create_text(tx, y + ch * .27, text=name, anchor="w", font=self.F(max(14, ch * .13), "bold"), fill=P["txt"])
            hh = ct.hour if self.h24 else (ct.hour % 12 or 12)
            suf = "" if self.h24 else (" AM" if ct.hour < 12 else " PM")
            cv.create_text(tx, y + ch * .52, text=f"{hh:02d}:{ct.minute:02d}:{ct.second:02d}{suf}", anchor="w",
                           font=self.F(max(16, ch * .17), "bold", True), fill=P["a1"])
            diff = off - loff
            dd = (ct.date() - self.now.date()).days
            rel = "misma hora" if abs(diff) < .01 else f"{diff:+g} h"
            rel += " · mañana" if dd == 1 else " · ayer" if dd == -1 else ""
            cv.create_text(tx, y + ch * .76, text=f"UTC{fmt_off(off)}  ·  {rel}", anchor="w",
                           font=self.F(max(11, ch * .08)), fill=P["dim"])
            ix, iy = x + cw - 28, y + 28
            if day:
                rot = self.now_ts * .5
                for j in range(8):
                    a = rot + j / 8 * TAU
                    cv.create_line(ix + 9 * math.cos(a), iy + 9 * math.sin(a), ix + 13 * math.cos(a),
                                   iy + 13 * math.sin(a), fill="#ffd25a", width=2)
                cv.create_oval(ix - 6, iy - 6, ix + 6, iy + 6, fill="#ffd25a", outline="")
            else:
                cv.create_oval(ix - 8, iy - 8, ix + 8, iy + 8, fill=P["txt"], outline="")
                cv.create_oval(ix - 4, iy - 11, ix + 12, iy + 5, fill=face, outline="")

    def mini_clock(self, cx, cy, r, t, P, face):
        cv, bg = self.cv, P["bg"]
        cv.create_oval(cx - r - 5, cy - r - 5, cx + r + 5, cy + r + 5, outline=mix(P["a1"], bg, .82), width=3)
        cv.create_oval(cx - r, cy - r, cx + r, cy + r, fill=mix(face, bg, .35), outline=mix(P["a1"], bg, .45), width=2)
        for i in range(12):
            a = i / 12 * TAU
            l = r * (.17 if i % 3 == 0 else .08)
            cv.create_line(cx + (r - 4) * math.sin(a), cy - (r - 4) * math.cos(a), cx + (r - 4 - l) * math.sin(a),
                           cy - (r - 4 - l) * math.cos(a), fill=mix(P["txt"], bg, .3 if i % 3 == 0 else .55),
                           width=2 if i % 3 == 0 else 1)
        s = t.second + t.microsecond / 1e6
        m = t.minute + s / 60
        h = t.hour % 12 + m / 60
        for val, length, w, col in ((h / 12, .5, 5, P["a3"]), (m / 60, .74, 3, P["a2"]), (s / 60, .84, 1, P["a1"])):
            a = val * TAU
            self.gline([cx, cy, cx + r * length * math.sin(a), cy - r * length * math.cos(a)], col, w, bg, glow=1)
        cv.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill=P["a1"], outline="")

    # ───────── 3. CRONÓMETRO ─────────

    def sw_elapsed(self):
        return self.sw_acc + (self.now_ts - self.sw_t0 if self.sw_run else 0)

    def sw_toggle(self):
        if self.sw_run:
            self.sw_acc += time.time() - self.sw_t0
            self.sw_run = False
        else:
            self.sw_t0 = time.time()
            self.sw_run = True
        if self.ring_c:
            self.wave(self.ring_c[0], self.ring_c[1], self.ring_c[2] * .3, self.ring_c[2] * 1.3, self.T["a1"])

    def sw_lap(self):
        if not self.sw_run:
            return
        self.laps.append(self.sw_acc + time.time() - self.sw_t0)
        if self.ring_c:
            cx, cy, R = self.ring_c
            self.wave(cx, cy, R, R * 1.5, self.T["a2"])
            for _ in range(20):
                self.spark(cx, cy - R, self.T["a2"], speed=4)

    def sw_reset(self):
        self.sw_run, self.sw_acc, self.laps = False, 0.0, []

    def ring_layout(self, top):
        R = max(110, min((self.H - top - 190) / 2, self.W * .2))
        cx, cy = self.W * .36, top + 52 + R
        self.ring_c = (cx, cy, R)
        return cx, cy, R

    def draw_crono(self, P, top):
        cv, W, H, bg = self.cv, self.W, self.H, P["bg"]
        e = self.sw_elapsed()
        cx, cy, R = self.ring_layout(top)
        live = self.sw_run

        cs = (e * 100) % 100  # anillo de centésimas que gira a toda velocidad
        for i in range(100):
            a = i / 100 * TAU
            d = (cs - i) % 100
            b = max(0.0, 1 - d / 30) if e > 0 else 0
            big = i % 10 == 0
            r1, r2 = R + 12, R + (27 if big else 19)
            col = mix(mix(P["dim"], bg, .45 if big else .7), P["a1"], b)
            cv.create_line(cx + r1 * math.sin(a), cy - r1 * math.cos(a), cx + r2 * math.sin(a), cy - r2 * math.cos(a),
                           fill=col, width=2 if (big or b > .5) else 1)
        for rr, val, col, w in ((R - 8, (e % 60) / 60, P["a2"], 6), (R - 25, (e % 3600) / 3600, P["a3"], 3)):
            cv.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=mix(col, bg, .86), width=w)
            self.garc(cx, cy, rr, 90, -val * 360, col, w, bg)

        tot = int(e * 100)
        cc, s, m, h = tot % 100, (tot // 100) % 60, (tot // 6000) % 60, tot // 360000
        main = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        dsz = R * (.32 if h else .42)
        fm, fc = self.F(dsz, "bold", True), self.F(dsz * .45, "bold", True)
        wm, wc = self.measure(fm, main), self.measure(fc, ".00")
        x0 = cx - (wm + wc) / 2
        self.gtext(x0, cy, main, fm, P["txt"], bg, glow_col=P["a1"], anchor="w")
        self.gtext(x0 + wm, cy + dsz * .2, f".{cc:02d}", fc, P["a2"], bg, glow=1, anchor="w")
        state = "EN MARCHA" if live else ("EN PAUSA" if e > 0 else "LISTO")
        cv.create_text(cx, cy - dsz * .85, text=state, font=self.F(14, "bold"), fill=P["a1"] if live else P["dim"])
        if self.laps:
            cv.create_text(cx, cy + dsz * .85, text=f"Vuelta {len(self.laps) + 1}:  {fmt_sw(e - self.laps[-1])}",
                           font=self.F(14, mono=True), fill=P["a3"])

        bw, bh, g = 150, 46, 16
        by = cy + R + 44
        bx = cx - (bw * 3 + g * 2) / 2
        self.button(bx, by, bw, bh, "PAUSAR" if live else ("REANUDAR" if e > 0 else "INICIAR"), self.sw_toggle, P,
                    active=live)
        self.button(bx + bw + g, by, bw, bh, "VUELTA", self.sw_lap, P, col=P["a2"])
        self.button(bx + 2 * (bw + g), by, bw, bh, "REINICIAR", self.sw_reset, P, col=P["a3"])

        px = W * .62
        pw, py, ph = W - 40 - px, top + 26, H - top - 70
        self.panel(px, py, pw, ph, f"VUELTAS  ({len(self.laps)})", P, P["a2"])
        if not self.laps:
            cv.create_text(px + pw / 2, py + ph / 2, text="Pulsa VUELTA (L) mientras\nel cronómetro está en marcha",
                           justify="center", font=self.F(15), fill=P["dim"])
            return
        durs = [self.laps[0]] + [self.laps[i] - self.laps[i - 1] for i in range(1, len(self.laps))]
        best = durs.index(min(durs)) if len(durs) > 1 else -1
        worst = durs.index(max(durs)) if len(durs) > 1 else -1
        chart_h = 120 if len(durs) > 1 else 0
        hy = py + 66
        fh, fr = self.F(12, "bold"), self.F(15, mono=True)
        cv.create_text(px + 26, hy, text="Nº", anchor="w", font=fh, fill=P["dim"])
        cv.create_text(px + pw * .45, hy, text="VUELTA", anchor="center", font=fh, fill=P["dim"])
        cv.create_text(px + pw - 26, hy, text="TOTAL", anchor="e", font=fh, fill=P["dim"])
        ry = hy + 30
        rows = max(1, int((ph - 110 - chart_h) / 30))
        for i in range(len(durs) - 1, max(-1, len(durs) - 1 - rows), -1):
            col = P["a1"] if i == best else P["a2"] if i == worst else P["txt"]
            if i in (best, worst):
                self.rrect(px + 16, ry - 13, px + pw - 16, ry + 13, 8, fill=mix(col, bg, .88), outline="")
            cv.create_text(px + 26, ry, text=f"{i + 1:02d}", anchor="w", font=fr, fill=col)
            cv.create_text(px + pw * .45, ry, text=fmt_sw(durs[i]), anchor="center", font=fr, fill=col)
            cv.create_text(px + pw - 26, ry, text=fmt_sw(self.laps[i]), anchor="e", font=fr, fill=mix(col, bg, .3))
            ry += 30
        if chart_h:
            data = durs[-24:]
            off = len(durs) - len(data)
            mx_ = max(data)
            cx0, cy0, cwid = px + 26, py + ph - 26, pw - 52
            cv.create_line(cx0, cy0, cx0 + cwid, cy0, fill=mix(P["dim"], bg, .3))
            bwid = cwid / len(data)
            for j, d in enumerate(data):
                idx = j + off
                hgt = (chart_h - 30) * d / mx_
                col = P["a1"] if idx == best else P["a2"] if idx == worst else mix(P["a3"], bg, .3)
                cv.create_rectangle(cx0 + j * bwid + 2, cy0 - hgt, cx0 + (j + 1) * bwid - 2, cy0, fill=col, outline="")
            cv.create_text(cx0, cy0 - chart_h + 8, text="MEJOR", anchor="w", font=self.F(11, "bold"), fill=P["a1"])
            cv.create_text(cx0 + 60, cy0 - chart_h + 8, text="PEOR", anchor="w", font=self.F(11, "bold"), fill=P["a2"])

    # ───────── 4. POMODORO ─────────

    def pomo_left(self):
        return max(0.0, self.pend - self.now_ts) if self.prun else self.pleft

    def pomo_toggle(self):
        if self.prun:
            self.pleft = max(0.0, self.pend - time.time())
            self.prun = False
        else:
            self.pend = time.time() + self.pleft
            self.prun = True

    def pomo_advance(self, counted):
        if self.pphase == "work":
            if counted:
                self.pdone += 1
                self.pfocus += self.pcfg["work"]
            nxt = "long" if counted and self.pdone % 4 == 0 else "short"
        else:
            nxt = "work"
        self.pphase = nxt
        self.pleft = self.pcfg[nxt] * 60.0
        self.pend = time.time() + self.pleft

    def pomo_complete(self):
        was_work = self.pphase == "work"
        self.pomo_advance(True)
        self.prun = True
        self.sound.play(POMO_SOUND)
        self.flash = 1.0
        cx, cy, R = self.ring_c or (self.W / 2, self.H / 2, 200)
        for i in range(3):
            self.wave(cx, cy, R * .5 + i * 30, R * 2, (self.T["a1"], self.T["a2"], self.T["a3"])[i], 60)
        self.toast("¡Sesión completada! Hora de descansar" if was_work else "Descanso terminado · ¡a enfocarse!")

    def pomo_skip(self):
        self.pomo_advance(False)
        if not self.prun:
            self.pleft = self.pcfg[self.pphase] * 60.0

    def pomo_reset(self):
        self.prun, self.pphase, self.pleft = False, "work", self.pcfg["work"] * 60.0

    def pomo_adj(self, key, d):
        self.pcfg[key] = int(clamp(self.pcfg[key] + d, 1, 90))
        if not self.prun and self.pphase == key:
            self.pleft = self.pcfg[key] * 60.0

    def draw_pomo(self, P, top):
        cv, W, H, bg, t = self.cv, self.W, self.H, P["bg"], self.now_ts
        cx, cy, R = self.ring_layout(top)
        total = self.pcfg[self.pphase] * 60
        left = self.pomo_left()
        rem = clamp(left / total, 0, 1) if total else 0
        work = self.pphase == "work"
        pcol = P["a2"] if work else P["a1"]

        if not work:  # círculo de respiración guiada (4 s inhalar, 4 s exhalar)
            b = .5 - .5 * math.cos(TAU * t / 8)
            for i in range(5, 0, -1):
                rr = R * (.4 + .45 * b) * (.5 + .1 * i)
                cv.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=mix(P["a1"], bg, .93 - .05 * (5 - i)),
                               outline=mix(P["a1"], bg, .75) if i == 5 else "")
        else:
            rr = R * .78
            for k in range(24):
                cv.create_arc(cx - rr, cy - rr, cx + rr, cy + rr, start=(-t * 8 + k * 15) % 360, extent=5,
                              style="arc", outline=mix(P["a3"], bg, .7), width=2)

        cv.create_oval(cx - R, cy - R, cx + R, cy + R, outline=mix(pcol, bg, .88), width=16)
        if rem > 0:
            self.garc(cx, cy, R, 90, -rem * 360, pcol, 12, bg)
            nseg = 90
            segs = rem * nseg
            for i in range(int(math.ceil(segs))):
                ext = 4 if i < int(segs) else (segs - i) * 4
                cv.create_arc(cx - R, cy - R, cx + R, cy + R, start=(90 - i * 4) % 360, extent=-min(ext + .6, 4.6),
                              style="arc", outline=mix(P["a1"], P["a2"], i / nseg), width=14)
            a = rem * TAU
            hx, hy = cx + R * math.sin(a), cy - R * math.cos(a)
            self.gdot(hx, hy, 9, mix(pcol, "#ffffff", .5), bg)
            if self.prun and random.random() < .4:
                self.spark(hx, hy, pcol, speed=2, life=35)

        m, s = divmod(int(math.ceil(left)), 60)
        dsz = R * .4
        self.gtext(cx, cy, f"{m:02d}:{s:02d}", self.F(dsz, "bold", True), P["txt"], bg, glow_col=pcol)
        cv.create_text(cx, cy - dsz * .9, text=self.POMO_NAMES[self.pphase], font=self.F(16, "bold"), fill=pcol)
        if not work and self.prun:
            sub = "Inhala…" if math.sin(TAU * t / 8) > 0 else "Exhala…"
        elif self.prun:
            sub = "Mantén el foco"
        else:
            sub = "En pausa · Espacio para iniciar"
        cv.create_text(cx, cy + dsz * .78, text=sub, font=self.F(14, "italic"), fill=mix(P["txt"], bg, .3))
        done_cycle = self.pdone % 4 if not (self.pphase == "long" and self.pdone) else 4
        for i in range(4):
            dx = cx + (i - 1.5) * 26
            dy = cy + dsz * 1.25
            if i < done_cycle:
                self.gdot(dx, dy, 7, P["a2"], bg, glow=2)
            else:
                cv.create_oval(dx - 7, dy - 7, dx + 7, dy + 7, outline=mix(P["a2"], bg, .55), width=2)

        bw, bh, g = 150, 46, 16
        by = cy + R + 44
        bx = cx - (bw * 3 + g * 2) / 2
        self.button(bx, by, bw, bh, "PAUSAR" if self.prun else "INICIAR", self.pomo_toggle, P, active=self.prun)
        self.button(bx + bw + g, by, bw, bh, "SALTAR", self.pomo_skip, P, col=P["a2"])
        self.button(bx + 2 * (bw + g), by, bw, bh, "REINICIAR", self.pomo_reset, P, col=P["a3"])

        px = W * .62
        pw, py, ph = W - 40 - px, top + 26, H - top - 70
        self.panel(px, py, pw, ph, "CONFIGURACIÓN", P)
        ry = py + 84
        for label, key in (("Enfoque", "work"), ("Descanso corto", "short"), ("Descanso largo", "long")):
            cv.create_text(px + 26, ry, text=label, anchor="w", font=self.F(15, "bold"),
                           fill=P["txt"] if key == self.pphase else mix(P["txt"], bg, .3))
            bx2 = px + pw - 26 - 150
            self.button(bx2, ry - 17, 40, 34, "−", lambda k=key: self.pomo_adj(k, -1), P, px=18)
            cv.create_text(bx2 + 75, ry, text=f"{self.pcfg[key]} min", font=self.F(15, "bold", True), fill=P["a1"])
            self.button(bx2 + 110, ry - 17, 40, 34, "+", lambda k=key: self.pomo_adj(k, 1), P, px=18)
            ry += 58
        cv.create_line(px + 26, ry - 10, px + pw - 26, ry - 10, fill=mix(P["a1"], bg, .8))
        ry += 20
        for label, val in (("Sesiones completadas", str(self.pdone)), ("Minutos de enfoque", str(self.pfocus)),
                           ("Ciclo actual", f"{done_cycle} / 4")):
            cv.create_text(px + 26, ry, text=label, anchor="w", font=self.F(14), fill=P["dim"])
            cv.create_text(px + pw - 26, ry, text=val, anchor="e", font=self.F(18, "bold", True), fill=P["a2"])
            ry += 36
        cv.create_text(px + 26, ry + 20, anchor="nw", width=pw - 52, font=self.F(13, "italic"),
                       fill=mix(P["txt"], bg, .4),
                       text="Cada 4 sesiones de enfoque llega un descanso largo. En los descansos, "
                            "sigue el círculo: inhala cuando crece, exhala cuando se encoge.")

    # ───────── 5. ALARMAS ─────────

    def load_alarms(self):
        try:
            with open(ALARM_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return [{"h": int(a["h"]) % 24, "m": int(a["m"]) % 60, "on": bool(a.get("on", True)),
                     "once": bool(a.get("once", False)), "anim": 1.0 if a.get("on", True) else 0.0} for a in data]
        except (OSError, ValueError, KeyError, TypeError):
            return []

    def save_alarms(self):
        self.alarms.sort(key=lambda a: (a["h"], a["m"]))
        try:
            with open(ALARM_FILE, "w", encoding="utf-8") as f:
                json.dump([{k: a[k] for k in ("h", "m", "on", "once")} for a in self.alarms], f, indent=2)
        except OSError:
            pass

    def fmt_hm(self, h, m):
        if self.h24:
            return f"{h:02d}:{m:02d}"
        return f"{h % 12 or 12:02d}:{m:02d} {'AM' if h < 12 else 'PM'}"

    def until(self, a):
        n = self.now
        tgt = n.replace(hour=a["h"], minute=a["m"], second=0, microsecond=0)
        if tgt <= n:
            tgt += dt.timedelta(days=1)
        return (tgt - n).total_seconds()

    def next_alarm(self):
        on = [a for a in self.alarms if a["on"]]
        return min(on, key=self.until) if on else None

    def adj_new(self, unit, d):
        if unit == "h":
            self.new_h = (self.new_h + d) % 24
        else:
            self.new_m = (self.new_m + d) % 60

    def add_alarm(self, h=None, m=None, once=False):
        h = self.new_h if h is None else h
        m = self.new_m if m is None else m
        if any(a["h"] == h and a["m"] == m and a["once"] == once for a in self.alarms):
            self.toast("Ya existe una alarma a esa hora")
            return
        self.alarms.append({"h": h, "m": m, "on": True, "once": once, "anim": 0.0})
        self.save_alarms()
        a = {"h": h, "m": m}
        self.toast(f"Alarma creada para las {self.fmt_hm(h, m)}  ·  suena en {fmt_dur(self.until(a))}")

    def quick_alarm(self, mins):
        t = self.now + dt.timedelta(minutes=mins)
        self.add_alarm(t.hour, t.minute, once=True)

    def toggle_alarm(self, a):
        a["on"] = not a["on"]
        self.save_alarms()

    def del_alarm(self, a):
        self.alarms = [x for x in self.alarms if x is not a]
        self.save_alarms()

    def check_alarms(self, n):
        if self.ringing:
            return
        for a in self.alarms:
            if a["on"] and a["h"] == n.hour and a["m"] == n.minute:
                self.ringing, self.ring_t0 = a, time.time()
                self.sound.alarm_start()
                self.flash = 1.0
                if a["once"]:
                    a["on"] = False
                break

    def stop_alarm(self, snooze=False):
        a = self.ringing
        if a is None:
            return
        self.ringing = None
        self.sound.alarm_stop()
        if a["once"]:
            self.alarms = [x for x in self.alarms if x is not a]
        if snooze:
            t = self.now + dt.timedelta(minutes=5)
            self.alarms.append({"h": t.hour, "m": t.minute, "on": True, "once": True, "anim": 0.0})
            self.toast(f"Pospuesta hasta las {self.fmt_hm(t.hour, t.minute)}")
        self.save_alarms()

    def arrow(self, x, y, up, cb, P):
        s = 15
        hv = self.hov(x - 30, y - 18, x + 30, y + 18)
        col = P["a1"] if hv else mix(P["a1"], P["bg"], .5)
        if up:
            pts = (x - s, y + s * .5, x + s, y + s * .5, x, y - s * .6)
        else:
            pts = (x - s, y - s * .5, x + s, y - s * .5, x, y + s * .6)
        if hv:
            self.cv.create_polygon(pts, fill="", outline=mix(col, P["bg"], .6), width=6, joinstyle="round")
        self.cv.create_polygon(pts, fill=col, outline="")
        self.btns.append((x - 30, y - 18, x + 30, y + 18, cb))

    def draw_alarmas(self, P, top):
        cv, W, H, bg = self.cv, self.W, self.H, P["bg"]
        lw = min(440, W * .38)
        lx, ly, lh = 40, top + 26, H - top - 70
        self.panel(lx, ly, lw, lh, "NUEVA ALARMA", P)
        cx = lx + lw / 2
        dsz = min(96, lw * .22)
        dy = ly + 80 + dsz * .9
        fm = self.F(dsz, "bold", True)
        hh = self.new_h if self.h24 else (self.new_h % 12 or 12)
        wpair, wcol = self.measure(fm, "00"), self.measure(fm, ":")
        xh, xm = cx - wcol / 2 - wpair / 2, cx + wcol / 2 + wpair / 2
        self.gtext(xh, dy, f"{hh:02d}", fm, P["txt"], bg, glow_col=P["a1"])
        self.gtext(cx, dy, ":", fm, P["a2"], bg, glow=1)
        self.gtext(xm, dy, f"{self.new_m:02d}", fm, P["txt"], bg, glow_col=P["a1"])
        for x, unit, step in ((xh, "h", 1), (xm, "m", 5)):
            self.arrow(x, dy - dsz * .78, True, lambda u=unit: self.adj_new(u, 1), P)
            self.arrow(x, dy + dsz * .78, False, lambda u=unit: self.adj_new(u, -1), P)
            self.wheels.append((x - wpair / 2 - 10, dy - dsz / 2, x + wpair / 2 + 10, dy + dsz / 2,
                                lambda d, u=unit, st=step: self.adj_new(u, d * st)))
        if not self.h24:
            cv.create_text(cx + wcol / 2 + wpair + 16, dy, text="AM" if self.new_h < 12 else "PM", anchor="w",
                           font=self.F(18, "bold"), fill=P["a3"])
        cv.create_text(cx, dy + dsz * .78 + 34, font=self.F(13), fill=P["dim"],
                       text=f"Sonaría en {fmt_dur(self.until({'h': self.new_h, 'm': self.new_m}))}")
        by = dy + dsz * .78 + 62
        self.button(lx + 30, by, lw - 60, 50, "+  AGREGAR ALARMA", self.add_alarm, P, px=16)
        qy = by + 90
        cv.create_text(lx + 30, qy, text="ALARMA RÁPIDA", anchor="w", font=self.F(13, "bold"), fill=P["a2"])
        qw = (lw - 60 - 3 * 10) / 4
        for i, (lab, mins) in enumerate((("+5 min", 5), ("+10 min", 10), ("+30 min", 30), ("+1 h", 60))):
            self.button(lx + 30 + i * (qw + 10), qy + 20, qw, 40, lab, lambda mm=mins: self.quick_alarm(mm), P,
                        col=P["a2"], px=13)
        nxt = self.next_alarm()
        ny = qy + 100
        if nxt and ly + lh - ny > 150:  # cuenta regresiva hasta la próxima alarma
            cv.create_line(lx + 30, ny, lx + lw - 30, ny, fill=mix(P["a1"], bg, .8))
            cv.create_text(lx + 30, ny + 26, text="PRÓXIMA ALARMA", anchor="w", font=self.F(13, "bold"), fill=P["a1"])
            cv.create_text(lx + lw - 30, ny + 26, text=self.fmt_hm(nxt["h"], nxt["m"]), anchor="e",
                           font=self.F(14, "bold", True), fill=P["txt"])
            left = int(self.until(nxt))
            h, r = divmod(left, 3600)
            self.gtext(cx, ny + 80, f"{h:02d}:{r // 60:02d}:{r % 60:02d}", self.F(min(56, lw * .13), "bold", True),
                       P["txt"], bg, glow_col=P["a2"])
            self.seg_bar(lx + 30, ny + 120, lw - 60, 8, 1 - left / 86400, P, n=30)

        rx = lx + lw + 26
        rw = W - 40 - rx
        self.panel(rx, ly, rw, lh, f"MIS ALARMAS  ({len(self.alarms)})", P, P["a2"])
        if not self.alarms:
            cv.create_text(rx + rw / 2, ly + lh / 2, justify="center", font=self.F(15), fill=P["dim"],
                           text="Aún no tienes alarmas.\nCrea una en el panel de la izquierda.")
            return
        nxt = self.next_alarm()
        rowh = 68
        ry = ly + 64
        rows = max(1, int((lh - 90) / rowh))
        for a in self.alarms[:rows]:
            a["anim"] += ((1.0 if a["on"] else 0.0) - a["anim"]) * .25
            is_next = a is nxt
            x1, x2 = rx + 20, rx + rw - 20
            self.rrect(x1, ry, x2, ry + rowh - 12, 14, fill=mix(P["bg2"], P["a1"] if is_next else bg, .1 if is_next else .3),
                       outline=P["a1"] if is_next else mix(P["a2"], bg, .8), width=2 if is_next else 1)
            mid = ry + (rowh - 12) / 2
            tc = mix(P["txt"], bg, .6 * (1 - a["anim"]))
            cv.create_text(x1 + 20, mid, text=self.fmt_hm(a["h"], a["m"]), anchor="w", font=self.F(30, "bold", True),
                           fill=tc)
            sub = "Una vez" if a["once"] else "Todos los días"
            sub += f"  ·  suena en {fmt_dur(self.until(a))}" if a["on"] else "  ·  desactivada"
            tw = self.measure(self.F(30, "bold", True), self.fmt_hm(a["h"], a["m"]))
            cv.create_text(x1 + 40 + tw, mid, text=sub, anchor="w", font=self.F(13),
                           fill=P["a1"] if is_next else P["dim"])
            # interruptor animado
            sx, sw_, sh = x2 - 130, 56, 28
            self.rrect(sx, mid - sh / 2, sx + sw_, mid + sh / 2, sh / 2, fill=mix(mix(P["dim"], bg, .5), P["a1"], a["anim"]),
                       outline="")
            kx = sx + sh / 2 + (sw_ - sh) * a["anim"]
            cv.create_oval(kx - 11, mid - 11, kx + 11, mid + 11, fill=P["txt"], outline="")
            self.btns.append((sx - 4, mid - 18, sx + sw_ + 4, mid + 18, lambda al=a: self.toggle_alarm(al)))
            # borrar
            dx = x2 - 38
            hv = self.hov(dx - 18, mid - 18, dx + 18, mid + 18)
            cv.create_oval(dx - 16, mid - 16, dx + 16, mid + 16, fill=mix(P["a2"], bg, .7 if hv else .92),
                           outline=P["a2"] if hv else mix(P["a2"], bg, .6))
            cv.create_text(dx, mid - 1, text="×", font=self.F(20, "bold"), fill=P["txt"] if hv else P["a2"])
            self.btns.append((dx - 18, mid - 18, dx + 18, mid + 18, lambda al=a: self.del_alarm(al)))
            ry += rowh
        if len(self.alarms) > rows:
            cv.create_text(rx + rw / 2, ly + lh - 20, text=f"+ {len(self.alarms) - rows} más", font=self.F(13),
                           fill=P["dim"])

    def draw_alarm(self, T):
        """Ventana de alarma sonando (encima de todo)."""
        cv, W, H, bg = self.cv, self.W, self.H, T["bg"]
        self.btns = []
        self.block = False
        el = self.now_ts - self.ring_t0
        pulse = .5 + .5 * math.sin(el * 7)
        # fondo sólido que late (la trama "stipple" de Tk es lentísima en Windows)
        cv.create_rectangle(0, 0, W, H, fill=mix(bg, T["a2"], .05 + .05 * pulse), outline="")
        cx, cy = W / 2, H / 2
        for i in range(20):  # rayos girando detrás del panel
            a = el * .4 + i / 10 * math.pi
            cv.create_line(cx, cy, cx + math.cos(a) * W, cy + math.sin(a) * W, fill=mix(T["a2"], bg, .9), width=2)
        for k in range(4):
            r = ((el * 140 + k * 110) % 440) + 60
            cv.create_oval(cx - r, cy - r, cx + r, cy + r, outline=mix(T["a2"], bg, r / 520), width=3)
        if random.random() < .15:
            self.burst(random.uniform(W * .2, W * .8), random.uniform(H * .2, H * .8), 14)
        shake = math.sin(el * 50) * 6 * max(0.0, 1 - (el % 2.0) * 2)
        pw, ph = 540, 340
        x, y = cx - pw / 2 + shake, cy - ph / 2
        self.rrect(x - 7, y - 7, x + pw + 7, y + ph + 7, 28, fill="", outline=mix(T["a2"], bg, .4 + .5 * (1 - pulse)),
                   width=7)
        self.rrect(x, y, x + pw, y + ph, 24, fill=T["bg2"], outline=T["a2"], width=3)
        a = self.ringing
        self.gtext(cx + shake, y + 48, "¡ ALARMA !", self.F(30, "bold"), mix(T["a2"], T["txt"], pulse * .5), bg, glow=2)
        self.gtext(cx + shake, y + 140, self.fmt_hm(a["h"], a["m"]), self.F(96, "bold", True), T["txt"], T["bg2"],
                   glow_col=T["a1"])
        cv.create_text(cx + shake, y + 214, text=frase_hora(a["h"], a["m"]), font=self.F(15, "italic"),
                       fill=mix(T["txt"], bg, .3))
        bw = 200
        self.button(cx - bw - 10, y + ph - 82, bw, 52, "DETENER  (Esc)", self.stop_alarm, T, col=T["a2"], active=True)
        self.button(cx + 10, y + ph - 82, bw, 52, "POSPONER 5 MIN  (P)", lambda: self.stop_alarm(True), T, px=13)

    # ───────── 6. BINARIO ─────────

    def draw_binario(self, P, top):
        cv, W, H, bg, n, t = self.cv, self.W, self.H, P["bg"], self.now, self.now_ts
        digits = [n.hour // 10, n.hour % 10, n.minute // 10, n.minute % 10, n.second // 10, n.second % 10]
        maxb = [2, 4, 3, 4, 3, 4]
        cols = [P["a1"], P["a1"], P["a2"], P["a2"], P["a3"], P["a3"]]
        r = max(15, min((H - top) * .043, W * .027))
        sp, gg = r * 3, r * 2.4
        xs, x = [], 0.0
        for c in range(6):
            xs.append(x)
            x += sp + (gg if c in (1, 3) else 0)
        ox = W / 2 - xs[-1] / 2
        xs = [ox + v for v in xs]
        ys = [top + 76 + r * 2.2 + k * sp for k in range(4)]

        for i, name in enumerate(("HORAS", "MINUTOS", "SEGUNDOS")):
            gx = (xs[2 * i] + xs[2 * i + 1]) / 2
            cv.create_text(gx, top + 40, text=name, font=self.F(15, "bold"), fill=cols[2 * i])
            cv.create_line(xs[2 * i] - r, top + 58, xs[2 * i + 1] + r, top + 58, fill=mix(cols[2 * i], bg, .6), width=2)
        for k in range(4):
            cv.create_text(xs[0] - r * 2.4, ys[k], text=str(8 >> k), font=self.F(16, "bold", True), fill=P["dim"])

        leds = []
        for c in range(6):
            for k in range(4):
                bit = 8 >> k
                if bit >= 2 ** maxb[c]:
                    continue
                on = bool(digits[c] & bit)
                prev = self.bin_state.get((c, k))
                if prev is None or prev[0] != on:
                    self.bin_state[(c, k)] = (on, t)
                    if on and prev is not None:
                        for _ in range(8):
                            self.spark(xs[c], ys[k], cols[c], speed=3, life=30)
                leds.append((xs[c], ys[k], on, cols[c], t - self.bin_state[(c, k)][1]))
        for lx, ly, on, col, age in leds:  # primero todos los halos…
            if on:
                boost = max(0.0, 1 - age / .5)
                for f, k in ((1.75, .9), (1.45, .8), (1.2, .6)):
                    rr = r * (1 + .25 * boost) * f
                    cv.create_oval(lx - rr, ly - rr, lx + rr, ly + rr, fill=mix(col, bg, k - .12 * boost), outline="")
        for lx, ly, on, col, age in leds:  # …luego los LEDs encima
            if on:
                rr = r * (1 + .25 * max(0.0, 1 - age / .5))
                cv.create_oval(lx - rr, ly - rr, lx + rr, ly + rr, fill=col, outline=mix(col, "#ffffff", .5), width=2)
                cv.create_oval(lx - r * .6, ly - r * .6, lx - r * .05, ly - r * .05, fill=mix(col, "#ffffff", .6),
                               outline="")
            else:
                cv.create_oval(lx - r, ly - r, lx + r, ly + r, fill=mix(P["bg2"], bg, .3), outline=mix(col, bg, .65),
                               width=2)
        dy = ys[-1] + r * 2.3
        for c in range(6):
            cv.create_text(xs[c], dy, text=str(digits[c]), font=self.F(r * 1.1, "bold", True), fill=P["txt"])

        iy = dy + r * 1.6 + 10
        fi = self.F(16, mono=True)
        cv.create_text(W / 2, iy, font=fi, fill=mix(P["txt"], bg, .2),
                       text=f"Binario puro   {n.hour:05b} : {n.minute:06b} : {n.second:06b}")
        cv.create_text(W / 2, iy + 28, font=fi, fill=mix(P["txt"], bg, .2),
                       text=f"Hexadecimal    0x{n.hour:02X} : 0x{n.minute:02X} : 0x{n.second:02X}")
        ts = int(t)
        cv.create_text(W / 2, iy + 66, font=self.F(14, "bold"), fill=P["a1"],
                       text=f"TIMESTAMP UNIX  ·  {ts:,} segundos desde 1970".replace(",", "."))
        bits = f"{ts & 0xFFFFFFFF:032b}"
        q = min(18.0, (W - 160) / 32 - 4)
        bx0 = W / 2 - (32 * (q + 4) - 4) / 2
        by0 = iy + 86
        for i, b in enumerate(bits):
            x1 = bx0 + i * (q + 4)
            if b == "1":
                c = mix(P["a1"], P["a2"], i / 31)
                cv.create_rectangle(x1 - 2, by0 - 2, x1 + q + 2, by0 + q + 2, fill=mix(c, bg, .7), outline="")
                cv.create_rectangle(x1, by0, x1 + q, by0 + q, fill=c, outline="")
            else:
                cv.create_rectangle(x1, by0, x1 + q, by0 + q, fill="", outline=mix(P["dim"], bg, .4))

    # ───────── entrada ─────────

    def set_mode(self, key):
        if key != self.mode:
            self.mode = key
            self.mode_t0 = time.time()

    def next_theme(self):
        self.theme_from = dict(self.T)
        self.ti = (self.ti + 1) % len(THEMES)
        self.theme_to = THEMES[self.ti]
        self.theme_t0 = time.time()
        self.toast(f"Tema: {self.theme_to['name']}")

    def toggle_sound(self):
        self.sound.on = not self.sound.on
        self.toast("Sonido activado" if self.sound.on else "Sonido silenciado")

    def on_resize(self, e):
        self.W, self.H = max(e.width, 200) / self.S, max(e.height, 200) / self.S

    def on_motion(self, e):
        self.mx, self.my = (e.x / self.S, e.y / self.S) if e else (-1000, -1000)

    def on_click(self, e):
        x, y = e.x / self.S, e.y / self.S
        for x1, y1, x2, y2, cb in reversed(self.btns):
            if x1 <= x <= x2 and y1 <= y <= y2:
                cb()
                for _ in range(8):
                    self.spark(x, y, self.T["a1"], speed=3, life=25, size=2)
                return
        if not self.ringing:
            self.burst(x, y)

    def on_wheel(self, e, d=None):
        if d is None:
            d = 1 if e.delta > 0 else -1
        x, y = e.x / self.S, e.y / self.S
        for x1, y1, x2, y2, cb in self.wheels:
            if x1 <= x <= x2 and y1 <= y <= y2:
                cb(d)
                return

    def on_key(self, e):
        k = e.keysym.lower()
        if self.ringing:
            if k in ("escape", "space", "return"):
                self.stop_alarm()
            elif k == "p":
                self.stop_alarm(snooze=True)
            return
        keys = [key for key, _ in self.TABS]
        if k in "123456" and len(k) == 1:
            self.set_mode(keys[int(k) - 1])
        elif k in ("right", "left"):
            self.set_mode(keys[(keys.index(self.mode) + (1 if k == "right" else -1)) % len(keys)])
        elif k == "t":
            self.next_theme()
        elif k == "m":
            self.toggle_sound()
        elif k == "c":
            self.chime = not self.chime
            self.toast("Campanada horaria " + ("activada" if self.chime else "desactivada"))
        elif k == "h":
            self.h24 = not self.h24
            self.toast("Formato 24 horas" if self.h24 else "Formato 12 horas (AM/PM)")
        elif k == "z":
            self.zen = not self.zen
            if self.zen:
                self.set_mode("reloj")
            self.toast("Modo zen · pulsa Z para salir" if self.zen else "Modo normal")
        elif k in ("f", "f11"):
            self.fullscreen = not self.fullscreen
            self.root.attributes("-fullscreen", self.fullscreen)
        elif k == "escape":
            if self.fullscreen:
                self.fullscreen = False
                self.root.attributes("-fullscreen", False)
            elif self.zen:
                self.zen = False
        elif k == "space":
            if self.mode == "crono":
                self.sw_toggle()
            elif self.mode == "pomo":
                self.pomo_toggle()
            elif self.clock_c:
                self.burst(*self.clock_c[:2], 40)
        elif k == "l" and self.mode == "crono":
            self.sw_lap()
        elif k == "r":
            if self.mode == "crono":
                self.sw_reset()
            elif self.mode == "pomo":
                self.pomo_reset()
        elif k == "s" and self.mode == "pomo":
            self.pomo_skip()
        elif k == "return" and self.mode == "alarmas":
            self.add_alarm()

    def on_close(self):
        self.sound.alarm_stop()
        self.save_alarms()
        self.root.destroy()


def main():
    try:  # nitidez en pantallas HiDPI de Windows
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    Chronos(root)
    root.mainloop()


if __name__ == "__main__":
    main()
