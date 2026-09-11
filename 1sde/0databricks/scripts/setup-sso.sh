#!/usr/bin/env bash
# Finish the IAM Identity Center setup for the edgar project account.
#
# PREREQUISITE (console, management account — see the banner this prints):
#   IAM Identity Center must already be enabled as an ORGANIZATION instance,
#   in any region. Account instances cannot do this: CreatePermissionSet returns
#   "not supported for account instances", and the management account cannot
#   create an instance via CLI at all ("Organization management account is not
#   allowed to perform the operation"). The console is the only path.
#
# Everything after that is automated here.
#   ./scripts/setup-sso.sh            create user, permission set, assignment
#   ./scripts/setup-sso.sh --verify   report current state only, change nothing
set -uo pipefail
export AWS_PAGER=""

MGMT_PROFILE="${MGMT_PROFILE:-default}"     # management account 381492022873
TARGET_ACCOUNT="${TARGET_ACCOUNT:-806168459926}"

# Where the Identity Center INSTANCE lives. This is NOT the region your
# resources are in and does not restrict them: an instance in us-east-1 hands
# out credentials for accounts and resources in every region. It only decides
# where the identity store and portal live, and it is permanent -- changing it
# means deleting the instance and every user and assignment with it.
# Leave it wherever the organization already is; do not move it to match a
# project. Unset means "search for it".
SSO_REGION="${SSO_REGION:-}"

# Default region for API calls made through the resulting profile -- this is
# the one that must match the project (us-east-2, the metastore region).
REGION="${REGION:-us-east-2}"
SSO_USER_EMAIL="${SSO_USER_EMAIL:-dark.show.time@gmail.com}"
SSO_USER_NAME="${SSO_USER_NAME:-dark417}"
PERMISSION_SET="${PERMISSION_SET:-EdgarAdmin}"
SESSION_DURATION="${SESSION_DURATION:-PT8H}"
LOCAL_PROFILE="${LOCAL_PROFILE:-edgar-sso}"
VERIFY_ONLY=0
[ "${1:-}" = "--verify" ] && VERIFY_ONLY=1

die() { echo "ERROR: $*" >&2; exit 1; }

# ---- 1. the instance must exist -------------------------------------------
# Probe for it rather than assuming a region: the instance can legitimately live
# anywhere, and guessing wrong would report "not enabled" for something that is.
find_instance() {
  local r out
  for r in ${SSO_REGION:-us-east-1 us-east-2 us-west-2 eu-west-1 ap-southeast-1}; do
    out="$(aws sso-admin list-instances --profile "$MGMT_PROFILE" --region "$r" \
      --query 'Instances[0].[InstanceArn,IdentityStoreId]' --output text 2>/dev/null)"
    case "$out" in
      ""|None*|*None) continue ;;
      *) printf '%s\t%s\n' "$out" "$r"; return 0 ;;
    esac
  done
  return 1
}

IFS=$'\t' read -r INSTANCE_ARN IDENTITY_STORE_ID FOUND_REGION <<<"$(find_instance)" || true
SSO_REGION="${FOUND_REGION:-${SSO_REGION:-us-east-1}}"

if [ -z "${INSTANCE_ARN:-}" ] || [ "$INSTANCE_ARN" = "None" ]; then
  cat <<'BANNER'
BLOCKED — enable IAM Identity Center in the console first.

  1. Sign in to the MANAGEMENT account (381492022873).
  2. Pick the console region with the dropdown in the top-right nav bar, or
     go straight to:  https://console.aws.amazon.com/singlesignon/home
  3. IAM Identity Center  ->  Enable  (choose "Enable with AWS Organizations").
  4. Re-run this script — it finds the instance in whichever region you used.

WHICH REGION: it does not have to match the project. An instance in us-east-1
hands out credentials for accounts and resources in every region; the choice
only decides where the identity store and sign-in portal live. Use whichever
region the organization already sits in. It is permanent -- changing it later
means deleting the instance along with every user and assignment.

Why the console at all: an organization instance cannot be created from the
CLI. AWS rejects CreateInstance from the management account outright, and an
account instance created in a member account cannot hold permission sets, so
it cannot grant AWS account access. Both were tested.
BANNER
  exit 2
fi

echo "instance      $INSTANCE_ARN"
echo "identitystore $IDENTITY_STORE_ID"
echo "sso region    $SSO_REGION   (instance home; permanent)"
echo "api region    $REGION   (project resources)"
echo

# ---- 2. the user -----------------------------------------------------------
USER_ID="$(aws identitystore list-users --identity-store-id "$IDENTITY_STORE_ID" \
  --profile "$MGMT_PROFILE" --region "$SSO_REGION" \
  --query "Users[?UserName=='$SSO_USER_NAME'].UserId | [0]" --output text 2>/dev/null)"

if [ "$USER_ID" = "None" ] || [ -z "$USER_ID" ]; then
  if [ "$VERIFY_ONLY" -eq 1 ]; then echo "user          MISSING ($SSO_USER_NAME)"; else
    USER_ID="$(aws identitystore create-user \
      --identity-store-id "$IDENTITY_STORE_ID" \
      --user-name "$SSO_USER_NAME" \
      --display-name "$SSO_USER_NAME" \
      --name "FamilyName=Owner,GivenName=Edgar" \
      --emails "Value=$SSO_USER_EMAIL,Type=work,Primary=true" \
      --profile "$MGMT_PROFILE" --region "$SSO_REGION" \
      --query UserId --output text)" || die "could not create user"
    echo "user          created $SSO_USER_NAME ($USER_ID)"
  fi
else
  echo "user          exists  $SSO_USER_NAME ($USER_ID)"
fi

# ---- 3. the permission set -------------------------------------------------
# A for-loop, not `... | while read`: a pipeline runs the loop in a subshell, so
# the match was found and then thrown away. That produced a verifier reporting
# MISSING for a permission set that existed -- a check that lies is worse than
# no check, which is the same rule the drift test is built on.
PS_ARN=""
for arn in $(aws sso-admin list-permission-sets --instance-arn "$INSTANCE_ARN" \
               --profile "$MGMT_PROFILE" --region "$SSO_REGION" \
               --query 'PermissionSets[]' --output text 2>/dev/null); do
  n="$(aws sso-admin describe-permission-set --instance-arn "$INSTANCE_ARN" \
        --permission-set-arn "$arn" --profile "$MGMT_PROFILE" --region "$SSO_REGION" \
        --query 'PermissionSet.Name' --output text 2>/dev/null)"
  if [ "$n" = "$PERMISSION_SET" ]; then PS_ARN="$arn"; break; fi
done

if [ -z "${PS_ARN:-}" ]; then
  if [ "$VERIFY_ONLY" -eq 1 ]; then echo "permissionset MISSING ($PERMISSION_SET)"; else
    PS_ARN="$(aws sso-admin create-permission-set --instance-arn "$INSTANCE_ARN" \
      --name "$PERMISSION_SET" --session-duration "$SESSION_DURATION" \
      --description "Admin on the edgar project account only" \
      --profile "$MGMT_PROFILE" --region "$SSO_REGION" \
      --query 'PermissionSet.PermissionSetArn' --output text)" || die "could not create permission set"
    aws sso-admin attach-managed-policy-to-permission-set \
      --instance-arn "$INSTANCE_ARN" --permission-set-arn "$PS_ARN" \
      --managed-policy-arn arn:aws:iam::aws:policy/AdministratorAccess \
      --profile "$MGMT_PROFILE" --region "$SSO_REGION" >/dev/null || die "could not attach policy"
    echo "permissionset created $PERMISSION_SET"
  fi
else
  echo "permissionset exists  $PERMISSION_SET"
fi

# ---- 4. assignment: this user -> this permission set -> the edgar account --
if [ -n "${USER_ID:-}" ] && [ -n "${PS_ARN:-}" ] && [ "$USER_ID" != "None" ]; then
  ASSIGNED="$(aws sso-admin list-account-assignments --instance-arn "$INSTANCE_ARN" \
    --account-id "$TARGET_ACCOUNT" --permission-set-arn "$PS_ARN" \
    --profile "$MGMT_PROFILE" --region "$SSO_REGION" \
    --query "AccountAssignments[?PrincipalId=='$USER_ID'] | length(@)" --output text 2>/dev/null)"
  if [ "${ASSIGNED:-0}" = "0" ]; then
    if [ "$VERIFY_ONLY" -eq 1 ]; then echo "assignment    MISSING"; else
      aws sso-admin create-account-assignment --instance-arn "$INSTANCE_ARN" \
        --target-id "$TARGET_ACCOUNT" --target-type AWS_ACCOUNT \
        --permission-set-arn "$PS_ARN" --principal-type USER --principal-id "$USER_ID" \
        --profile "$MGMT_PROFILE" --region "$SSO_REGION" >/dev/null || die "could not assign"
      echo "assignment    created -> account $TARGET_ACCOUNT"
    fi
  else
    echo "assignment    exists  -> account $TARGET_ACCOUNT"
  fi
fi

# ---- 5. what the human does next ------------------------------------------
START_URL="$(aws sso-admin list-instances --profile "$MGMT_PROFILE" --region "$SSO_REGION" \
  --query 'Instances[0].InstanceArn' --output text >/dev/null 2>&1; \
  aws sso-admin describe-instance --instance-arn "$INSTANCE_ARN" \
  --profile "$MGMT_PROFILE" --region "$SSO_REGION" --query 'Name' --output text 2>/dev/null)"

cat <<EOF

next:
  1. Check the inbox for $SSO_USER_EMAIL — accept the invitation, set a
     password, and register MFA. Do not skip MFA; it is the entire point.
  2. Find the portal URL: IAM Identity Center -> Settings -> "AWS access portal URL".
  3. Configure the local profile:

       aws configure sso --profile $LOCAL_PROFILE
         SSO start URL : <the portal URL from step 2>
         SSO region    : $SSO_REGION
         account       : $TARGET_ACCOUNT
         role          : $PERMISSION_SET

       aws sso login --profile $LOCAL_PROFILE
       aws sts get-caller-identity --profile $LOCAL_PROFILE

  4. Point work at it:  export AWS_PROFILE=$LOCAL_PROFILE
  5. ONLY after step 4 works, retire the long-lived key:

       aws iam update-access-key --user-name xx_ai0 --access-key-id <ID> \\
         --status Inactive --profile $MGMT_PROFILE
       # leave it Inactive for a few days, then delete-access-key

     That key was created 2025-01-17, has no MFA, and can assume into every
     account in the organization. Retiring it is the reason this exists.
EOF
