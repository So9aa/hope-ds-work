#!/bin/bash
set +e

REPO_NAME="hope-ds-work"
WEBHOOK_URL="${DISCORD_WEBHOOK_URL:-https://discordapp.com/api/webhooks/1553463314422698085/tmWHGyzq7leGIFI1km9VbvnkVRsTexrL-JOsdPVoWoMR1AF7sfHVcx-zbf_DFbW2BEMj}"

if [ "$#" -eq 0 ]; then
  echo "Usage: $0 <command> [args...]" >&2
  exit 2
fi

"$@"
status=$?

if [ "$status" -eq 0 ]; then
  python3 /workspaces/hope-ds-work/discord_lunch_logger.py \
    --status done \
    --exit-code "$status" \
    --detail "Command: $*" \
    --repo "$REPO_NAME" \
    --webhook "$WEBHOOK_URL"
else
  python3 /workspaces/hope-ds-work/discord_lunch_logger.py \
    --status failed \
    --exit-code "$status" \
    --detail "Command: $*" \
    --repo "$REPO_NAME" \
    --webhook "$WEBHOOK_URL"
fi

exit "$status"
