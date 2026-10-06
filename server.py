import socket
import os

def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    host = '0.0.0.0'
    port = 9999
    
    server_socket.bind((host, port))
    
    server_socket.listen(1)
    print(f"[*] Сервер запущен и слушает на {host}:{port}")
    
    client_socket, addr = server_socket.accept()
    print(f"[*] Получено подключение от {addr[0]}:{addr[1]}")
    
    while True:
        command = input(">> ")
        
        if command.lower() == 'exit':
            break
        
        if command.startswith('upload '):
            client_socket.send(command.encode('utf-8'))
            filepath = command.split(' ', 1)[1]
            if os.path.exists(filepath):
                with open(filepath, 'rb') as f:
                    while True:
                        bytes_read = f.read(4096)
                        if not bytes_read:
                            break
                        client_socket.sendall(bytes_read)
                client_socket.send(b"DONE")
                print(client_socket.recv(1024).decode('utf-8'))
            else:
                print("Файл не найден.")
                client_socket.send(b"FILE NOT FOUND")

        elif command.startswith('download '):
            client_socket.send(command.encode('utf-8'))
            filepath = command.split(' ', 1)[1]
            with open(filepath, 'wb') as f:
                while True:
                    bytes_read = client_socket.recv(4096)
                    if bytes_read.endswith(b"DONE"):
                        f.write(bytes_read[:-4])
                        break
                    elif bytes_read == b"FILE NOT FOUND":
                        print("Файл не найден на удаленной машине.")
                        os.remove(filepath)
                        break
                    f.write(bytes_read)
            print("Файл успешно скачан.")

        else:
            client_socket.send(command.encode('utf-8'))
            
            response = client_socket.recv(4096).decode('utf-8')
            print(response)
        
    client_socket.close()
    server_socket.close()

if __name__ == "__main__":
    main()
