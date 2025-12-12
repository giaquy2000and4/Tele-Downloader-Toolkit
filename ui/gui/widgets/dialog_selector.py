import flet as ft


class DialogSelector(ft.UserControl):
    def __init__(self, tele_client, on_dialog_selected, height=None):
        super().__init__()
        self.client = tele_client
        self.on_dialog_selected = on_dialog_selected
        self.dialogs = []
        self.selected_id = None

        if height is None:
            self.expand = True
        else:
            self.height = height

        self.list_view = ft.ListView(expand=True, spacing=2, padding=5)
        self.search_box = ft.TextField(
            hint_text="🔍 Tìm kiếm nhóm/kênh...",
            on_change=self.filter_dialogs,
            prefix_icon=ft.icons.SEARCH,
            height=40,
            text_size=14,
            content_padding=10
        )
        self.loading = ft.ProgressBar(visible=False, color="blue", height=2)
        self.status_text = ft.Text("", size=12, color="grey")

    async def load_dialogs(self):
        # --- SỬA LỖI TẠI ĐÂY: Xóa dòng kiểm tra cache cũ ---
        # if self.dialogs: return  <-- Đã xóa dòng này

        self.loading.visible = True
        self.status_text.value = "Đang tải danh sách mới nhất..."
        self.list_view.controls.clear()  # Xóa list cũ trên UI
        self.update()

        try:
            # Luôn lấy dữ liệu mới từ Telegram
            self.dialogs = await self.client.get_dialogs(limit=100)
            self.render_list(self.dialogs)
            self.status_text.value = f"Tìm thấy {len(self.dialogs)} kết quả."
        except Exception as e:
            self.status_text.value = f"Lỗi: {e}"

        self.loading.visible = False
        self.update()

    # ... (Các hàm render_list, handle_click, filter_dialogs, build GIỮ NGUYÊN) ...
    def render_list(self, data):
        self.list_view.controls.clear()
        if not data:
            self.list_view.controls.append(ft.Text("Không tìm thấy.", italic=True))

        for chat in data:
            icon = ft.icons.PERSON
            icon_color = ft.colors.BLUE_200
            if chat['type'] == "Channel":
                icon = ft.icons.CAMPAIGN;
                icon_color = ft.colors.ORANGE_200
            elif chat['type'] == "Group":
                icon = ft.icons.GROUPS;
                icon_color = ft.colors.GREEN_200

            is_selected = (self.selected_id == chat['id'])
            bg_color = ft.colors.BLUE_900 if is_selected else ft.colors.with_opacity(0.05, ft.colors.WHITE)

            self.list_view.controls.append(
                ft.Container(
                    content=ft.ListTile(
                        leading=ft.Icon(icon, color=icon_color),
                        title=ft.Text(chat['name'], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                                      weight="bold" if is_selected else "normal"),
                        subtitle=ft.Text(f"ID: {chat['id']}", size=10),
                        on_click=lambda e, c=chat: self.handle_click(c),
                        dense=True
                    ),
                    bgcolor=bg_color,
                    border=ft.border.all(1, ft.colors.BLUE) if is_selected else None,
                    border_radius=5,
                    margin=ft.margin.only(bottom=2)
                )
            )
        self.update()

    def handle_click(self, chat):
        self.selected_id = chat['id']
        self.on_dialog_selected(chat)
        self.filter_dialogs(None)

    def filter_dialogs(self, e):
        search_term = self.search_box.value.lower() if self.search_box.value else ""
        if not search_term:
            self.render_list(self.dialogs)
        else:
            filtered = [d for d in self.dialogs if search_term in d['name'].lower()]
            self.render_list(filtered)

    def build(self):
        return ft.Container(
            border=ft.border.all(1, ft.colors.OUTLINE),
            border_radius=10,
            padding=10,
            content=ft.Column([
                self.search_box,
                self.loading,
                self.status_text,
                self.list_view
            ])
        )