"""CLI entry point. Import-safe; uvicorn runs only from main()."""
import argparse


def main():
    parser = argparse.ArgumentParser(description="Independent CrisisFusion scoring plugin")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8811, type=int)
    parser.add_argument("--db", default="work/scoring.sqlite3")
    parser.add_argument("--allow-host", action="append", default=None,
                        help="Explicit allowed HTTP hostname (repeatable); requires host-managed authentication remotely")
    args = parser.parse_args()
    from . import create_app
    import uvicorn
    uvicorn.run(create_app(args.db, args.allow_host), host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
