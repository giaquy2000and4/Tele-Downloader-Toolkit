import flet as ft
from telethon.errors import SessionPasswordNeededError


class LoginScreen:
    def __init__(self, page, tele_client):
        self.page = page
        self.client = tele_client

        # UI Components
        self.phone_input = ft.TextField(label="Số điện thoại (+84...)", width=300)
        self.code_input = ft.TextField(label="Mã OTP", width=300, visible=False)
        self.password_input = ft.TextField(
            label="Mật khẩu 2 lớp (Cloud Password)",
            width=300,
            visible=False,
            password=True,
            can_reveal_password=True
        )

        self.btn_action = ft.ElevatedButton("Gửi mã", on_click=self.on_action)
        self.status_text = ft.Text("", color="red", size=12)

    async def on_action(self, e):
        phone = self.phone_input.value
        code = self.code_input.value
        password = self.password_input.value

        self.status_text.value = "Đang xử lý..."
        self.status_text.color = "yellow"
        self.page.update()

        try:
            # GIAI ĐOẠN 1: Gửi số điện thoại
            if not self.code_input.visible:
                await self.client.send_code(phone)

                # Update UI
                self.code_input.visible = True
                self.phone_input.disabled = True
                self.btn_action.text = "Đăng nhập"
                self.status_text.value = "Đã gửi mã OTP! Hãy kiểm tra Telegram."
                self.status_text.color = "green"

            # GIAI ĐOẠN 2: Gửi OTP (Chưa hiện ô password)
            elif not self.password_input.visible:
                try:
                    await self.client.sign_in(phone=phone, code=code)
                    # Nếu thành công ngay (không có 2FA)
                    self.page.go("/download")
                except SessionPasswordNeededError:
                    # Nếu Telegram báo cần mật khẩu 2 bước
                    self.password_input.visible = True
                    self.code_input.disabled = True
                    self.btn_action.text = "Xác nhận mật khẩu"
                    self.status_text.value = "Tài khoản có bảo mật 2 lớp. Vui lòng nhập mật khẩu."
                    self.status_text.color = "orange"

            # GIAI ĐOẠN 3: Gửi Password (2FA)
            else:
                await self.client.sign_in(password=password)
                self.page.go("/")  # Chuyển về trang chủ

        except Exception as ex:
            self.status_text.value = f"Lỗi: {str(ex)}"
            self.status_text.color = "red"

        self.page.update()

    def get_view(self):
        return ft.View(
            "/login",
            controls=[
                ft.AppBar(title=ft.Text("Đăng nhập Telegram"), center_title=True),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.icons.TELEGRAM, size=100, color="blue"),
                            self.phone_input,
                            self.code_input,
                            self.password_input,  # Đã thêm ô password vào đây
                            ft.Container(height=10),
                            self.btn_action,
                            ft.Container(height=10),
                            self.status_text
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=20,
                    alignment=ft.alignment.center
                )
            ]
        )