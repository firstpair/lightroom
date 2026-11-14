#!/bin/bash
# Receive a closed Lightroom Classic catalog from a portable volume by plain copy.
# See docs/SHUTTLE-RECEIVE.md.
#
#   shuttle_receive.sh check  SRC_DIR DST_DIR NAME   run the checks only
#   shuttle_receive.sh copy   SRC_DIR DST_DIR NAME   checks, set the old copy aside, copy, compare
#   shuttle_receive.sh verify SRC_DIR DST_DIR NAME   compare sha256 only
#
# SRC_DIR  catalog folder on the portable volume (holds NAME.lrcat)
# DST_DIR  catalog folder on this Mac (may hold an older copy, or not exist)
# NAME     catalog name without ".lrcat"
#
# Copies NAME.lrcat, NAME.lrcat-data, "NAME Helper.lrdata" and "NAME Sync.lrdata".
# Previews and Smart Previews in DST_DIR are left where they are. Nothing is deleted:
# the older copy is moved to DST_DIR/../NAME-before-<time>.

set -u
MODE=${1:-}; S=${2:-}; D=${3:-}; N=${4:-}
die() { echo "STOP: $*" >&2; exit 1; }
case "$MODE" in check|copy|verify) ;; *) die "usage: $0 check|copy|verify SRC_DIR DST_DIR NAME" ;; esac
[ -n "$S" ] && [ -n "$D" ] && [ -n "$N" ] || die "usage: $0 check|copy|verify SRC_DIR DST_DIR NAME"
S=${S%/}; D=${D%/}

ITEMS=("$N.lrcat" "$N.lrcat-data" "$N Helper.lrdata" "$N Sync.lrdata")
SIDE=("$N.lrcat-wal" "$N.lrcat-shm" "$N.lrcat-journal" "$N.lrcat.lock")

# Classic must be closed, whichever build.
pgrep -f 'Lightroom Classic[^/]*\.app/Contents/MacOS/Adobe Lightroom' >/dev/null && die "Classic is running"

# Source: a closed catalog.
[ -f "$S/$N.lrcat" ] || die "$S/$N.lrcat is missing (is the volume mounted?)"
[ -e "$S/$N.lrcat.lock" ] && die "the source catalog has a .lock file"
for j in wal journal; do [ -s "$S/$N.lrcat-$j" ] && die "source $N.lrcat-$j has content"; done
PRESENT=()
for i in "${ITEMS[@]}"; do
  [ -L "$S/$i" ] && die "source $i is a link"
  [ -e "$S/$i" ] && PRESENT+=("$i")
done

# Destination: not open, and on a different volume from the source.
if [ -d "$D" ]; then
  [ -e "$D/$N.lrcat.lock" ] && die "the destination catalog has a .lock file"
  for j in wal journal; do [ -s "$D/$N.lrcat-$j" ] && die "destination $N.lrcat-$j has content; open and quit that catalog normally first"; done
  if [ -e "$D/$N.lrcat" ]; then
    open=$(lsof -- "$D/$N.lrcat" 2>/dev/null | tail -n +2)
    [ -n "$open" ] && { echo "$open" >&2; die "the destination catalog is open"; }
  fi
fi
[ "$(cd "$S" && pwd -P)" = "$(cd "$D" 2>/dev/null && pwd -P)" ] && die "source and destination are the same folder"

hashes() {  # sha256 of every file under the copied items, in a stable order
  (cd "$1" && find "${PRESENT[@]}" -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256)
}
compare() {
  T=$(mktemp -d) || die "no temporary directory"
  echo "comparing sha256 (this reads both copies in full)"
  hashes "$S" > "$T/src" || die "could not read the source"
  hashes "$D" > "$T/dst" || die "could not read the destination"
  n=$(wc -l < "$T/src" | tr -d ' ')
  if cmp -s "$T/src" "$T/dst"; then
    echo "$n files compared, 0 differ"; rm -rf "$T"; return 0
  fi
  echo "DIFFERENT; first lines:"; diff "$T/src" "$T/dst" | head -20
  echo "full lists kept in $T"; return 1
}

echo "checks passed: Classic closed, source closed, destination not open"
echo "items: ${PRESENT[*]}"
[ "$MODE" = check ] && exit 0
if [ "$MODE" = verify ]; then compare; exit $?; fi

# Space: the copy must fit with 10 GB to spare.
need=$(cd "$S" && du -sk "${PRESENT[@]}" | awk '{s+=$1} END {print s}')
mkdir -p "$D" || die "cannot create $D"
free=$(df -k "$D" | awk 'NR==2 {print $4}')
[ "$free" -gt $((need + 10485760)) ] || die "not enough space: need $((need/1048576)) GB plus 10 GB, free $((free/1048576)) GB"

# Set the older copy aside (same volume, so this is a rename).
OLD="$(dirname "$D")/$N-before-$(date +%Y%m%d-%H%M%S)"
moved=0
for i in "${ITEMS[@]}" "${SIDE[@]}"; do
  if [ -e "$D/$i" ] || [ -L "$D/$i" ]; then
    mkdir -p "$OLD" || die "cannot create $OLD"
    mv "$D/$i" "$OLD/" || die "could not move $i aside"
    moved=$((moved + 1))
  fi
done
[ "$moved" -gt 0 ] && echo "older copy set aside in $OLD ($moved items)"

echo "copying $((need/1048576)) GB"
for i in "${PRESENT[@]}"; do
  caffeinate -i cp -Rp "$S/$i" "$D/" || die "copy of $i failed; the older copy is in $OLD"
done
compare || die "the copy does not match; do not open it. The older copy is in $OLD"
echo "received. Open $D/$N.lrcat only after the steps in docs/SHUTTLE-RECEIVE.md"
