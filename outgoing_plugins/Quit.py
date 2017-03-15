from common import LoopControl


class Plugin(object):
    version = 'v1.0'
    invocation = ['quit', 'exit']
    enabled = True

    def run(self, server, data):
        # print('< Detaching from client... >')

        try:
            server.connection_mgr.close_connection(server.connection_mgr.current_connection.ip)
        except (BrokenPipeError, OSError) as err_msg:
            server.connection_mgr.remove_connection(server.connection_mgr.current_connection)
            server.connection_mgr.current_connection = None
            return LoopControl.should_break()

        server.connection_mgr.remove_connection(server.connection_mgr.current_connection)
        server.connection_mgr.current_connection = None

        return LoopControl.should_break()