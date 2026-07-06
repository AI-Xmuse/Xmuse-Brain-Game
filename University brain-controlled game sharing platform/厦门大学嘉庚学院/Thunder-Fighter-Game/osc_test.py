"""OSC test - listens on 127.0.0.1:7000 for /acc data."""
from pythonosc import dispatcher, osc_server

HOST = "127.0.0.1"
PORT = 7000


def acc_handler(address, *args):
    print(f"[ACC] {address} | args: {list(args)}")


def default_handler(address, *args):
    print(f"[OTHER] {address} | args: {list(args)}")


def main():
    disp = dispatcher.Dispatcher()
    disp.map("/hab/acc", acc_handler)
    disp.set_default_handler(default_handler)

    try:
        server = osc_server.ThreadingOSCUDPServer((HOST, PORT), disp)
        print(f"Listening on {HOST}:{PORT} for /hab/acc ... (Ctrl+C to stop)")
        server.serve_forever()
    except OSError as e:
        print(f"Bind failed (port {PORT} may be in use): {e}")
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
