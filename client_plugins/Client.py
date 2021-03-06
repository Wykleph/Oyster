import shlex
import sys
import socket
import subprocess
from os.path import realpath
from code import InteractiveConsole


class FileCache:
    """
    Cache the stdout/stderr text so we can analyze it before returning it.
    """
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
    """
    Wrapper around InteractiveConsole so stdout and stderr can be intercepted easily.
    """
    def __init__(self, locals=None, filename='<console>'):
        self.stdout = sys.stdout
        self.stderr = sys.stderr
        self.cache = FileCache()
        super(Shell, self).__init__(locals=locals, filename=filename)
        return

    def get_output(self):
        sys.stdout = self.cache
        sys.stderr = self.cache

    def return_output(self):
        sys.stdout = self.stdout
        sys.stderr = self.stderr

    def push(self, line):
        self.get_output()
        InteractiveConsole.push(self, line)
        self.return_output()
        output = self.cache.flush().strip()
        print(output)
        return output


class Plugin(object):
    """
    Client v1.0

    Plugin made for handling client-based commands or commands that have to do with
    the `Client` object.

    Invocation:

        client

    Commands:

        client -i               -   Enter an interactive Python console.
                                    Use `exit()` to exit.  The `Client`
                                    object is accessible through the
                                    `client` variable when in the
                                    console.  Any changes will persist.

        client -s {key} {value} -   Basically a simple way to set an
                                    attribute on the `Client` object
                                    quickly.  Anything complex should
                                    use the interactive shell.

        client -g {key}         -   Wrapper around `getattr` for the
                                    `Client` object.

        client -r               -   Reboot the `client.py` script.
                                    Any attributes changed

        client -sh              -   Shutdown the client.

    Example:

        <127.0.0.1> /Users/user/Oyster> client -i
        |>>> client.port
        6667
        |>>> client.port = 6668
        |>>> x
        Traceback (most recent call last):
          File "/Users/sanctuary/Dropbox/Python/Oyster/common.py", line 114, in run_plugin
            result = plugin.run(self, command)
        TypeError: run() missing 1 required positional argument: 'data'

        During handling of the above exception, another exception occurred:

        Traceback (most recent call last):
          File "< Interactive Python Console >", line 1, in <module>
        NameError: name 'x' is not defined
        |>>>
    """

    version = 'v1.0'
    invocation = 'client'
    enabled = True

    def run(self, client, data):
        args = shlex.split(data)

        if not args:
            client.server_print('< The `client` command requires an argument. >')

        # Create an interactive shell for the server.
        if args[0] == '-i':
            # Tell the server the client got the command.
            client.send_data('')
            return Plugin.python_shell(client, data)

        # Set an attribute on the Client instance.
        if args[0] == '-s':
            try:
                key = args[1]
            except IndexError:
                client.server_print('< `-s`(setattr) requires a `key`. >')
                return

            # If there is not second argument, assume it should be set to
            # a blank string. This
            try:
                value = args[2]
            except IndexError:
                value = ''

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

        # Restart the `client.py` script.
        if args[0] == '-r':
            client.send_data('')
            Plugin.reboot_client(client)
            sys.exit()

        # Shutdown the `client.py` script.
        if args[0] == '-sh':
            client.send_data('')
            sys.exit()

        # Use an interactive shell to capture the output of the `help` command.
        # Kind of hacky, but since the `Shell` class is already available I don't
        # see why not.
        shell = Shell(locals={'client': client, 'Plugin': Plugin, 'self': self})
        result = shell.push('help(Plugin)')

        client.server_print(result)
        return

    @staticmethod
    def python_shell(client, data):
        """
        The main loop for the custom interactive python shell.

        :param client:
        :param data:
        :return:
        """

        # Create a InteractiveConsole instance.
        l = {
            'client': client,
            'data': data,
            '__file__': __file__,
            '__name__': __name__,
            '__package__': __package__
        }
        console = Shell(filename='< Remote Python Console >', locals=l)
        while True:
            # Receive a command.
            command = client.sock.receive_data()
            # Check for the exit.
            if command == 'exit()':
                client.server_print('< InteractiveConsole shutting down. >')
                break
            # Push the command onto the InteractiveConsole instance.
            output = console.push(command)
            # Send the result back.
            client.send_data(output)
        return

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

