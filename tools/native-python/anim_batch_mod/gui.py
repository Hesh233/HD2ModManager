from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


DEFAULT_GAME_DATA = r"E:\Steam\steamapps\common\Helldivers 2\data"
UNIT_ID = "5556372446766824087"
KEYWORD = "18235e0c9ec0e636"


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("hd2批量骨架转换工具")
        self.root.geometry("720x390")
        self.root.minsize(640, 330)
        self.running = False
        self.game_data = tk.StringVar(value=DEFAULT_GAME_DATA)
        self.animation_threads = tk.StringVar(value="2")
        self.status = tk.StringVar(value="就绪")
        self.buttons: list[ttk.Button] = []
        self._build_ui()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        ttk.Label(frame, text="游戏 data 目录 (--game-data)").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        path_frame = ttk.Frame(frame)
        path_frame.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        path_frame.columnconfigure(0, weight=1)
        ttk.Entry(path_frame, textvariable=self.game_data).grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Button(path_frame, text="浏览...", command=self.choose_game_data).grid(
            row=0, column=1, padx=(8, 0)
        )

        button_frame = ttk.LabelFrame(frame, text="操作")
        button_frame.grid(row=2, column=0, sticky="nsew")
        button_frame.columnconfigure(0, weight=1)
        actions = [
            ("完整重建本地索引", self.rebuild_index),
            ("导出配置文件", self.generate_config),
            ("按 anim_id.txt 导出 mod 文件", self.export_selected),
            ("全量导出 mod 文件", self.export_all),
            ("打开 config.toml", self.open_config),
            ("打开项目文件夹", self.open_project),
            ("打开 --game-data 文件夹", self.open_game_data),
        ]
        for row, (label, command) in enumerate(actions):
            button = ttk.Button(button_frame, text=label, command=command)
            button.grid(row=row, column=0, columnspan=1 if command == self.export_all else 2,
                        sticky="ew", padx=12, pady=5)
            if command == self.export_all:
                thread_frame = ttk.Frame(button_frame)
                thread_frame.grid(row=row, column=1, padx=(0, 12), pady=5)
                ttk.Label(thread_frame, text="线程数：").pack(side=tk.LEFT)
                ttk.Entry(thread_frame, textvariable=self.animation_threads, width=5).pack(side=tk.LEFT)
            self.buttons.append(button)

        ttk.Label(frame, textvariable=self.status, relief=tk.SUNKEN, anchor="w").grid(
            row=3, column=0, sticky="ew", pady=(14, 0)
        )

    @property
    def app_dir(self) -> Path:
        """Directory containing the GUI executable (or source file)."""
        return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent

    @property
    def resource_dir(self) -> Path:
        """PyInstaller's bundled resource directory, or the source directory."""
        return Path(getattr(sys, "_MEIPASS", self.app_dir))

    @property
    def cli_path(self) -> Path:
        # The worker must sit beside the GUI executable so its PyInstaller
        # bootloader resolves the shared sibling _internal directory.
        external = self.app_dir / "anim_batch_mod.exe"
        if external.exists():
            return external
        bundled = self.resource_dir / "anim_batch_mod.exe"
        if bundled.exists():
            return bundled
        return self.app_dir / "main.py"

    def choose_game_data(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.game_data.get())
        if selected:
            self.game_data.set(selected)

    def command_base(self) -> list[str]:
        game_data = self.game_data.get().strip()
        if not game_data:
            raise ValueError("请填写 --game-data 路径")
        if not Path(game_data).is_dir():
            raise ValueError(f"游戏目录不存在：{game_data}")
        command = [str(self.cli_path), "--game-data", game_data]
        if self.cli_path.suffix.lower() != ".exe":
            command = [sys.executable] + command
        return command

    def path_arg(self, name: str) -> list[str]:
        path = self.app_dir / name
        return [f"--{name.replace('_', '-')}", str(path)]

    def run_cli(self, args: list[str], label: str) -> None:
        if self.running:
            return
        try:
            command = self.command_base() + args
        except ValueError as error:
            messagebox.showerror("参数错误", str(error))
            return
        self.running = True
        for button in self.buttons:
            button.configure(state=tk.DISABLED)
        self.status.set(f"正在执行：{label}")
        try:
            # Launch through cmd.exe so stdout/stderr are attached to the visible console.
            command_line = subprocess.list2cmdline(command)
            comspec = os.environ.get("COMSPEC", "cmd.exe")
            subprocess.Popen(
                f'"{comspec}" /d /k {command_line}',
                cwd=self.resource_dir,
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )
            self.status.set(f"已启动：{label}（请查看 CMD 窗口输出）")
        except OSError as error:
            messagebox.showerror("启动失败", str(error))
            self.status.set("启动失败")
        finally:
            self.running = False
            for button in self.buttons:
                button.configure(state=tk.NORMAL)

    def rebuild_index(self) -> None:
        self.run_cli(["--build-index-only", "--rebuild-index"], "重建本地索引")

    def generate_config(self) -> None:
        self.run_cli(
            [
                "generate-config", "--unit-id", UNIT_ID, "--force",
                "--output-config", str(self.app_dir / "config.toml"),
                "--base-anim", str(self.app_dir / "base_anim"),
            ],
            "导出配置文件",
        )

    def export_selected(self) -> None:
        self.run_cli(
            [
                "batch", "--keyword", KEYWORD, "--animation-id-file", str(self.app_dir / "anim_id.txt"),
                "--config", str(self.app_dir / "config.toml"), "--allow-additive",
                "--rotate-multipliers", "true", "--force",
            ],
            "按 anim_id.txt 导出 mod 文件",
        )

    def export_all(self) -> None:
        threads = self.animation_threads.get().strip()
        if not threads.isascii() or not threads.isdecimal() or not 1 <= int(threads) <= 16:
            messagebox.showerror("参数错误", "全量动画打包线程数必须为 1–16 之间的整数。")
            return
        self.run_cli(
            [
                "batch", "--keyword", KEYWORD, "--config", str(self.app_dir / "config.toml"),
                "--threads", str(int(threads)),
                "--allow-additive", "--rotate-multipliers", "true", "--force",
            ],
            "全量导出 mod 文件",
        )

    def open_path(self, path: Path) -> None:
        if not path.exists():
            messagebox.showerror("文件不存在", str(path))
            return
        os.startfile(str(path))

    def open_config(self) -> None:
        self.open_path(self.app_dir / "config.toml")

    def open_project(self) -> None:
        self.open_path(self.app_dir)

    def open_game_data(self) -> None:
        self.open_path(Path(self.game_data.get().strip()))


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
