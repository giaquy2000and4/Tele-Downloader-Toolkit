import flet as ft
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
        self.file_path = None

        self.file_picker = ft.FilePicker(on_result=self.on_file_picked)
        self.page.overlay.append(self.file_picker)

        self.btn_select_file = ft.ElevatedButton("Chọn File", icon=ft.icons.UPLOAD_FILE,
                                                 on_click=lambda _: self.file_picker.pick_files())
        self.lbl_file = ft.Text("Chưa chọn file", italic=True)
        self.lbl_chat = ft.Text("Chưa chọn nơi gửi", italic=True, color="yellow")

        # Upload: Truyền height cố định => Không expand => Không vỡ layout
        self.dialog_selector = DialogSelector(self.tele_client_wrapper, self.on_chat_selected, height=300)

        self.progress_bar = ft.ProgressBar(value=0, visible=False)
        self.status = ft.Text("")

    def on_file_picked(self, e: ft.FilePickerResultEvent):
        if e.files:
            self.file_path = e.files[0].path
            self.lbl_file.value = f"File: {e.files[0].name}"
            self.lbl_file.weight = "bold"
            self.page.update()

    def on_chat_selected(self, chat):
        self.selected_chat = chat
        self.lbl_chat.value = f"✅ Gửi tới: {chat['name']}"
        self.lbl_chat.color = "green"
        self.lbl_chat.weight = "bold"
        self.page.update()

    async def start_upload(self, e):
        if not self.file_path:
            self.status.value = "❌ Chưa chọn file!";
            self.page.update();
            return
        if not self.selected_chat:
            self.status.value = "❌ Chưa chọn nơi gửi!";
            self.page.update();
            return

        self.progress_bar.visible = True
        self.status.value = "Đang upload..."
        self.page.update()

        tracker = ProgressTracker(self.update_progress)
        try:
            await self.uploader.upload_file(
                self.selected_chat['entity'],
                self.file_path,
                progress_callback=tracker.callback
            )
            self.status.value = "✅ Upload thành công!"
            self.status.color = "green"
        except Exception as ex:
            self.status.value = f"❌ Lỗi: {ex}"

        self.progress_bar.visible = False
        self.page.update()

    def update_progress(self, pct, msg):
        self.progress_bar.value = pct
        self.status.value = f"Đang tải lên: {msg}"
        self.page.update()

    def get_view(self):
        btn_load = ft.ElevatedButton("Tải danh sách nhóm", icon=ft.icons.REFRESH,
                                     on_click=lambda _: self.page.run_task(self.dialog_selector.load_dialogs))

        return ft.Column([
            ft.Text("Upload Media", size=20, weight="bold"),
            ft.Divider(),

            ft.Container(
                padding=10,
                border=ft.border.all(1, "grey"), border_radius=10,
                content=ft.Row([self.btn_select_file, self.lbl_file])
            ),
            ft.Divider(height=20, color="transparent"),

            ft.Row([ft.Text("Chọn nơi gửi:", weight="bold"), btn_load], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            self.dialog_selector,
            ft.Row([ft.Icon(ft.icons.CHECK_CIRCLE, color="green"), self.lbl_chat]),

            ft.Divider(),
            ft.ElevatedButton("BẮT ĐẦU UPLOAD", on_click=self.start_upload, bgcolor="blue", color="white", width=200),

            ft.Divider(height=20, color="transparent"),
            self.status,
            self.progress_bar
        ], scroll=ft.ScrollMode.AUTO, expand=True)