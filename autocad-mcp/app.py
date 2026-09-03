"""
AutoCAD 2022 MCP Controller & Dashboard GUI
Ứng dụng điều khiển trung tâm và giao diện kết nối MCP Server cho AutoCAD 2022.
"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

# Đảm bảo mã hóa UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# .mcp.json nằm ở gốc dự án (thư mục cha), không nằm cạnh app.py
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
SERVER_SCRIPT = os.path.join(CURRENT_DIR, "server.py")
PYTHON_EXE = sys.executable

class AutoCADMCPApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AutoCAD 2022 MCP Controller & AI Hub")
        self.root.geometry("820x680")
        self.root.minsize(760, 600)

        # Biến trạng thái
        self.server_process = None
        self.is_server_running = False
        self.is_acad_connected = False
        self.log_queue = queue.Queue()
        self.stop_monitoring = False

        # Thiết lập màu sắc & Theme (Modern Dark Slate)
        self.bg_color = "#1e1e2e"
        self.card_bg = "#252538"
        self.card_border = "#313244"
        self.text_primary = "#cdd6f4"
        self.text_secondary = "#a6adc8"
        self.accent_green = "#a6e3a1"
        self.accent_red = "#f38ba8"
        self.accent_blue = "#89b4fa"
        self.accent_yellow = "#f9e2af"
        self.accent_purple = "#cba6f7"
        self.console_bg = "#11111b"
        self.console_fg = "#a6e3a1"

        self.root.configure(bg=self.bg_color)
        self.setup_styles()
        self.build_ui()

        # Bắt đầu luồng kiểm tra log và AutoCAD
        self.root.after(100, self.process_log_queue)
        self.monitor_thread = threading.Thread(target=self.acad_monitor_loop, daemon=True)
        self.monitor_thread.start()

        # Xử lý đóng cửa sổ an toàn
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.log("🚀 Ứng dụng điều khiển AutoCAD 2022 MCP đã khởi động sẵn sàng!")
        self.log(f"📁 Thư mục làm việc: {CURRENT_DIR}")
        self.log("💡 Bạn có thể bật MCP Server bên dưới để các AI (Claude, Antigravity, Cursor) kết nối.")

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TFrame", background=self.bg_color)
        style.configure("Card.TFrame", background=self.card_bg)
        style.configure("TLabel", background=self.bg_color, foreground=self.text_primary, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=self.card_bg, foreground=self.text_primary, font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=self.bg_color, foreground="#ffffff", font=("Segoe UI", 15, "bold"))
        style.configure("SubTitle.TLabel", background=self.bg_color, foreground=self.text_secondary, font=("Segoe UI", 9))
        style.configure("StatusHead.TLabel", background=self.card_bg, foreground=self.text_secondary, font=("Segoe UI", 9, "bold"))
        style.configure("StatusVal.TLabel", background=self.card_bg, foreground=self.text_primary, font=("Segoe UI", 10, "bold"))

        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=6)
        style.configure("Action.TButton", font=("Segoe UI", 9), padding=5)

    def build_ui(self):
        # 1. Header Frame
        header_frame = ttk.Frame(self.root, padding="15 12 15 8")
        header_frame.pack(fill="x")

        title_lbl = ttk.Label(header_frame, text="⚡ AUTOCAD 2022 MCP CONTROLLER & HUB", style="Title.TLabel")
        title_lbl.pack(anchor="w")
        sub_lbl = ttk.Label(header_frame, text="Quản lý kết nối Model Context Protocol (MCP) & Điều khiển AutoCAD qua AI", style="SubTitle.TLabel")
        sub_lbl.pack(anchor="w")

        # 2. Status Dashboard Cards Frame
        status_frame = ttk.Frame(self.root, padding="15 0 15 10")
        status_frame.pack(fill="x")

        cards_container = tk.Frame(status_frame, bg=self.card_bg, bd=1, relief="solid", highlightbackground=self.card_border)
        cards_container.pack(fill="x", ipady=8, ipadx=10)

        cards_container.columnconfigure(0, weight=1)
        cards_container.columnconfigure(1, weight=1)
        cards_container.columnconfigure(2, weight=1)

        # Card 1: MCP Server Status
        card1 = tk.Frame(cards_container, bg=self.card_bg)
        card1.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)
        tk.Label(card1, text="TRẠNG THÁI MCP SERVER", bg=self.card_bg, fg=self.text_secondary, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.server_status_badge = tk.Label(card1, text="🔴 ĐÃ DỪNG (OFF)", bg=self.card_bg, fg=self.accent_red, font=("Segoe UI", 12, "bold"))
        self.server_status_badge.pack(anchor="w", pady=(2, 0))
        self.server_info_lbl = tk.Label(card1, text="Giao thức: stdio (server.py)", bg=self.card_bg, fg=self.text_secondary, font=("Segoe UI", 8))
        self.server_info_lbl.pack(anchor="w")

        # Card 2: AutoCAD Status
        card2 = tk.Frame(cards_container, bg=self.card_bg)
        card2.grid(row=0, column=1, sticky="nsew", padx=10, pady=5)
        tk.Label(card2, text="KẾT NỐI AUTOCAD 2022", bg=self.card_bg, fg=self.text_secondary, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.acad_status_badge = tk.Label(card2, text="⏳ Đang kiểm tra...", bg=self.card_bg, fg=self.accent_yellow, font=("Segoe UI", 12, "bold"))
        self.acad_status_badge.pack(anchor="w", pady=(2, 0))
        self.acad_info_lbl = tk.Label(card2, text="Phiên bản: AutoCAD 2022 (R24.1)", bg=self.card_bg, fg=self.text_secondary, font=("Segoe UI", 8))
        self.acad_info_lbl.pack(anchor="w")

        # Card 3: Active Drawing Info
        card3 = tk.Frame(cards_container, bg=self.card_bg)
        card3.grid(row=0, column=2, sticky="nsew", padx=10, pady=5)
        tk.Label(card3, text="BẢN VẼ HIỆN HÀNH", bg=self.card_bg, fg=self.text_secondary, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.doc_name_lbl = tk.Label(card3, text="Chưa có bản vẽ", bg=self.card_bg, fg=self.text_primary, font=("Segoe UI", 11, "bold"))
        self.doc_name_lbl.pack(anchor="w", pady=(2, 0))
        self.doc_details_lbl = tk.Label(card3, text="Layers: 0 | Đối tượng: 0", bg=self.card_bg, fg=self.text_secondary, font=("Segoe UI", 8))
        self.doc_details_lbl.pack(anchor="w")

        # 3. Main Controls (Big Switch Button + Launch CAD + Auto Config)
        control_frame = ttk.Frame(self.root, padding="15 0 15 10")
        control_frame.pack(fill="x")

        btn_box = tk.Frame(control_frame, bg=self.bg_color)
        btn_box.pack(fill="x")

        # Nút to BẬT / TẮT SERVER
        self.toggle_btn = tk.Button(
            btn_box,
            text="🟢 BẬT MCP SERVER",
            bg="#2ecc71",
            fg="#ffffff",
            activebackground="#27ae60",
            activeforeground="#ffffff",
            font=("Segoe UI", 11, "bold"),
            relief="flat",
            bd=0,
            padx=18,
            pady=8,
            cursor="hand2",
            command=self.toggle_server
        )
        self.toggle_btn.pack(side="left", padx=(0, 8))

        # Nút Mở AutoCAD
        self.launch_acad_btn = tk.Button(
            btn_box,
            text="🚀 Mở AutoCAD 2022",
            bg="#34495e",
            fg="#ffffff",
            activebackground="#2c3e50",
            activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            bd=0,
            padx=12,
            pady=8,
            cursor="hand2",
            command=self.launch_autocad
        )
        self.launch_acad_btn.pack(side="left", padx=(0, 8))

        # Nút Quét lại kết nối
        self.refresh_btn = tk.Button(
            btn_box,
            text="🔄 Làm Mới Kết Nối",
            bg="#2c3e50",
            fg="#cdd6f4",
            activebackground="#1a252f",
            activeforeground="#ffffff",
            font=("Segoe UI", 9),
            relief="flat",
            bd=0,
            padx=10,
            pady=8,
            cursor="hand2",
            command=self.check_acad_status_manual
        )
        self.refresh_btn.pack(side="left", padx=(0, 8))

        # Nút Tự động cấu hình MCP
        self.config_btn = tk.Button(
            btn_box,
            text="⚙️ Cấu Hình MCP 1-Click",
            bg="#8e44ad",
            fg="#ffffff",
            activebackground="#732d91",
            activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            bd=0,
            padx=12,
            pady=8,
            cursor="hand2",
            command=self.auto_configure_mcp
        )
        self.config_btn.pack(side="right")

        # 4. Quick CAD Test Tools Bar
        quick_frame = ttk.Frame(self.root, padding="15 0 15 8")
        quick_frame.pack(fill="x")

        quick_box = tk.Frame(quick_frame, bg=self.card_bg, bd=1, relief="solid", highlightbackground=self.card_border)
        quick_box.pack(fill="x", ipady=5, ipadx=8)

        tk.Label(quick_box, text="⚡ THỬ NGHIỆM NHANH:", bg=self.card_bg, fg=self.accent_yellow, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(8, 10))

        # Quick Test Button 1: Vẽ hình vuông
        tk.Button(
            quick_box,
            text="📐 Vẽ Hình Vuông 100x100",
            bg="#313244",
            fg="#cdd6f4",
            activebackground="#45475a",
            activeforeground="#ffffff",
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            padx=8,
            pady=4,
            cursor="hand2",
            command=self.quick_test_draw_square
        ).pack(side="left", padx=4)

        # Quick Test Button 2: Vẽ 4 Cột Tròn
        tk.Button(
            quick_box,
            text="⭕ Vẽ 4 Tròn Cột Mẫu",
            bg="#313244",
            fg="#cdd6f4",
            activebackground="#45475a",
            activeforeground="#ffffff",
            font=("Segoe UI", 8),
            relief="flat",
            padx=8,
            pady=4,
            cursor="hand2",
            command=self.quick_test_draw_circles
        ).pack(side="left", padx=4)

        # Quick Test Button 3: Zoom Extents
        tk.Button(
            quick_box,
            text="🔍 Zoom Extents",
            bg="#313244",
            fg="#cdd6f4",
            activebackground="#45475a",
            activeforeground="#ffffff",
            font=("Segoe UI", 8),
            relief="flat",
            padx=8,
            pady=4,
            cursor="hand2",
            command=self.quick_test_zoom
        ).pack(side="left", padx=4)

        # Quick Test Button 4: Thống kê bản vẽ
        tk.Button(
            quick_box,
            text="📊 Thống Kê Đối Tượng",
            bg="#313244",
            fg="#cdd6f4",
            activebackground="#45475a",
            activeforeground="#ffffff",
            font=("Segoe UI", 8),
            relief="flat",
            padx=8,
            pady=4,
            cursor="hand2",
            command=self.quick_test_summary
        ).pack(side="left", padx=4)

        # 5. Live Console Log Frame
        log_frame = ttk.Frame(self.root, padding="15 0 15 15")
        log_frame.pack(fill="both", expand=True)

        log_header = tk.Frame(log_frame, bg=self.bg_color)
        log_header.pack(fill="x", pady=(0, 4))
        tk.Label(log_header, text="📋 NHẬT KÝ HOẠT ĐỘNG & LỆNH AI (LIVE CONSOLE LOGS):", bg=self.bg_color, fg=self.text_secondary, font=("Segoe UI", 9, "bold")).pack(side="left")

        tk.Button(
            log_header,
            text="🧹 Xóa Log",
            bg=self.bg_color,
            fg=self.text_secondary,
            activebackground=self.card_bg,
            activeforeground="#ffffff",
            font=("Segoe UI", 8),
            relief="flat",
            cursor="hand2",
            command=self.clear_logs
        ).pack(side="right")

        self.console = scrolledtext.ScrolledText(
            log_frame,
            bg=self.console_bg,
            fg=self.console_fg,
            insertbackground="#ffffff",
            font=("Consolas", 9),
            wrap="word",
            bd=1,
            relief="solid",
            highlightbackground=self.card_border
        )
        self.console.pack(fill="both", expand=True)

        # Tag styles trong console
        self.console.tag_config("SUCCESS", foreground=self.accent_green)
        self.console.tag_config("ERROR", foreground=self.accent_red)
        self.console.tag_config("INFO", foreground=self.accent_blue)
        self.console.tag_config("WARN", foreground=self.accent_yellow)
        self.console.tag_config("TIMESTAMP", foreground="#6c7086")

    # ==================== Logging Helpers ====================

    def log(self, message: str, tag: str = "INFO"):
        timestamp = time.strftime("[%H:%M:%S]")
        self.log_queue.put((timestamp, message, tag))

    def process_log_queue(self):
        while not self.log_queue.empty():
            try:
                timestamp, message, tag = self.log_queue.get_nowait()
                self.console.insert("end", f"{timestamp} ", "TIMESTAMP")
                self.console.insert("end", f"{message}\n", tag)
                self.console.see("end")
            except queue.Empty:
                break
        self.root.after(100, self.process_log_queue)

    def clear_logs(self):
        self.console.delete("1.0", "end")
        self.log("Đã làm sạch màn hình log.")

    # ==================== Server Control ====================

    def toggle_server(self):
        if not self.is_server_running:
            self.start_server()
        else:
            self.stop_server()

    def start_server(self):
        if not os.path.exists(SERVER_SCRIPT):
            messagebox.showerror("Lỗi", f"Không tìm thấy file server: {SERVER_SCRIPT}")
            return

        try:
            self.log("Đang khởi động AutoCAD MCP Server...", "INFO")

            # Khởi chạy server process
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"

            self.server_process = subprocess.Popen(
                [PYTHON_EXE, SERVER_SCRIPT],
                cwd=CURRENT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )

            self.is_server_running = True
            self.toggle_btn.configure(
                text="🔴 DỪNG MCP SERVER",
                bg="#e74c3c",
                activebackground="#c0392b"
            )
            self.server_status_badge.configure(text="🟢 ĐANG CHẠY (ON)", fg=self.accent_green)
            self.server_info_lbl.configure(text=f"PID: {self.server_process.pid} | Giao thức: stdio (Sẵn sàng)")
            self.log(f"✅ AutoCAD MCP Server đã khởi chạy thành công (PID: {self.server_process.pid})!", "SUCCESS")
            self.log("💡 Các mô hình AI như Antigravity/Claude Desktop giờ đây có thể gửi lệnh trực tiếp vào AutoCAD.", "SUCCESS")

            # Luồng đọc logs từ server process
            threading.Thread(target=self.read_server_stdout, daemon=True).start()
            threading.Thread(target=self.read_server_stderr, daemon=True).start()

        except Exception as e:
            self.log(f"❌ Không thể khởi động server: {e}", "ERROR")
            messagebox.showerror("Lỗi", f"Không thể khởi động MCP Server:\n{e}")

    def stop_server(self):
        if self.server_process:
            try:
                self.log("Đang dừng AutoCAD MCP Server...", "WARN")
                self.server_process.terminate()
                self.server_process.wait(timeout=2)
            except Exception:
                try:
                    self.server_process.kill()
                except Exception:
                    pass
            self.server_process = None

        self.is_server_running = False
        self.toggle_btn.configure(
            text="🟢 BẬT MCP SERVER",
            bg="#2ecc71",
            activebackground="#27ae60"
        )
        self.server_status_badge.configure(text="🔴 ĐÃ DỪNG (OFF)", fg=self.accent_red)
        self.server_info_lbl.configure(text="Giao thức: stdio (server.py)")
        self.log("⏹️ AutoCAD MCP Server đã dừng.", "WARN")

    def read_server_stdout(self):
        if not self.server_process or not self.server_process.stdout:
            return
        for line in iter(self.server_process.stdout.readline, ''):
            if line:
                self.log(f"[MCP STDOUT] {line.strip()}", "INFO")

    def read_server_stderr(self):
        if not self.server_process or not self.server_process.stderr:
            return
        for line in iter(self.server_process.stderr.readline, ''):
            if line:
                self.log(f"[MCP STDERR] {line.strip()}", "WARN")

    # ==================== AutoCAD Background Monitor ====================

    def acad_monitor_loop(self):
        """Vòng lặp chạy nền kiểm tra định kỳ trạng thái AutoCAD."""
        while not self.stop_monitoring:
            self.check_acad_status_quiet()
            time.sleep(4)

    def check_acad_status_quiet(self):
        try:
            from autocad_client import AutoCADClient
            client = AutoCADClient()
            doc_info = client.get_document_info()

            self.is_acad_connected = True
            doc_name = doc_info.get("name", "Bản vẽ chưa đặt tên")
            layers_count = doc_info.get("layers_count", 0)
            entities_count = doc_info.get("model_space_entities_count", 0)

            self.root.after(0, lambda: self.update_acad_ui(True, doc_name, layers_count, entities_count))
        except Exception:
            self.is_acad_connected = False
            self.root.after(0, lambda: self.update_acad_ui(False, None, 0, 0))

    def update_acad_ui(self, connected: bool, doc_name: str = None, layers: int = 0, entities: int = 0):
        if connected:
            self.acad_status_badge.configure(text="🟢 ĐÃ KẾT NỐI", fg=self.accent_green)
            self.acad_info_lbl.configure(text="AutoCAD 2022 đang mở & sẵn sàng")
            if doc_name:
                self.doc_name_lbl.configure(text=f"📄 {doc_name}", fg="#ffffff")
                self.doc_details_lbl.configure(text=f"Layers: {layers} | Đối tượng: {entities}")
            else:
                self.doc_name_lbl.configure(text="Chưa mở bản vẽ (.dwg)", fg=self.accent_yellow)
                self.doc_details_lbl.configure(text="Hãy tạo mới hoặc mở file DWG")
        else:
            self.acad_status_badge.configure(text="🔴 CHƯA KẾT NỐI", fg=self.accent_red)
            self.acad_info_lbl.configure(text="AutoCAD 2022 chưa chạy hoặc chưa mở file")
            self.doc_name_lbl.configure(text="Không có bản vẽ", fg=self.text_secondary)
            self.doc_details_lbl.configure(text="Layers: 0 | Đối tượng: 0")

    def check_acad_status_manual(self):
        self.log("🔍 Đang quét và kiểm tra kết nối AutoCAD 2022...", "INFO")
        threading.Thread(target=self._do_check_manual, daemon=True).start()

    def _do_check_manual(self):
        try:
            from autocad_client import AutoCADClient
            client = AutoCADClient()
            doc_info = client.get_document_info()
            layers = client.list_layers()

            self.log("✅ Đã kết nối thành công tới AutoCAD 2022!", "SUCCESS")
            self.log(f"   - Bản vẽ: {doc_info.get('name')} ({doc_info.get('full_name')})", "SUCCESS")
            self.log(f"   - Số đối tượng ModelSpace: {doc_info.get('model_space_entities_count')}", "INFO")
            self.log(f"   - Số Layer: {len(layers)} (Hiện hành: {doc_info.get('active_layer')})", "INFO")
            self.check_acad_status_quiet()
        except Exception as e:
            self.log(f"❌ Kết nối AutoCAD thất bại: {e}", "ERROR")
            self.log("💡 Gợi ý: Hãy bấm nút '🚀 Mở AutoCAD 2022' hoặc mở phần mềm AutoCAD trên máy và tạo một bản vẽ mới.", "WARN")

    def launch_autocad(self):
        self.log("🚀 Đang khởi chạy phần mềm AutoCAD 2022...", "INFO")
        def _launch():
            try:
                # Tìm đường dẫn acad.exe mặc định
                acad_paths = [
                    r"C:\Program Files\Autodesk\AutoCAD 2022\acad.exe",
                    r"C:\Program Files\Autodesk\AutoCAD 2021\acad.exe",
                    r"C:\Program Files\Autodesk\AutoCAD 2023\acad.exe",
                ]
                found_path = None
                for p in acad_paths:
                    if os.path.exists(p):
                        found_path = p
                        break

                if found_path:
                    subprocess.Popen([found_path])
                    self.log(f"✅ Đã gửi lệnh mở AutoCAD từ: {found_path}", "SUCCESS")
                else:
                    # Thử COM Dispatch
                    import pythoncom
                    import win32com.client
                    pythoncom.CoInitialize()
                    app = win32com.client.Dispatch("AutoCAD.Application.24.1")
                    app.Visible = True
                    self.log("✅ Đã khởi động AutoCAD 2022 qua COM API!", "SUCCESS")
            except Exception as e:
                self.log(f"❌ Không thể tự động mở AutoCAD: {e}", "ERROR")
        threading.Thread(target=_launch, daemon=True).start()

    # ==================== 1-Click Auto Configuration ====================

    def auto_configure_mcp(self):
        """Tự động ghi cấu hình MCP vào file .mcp.json và Claude Desktop config."""
        self.log("⚙️ Đang thực hiện cấu hình tự động MCP cho các mô hình AI...", "INFO")

        # Đảm bảo dùng python.exe (không dùng pythonw.exe vì stdio MCP server cần stdout)
        python_exe = sys.executable.replace("pythonw.exe", "python.exe")

        mcp_entry = {
            "command": python_exe,
            "args": [SERVER_SCRIPT],
            "cwd": CURRENT_DIR,
            "env": {
                "PYTHONUNBUFFERED": "1",
                "PYTHONIOENCODING": "utf-8"
            }
        }

        # 1. Ghi vào workspace .mcp.json
        local_mcp_file = os.path.join(PROJECT_ROOT, ".mcp.json")
        try:
            cfg = {}
            if os.path.exists(local_mcp_file):
                try:
                    with open(local_mcp_file, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    cfg = {}
            if "mcpServers" not in cfg:
                cfg["mcpServers"] = {}
            cfg["mcpServers"]["autocad-2022"] = mcp_entry
            with open(local_mcp_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            self.log(f"✅ Đã cập nhật cấu hình MCP workspace: {local_mcp_file}", "SUCCESS")
        except Exception as e:
            self.log(f"⚠️ Không thể cập nhật .mcp.json: {e}", "WARN")

        # 2. Cố gắng ghi vào Claude Desktop config nếu có
        appdata = os.getenv("APPDATA", "")
        if appdata:
            claude_cfg_dir = os.path.join(appdata, "Claude")
            claude_cfg_file = os.path.join(claude_cfg_dir, "claude_desktop_config.json")
            try:
                os.makedirs(claude_cfg_dir, exist_ok=True)
                c_cfg = {}
                if os.path.exists(claude_cfg_file):
                    try:
                        with open(claude_cfg_file, "r", encoding="utf-8") as f:
                            c_cfg = json.load(f)
                    except Exception:
                        c_cfg = {}
                if "mcpServers" not in c_cfg:
                    c_cfg["mcpServers"] = {}
                c_cfg["mcpServers"]["autocad-2022"] = mcp_entry
                with open(claude_cfg_file, "w", encoding="utf-8") as f:
                    json.dump(c_cfg, f, indent=2)
                self.log(f"✅ Đã cấu hình cho Claude Desktop: {claude_cfg_file}", "SUCCESS")
            except Exception as e:
                self.log(f"⚠️ Bỏ qua Claude Desktop config ({e})", "WARN")

        messagebox.showinfo(
            "Cấu Hình Hoàn Tất",
            "Đã tự động cập nhật cấu hình MCP Server cho AutoCAD 2022!\n\n"
            "Các trợ lý AI (Antigravity, Claude Desktop, Cursor) có thể nhận diện và sử dụng ngay các công cụ AutoCAD."
        )

    # ==================== Quick Test Actions ====================

    def quick_test_draw_square(self):
        self.log("📐 Đang gửi lệnh vẽ thử nghiệm Hình Vuông 100x100...", "INFO")
        def _task():
            try:
                from autocad_client import AutoCADClient
                client = AutoCADClient()
                client.ensure_connected()

                # Tạo layer TEST_MCP
                client.create_or_set_layer("TEST_MCP_SQUARE", color=1, activate=True)

                # Vẽ hình vuông 100x100
                client.add_rectangle((0, 0), 100, 100, layer="TEST_MCP_SQUARE", color=1)

                # Thêm chữ Text
                client.add_text("TEST MCP: HINH VUONG 100x100", (10, 50, 0), height=5.0, layer="TEST_MCP_SQUARE", color=2)

                # Thêm Dim
                client.add_aligned_dimension((0, 0, 0), (100, 0, 0), (50, -15, 0), layer="TEST_MCP_SQUARE")
                client.add_aligned_dimension((100, 0, 0), (100, 100, 0), (115, 50, 0), layer="TEST_MCP_SQUARE")

                # Zoom
                client.zoom_extents()

                self.log("✅ Đã vẽ thành công Hình Vuông 100x100 kèm Text & Kích Thước vào AutoCAD!", "SUCCESS")
                self.check_acad_status_quiet()
            except Exception as e:
                self.log(f"❌ Lỗi khi vẽ hình vuông: {e}", "ERROR")
        threading.Thread(target=_task, daemon=True).start()

    def quick_test_draw_circles(self):
        self.log("⭕ Đang gửi lệnh vẽ 4 Cột Tròn...", "INFO")
        def _task():
            try:
                from autocad_client import AutoCADClient
                client = AutoCADClient()
                client.ensure_connected()

                client.create_or_set_layer("COT_TRON_DEMO", color=3, activate=True)
                centers = [(0, 0), (200, 0), (200, 200), (0, 200)]
                for idx, (cx, cy) in enumerate(centers, 1):
                    client.add_circle((cx, cy, 0), radius=25.0, layer="COT_TRON_DEMO", color=3)
                    client.add_text(f"C{idx}", (cx - 5, cy - 3, 0), height=6.0, layer="COT_TRON_DEMO", color=7)
                client.zoom_extents()
                self.log("✅ Đã vẽ thành công 4 Cột Tròn (R=25) tại các góc (0,0), (200,0), (200,200), (0,200)!", "SUCCESS")
                self.check_acad_status_quiet()
            except Exception as e:
                self.log(f"❌ Lỗi khi vẽ cột tròn: {e}", "ERROR")
        threading.Thread(target=_task, daemon=True).start()

    def quick_test_zoom(self):
        def _task():
            try:
                from autocad_client import AutoCADClient
                client = AutoCADClient()
                client.zoom_extents()
                self.log("✅ Đã Zoom Extents toàn bộ bản vẽ!", "SUCCESS")
            except Exception as e:
                self.log(f"❌ Lỗi Zoom: {e}", "ERROR")
        threading.Thread(target=_task, daemon=True).start()

    def quick_test_summary(self):
        def _task():
            try:
                from autocad_client import AutoCADClient
                client = AutoCADClient()
                summary = client.get_drawing_summary()
                self.log("📊 Thống kê chi tiết bản vẽ hiện tại:", "SUCCESS")
                self.log(f"   - Tên bản vẽ: {summary.get('drawing_name')}", "INFO")
                self.log(f"   - Tổng số đối tượng: {summary.get('total_entities')}", "INFO")
                self.log(f"   - Chi tiết theo loại: {json.dumps(summary.get('entity_breakdown', {}), ensure_ascii=False)}", "INFO")
                self.log(f"   - Tổng số Layer: {summary.get('layers_count')}", "INFO")
            except Exception as e:
                self.log(f"❌ Lỗi thống kê: {e}", "ERROR")
        threading.Thread(target=_task, daemon=True).start()

    # ==================== Exit Cleanup ====================

    def on_close(self):
        self.stop_monitoring = True
        if self.server_process:
            try:
                self.server_process.terminate()
            except Exception:
                pass
        self.root.destroy()

def main():
    root = tk.Tk()
    AutoCADMCPApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
