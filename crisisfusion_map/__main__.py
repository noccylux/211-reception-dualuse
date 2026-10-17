import argparse


def main():
    parser=argparse.ArgumentParser(description="CrisisFusion independent map plugin")
    parser.add_argument("--host",default="127.0.0.1")
    parser.add_argument("--port",type=int,default=8812)
    parser.add_argument("--db",default="work/map.sqlite3")
    args=parser.parse_args()
    if args.host not in {"127.0.0.1","localhost","::1"}:
        parser.error("CLI is loopback only; mount create_app with host authentication for remote deployment")
    import uvicorn
    from . import create_app
    uvicorn.run(create_app(db_path=args.db),host=args.host,port=args.port)


if __name__ == "__main__":
    main()
