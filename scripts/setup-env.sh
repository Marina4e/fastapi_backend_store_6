#!/usr/bin/env sh
set -eu

if [ -f ".env" ]; then
  echo ".env already exists. Nothing to copy."
  exit 0
fi

if [ ! -f ".env.example" ]; then
  echo ".env.example was not found." >&2
  exit 1
fi

cp ".env.example" ".env"
echo ".env created from .env.example."
