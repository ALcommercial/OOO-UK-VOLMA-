import sys


def enable_dpi():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def main():
    enable_dpi()
    from volma.ui.app import App
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
