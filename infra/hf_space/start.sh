#!/bin/sh
# Start every GigBid service inside one container (Hugging Face Space). The API listens on 7860.
set -e
PGBIN=$(ls -d /usr/lib/postgresql/*/bin | head -1)
PGDATA=/home/user/pgdata
if [ ! -d "$PGDATA" ]; then
  "$PGBIN/initdb" -D "$PGDATA" -U user --auth=trust >/dev/null
fi
"$PGBIN/pg_ctl" -D "$PGDATA" -o "-k /tmp -c listen_addresses=localhost" -l /home/user/pg.log start
sleep 3
"$PGBIN/createdb" -h localhost -U user gigbid 2>/dev/null || true
redis-server --daemonize yes --dir /home/user
GIGSIM_STATE=/home/user/gigsim_state.json uvicorn gigsim.app:app --host 127.0.0.1 --port 8081 &
python -m scripts.run_mcp_servers &
sleep 15
python -m worker.main &
exec python -m scripts.serve_api --port 7860
