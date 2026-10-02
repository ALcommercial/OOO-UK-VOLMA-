import tkinter as tk
from tkinter import ttk

BG = "#F3F5F8"
PANEL = "#FFFFFF"
HEADER = "#14213D"
HEADER_2 = "#1F3263"
ACCENT = "#C8102E"
ACCENT_DARK = "#9E0C24"
TEXT = "#1B2430"
MUTED = "#6B7685"
BORDER = "#DDE2EA"
GOOD = "#1E9E5A"
WARN = "#E39B17"
BAD = "#D6342C"
BLUE = "#2563EB"
MAP_BG = "#EEF2F6"
MAP_GRID = "#DCE3EB"

FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI Semibold", 10)
FONT_S = ("Segoe UI", 9)
FONT_H1 = ("Segoe UI Semibold", 16)
FONT_H2 = ("Segoe UI Semibold", 12)
FONT_KPI = ("Segoe UI Semibold", 20)


def setup_style(root):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    root.configure(bg=BG)
    root.option_add("*Font", FONT)
    root.option_add("*TCombobox*Listbox.font", FONT)
    style.configure(".", background=BG, foreground=TEXT, font=FONT, bordercolor=BORDER)
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Panel.TLabel", background=PANEL)
    style.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=FONT_S)
    style.configure("H1.TLabel", font=FONT_H1, background=BG)
    style.configure("H2.TLabel", font=FONT_H2, background=PANEL)
    style.configure("H2bg.TLabel", font=FONT_H2, background=BG)
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(8, 6, 8, 0))
    style.configure("TNotebook.Tab", padding=(16, 8), font=FONT_B, background="#E4E8EF", foreground=MUTED, borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", ACCENT)])
    style.configure("TButton", padding=(12, 6), background="#E8ECF2", foreground=TEXT, borderwidth=1, focusthickness=0)
    style.map("TButton", background=[("active", "#DCE2EA")])
    style.configure("Accent.TButton", background=ACCENT, foreground="white", borderwidth=0, font=FONT_B)
    style.map("Accent.TButton", background=[("active", ACCENT_DARK), ("disabled", "#E3A3AE")])
    style.configure("Treeview", rowheight=26, background=PANEL, fieldbackground=PANEL, borderwidth=0, font=FONT)
    style.configure("Treeview.Heading", font=FONT_B, background="#EEF1F6", foreground=TEXT, relief="flat", padding=(6, 6))
    style.map("Treeview", background=[("selected", "#DCE7FB")], foreground=[("selected", TEXT)])
    style.configure("TLabelframe", background=PANEL, bordercolor=BORDER)
    style.configure("TLabelframe.Label", background=PANEL, font=FONT_B, foreground=TEXT)
    style.configure("TCheckbutton", background=PANEL)
    style.configure("TRadiobutton", background=PANEL)
    style.configure("Bg.TCheckbutton", background=BG)
    style.configure("TEntry", padding=4)
    style.configure("TCombobox", padding=4)
    style.configure("TSpinbox", padding=4)
    style.configure("Horizontal.TScale", background=PANEL)
    return style


class Card(tk.Frame):
    def __init__(self, parent, title=None, pad=14, **kw):
        super().__init__(parent, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, **kw)
        self.body = tk.Frame(self, bg=PANEL)
        if title:
            tk.Label(self, text=title, bg=PANEL, fg=TEXT, font=FONT_H2, anchor="w").pack(fill="x", padx=pad, pady=(pad - 2, 4))
            self.body.pack(fill="both", expand=True, padx=pad, pady=(0, pad))
        else:
            self.body.pack(fill="both", expand=True, padx=pad, pady=pad)


class Kpi(tk.Frame):
    def __init__(self, parent, title, value="—", sub="", color=TEXT):
        super().__init__(parent, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        tk.Frame(self, bg=color, width=4).pack(side="left", fill="y")
        inner = tk.Frame(self, bg=PANEL)
        inner.pack(side="left", fill="both", expand=True, padx=12, pady=10)
        tk.Label(inner, text=title, bg=PANEL, fg=MUTED, font=FONT_S, anchor="w").pack(fill="x")
        self.value = tk.Label(inner, text=value, bg=PANEL, fg=TEXT, font=FONT_KPI, anchor="w")
        self.value.pack(fill="x")
        self.sub = tk.Label(inner, text=sub, bg=PANEL, fg=MUTED, font=FONT_S, anchor="w", justify="left")
        self.sub.pack(fill="x")

    def set(self, value, sub=None, color=None):
        self.value.configure(text=value)
        if sub is not None:
            self.sub.configure(text=sub)
        if color:
            self.value.configure(fg=color)


def make_tree(parent, columns, height=12, stretch=None):
    frame = tk.Frame(parent, bg=PANEL)
    tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", height=height, selectmode="browse")
    vs = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vs.set)
    for key, title, width, anchor in columns:
        tree.heading(key, text=title, command=lambda k=key: sort_tree(tree, k, False))
        tree.column(key, width=width, anchor=anchor, stretch=(stretch is None or key in stretch))
    tree.grid(row=0, column=0, sticky="nsew")
    vs.grid(row=0, column=1, sticky="ns")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    tree.tag_configure("bad", foreground=BAD)
    tree.tag_configure("good", foreground=GOOD)
    tree.tag_configure("warn", foreground="#A86C00")
    tree.tag_configure("muted", foreground=MUTED)
    tree.tag_configure("bold", font=FONT_B)
    tree.tag_configure("odd", background="#F8FAFC")
    return frame, tree


def _key(v):
    s = str(v).replace(" ", "").replace("₽", "").replace("%", "").replace(",", ".").replace(" ", "")
    try:
        return (0, float(s))
    except ValueError:
        return (1, str(v).lower())


def sort_tree(tree, col, reverse):
    items = [(tree.set(k, col), k) for k in tree.get_children("")]
    items.sort(key=lambda t: _key(t[0]), reverse=reverse)
    for i, (_, k) in enumerate(items):
        tree.move(k, "", i)
    tree.heading(col, command=lambda: sort_tree(tree, col, not reverse))


def fill_tree(tree, rows, tags=None):
    tree.delete(*tree.get_children())
    for i, row in enumerate(rows):
        iid, values = row[0], row[1:]
        t = list(tags[i]) if tags else []
        tree.insert("", "end", iid=str(iid), values=values, tags=t)


def form_row(parent, r, label, widget, bg=PANEL):
    tk.Label(parent, text=label, bg=bg, fg=MUTED, font=FONT_S, anchor="w").grid(row=r, column=0, sticky="w", pady=4, padx=(0, 10))
    widget.grid(row=r, column=1, sticky="ew", pady=4)
    parent.columnconfigure(1, weight=1)
    return widget


def congestion_color(c):
    if c < 1.15:
        return GOOD
    if c < 1.4:
        return WARN
    return BAD
