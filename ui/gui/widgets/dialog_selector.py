import flet as ft


class DialogSelector(ft.UserControl):
    def __init__(self, tele_client, on_dialog_selected):
        super().__init__()
        self.client = tele_client
        self.on_dialog_selected = on_dialog_selected
        self.dialogs = []
        # Widget hiển thị danh sách
        self.list_view = ft.ListView(expand=True, spacing=5, padding=10)
        self.search_box = ft.TextField(
            label="Tìm kiếm nhóm/kênh...",
            on_change=self.filter_dialogs,
            prefix_icon=ft.icons.SEARCH
        )
        self.loading = ft.ProgressBar(visible=False)

    async def load_dialogs(self):
        self.loading.visible = True
        self.update()

        # Gọi hàm từ core/client.py
        self.dialogs = await self.client.get_dialogs(limit=50)

        self.loading.visible = False
        self.render_list(self.dialogs)
        self.update()

    def render_list(self, data):
        self.list_view.controls.clear()
        if not data:
            self.list_view.controls.append(ft.Text("Không tìm thấy đoạn chat nào."))

        for chat in data:
            icon = ft.icons.PERSON
            if chat['type'] == "Channel":
                icon = ft.icons.CAMPAIGN
            elif chat['type'] == "Group":
                icon = ft.icons.GROUPS

            self.list_view.controls.append(
                ft.ListTile(
                    leading=ft.Icon(icon),
                    title=ft.Text(chat['name']),
                    subtitle=ft.Text(f"{chat['type']}"),
                    on_click=lambda e, c=chat: self.select_chat(c),
                    bgcolor=ft.colors.with_opacity(0.1, ft.colors.WHITE)
                )
            )
        self.update()

    def filter_dialogs(self, e):
        search_term = self.search_box.value.lower()
        if not search_term:
            self.render_list(self.dialogs)
        else:
            filtered = [d for d in self.dialogs if search_term in d['name'].lower()]
            self.render_list(filtered)

    def select_chat(self, chat):
        self.on_dialog_selected(chat)

    def build(self):
        return ft.Container(
            height=400,
            border=ft.border.all(1, ft.colors.OUTLINE),
            border_radius=10,
            padding=10,
            content=ft.Column([
                self.search_box,
                self.loading,
                ft.Container(content=self.list_view, expand=True)
            ])
        )