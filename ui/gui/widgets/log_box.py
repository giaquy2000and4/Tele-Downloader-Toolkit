import flet as ft

class LogBox(ft.UserControl):
    def __init__(self):
        super().__init__()
        self.text_view = ft.ListView(expand=True, spacing=10, auto_scroll=True)

    def log(self, message, color="white"):
        self.text_view.controls.append(ft.Text(message, color=color, size=12))
        self.update()

    def build(self):
        return ft.Container(
            content=self.text_view,
            height=150,
            bgcolor=ft.colors.BLACK12,
            border_radius=10,
            padding=10
        )