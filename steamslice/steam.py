"""스팀 창작마당 전시대 등록 안내에 필요한 값과 도우미. 앱은 스팀에 직접 접속하지 않는다."""
import os
import subprocess
import webbrowser

UPLOAD_URL = "https://steamcommunity.com/sharedfiles/edititem/767/3/"
CONSOLE_SNIPPET = ("$J('[name=consumer_app_id]').val(480);"
                   "$J('[name=file_type]').val(0);"
                   "$J('[name=visibility]').val(0);")
NOTICE = "이 명령어는 편법적인 방법이지만 약관 위반은 아니므로, 계속 등록할 수 있습니다."
HOWTO = (
    "스팀에 올리는 방법",
    "1. 1번부터 5번까지 순서대로 올립니다. 1번이 가장 왼쪽 조각입니다.",
    "2. 올릴 때마다 업로드 페이지에서 F12 → Console에 명령어를 붙여 넣고 Enter를 누른 뒤에 파일을 올립니다.",
    "3. 다 올린 뒤에 프로필 편집에서 '내 창작마당' 전시대의 칸을 왼쪽부터 1번 ~ 5번으로 지정합니다.",
)


def open_upload_page():
    webbrowser.open(UPLOAD_URL)


def reveal(path):
    """탐색기에서 해당 파일이 선택된 상태로 폴더를 연다."""
    subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
