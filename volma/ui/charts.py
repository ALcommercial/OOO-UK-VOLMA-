import tkinter as tk

from .theme import BORDER, FONT_S, MUTED, PANEL, TEXT

AXIS = "#C3CBD6"


class Chart(tk.Canvas):
    def __init__(self, parent, height=220, **kw):
        super().__init__(parent, bg=PANEL, highlightthickness=0, height=height, **kw)
        self._draw = None
        self.bind("<Configure>", lambda e: self._draw and self._draw())

    def bars(self, labels, series, colors, names=None, fmt=lambda v: f"{v:,.0f}".replace(",", " "), horizontal=False):
        self._draw = lambda: self._bars(labels, series, colors, names, fmt, horizontal)
        self._draw()

    def line(self, xs, ys_list, colors, names=None, ylabel="", xfmt=str, band=None):
        self._draw = lambda: self._line(xs, ys_list, colors, names, ylabel, xfmt, band)
        self._draw()

    def _empty(self, w, h, text="Нет данных"):
        self.create_text(w / 2, h / 2, text=text, fill=MUTED, font=FONT_S)

    def _legend(self, names, colors, w):
        if not names:
            return 0
        x = 10
        for n, c in zip(names, colors):
            self.create_rectangle(x, 8, x + 12, 20, fill=c, outline="")
            t = self.create_text(x + 18, 14, text=n, anchor="w", fill=TEXT, font=FONT_S)
            x = self.bbox(t)[2] + 16
        return 22

    def _bars(self, labels, series, colors, names, fmt, horizontal):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if not labels or w < 50:
            self._empty(w, h)
            return
        top = 10 + self._legend(names, colors, w)
        if horizontal:
            vals = series[0]
            lw = min(220, max(self._text_w(l) for l in labels) + 16)
            vmax = max(abs(v) for v in vals) or 1
            has_neg = any(v < 0 for v in vals)
            x0 = lw + (w - lw - 110) / 2 + 50 if has_neg else lw
            span = (w - lw - 110) / (2 if has_neg else 1)
            rh = (h - top - 6) / len(labels)
            for i, (lab, v) in enumerate(zip(labels, vals)):
                y = top + i * rh + rh / 2
                self.create_text(lw - 8, y, text=lab, anchor="e", fill=TEXT, font=FONT_S)
                L = span * abs(v) / vmax
                col = colors[0] if v >= 0 else (colors[1] if len(colors) > 1 else colors[0])
                bh = min(16, rh * 0.7)
                if v >= 0:
                    self.create_rectangle(x0, y - bh / 2, x0 + L, y + bh / 2, fill=col, outline="")
                    self.create_text(x0 + L + 4, y, text=fmt(v), anchor="w", fill=MUTED, font=FONT_S)
                else:
                    self.create_rectangle(x0 - L, y - bh / 2, x0, y + bh / 2, fill=col, outline="")
                    self.create_text(x0 - L - 4, y, text=fmt(v), anchor="e", fill=MUTED, font=FONT_S)
            self.create_line(x0, top, x0, h - 4, fill=AXIS)
            return
        left, bottom = 60, 34
        vmax = max(max(s) for s in series) or 1
        vmax *= 1.12
        ph = h - top - bottom
        pw = w - left - 12
        for k in range(5):
            y = top + ph - ph * k / 4
            self.create_line(left, y, w - 12, y, fill="#EEF1F5")
            self.create_text(left - 6, y, text=fmt(vmax * k / 4), anchor="e", fill=MUTED, font=FONT_S)
        n = len(labels)
        gw = pw / n
        bw = min(28, gw * 0.8 / len(series))
        for i, lab in enumerate(labels):
            cx = left + gw * i + gw / 2
            for j, s in enumerate(series):
                x = cx - bw * len(series) / 2 + j * bw
                y = top + ph - ph * s[i] / vmax
                self.create_rectangle(x + 1, y, x + bw - 1, top + ph, fill=colors[j], outline="")
            if n <= 30:
                self.create_text(cx, top + ph + 12, text=lab, fill=MUTED, font=FONT_S)
        self.create_line(left, top + ph, w - 12, top + ph, fill=AXIS)

    def _line(self, xs, ys_list, colors, names, ylabel, xfmt, band):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if not xs or w < 50:
            self._empty(w, h)
            return
        top = 10 + self._legend(names, colors, w)
        left, bottom = 50, 28
        allv = [v for ys in ys_list for v in ys]
        vmin = min(1.0, min(allv))
        vmax = max(allv) * 1.08
        ph = h - top - bottom
        pw = w - left - 12

        def P(i, v):
            return left + pw * i / max(1, len(xs) - 1), top + ph - ph * (v - vmin) / ((vmax - vmin) or 1)

        for k in range(5):
            v = vmin + (vmax - vmin) * k / 4
            y = top + ph - ph * k / 4
            self.create_line(left, y, w - 12, y, fill="#EEF1F5")
            self.create_text(left - 6, y, text=f"{v:.2f}", anchor="e", fill=MUTED, font=FONT_S)
        if band:
            for (a, b, col) in band:
                x1, _ = P(a, vmin)
                x2, _ = P(b, vmin)
                self.create_rectangle(x1, top, x2, top + ph, fill=col, outline="")
        for ys, col in zip(ys_list, colors):
            pts = []
            for i, v in enumerate(ys):
                pts.extend(P(i, v))
            if len(pts) >= 4:
                self.create_line(*pts, fill=col, width=2.5, smooth=True)
        for i, x in enumerate(xs):
            if i % max(1, len(xs) // 12) == 0:
                px, _ = P(i, vmin)
                self.create_text(px, top + ph + 12, text=xfmt(x), fill=MUTED, font=FONT_S)
        self.create_line(left, top + ph, w - 12, top + ph, fill=AXIS)
        if ylabel:
            self.create_text(left + 4, top + 2, text=ylabel, anchor="nw", fill=MUTED, font=FONT_S)

    def _text_w(self, s):
        t = self.create_text(0, 0, text=s, font=FONT_S)
        bx = self.bbox(t)
        self.delete(t)
        return bx[2] - bx[0]
