import fonts

# GUI 모듈 import 전에 폰트를 프로세스에 등록
fonts.register()

from gui import WatcherApp


def main():
    app = WatcherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
