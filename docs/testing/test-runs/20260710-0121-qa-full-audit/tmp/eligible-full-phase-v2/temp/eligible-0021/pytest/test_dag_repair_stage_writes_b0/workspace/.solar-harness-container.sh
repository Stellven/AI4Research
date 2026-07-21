#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

rm -f /etc/apt/sources.list.d/solar-pmars-src.list /etc/apt/sources.list.d/deb-src.list
printf '%s\n' 'deb-src http://deb.debian.org/debian stable main' > /etc/apt/sources.list.d/solar-pmars-src.list

apt-get update
apt-get install -y --no-install-recommends build-essential libncurses-dev ca-certificates dpkg-dev

cd /app
apt-get source pmars
cd /app/pmars-*/src
sed -i 's/-DXWINGRAPHX//g' Makefile
sed -i 's/^LIB *=.*/LIB = -lncurses/' Makefile
make clean
make
install -m 0755 pmars /usr/local/bin/pmars

test -x /usr/local/bin/pmars
if ldd /usr/local/bin/pmars | grep -Eq 'libX11|libXt|libXext|libXaw'; then
  echo 'pmars links against X11 libraries' >&2
  exit 1
fi
pmars -b -r 50 -f /app/flashpaper.red /app/rave.red | tail -n 1 | grep -E '^Results: [0-9]+ [0-9]+ [0-9]+$'
