#!/bin/sh
set -eu
createdb --username "$POSTGRES_USER" --owner "$POSTGRES_USER" "${POSTGRES_DB}_test"
