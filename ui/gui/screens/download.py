import flet as ft
from core.downloader import Downloader
from utils.progress import ProgressTracker
from ui.gui.widgets.dialog_selector import DialogSelector


class DownloadScreen:
    def __init__(self, page, tele_client):
        self.page = page
        self.client = tele_client.get_client()
        self.tele_client_wrapper = tele_client
        self.downloader = Downloader(self.client)

        # --- CỘT TRÁI ---
        self.link_input = ft.TextField(label="Dán Link bài viết", expand=True)
        self.selected_chat = None
        self.lbl_selected_source = ft.Text("Chưa chọn nhóm nào", italic=True, color="yellow", size=12)

        # Màn hình Download: Không truyền height => Tự động expand
        self.dialog_selector = DialogSelector(self.tele_client_wrapper, self.on_source_selected)

        self.msg_limit_input = ft.TextField(label="Số lượng", value="20", width=80, keyboard_type="number",
                                            text_size=12, content_padding=10)

        # --- CỘT PHẢI ---
        self.progress_bar = ft.ProgressBar(value=0, visible=False, color="green", bgcolor="grey")
        self.progress_text = ft.Text("", visible=False, size=12)
        self.status_log = ft.ListView(expand=True, spacing=2, auto_scroll=True)

    def log(self, msg, color="white"):
        self.status_log.controls.append(ft.Text(f"> {msg}", color=color, size=13, font_family="Consolas"))
        self.page.update()

    def update_progress(self, percentage, msg):
        self.progress_bar.value = percentage
        self.progress_text.value = msg
        self.page.update()

    def on_source_selected(self, chat):
        self.selected_chat = chat
        self.lbl_selected_source.value = f"✅ {chat['name']} (ID: {chat['id']})"
        self.lbl_selected_source.color = "green"
        self.lbl_selected_source.weight = "bold"
        self.page.update()

    async def start_download_link(self, e):
        url = self.link_input.value
        if not url: return
        self.log(f"Link: {url}", "cyan")
        self.progress_bar.visible = True;
        self.page.update()
        try:
            if "t.me/" in url:
                parts = url.rstrip('/').split('/')
                msg_id = int(parts[-1]);
                chat = parts[-2]
                if chat == "c":
                    chat_id = int("-100" + parts[-3]); message = await self.client.get_messages(chat_id, ids=msg_id)
                else:
                    message = await self.client.get_messages(chat, ids=msg_id)

                if message and message.media:
                    tracker = ProgressTracker(self.update_progress)
                    path = await self.downloader.download_message_media(message, tracker.callback)
                    self.log(f"OK: {path}", "green")
                else:
                    self.log("Không có media.", "orange")
        except Exception as ex:
            self.log(f"Lỗi: {str(ex)}", "red")
        self.progress_bar.visible = False;
        self.page.update()

    async def start_scan_download(self, e):
        if not self.selected_chat:
            self.log("Chưa chọn nhóm bên cột trái!", "red");
            return
        try:
            limit = int(self.msg_limit_input.value)
        except:
            limit = 10

        self.log(f"Quét {limit} tin từ '{self.selected_chat['name']}'...", "cyan")
        self.progress_bar.visible = True;
        self.page.update()
        count = 0
        try:
            messages = await self.client.get_messages(self.selected_chat['entity'], limit=limit)
            for msg in messages:
                if msg.media:
                    self.log(f"Tải ID {msg.id}...", "yellow")
                    tracker = ProgressTracker(self.update_progress)
                    path = await self.downloader.download_message_media(msg, tracker.callback)
                    if path: self.log(f"-> {path}", "green"); count += 1
            self.log(f"Hoàn tất. {count} files.", "blue")
        except Exception as ex:
            self.log(f"Lỗi: {str(ex)}", "red")
        self.progress_bar.visible = False;
        self.page.update()

    def get_view(self):
        # Tab 1: Link
        tab_link = ft.Column([
            ft.Text("Tải qua Link (Public/Private)", weight="bold"),
            ft.Row([self.link_input, ft.ElevatedButton("Tải", on_click=self.start_download_link)]),
        ])

        # Tab 2: Scan
        btn_load = ft.ElevatedButton("Tải DS Nhóm", icon=ft.icons.REFRESH,
                                     on_click=lambda _: self.page.run_task(self.dialog_selector.load_dialogs))

        # Header Tab Scan
        scan_header = ft.Row([btn_load, self.lbl_selected_source], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        # Footer Tab Scan (Sửa lỗi expand của Button để tránh vỡ layout)
        scan_footer = ft.Row([
            ft.Row([ft.Text("Quét:", size=12), self.msg_limit_input, ft.Text("tin")],
                   alignment=ft.MainAxisAlignment.START),
            ft.ElevatedButton("DOWNLOAD", icon=ft.icons.DOWNLOAD, on_click=self.start_scan_download, bgcolor="blue",
                              color="white")
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        # Content Tab Scan
        tab_scan = ft.Column([
            scan_header,
            self.dialog_selector,  # Widget này sẽ tự động expand nhờ DialogSelector mới
            ft.Container(height=5),
            scan_footer
        ], expand=True)

        tabs = ft.Tabs(
            selected_index=1,
            tabs=[ft.Tab(text="Dán Link", content=tab_link), ft.Tab(text="Chọn Nhóm", content=tab_scan)],
            expand=True
        )

        layout = ft.Row(
            controls=[
                ft.Container(content=tabs, expand=5, padding=5,
                             border=ft.border.only(right=ft.border.BorderSide(1, "grey"))),
                ft.Container(
                    content=ft.Column([
                        ft.Text("Nhật ký (Logs)", weight="bold"),
                        ft.Container(content=self.status_log, bgcolor=ft.colors.BLACK26, border_radius=5, padding=5,
                                     expand=True),
                        self.progress_text,
                        self.progress_bar
                    ], expand=True),
                    expand=5, padding=10
                )
            ],
            expand=True
        )

        return ft.Column([ft.Text("Download Manager", size=20, weight="bold"), layout], expand=True)