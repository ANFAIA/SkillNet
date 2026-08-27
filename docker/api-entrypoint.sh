#!/bin/sh
# Make the mounted data volumes writable by the unprivileged user, then drop to it.
#
# The image creates /data/uploads, /data/media_assets and /data/tts_cache owned by
# `skillnet` so a NEW named volume inherits that owner. Docker only seeds a volume the
# first time it creates it, so a volume that predates that fix stays root:root forever
# and rebuilding the image does not touch it: every podcast and every infographic keeps
# dying on `PermissionError: [Errno 13] Permission denied: '/data/media_assets/...'`.
# Reported from a real deployment. Fixing ownership at start is what makes the repair
# reach volumes that already exist.
#
# Started as root, this drops to `skillnet` via gosu. Started as anyone else (a compose
# file pinning `user:`), it skips the repair and execs straight through, so nothing here
# forces the container to run privileged.
set -e

if [ "$(id -u)" = "0" ]; then
    for dir in /data/uploads /data/media_assets /data/tts_cache; do
        mkdir -p "$dir"
        # Look INSIDE, not just at the mount point. `docker compose exec` runs as root
        # here, so a seed can leave a root-owned subdirectory (podcast_cache is the one
        # that bites) under a correctly-owned volume; a check that stopped at the top
        # would declare that healthy and leave the app unable to write for good.
        # `-print -quit` stops at the first offender, so a healthy volume costs a walk
        # that ends on its first entry rather than a chown over every stored asset.
        if [ -n "$(find "$dir" ! -user skillnet -print -quit 2>/dev/null)" ]; then
            echo "entrypoint: repairing ownership of $dir" >&2
            chown -R skillnet:skillnet "$dir" || true
        fi
    done
    exec gosu skillnet "$@"
fi

exec "$@"
