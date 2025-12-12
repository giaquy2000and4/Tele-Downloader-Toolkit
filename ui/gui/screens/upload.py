import flet as ft
import os
from core.uploader import Uploader
from ui.gui.widgets.dialog_selector import DialogSelector
from utils.progress import ProgressTracker


class UploadScreen:
    def __init__(self, page, tele_client):
        self.page = page
        self.client = tele_client.get_client()
        self.tele_client_wrapper = tele_client
        self.uploader = Uploader(self.client)
        self.selected_chat = None
        self.file_paths = []  # Đổi thành list

        # allow_multiple=True để chọn nhiều file
        self.file_picker = ft.FilePicker(on_result=self.on_file_picked)
        self.page.overlay.append(self.file_picker)

        self.btn_select_file = ft.ElevatedButton("Chọn File (Nhiều)", icon=ft.icons.UPLOAD_FILE,
                                                 on_click=lambda _: self.file_picker.pick_files(allow_multiple=True))
        self.file_list_view = ft.ListView(height=100, spacing=5)  # List hiển thị file đã chọn
        self.lbl_chat = ft.Text("Chưa chọn nơi gửi", italic=True, color="yellow")

        self.dialog_selector = DialogSelector(self.tele_client_wrapper, self.on_chat_selected, height=300)
        self.progress_bar = ft.ProgressBar(value=0, visible=False)
        self.status = ft.Text("")

    def on_file_picked(self, e: ft.FilePickerResultEvent):
        if e.files:
            self.file_paths = [f.path for f in e.files]
            # Hiển thị danh sách file
            self.file_list_view.controls = [
                ft.Text(f"📄 {f.name}", size=12) for f in e.files
            ]
            self.status.value = f"Đã chọn {len(self.file_paths)} files."
            self.page.update()

    def on_chat_selected(self, chat):
        self.selected_chat = chat
        self.lbl_chat.value = f"✅ Gửi tới: {chat['name']}"
        self.lbl_chat.color = "green"
        self.lbl_chat.weight = "bold"
        self.page.update()

    async def start_upload(self, e):
        if not self.file_paths:
            self.status.value = "❌ Chưa chọn file!";
            self.page.update();
            return
        if not self.selected_chat:
            self.status.value = "❌ Chưa chọn nơi gửi!";
            self.page.update();
            return

        self.progress_bar.visible = True
        total_files = len(self.file_paths)

        for idx, file_path in enumerate(self.file_paths):
            file_name = os.path.basename(file_path)
            self.status.value = f"Đang upload ({idx + 1}/{total_files}): {file_name}..."
            self.page.update()

            tracker = ProgressTracker(self.update_progress)
            try:
                await self.uploader.upload_file(
                    self.selected_chat['entity'],
                    file_path,
                    progress_callback=tracker.callback
                )
            except Exception as ex:
                self.status.value = f"❌ Lỗi file {file_name}: {ex}"
                self.page.update()
                # Tùy chọn: break hoặc continue để upload file tiếp theo

        self.status.value = "✅ Đã upload hoàn tất tất cả file!"
        self.status.color = "green"
        self.progress_bar.visible = False
        self.page.update()

    def update_progress(self, pct, msg):
        self.progress_bar.value = pct
        self.page.update()

    def get_view(self):
        btn_load = ft.ElevatedButton("Tải danh sách nhóm", icon=ft.icons.REFRESH,
                                     on_click=lambda _: self.page.run_task(self.dialog_selector.load_dialogs))

        return ft.Column([
            ft.Text("Upload Media (Multi-files)", size=20, weight="bold"),
            ft.Divider(),
            ft.Container(
                padding=10,
                border=ft.border.all(1, "grey"), border_radius=10,
                content=ft.Column([
                    self.btn_select_file,
                    ft.Text("Danh sách file:", weight="bold"),
                    ft.Container(content=self.file_list_view, bgcolor=ft.colors.BLACK12, padding=5, border_radius=5)
                ])
            ),
            ft.Divider(height=20, color="transparent"),
            ft.Row([ft.Text("Chọn nơi gửi:", weight="bold"), btn_load], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            self.dialog_selector,
            ft.Row([ft.Icon(ft.icons.CHECK_CIRCLE, color="green"), self.lbl_chat]),
            ft.Divider(),
            ft.ElevatedButton("BẮT ĐẦU UPLOAD", on_click=self.start_upload, bgcolor="blue", color="white", width=200),
            self.status,
            self.progress_bar
        ], scroll=ft.ScrollMode.AUTO, expand=True)