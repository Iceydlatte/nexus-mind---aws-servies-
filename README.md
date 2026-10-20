# Nexus Mind

Nexus Mind is a personal activity journal and productivity dashboard with optional AWS account sync. The browser keeps a local cache so the current device remains usable between requests; after sign-in, your account data is loaded from AWS and changes are saved to your account. Sign in on another device to get the same data.

## AWS architecture

- **Amazon Cognito** creates accounts, confirms email addresses, and issues sign-in tokens.
- **Amazon API Gateway HTTP API** accepts requests only with a valid Cognito token.
- **AWS Lambda** reads and writes the signed-in user's data, loads synthetic demo rows from S3, archives reports, and sends requested reports.
- **Amazon Bedrock** powers the signed-in ChatGPT-style assistant through the Converse API. Bedrock can answer general productivity questions and uses validated task tools to list, add, complete, and reopen tasks. Lambda supplies only the signed-in user's private task data.
- **Amazon DynamoDB** stores one private data record per Cognito user ID. The browser cannot choose another user's ID.
- **Amazon SES** sends Cognito signup confirmation codes and weekly activity summaries on demand to the signed-in, email-verified user's address. It does not send scheduled email.
- A separate **private Amazon S3 data bucket** stores the generated synthetic training dataset and report JSON files. Reports are partitioned by Cognito user ID, encrypted at rest, and expire after one year. Deleting account data also removes that user's report files.
- **Amazon S3** stores the static site files in a private bucket. **Amazon CloudFront** serves the site over HTTPS using Origin Access Control.

The browser configuration file contains only public Cognito and API identifiers. There are no AWS access keys, SES SMTP credentials, or API keys in the frontend. Lambda uses its IAM role to call DynamoDB and SES.

## Data and privacy

Activities, goals, tasks, habits, reflections, and profile preferences sync to the signed-in AWS project. The same values are cached in the current browser for quick loading. Voice and floating-button preferences stay on the current device. Starter entries are synthetic examples loaded from the private S3 data bucket through a read-only Lambda route; the mentor remains a local rule-based feature. The Python MLOps pipeline uses the generated synthetic CSV in S3 and does not train on journal entries.

On the first sign-in from a browser, Nexus Mind asks whether to copy that browser's saved app data into the new AWS account. Synthetic starter activity is shown as a demo and filtered out of cloud sync; goals, tasks, and habits start empty in a new AWS profile. If you decline, it clears that app-data cache on the device and starts a fresh profile. Once data is synced, the Settings page can export a copy or permanently delete the account's saved app data from DynamoDB and this device. Deleting that data does not delete the Cognito login.

If two devices edit the same account at nearly the same time, a version check prevents an older copy from silently replacing a newer one. The app asks you to reload the latest cloud copy before continuing.

Activity reports are stored in the private S3 bucket when downloaded or emailed. Email reports include a short activity summary and are sent only when the user clicks **Email summary to my account**; the destination is the verified sign-in address. Cognito confirmation and report email use the same SES sender identity in `ap-southeast-2`. New SES accounts are sandboxed, so test recipients must also be verified until AWS grants production access.

## Deploy to AWS

The stack is described in `infra/template.yaml` using AWS SAM. It creates Cognito, API Gateway, Lambda, DynamoDB, Amazon Bedrock access, a private S3 website bucket, and a CloudFront distribution. It requires an AWS account, AWS CLI, AWS SAM CLI, Bedrock model access in the selected Region, and a verified SES sender email/domain. Never put a password, access key, or secret in this repository.

1. In **AWS Settings → Billing**, confirm your spend limit and billing alert. Resources such as CloudFront can incur charges even at low traffic.
2. Install the AWS SAM CLI using the official AWS installation guide. The AWS CLI profile `nexus-mind` is already configured for this project; refresh its browser session with `aws login --profile nexus-mind` when it expires.
3. In the AWS Management Console, open **Amazon SES** and select `Asia Pacific (Sydney) / ap-southeast-2`. Create and verify a sender identity. For a domain, publish the DKIM DNS records SES provides. For a first test, verify your own email address as the sender.
4. From the project root in PowerShell, deploy the stack using the helper script. Use the exact verified email or domain for `SesIdentity`:

   ```powershell
   .\scripts\deploy-infrastructure.ps1 -SenderEmail "you@example.com" -SesIdentity "you@example.com"
   ```

   The helper builds the SAM app and asks AWS to show a CloudFormation change set before applying it. It uses the stack name `nexus-mind`, profile `nexus-mind`, selected Region `ap-southeast-2`, and the `global.amazon.nova-2-lite-v1:0` Bedrock inference profile by default. Review the change set before approving it. It creates the private data bucket, website hosting, Cognito, API Gateway, Lambda, DynamoDB, and CloudFront resources.

5. Upload the frontend and refresh CloudFront from the project root. Replace the Region if you chose another one:

   ```powershell
   .\scripts\deploy-frontend.ps1
   ```

6. Open the `WebsiteUrl` printed by the script. Create an account, confirm its email, sign in, and check that the top bar says it is synced. Add a test activity, open the same site in a second browser/device, sign in with that account, and confirm the entry appears.
7. Open the assistant button in the lower-right corner and test messages such as `Help me plan my study session`, `What tasks are pending?`, `Add a task`, and `Mark my reading task complete`. The AI assistant requires a signed-in, confirmed Cognito session. If Bedrock reports that the AWS project is still being verified, wait for AWS verification to finish before testing.
8. Test report email from the Weekly report page. In SES sandbox, also verify the recipient address in SES first. Request SES production access before sending to unverified recipients.

This second script generates the synthetic CSV if needed, uploads it to the private S3 `synthetic/` prefix, writes public Cognito/API identifiers to `frontend/aws-config.js`, uploads the frontend to the private website bucket, and invalidates CloudFront. The website bucket is private; CloudFront is its reader. Never put AWS access keys, account passwords, or SES credentials in frontend files.

## Run locally

Open `frontend/index.html` for the offline demo. AWS sync remains disabled until the frontend config is generated and the site is served over HTTPS. The trained Python estimator and MLflow workflow remain local; they are not a live prediction endpoint.

Python 3.11 or newer is recommended:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/generate_dataset.py
python scripts/train.py
```

The dataset generator creates 1,500 deterministic synthetic rows at `data/generated/activities.csv`. The local pipeline validates the data, engineers features, trains a Random Forest, evaluates held-out data, tracks the run in MLflow, applies a macro-F1 quality gate, and saves a versioned joblib model when the gate passes. To view MLflow:

```powershell
mlflow ui --backend-store-uri sqlite:///./mlflow.db
```

Then open http://localhost:5000. To retrain, run `python scripts/retrain.py`.

## Project layout

```text
frontend/index.html             Dashboard and local cache
frontend/cloud-client.js        Cognito sign-in, cloud sync, Bedrock chat, report email
frontend/aws-config.js          Public AWS identifiers (generated at deploy time)
infra/template.yaml             AWS SAM infrastructure
backend/lambda/app.py           Authenticated data, Bedrock chat, and SES report API
scripts/deploy-frontend.ps1     Configure, upload, and invalidate CloudFront
scripts/configure_aws_frontend.py Generate browser settings from stack outputs
ml/                             Local training pipeline
scripts/train.py                Train and record a local experiment
scripts/retrain.py              Repeat local training workflow
tests/test_ml.py                ML feature and validation tests
```
