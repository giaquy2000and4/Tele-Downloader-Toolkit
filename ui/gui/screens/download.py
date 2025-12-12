import flet as ft
import asyncio
import humanize
from core.downloader import Downloader
from ui.gui.widgets.dialog_selector import DialogSelector
from storage.database import db


# --- ITEM HIỂN THỊ TỪNG FILE DOWNLOAD ---
class DownloadTaskItem(ft.UserControl):
    def __init__(self, task_data, downloader, client, page_ref):
        super().__init__()
        # Giải nén dữ liệu từ DB
        self.task_id = task_data[0]
        self.chat_id = task_data[1]
        self.msg_id = task_data[2]
        self.filename = task_data[3]
        self.total = task_data[5]
        self.current = task_data[6]
        self.status = task_data[7]

        self.downloader = downloader
        self.client = client
        self.page_ref = page_ref

        self.cancel_event = asyncio.Event()

        # UI Components
        self.progress_bar = ft.ProgressBar(value=self.current / self.total if self.total > 0 else 0, height=5,
                                           color="blue", bgcolor="grey")
        self.lbl_status = ft.Text(self.status, size=12, color="white")
        self.lbl_size = ft.Text(f"{humanize.naturalsize(self.current)} / {humanize.naturalsize(self.total)}", size=10)

        icon = ft.icons.PLAY_ARROW
        if self.status == 'downloading':
            icon = ft.icons.PAUSE
        elif self.status == 'completed':
            icon = ft.icons.CHECK

        self.btn_control = ft.IconButton(
            icon=icon,
            on_click=self.toggle_download,
            icon_color="white"
        )

    def build(self):
        return ft.Container(
            padding=10,
            bgcolor=ft.colors.with_opacity(0.05, "white"),
            border_radius=5,
            margin=ft.margin.only(bottom=5),
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.icons.FILE_DOWNLOAD, color="blue"),
                    ft.Text(self.filename, weight="bold", expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    self.lbl_status,
                    self.btn_control
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                self.progress_bar,
                self.lbl_size
            ])
        )

    async def toggle_download(self, e=None):
        if self.status == 'downloading':
            # ACTION: PAUSE
            self.cancel_event.set()
            self.status = 'paused'
            self.btn_control.icon = ft.icons.PLAY_ARROW
            self.lbl_status.value = "Paused"
            self.lbl_status.color = "yellow"
        else:
            # ACTION: RESUME / START
            if self.status == 'completed': return

            self.cancel_event.clear()
            self.status = 'downloading'
            self.btn_control.icon = ft.icons.PAUSE
            self.lbl_status.value = "Downloading..."
            self.lbl_status.color = "blue"
            self.update()

            try:
                # Lấy message object thực tế từ Telegram để tải
                msgs = await self.client.get_messages(self.chat_id, ids=self.msg_id)

                if msgs and msgs.media:
                    await self.downloader.download_with_resume(
                        msgs, self.filename, self.task_id, db, self.update_ui_progress, self.cancel_event
                    )

                    if not self.cancel_event.is_set():
                        self.status = 'completed'
                        self.btn_control.icon = ft.icons.CHECK
                        self.btn_control.disabled = True
                        self.lbl_status.value = "Completed"
                        self.lbl_status.color = "green"
                        self.progress_bar.value = 1.0
                        self.progress_bar.color = "green"
                else:
                    self.status = 'error'
                    self.lbl_status.value = "Msg not found"
                    self.lbl_status.color = "red"
            except Exception as ex:
                self.status = 'error'
                self.lbl_status.value = "Error"
                print(f"Download Error: {ex}")

        self.update()

    def update_ui_progress(self, pct, current, total):
        self.current = current
        self.progress_bar.value = pct
        self.lbl_size.value = f"{humanize.naturalsize(current)} / {humanize.naturalsize(total)}"
        self.update()


# --- MÀN HÌNH CHÍNH DOWNLOAD ---
class DownloadScreen:
    def __init__(self, page, tele_client):
        self.page = page
        self.client = tele_client.get_client()
        self.downloader = Downloader(self.client, tele_client.session_name)
        self.tele_client_wrapper = tele_client

        # Danh sách Task (Container chứa các DownloadTaskItem)
        self.task_list_col = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=5)

        # Phần chọn nguồn (Scan)
        self.dialog_selector = DialogSelector(self.tele_client_wrapper, self.on_source_selected)
        self.selected_chat = None
        self.msg_limit_input = ft.TextField(label="Số lượng tin", value="5", width=100, keyboard_type="number",
                                            text_size=12, content_padding=10)
        self.lbl_selected = ft.Text("Chưa chọn nhóm nào (Chọn bên dưới)", italic=True, color="yellow", size=12)

        # Load lịch sử cũ từ Database
        self.load_tasks_from_db()

    def load_tasks_from_db(self):
        try:
            tasks = db.get_all_tasks(self.tele_client_wrapper.session_name)
            for task in tasks:
                item = DownloadTaskItem(task, self.downloader, self.client, self.page)
                self.task_list_col.controls.append(item)
        except Exception as e:
            print(f"Error loading DB: {e}")

    def on_source_selected(self, chat):
        self.selected_chat = chat
        self.lbl_selected.value = f"✅ {chat['name']} (ID: {chat['id']})"
        self.lbl_selected.color = "green"
        self.lbl_selected.weight = "bold"
        self.page.update()

    async def add_task_to_queue(self, e):
        if not self.selected_chat:
            self.lbl_selected.value = "❌ Vui lòng chọn nhóm trước!";
            self.lbl_selected.color = "red"
            self.page.update()
            return

        try:
            limit = int(self.msg_limit_input.value)
        except:
            limit = 5

        self.lbl_selected.value = f"⏳ Đang quét {limit} tin nhắn..."
        self.lbl_selected.color = "cyan"
        self.page.update()

        try:
            msgs = await self.client.get_messages(self.selected_chat['entity'], limit=limit)
            count = 0

            for msg in msgs:
                if msg.media:
                    # Tạo tên file: ID_TênFileGốc
                    fname = f"{msg.id}_{msg.file.name}" if msg.file.name else f"{msg.id}_file{msg.file.ext}"

                    # 1. Lưu vào Database
                    task_id = db.add_task(
                        chat_id=self.selected_chat['id'],
                        message_id=msg.id,
                        file_name=fname,
                        save_path="",
                        total_size=msg.file.size,
                        account_name=self.tele_client_wrapper.session_name
                    )

                    # 2. Tạo Item trên UI
                    task_data = (task_id, self.selected_chat['id'], msg.id, fname, "", msg.file.size, 0, 'pending',
                                 self.tele_client_wrapper.session_name)

                    item = DownloadTaskItem(task_data, self.downloader, self.client, self.page)
                    self.task_list_col.controls.insert(0, item)

                    # 3. Tự động Start
                    self.page.run_task(item.toggle_download)
                    count += 1

            self.lbl_selected.value = f"✅ Đã thêm {count} file vào hàng đợi."
            self.lbl_selected.color = "green"

        except Exception as ex:
            self.lbl_selected.value = f"❌ Lỗi: {str(ex)}"
            self.lbl_selected.color = "red"

        self.page.update()

    def get_view(self):
        # --- CỘT TRÁI: ĐIỀU KHIỂN ---
        left_panel = ft.Column([
            ft.Text("Bước 1: Chọn nguồn", weight="bold"),
            ft.ElevatedButton("Tải DS Nhóm", icon=ft.icons.REFRESH,
                              on_click=lambda _: self.page.run_task(self.dialog_selector.load_dialogs)),
            self.lbl_selected,
            self.dialog_selector,

            ft.Divider(),
            ft.Text("Bước 2: Quét & Tải", weight="bold"),
            ft.Row([
                self.msg_limit_input,
                # SỬA LỖI TẠI ĐÂY: ft.icons.PLAYLIST_ADD (viết hoa)
                ft.ElevatedButton("Thêm vào hàng đợi", icon=ft.icons.PLAYLIST_ADD, on_click=self.add_task_to_queue,
                                  expand=True)
            ])
        ], expand=4)

        # --- CỘT PHẢI: DANH SÁCH TASK ---
        right_panel = ft.Column([
            ft.Text("Danh sách hàng đợi (Tự động tải & Resume)", weight="bold"),
            ft.Container(
                content=self.task_list_col,
                bgcolor=ft.colors.BLACK12,
                border_radius=10,
                padding=10,
                expand=True
            )
        ], expand=6)

        return ft.Column([
            ft.Text("Download Manager Pro (Resume Supported)", size=20, weight="bold"),
            ft.Row([left_panel, ft.VerticalDivider(width=1, color="grey"), right_panel], expand=True)
        ], expand=True)