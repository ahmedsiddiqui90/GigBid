#!/bin/sh
# Assemble and push the Hugging Face Space repo (Dockerfile + README front matter at the root).
# Usage: HF_USER=<user> HF_TOKEN=<write token> sh scripts/deploy_hf.sh [space-name]
# The token is passed in the push URL only for this command and is not stored in the repo or git config.
set -e
SPACE=${1:-gigbid}
: "${HF_USER:?set HF_USER}"; : "${HF_TOKEN:?set HF_TOKEN}"
ROOT=$(cd "$(dirname "$0")/.." && pwd)
STAGE=$(mktemp -d)
cd "$ROOT"
git archive --format=tar HEAD | tar -x -C "$STAGE"
cp infra/hf_space/Dockerfile "$STAGE/Dockerfile"
cp infra/hf_space/README.md "$STAGE/README.md"
rm -rf "$STAGE/docs/images" "$STAGE/docs/Assignment-II_AI-4016-GigBid.pdf"
cd "$STAGE"
git init -q -b main
git add -A
git -c user.name="$HF_USER" -c user.email="$HF_USER@users.noreply.huggingface.co" commit -qm "Deploy GigBid"
git push -f "https://$HF_USER:$HF_TOKEN@huggingface.co/spaces/$HF_USER/$SPACE" main
echo "Pushed. Build logs: https://huggingface.co/spaces/$HF_USER/$SPACE  App: https://$HF_USER-$SPACE.hf.space"
