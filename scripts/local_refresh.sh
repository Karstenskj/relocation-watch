#!/bin/bash
# Kører opdateringen fra denne Mac.
#
# Formålet er de kilder der afviser GitHubs servere, først og fremmest DriveNow, som
# Cloudflare kun lukker ind fra en almindelig internetforbindelse. GitHub kører de øvrige
# fem kilder fire gange i døgnet uanset om maskinen er tændt, så det her er et supplement,
# ikke en erstatning.
#
# Efter datoen i data.json (window.stopAfter) afinstallerer scriptet sig selv.
#
# Slå den fra i utide med:
#   launchctl bootout gui/$(id -u)/dk.cpha.relocation-watch
set -u
cd "$(dirname "$0")/.." || exit 1
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

LABEL="dk.cpha.relocation-watch"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }

# Uden netværk er der intet at gøre.
curl -sf --max-time 15 -o /dev/null https://api.github.com || { log "intet netværk, springer over"; exit 0; }

# Rør aldrig uafsluttet arbejde. Ligger der lokale ændringer, gør vi ingenting.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  log "der ligger lokale ændringer i mappen, springer over"
  exit 0
fi

git pull --rebase --quiet origin main || { log "kunne ikke hente fra GitHub, springer over"; git rebase --abort 2>/dev/null; exit 0; }

python3 scripts/refresh.py || { log "opdateringen fejlede"; exit 1; }

git add -A
if git diff --cached --quiet; then
  log "ingen ændringer"
else
  git commit --quiet -m "tjek: automatisk opdatering fra Karstens Mac (inkl. DriveNow)"
  if git push --quiet origin main; then log "pushet"; else log "kunne ikke pushe"; fi
fi

# Er sidste brugsdag passeret, afmelder vi os selv. refresh.py har allerede skrevet
# den afsluttende status, og den er pushet ovenfor.
STOPPED=$(python3 -c "
import json, sys
sys.path.insert(0, 'scripts')
from common import past_cutoff
print('yes' if past_cutoff(json.load(open('data.json'))['window']) else 'no')
" 2>/dev/null || echo no)

if [ "$STOPPED" = "yes" ]; then
  log "sidste brugsdag er passeret, afinstallerer det lokale job"
  if [ -f "$PLIST" ]; then
    mv "$PLIST" "$PLIST.slukket" && log "flyttede $PLIST til $PLIST.slukket"
  fi
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null && log "jobbet er afmeldt"
fi
