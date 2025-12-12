import flet as ft
from core.session_manager import SessionManager
from telethon.errors import SessionPasswordNeededError


class LoginScreen:
    def __init__(self, page, tele_client_class, on_login_success):
        self.page = page
        self.TeleClientClass = tele_client_class  # Class để khởi tạo dynamic
        self.on_login_success = on_login_success  # Callback khi login xong

        # --- UI FORM LOGIN ---
        self.session_name_input = ft.TextField(label="Tên gợi nhớ (VD: acc_chinh)", width=300)
        self.phone_input = ft.TextField(label="Số điện thoại (+84...)", width=300)
        self.code_input = ft.TextField(label="Mã OTP", width=300, visible=False)
        self.password_input = ft.TextField(label="Mật khẩu 2 lớp", width=300, visible=False, password=True,
                                           can_reveal_password=True)
        self.btn_action = ft.ElevatedButton("Gửi mã", on_click=self.on_action)
        self.btn_back = ft.TextButton("Quay lại danh sách", on_click=self.show_list_mode, visible=False)
        self.status_text = ft.Text("", color="red", size=12)

        # Biến tạm cho process login mới
        self.current_temp_client = None

        # --- UI LIST ACCOUNTS ---
        self.account_list = ft.Column()

        # Main content container
        self.main_content = ft.Column(alignment=ft.MainAxisAlignment.CENTER,
                                      horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        # Khởi động ở chế độ List
        self.show_list_mode(None)

    def show_list_mode(self, e):
        """Hiển thị danh sách tài khoản đã lưu"""
        self.main_content.controls.clear()

        sessions = SessionManager.get_all_sessions()

        if not sessions:
            self.show_login_form(None)  # Nếu chưa có acc nào thì hiện form luôn
            return

        self.account_list.controls.clear()
        for sess_name in sessions:
            self.account_list.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.icons.ACCOUNT_CIRCLE, size=30, color="blue"),
                        ft.Text(sess_name, size=16, weight="bold", expand=True),
                        ft.IconButton(ft.icons.LOGIN, tooltip="Đăng nhập",
                                      on_click=lambda e, n=sess_name: self.login_existing(n)),
                        ft.IconButton(ft.icons.DELETE, tooltip="Xóa", icon_color="red",
                                      on_click=lambda e, n=sess_name: self.delete_account(n))
                    ]),
                    padding=10,
                    bgcolor=ft.colors.with_opacity(0.1, ft.colors.WHITE),
                    border_radius=10
                )
            )

        self.main_content.controls = [
            ft.Icon(ft.icons.TELEGRAM, size=80, color="blue"),
            ft.Text("Chọn tài khoản", size=24, weight="bold"),
            ft.Container(height=20),
            self.account_list,
            ft.Container(height=20),
            ft.ElevatedButton("Thêm tài khoản mới", icon=ft.icons.ADD, on_click=self.show_login_form)
        ]
        self.page.update()

    def show_login_form(self, e):
        """Hiển thị form đăng nhập mới"""
        self.main_content.controls = [
            ft.Text("Đăng nhập mới", size=24, weight="bold"),
            self.session_name_input,
            self.phone_input,
            self.code_input,
            self.password_input,
            ft.Container(height=10),
            self.btn_action,
            self.btn_back,
            self.status_text
        ]

        # Reset inputs
        self.session_name_input.visible = True
        self.phone_input.disabled = False
        self.code_input.visible = False
        self.password_input.visible = False
        self.btn_action.text = "Gửi mã"
        self.session_name_input.value = ""
        self.phone_input.value = ""
        self.code_input.value = ""

        # Hiện nút back nếu đang có session khác
        if SessionManager.get_all_sessions():
            self.btn_back.visible = True

        self.page.update()

    async def login_existing(self, session_name):
        """Đăng nhập vào một session đã có"""
        self.page.snack_bar = ft.SnackBar(ft.Text(f"Đang kết nối vào {session_name}..."))
        self.page.snack_bar.open = True
        self.page.update()

        # Khởi tạo client với session name đã chọn
        client = self.TeleClientClass(session_name)
        await client.connect()

        if await client.is_user_authorized():
            self.on_login_success(client)  # Callback về app.py
        else:
            self.page.snack_bar = ft.SnackBar(ft.Text("Session hết hạn, vui lòng đăng nhập lại."))
            self.page.snack_bar.open = True
            self.page.update()
            # Xóa session hỏng
            SessionManager.delete_session(session_name)
            self.show_list_mode(None)

    def delete_account(self, session_name):
        SessionManager.delete_session(session_name)
        self.show_list_mode(None)

    async def on_action(self, e):
        """Xử lý logic đăng nhập mới"""
        name = self.session_name_input.value
        phone = self.phone_input.value

        if not name:
            self.status_text.value = "Vui lòng nhập tên gợi nhớ!";
            self.page.update();
            return

        if not self.current_temp_client:
            self.current_temp_client = self.TeleClientClass(name)
            await self.current_temp_client.connect()

        try:
            if not self.code_input.visible:
                await self.current_temp_client.send_code(phone)
                self.code_input.visible = True
                self.session_name_input.disabled = True
                self.phone_input.disabled = True
                self.btn_action.text = "Đăng nhập"
                self.status_text.value = "Đã gửi OTP"
            elif not self.password_input.visible:
                try:
                    await self.current_temp_client.sign_in(phone, self.code_input.value)
                    # Thành công -> lưu và vào app
                    self.on_login_success(self.current_temp_client)
                except SessionPasswordNeededError:
                    self.password_input.visible = True
                    self.code_input.disabled = True
                    self.btn_action.text = "Xác nhận mật khẩu"
            else:
                await self.current_temp_client.sign_in(password=self.password_input.value)
                self.on_login_success(self.current_temp_client)

        except Exception as ex:
            self.status_text.value = f"Lỗi: {ex}"
        self.page.update()

    def get_view(self):
        return ft.View(
            "/login",
            controls=[
                ft.AppBar(title=ft.Text("Quản lý tài khoản"), center_title=True),
                ft.Container(
                    content=self.main_content,
                    padding=20,
                    alignment=ft.alignment.center
                )
            ]
        )