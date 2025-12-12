import flet as ft
from core.client import TeleClient
from ui.gui.screens.login import LoginScreen
from ui.gui.screens.download import DownloadScreen
from ui.gui.screens.upload import UploadScreen


async def main(page: ft.Page):
    # 1. Cấu hình cửa sổ
    page.title = "Tele Downloader Toolkit Pro"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 1100
    page.window_height = 800

    # 2. Khởi tạo Telegram Client
    tele_client = TeleClient()
    await tele_client.connect()

    # 3. Định nghĩa Giao diện chính (Sidebar + Tabs)
    def build_main_ui():
        download_screen = DownloadScreen(page, tele_client)
        upload_screen = UploadScreen(page, tele_client)

        # Danh sách nội dung các Tab
        tabs_content = [
            download_screen.get_view(),  # Index 0
            upload_screen.get_view(),  # Index 1
            ft.Container(content=ft.Text("Cài đặt / Account (Coming Soon)", size=20))  # Index 2
        ]

        # Khu vực hiển thị nội dung bên phải
        content_area = ft.Container(content=tabs_content[0], expand=True, padding=20)

        # Hàm đổi Tab khi bấm Sidebar
        def change_tab(e):
            selected_idx = e.control.selected_index
            content_area.content = tabs_content[selected_idx]
            content_area.update()

        # Sidebar bên trái
        rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=100,
            min_extended_width=200,
            destinations=[
                ft.NavigationRailDestination(icon=ft.icons.DOWNLOAD, label="Download"),
                ft.NavigationRailDestination(icon=ft.icons.UPLOAD, label="Upload"),
                ft.NavigationRailDestination(icon=ft.icons.SETTINGS, label="Cài đặt"),
            ],
            on_change=change_tab,
        )

        # Nút Đăng xuất ở góc trên phải (Optional)
        async def logout_action(e):
            await tele_client.client.log_out()
            page.go("/login")

        return ft.View(
            route="/",
            controls=[
                ft.AppBar(
                    title=ft.Text("Tele Downloader Toolkit"),
                    actions=[ft.IconButton(ft.icons.LOGOUT, tooltip="Đăng xuất", on_click=logout_action)]
                ),
                ft.Row(
                    [
                        rail,
                        ft.VerticalDivider(width=1),
                        content_area,
                    ],
                    expand=True,
                )
            ]
        )

    # 4. Hàm xử lý điều hướng (Router)
    def route_change(route):
        page.views.clear()

        if page.route == "/login":
            # Hiện màn hình đăng nhập
            login_view = LoginScreen(page, tele_client).get_view()
            page.views.append(login_view)

        elif page.route == "/":
            # Hiện giao diện chính
            page.views.append(build_main_ui())

        page.update()

    # Gán hàm xử lý sự kiện
    page.on_route_change = route_change

    # 5. Kiểm tra trạng thái đăng nhập ban đầu
    if await tele_client.is_user_authorized():
        page.go("/")
    else:
        page.go("/login")


if __name__ == "__main__":
    ft.app(target=main)